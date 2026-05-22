# -*- coding: utf-8 -*-
"""Jenkins API：认证、状态、触发、停止、日志、构建详情等"""

import os
import json
import base64
import urllib.request
import urllib.error
import urllib.parse
import http.cookiejar
import xml.etree.ElementTree as ET
import logging

from config import Config, get_jenkins_credentials

logger = logging.getLogger(__name__)
BUILDS_DIR = Config.JENKINS_BUILDS_DIR
JOB_NAME = Config.JENKINS_JOB_NAME


def _base_url_and_builds(base_url=None, builds_dir=None):
    """统一返回 (base_url, builds_dir)。None 时用 Config 默认。"""
    url = (base_url or Config.JENKINS_URL).rstrip('/')
    bdir = builds_dir or BUILDS_DIR
    return (url, bdir)


def _credentials_for_instance(instance_id=None):
    """若 instance_id 在「Jenkins 管理」列表中，一律用固定账号；否则用 .env。"""
    if instance_id:
        try:
            from models.data import load_jenkins_instances
            for inst in load_jenkins_instances():
                if inst.get('id') == instance_id:
                    u = (Config.JENKINS_DEFAULT_USER or 'admin').strip() or 'admin'
                    p = (Config.JENKINS_DEFAULT_PASSWORD or 'admin123').strip() or 'admin123'
                    return (u, p)
        except Exception:
            pass
    return get_jenkins_credentials()


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """不跟随重定向，使 POST /stop 的 302 被当作成功。"""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def auth_header(instance_id=None):
    """Jenkins Basic 认证头。instance_id 为管理内实例且 default_creds 时用固定账号。"""
    user, token = _credentials_for_instance(instance_id)
    if not (user and token):
        return None
    return 'Basic ' + base64.b64encode((user + ':' + token).encode()).decode()


def fetch_jenkins_status(base_url=None, builds_dir=None, instance_id=None):
    """检查 Jenkins 是否可达及 job 状态。base_url/builds_dir 为 None 时用 Config。"""
    url, _ = _base_url_and_builds(base_url, builds_dir)
    try:
        req = urllib.request.Request(
            url + "/job/" + JOB_NAME + "/api/json?tree=lastBuild[number],lastCompletedBuild[number],builds[number,result,building]",
            headers={"Accept": "application/json"}
        )
        auth = auth_header(instance_id)
        if auth:
            req.add_header('Authorization', auth)
        with urllib.request.urlopen(req, timeout=5) as r:
            if r.getcode() != 200:
                return {'ok': False, 'message': 'Jenkins 返回非 200', 'code': r.getcode(), 'jenkinsUrl': url}
            data = json.loads(r.read().decode())
            last = data.get('lastBuild') or {}
            last_num = last.get('number')
            builds = data.get('builds', [])[:15]
            building = any(b.get('building') for b in builds)
            return {
                'ok': True,
                'message': 'Jenkins 正常，任务 ' + JOB_NAME + ' 可访问',
                'jenkinsUrl': url,
                'lastBuildNumber': last_num,
                'building': building,
                'recent': builds
            }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {'ok': False, 'message': 'Jenkins 正常，但未找到任务 "' + JOB_NAME + '"', 'code': 404, 'jenkinsUrl': url}
        return {'ok': False, 'message': f'Jenkins 返回错误: {e.code}', 'code': e.code, 'jenkinsUrl': url}
    except urllib.error.URLError as e:
        return {'ok': False, 'message': '无法连接 Jenkins（请确认已启动且地址为 ' + url + '）', 'error': str(e.reason), 'jenkinsUrl': url}
    except Exception as e:
        return {'ok': False, 'message': '检查 Jenkins 时出错: ' + str(e), 'jenkinsUrl': url}


def get_last_successful_params(base_url=None, builds_dir=None):
    """返回最近一次构建成功（SUCCESS）的参数 dict。"""
    _, bdir = _base_url_and_builds(base_url, builds_dir)
    try:
        if not os.path.isdir(bdir):
            return {}
        build_nums = []
        for item in os.listdir(bdir):
            if os.path.isdir(os.path.join(bdir, item)) and item.isdigit():
                build_nums.append(int(item))
        build_nums.sort(reverse=True)
        for build_num in build_nums:
            build_xml = os.path.join(bdir, str(build_num), 'build.xml')
            if not os.path.exists(build_xml):
                continue
            try:
                tree = ET.parse(build_xml)
                root = tree.getroot()
                res = root.find('result')
                if res is None or not res.text or res.text.strip() != 'SUCCESS':
                    continue
                params = {}
                for p in root.iter():
                    if p.tag == 'parameter' or (p.tag and 'ParameterValue' in p.tag):
                        name_el = p.find('name')
                        val_el = p.find('value')
                        if name_el is not None and name_el.text:
                            params[name_el.text] = (val_el.text if val_el is not None and val_el.text else '') or ''
                if params:
                    return params
            except Exception:
                continue
        return {}
    except Exception as e:
        logger.warning("获取上次成功构建参数失败: %s", e)
        return {}


