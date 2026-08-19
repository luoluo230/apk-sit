# -*- coding: utf-8 -*-
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

STRING_TO_CODE = {
    "无权限": "BAAS_FORBIDDEN",
    "休闲服务不存在": "BAAS_SERVICE_NOT_FOUND",
    "未登录": "BAAS_NOT_LOGGED_IN",
    "项目不存在": "BAAS_PROJECT_NOT_FOUND",
    "项目 ID 与名称必填": "BAAS_PROJECT_FIELDS_REQUIRED",
    "项目 ID 已存在": "BAAS_PROJECT_ID_EXISTS",
    "server_mode 无效": "BAAS_SERVER_MODE_INVALID",
    "player_id 必填": "BAAS_PLAYER_ID_REQUIRED",
    "BaaS 服务器框架未部署": "BAAS_FRAMEWORK_NOT_DEPLOYED",
    "拓扑服务器框架未部署": "BAAS_TOPOLOGY_NOT_DEPLOYED",
    "项目凭证无效": "BAAS_BOOTSTRAP_INVALID_PROJECT",
    "game_id、game_key、env_key、channel 必填": "BAAS_BOOTSTRAP_PARAMS_REQUIRED",
    "platform 无效": "BAAS_BOOTSTRAP_PLATFORM_INVALID",
}

IMPORT_LINE = "from services.baas.errors import baas_fail, baas_fail_exc, baas_success\n"


def patch_file(rel: str) -> None:
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    if "baas_fail_exc" not in text:
        text = text.replace("from flask import", IMPORT_LINE + "from flask import", 1)

    text = re.sub(
        r"return jsonify\(\{\"ok\": False, \"error\": str\(exc\)\}\), \d+",
        "return baas_fail_exc(exc)",
        text,
    )
    for msg, code in STRING_TO_CODE.items():
        text = re.sub(
            rf'return jsonify\(\{{\"ok\": False, \"error\": \"{re.escape(msg)}\"\}}\), \d+',
            f'return baas_fail("{code}")',
            text,
        )
    path.write_text(text, encoding="utf-8")
    print("patched", rel)


for rel in [
    "routes/baas/public_api.py",
    "routes/baas/gm_api.py",
    "routes/baas/admin_api.py",
    "routes/baas/standalone_shell.py",
    "server_frameworks/bootstrap.py",
    "routes/delivery/public_api.py",
]:
    if (ROOT / rel).exists():
        patch_file(rel)