def get_build_status(build_number, base_url=None, builds_dir=None):
    """获取单次构建状态。"""
    url, bdir = _base_url_and_builds(base_url, builds_dir)
    try:
        build_path = os.path.join(bdir, str(build_number))
        result_file = os.path.join(build_path, 'build.xml')

        # 优先读取本地 build.xml
        if os.path.exists(result_file):
            try:
                tree = ET.parse(result_file)
                root = tree.getroot()
                re_el = root.find('result')
                if re_el is not None and re_el.text and re_el.text.strip():
                    return {'building': False, 'status': re_el.text.strip()}
            except Exception:
                pass

        # 本地未拿到终态时，回退查询 Jenkins API（避免页面一直“构建中”）
        try:
            resp = requests.get(
                f"{url}/job/{JOB_NAME}/{int(build_number)}/api/json?tree=building,result",
                timeout=8,
            )
            if resp.status_code == 200:
                data = resp.json() or {}
                api_building = bool(data.get('building'))
                api_result = (data.get('result') or '').strip()
                if api_building:
                    return {'building': True, 'status': 'BUILDING'}
                if api_result:
                    return {'building': False, 'status': api_result}
                return {'building': False, 'status': 'UNKNOWN'}
        except Exception:
            pass

        if not os.path.isdir(build_path):
            return {'building': True, 'status': 'QUEUED'}
        return {'building': True, 'status': 'BUILDING'}
    except Exception as e:
        return {'building': True, 'status': 'UNKNOWN', 'error': str(e)}

def _read_text_file_best_encoding(path, max_bytes=None):
    """按 UTF-8 / GBK 择优解码 Jenkins 日志（Windows 控制台常为 GBK，流水线脚本为 UTF-8）。"""
    try:
        with open(path, 'rb') as f:
            raw = f.read(max_bytes) if max_bytes else f.read()
    except OSError:
        return ''
    if not raw:
        return ''
    candidates = []
    for enc in ('utf-8-sig', 'utf-8', 'gbk', 'cp936'):
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        replacement = text.count('\ufffd')
        cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        score = cjk * 4 - replacement * 200 - (len(text) - len(text.encode(enc, errors='ignore'))) * 0.01
        candidates.append((score, enc, text))
    if not candidates:
        return raw.decode('utf-8', errors='replace')
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][2]


def get_build_log_content(build_number, max_chars=500000, base_url=None, builds_dir=None):
    """读取构建日志文件内容。"""
    _, bdir = _base_url_and_builds(base_url, builds_dir)
    log_file = os.path.join(bdir, str(build_number), "log")
    if os.path.exists(log_file):
        log_content = _read_text_file_best_encoding(log_file, max_bytes=max_chars * 8)
        if len(log_content) > max_chars:
            log_content = log_content[-max_chars:]
        return log_content
    return "构建日志尚未生成（Jenkins 可能仍在排队或未创建该构建）"


def get_build_detail(build_number, base_url=None, builds_dir=None):
    """获取单次构建详情：参数 + 完整日志。"""
    _, bdir = _base_url_and_builds(base_url, builds_dir)
    try:
        build_path = os.path.join(bdir, str(build_number))
        if not os.path.isdir(build_path):
            return None
        info = {'number': int(build_number), 'status': 'UNKNOWN', 'timestamp': None, 'duration': None, 'parameters': {}, 'log': ''}
        build_xml = os.path.join(build_path, 'build.xml')
        if os.path.exists(build_xml):
            try:
                tree = ET.parse(build_xml)
                root = tree.getroot()
                for tag, key in [('result', 'status'), ('timestamp', 'timestamp'), ('duration', 'duration')]:
                    el = root.find(tag)
                    if el is not None and el.text:
                        if tag == 'timestamp':
                            from datetime import datetime
                            info['timestamp'] = datetime.fromtimestamp(int(el.text) / 1000).strftime('%Y-%m-%d %H:%M:%S')
                        elif tag == 'duration':
                            info['duration'] = f"{int(el.text) / 1000:.1f}s"
                        else:
                            info[key] = el.text
                for p in root.iter():
                    if p.tag == 'parameter' or (p.tag and 'ParameterValue' in p.tag):
                        name_el = p.find('name')
                        val_el = p.find('value')
                        if name_el is not None and name_el.text:
                            info['parameters'][name_el.text] = (val_el.text if val_el is not None and val_el.text else '') or ''
            except Exception as e:
                logger.warning("解析 build.xml 失败: %s", e)
        log_file = os.path.join(build_path, 'log')
        if os.path.exists(log_file):
            info['log'] = _read_text_file_best_encoding(log_file)
        return info
    except Exception as e:
        logger.warning("获取构建详情失败: %s", e)
        return None


def stop_build(build_number, base_url=None, builds_dir=None, instance_id=None):
    """通知 Jenkins 停止指定构建。"""
    try:
        url, _ = _base_url_and_builds(base_url, builds_dir)
        stop_url = url + "/job/" + JOB_NAME + "/" + str(build_number) + "/stop"
        auth = auth_header(instance_id)
        cookie_jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(
            _NoRedirectHandler(),
            urllib.request.HTTPCookieProcessor(cookie_jar),
        )
        if auth:
            opener.addheaders.append(('Authorization', auth))
        crumb_header = None
        try:
            crumb_req = urllib.request.Request(url + "/crumbIssuer/api/json")
            with opener.open(crumb_req, timeout=5) as crumb_resp:
                if crumb_resp.getcode() == 200:
                    crumb_data = json.loads(crumb_resp.read().decode())
                    field = crumb_data.get('crumbRequestField') or 'Jenkins-Crumb'
                    value = crumb_data.get('crumb', '')
                    if value:
                        crumb_header = (field, value)
        except Exception:
            pass

        def do_stop(method='POST'):
            if method == 'POST':
                req = urllib.request.Request(stop_url, data=b'', method='POST')
                req.add_header('Content-Type', 'application/x-www-form-urlencoded')
                req.add_header('Content-Length', '0')
            else:
                req = urllib.request.Request(stop_url, method='GET')
            if crumb_header:
                req.add_header(crumb_header[0], crumb_header[1])
            try:
                r = opener.open(req, timeout=10)
                return r.getcode()
            except urllib.error.HTTPError as e:
                return e.code
            except Exception:
                return None

        code = do_stop('POST')
        if code == 405:
            code = do_stop('GET')
        if code in (200, 201, 302):
            return (True, None)
        if code is not None:
            return (False, f'Jenkins 返回 {code}')
        return (False, 'Jenkins 无有效响应')
    except urllib.error.HTTPError as e:
        if e.code in (200, 201, 302):
            return (True, None)
        return (False, f'Jenkins {e.code}: {e.reason}')
    except Exception as e:
        logger.warning("停止构建失败: %s", e)
        return (False, str(e))


def trigger_build(params, base_url=None, builds_dir=None, instance_id=None):
    """
    触发 Jenkins 构建。params: dict。可选 base_url/builds_dir/instance_id 指定实例。
    返回 (success: bool, build_number: int or None, error: str or None)。
    """
    import time
    url, bdir = _base_url_and_builds(base_url, builds_dir)
    jenkins_url = url + "/job/" + JOB_NAME + "/buildWithParameters"
    auth = auth_header(instance_id)
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    if auth:
        opener.addheaders.append(('Authorization', auth))

    def _open(req, timeout=5):
        return opener.open(req, timeout=timeout)

    crumb_header = None
    try:
        crumb_req = urllib.request.Request(url + "/crumbIssuer/api/json")
        with _open(crumb_req) as crumb_resp:
            if crumb_resp.getcode() == 200:
                crumb_data = json.loads(crumb_resp.read().decode())
                field = crumb_data.get('crumbRequestField') or 'Jenkins-Crumb'
                value = crumb_data.get('crumb', '')
                if value:
                    crumb_header = (field, value)
    except Exception:
        pass

    current_build_num = 1
    if os.path.exists(bdir):
        build_nums = [int(d) for d in os.listdir(bdir) if d.isdigit() and os.path.isdir(os.path.join(bdir, d))]
        current_build_num = max(build_nums) + 1 if build_nums else 1

    data_encoded = urllib.parse.urlencode(params).encode('utf-8')
    req = urllib.request.Request(jenkins_url, data=data_encoded, method='POST')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded; charset=utf-8')
    if crumb_header:
        req.add_header(crumb_header[0], crumb_header[1])
    try:
        queue_url = None
        with _open(req, timeout=15) as response:
            if response.getcode() not in (200, 201):
                return (False, None, f'Jenkins ??: {response.getcode()}')
            queue_url = response.headers.get('Location')

        # ???? Queue API ????????????????
        if queue_url:
            queue_api = queue_url.rstrip('/') + "/api/json"
            for _ in range(16):  # ????? 16 ?
                try:
                    q_req = urllib.request.Request(queue_api, headers={"Accept": "application/json"})
                    q_resp = _open(q_req, timeout=6)
                    if q_resp.getcode() == 200:
                        q_data = json.loads(q_resp.read().decode(errors='replace'))
                        executable = q_data.get('executable') or {}
                        real_num = executable.get('number')
                        if isinstance(real_num, int) and real_num > 0:
                            return (True, real_num, None)
                        if q_data.get('cancelled'):
                            return (False, None, '?????????')
                except Exception:
                    pass
                time.sleep(1)

        # ?????????????? lastBuild
        time.sleep(1)
        try:
            r_req = urllib.request.Request(url + "/job/" + JOB_NAME + "/lastBuild/buildNumber")
            r = _open(r_req)
            if r.getcode() == 200:
                real_num = int(r.read().decode().strip())
                if real_num >= current_build_num:
                    current_build_num = real_num
        except Exception:
            pass
        return (True, current_build_num, None)
    except urllib.error.HTTPError as e:
        err_msg = f'Jenkins HTTP {e.code}: {e.reason}'
        try:
            body = e.read().decode('utf-8', errors='replace')
        except Exception:
            body = ''
        import re

        m = re.search(r'Illegal choice for parameter ([A-Z_]+):\s*([^\s<]+)', body)
        if m:
            err_msg = (
                'Jenkins 参数不合法：%s=%s（Job 下拉未包含该值）。'
                ' 请在 Jenkins 管理中同步实例 Job，或检查 Unity 版本库 / Git 分支配置。'
                % (m.group(1), m.group(2))
            )
        elif 'Illegal choice for parameter' in body:
            err_msg = 'Jenkins 参数不在 Job 允许列表内，请同步 Jenkins 实例 Job 配置后重试。'
        elif e.code == 500 and body and ('Illegal choice' in body or 'ParameterValue' in body):
            err_msg = (
                'Jenkins 参数校验失败（HTTP 500，多为 CHANNEL/UNITY_VERSION/GIT_BRANCH 不在 Job 允许列表）。'
                ' 请在 Jenkins 管理中对该实例执行「同步 Job 配置」或重启实例后重试。'
            )
        if e.code == 401:
            err_msg = (
                '认证失败(401)。若为「Jenkins 管理」内实例，请在管理中心停止该实例后重新启动一次，'
                '以便注入固定账号（admin/admin123）后再构建。'
            )
        elif e.code == 403:
            user, token = _credentials_for_instance(instance_id)
            auth_ok = bool(user and token)
            if auth_ok:
                err_msg = (
                    'Jenkins 拒绝请求(403)。若为新建的 Jenkins 实例，请先在该实例页面完成初始化、'
                    '创建与 .env 中 JENKINS_USER 一致的用户并生成 API Token 填入 JENKINS_TOKEN；'
                    '或在该实例中创建新用户后，将 .env 改为新账号。'
                )
            else:
                err_msg = 'Jenkins 拒绝请求(403)。请在 .env 中配置 JENKINS_USER 与 JENKINS_TOKEN（或使用 fix_apksite_403.sh）。'
        return (False, None, err_msg)
    except Exception as e:
        return (False, None, str(e))


def delete_build_folder(build_number, base_url=None, builds_dir=None):
    """删除本地构建目录。"""
    _, bdir = _base_url_and_builds(base_url, builds_dir)
    try:
        import shutil
        build_path = os.path.join(bdir, str(build_number))
        if os.path.exists(build_path):
            shutil.rmtree(build_path)
            return (True, None)
        return (False, '构建不存在')
    except Exception as e:
        return (False, str(e))

