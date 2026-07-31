#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Repair UTF-8/GBK mojibake in source comments and user-facing strings."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MOJIBAKE_RE = re.compile(
    r"[\uE000-\uF8FF]"
    r"|锟斤拷"
    r"|(?:[鐗杩鍏闇鑷鍟缂娴鍙鎴浼鍓]{2,})"
    r"|Ã[\x80-\xbf]"
    r"|ï¿½"
    r"|\ufffd"
)

SKIP_DIRS = {
    "node_modules",
    "venv",
    ".git",
    "__pycache__",
    "bin",
    "obj",
    "Library",
    "release_bundles",
    "jenkins-clone",
    "artifacts",
    "Generated",
    "tmp",
}

SCAN_ROOTS = [
    ROOT / "portals" / "common" / "core",
    Path(r"E:/maclient/Assets"),
    Path(r"E:/maclient/game-server"),
    Path(r"E:/maclient/.cursor"),
]

EXTENSIONS = {".py", ".js", ".html", ".css", ".md", ".json", ".cs", ".ps1", ".sh", ".tsx", ".ts"}

# Files that only mention mojibake in detection helpers — never rewrite.
SKIP_FILES = {
    "encoding_gate.py",
    "quality_static_gate.py",
    "encoding.py",
    "extract_admin_views.py",
    "common.py",
    "dashboard.py",
    "player_community.py",
    "ops_platform_agent_detail.js",
}

MANUAL_REPLACEMENTS = {
    "Token 缂哄け锛岃閲嶆柊鐧诲綍": "Token 缺失，请重新登录",
    "/// 鐜╁妗ｆ涓庤儗鍖呯浉鍏充笟鍔¤剼鏈€?": "/// 玩家档案与背包相关业务脚本。",
    "/// 鎴樻枟鐩稿叧涓氬姟鑴氭湰锛氭湇鍔″櫒鏉冨▉鎴樻枟妯℃嫙 + 瀹㈡埛绔〃婕斻€?": "/// 战斗相关业务脚本：服务器权威战斗模拟 + 客户端表演。",
    "/// 鍓湰鍖归厤/璺ㄦ湇璺敱涓氬姟鑴氭湰銆?": "/// 副本匹配/跨服路由业务脚本。",
    "/// 杩愯鏃惰鍙栫殑鐗堟湰鍏冩暟鎹暟鎹粨鏋勶紝闇€涓庢墦鍖呯淇濇寔涓€鑷淬€?": "/// 运行时读取的版本元数据数据结构，需与打包端保持一致。",
    "/// 鍗曚釜鐗堟湰鍏冩暟鎹紝鍖呭惈鏋勫缓銆佸彂甯冦€佷緷璧栥€佸彉鏇翠笌涓婁紶淇℃伅銆?": "/// 单个版本元数据，包含构建、发布、依赖、变更与上传信息。",
    "/// 杩愯鏃堕€夋嫨鍑虹殑鐗堟湰涓婁笅鏂囷紝鐢ㄤ簬椹卞姩鐏板害涓庡洖婊氥€?": "/// 运行时选择出的版本上下文，用于驱动灰度与回滚。",
    "/// 鍏冩暟鎹繍琛屾椂璇诲彇涓庢牎楠屾湇鍔°€?": "/// 元数据运行时读取与校验服务。",
    "/** 鑷姩鐢熸垚鏈嶅姟绔厤缃粨搴擄紙Node.js锛夈€?*/": "/** 自动生成服务端配置仓库（Node.js）。 */",
    "NOTE: Windows 缂哄皯 bash锛岄渶瀹夎 Git for Windows 鍚庨噸璇?Jenkins 鏋勫缓銆?": "NOTE: Windows 缺少 bash，需安装 Git for Windows 后重试 Jenkins 构建。",
}


def looks_mojibake(text: str) -> bool:
    return bool(MOJIBAKE_RE.search(text))


def fix_line(line: str) -> str:
    if line in MANUAL_REPLACEMENTS:
        return MANUAL_REPLACEMENTS[line]
    if not looks_mojibake(line):
        return line
    stripped = line.strip()
    if stripped in MANUAL_REPLACEMENTS:
        prefix = line[: len(line) - len(line.lstrip())]
        return prefix + MANUAL_REPLACEMENTS[stripped]
    cleaned = re.sub(r"[\uE000-\uF8FF\ufffd]", "", line)
    cleaned = cleaned.replace("\u20ac", "").replace("€", "")
    cleaned = re.sub(r"[?\uFFFD]+$", "", cleaned)
    fixed = cleaned
    for _ in range(3):
        try:
            nxt = fixed.encode("gbk").decode("utf-8")
        except UnicodeError:
            break
        if nxt == fixed:
            break
        fixed = nxt
    fixed = re.sub(r"\ufffd", "", fixed)
    if ("//" in line or "///" in line or "/*" in line) and fixed.rstrip().endswith("?"):
        fixed = fixed.rstrip()[:-1] + "。"
        if line.endswith("\n") and not fixed.endswith("\n"):
            pass
    return fixed


def fix_text(text: str) -> str:
    if not looks_mojibake(text):
        return text
    lines = [fix_line(line) for line in text.splitlines()]
    out = "\n".join(lines)
    if text.endswith("\n"):
        out += "\n"
    for src, dst in MANUAL_REPLACEMENTS.items():
        out = out.replace(src, dst)
    return out


def iter_files(roots: list[Path]):
    seen: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            if any(part in SKIP_DIRS for part in Path(dirpath).parts):
                continue
            for name in filenames:
                if name in SKIP_FILES:
                    continue
                if Path(name).suffix.lower() not in EXTENSIONS:
                    continue
                path = Path(dirpath) / name
                key = str(path.resolve()).lower()
                if key in seen:
                    continue
                seen.add(key)
                yield path


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix mojibake in web/client/server sources")
    parser.add_argument("--apply", action="store_true", help="Write fixes to disk")
    parser.add_argument("--root", action="append", default=[], help="Extra scan root")
    parser.add_argument("--pass3", action="store_true", help="Run aggressive mixed-line cleanup after base pass")
    args = parser.parse_args()

    roots = list(SCAN_ROOTS)
    for item in args.root:
        roots.append(Path(item))

    changed: list[str] = []
    skipped: list[str] = []
    for path in iter_files(roots):
        try:
            original = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            skipped.append(f"{path}: unreadable")
            continue
        if not looks_mojibake(original):
            continue
        fixed = fix_text(original)
        if fixed == original:
            skipped.append(f"{path}: still mojibake after auto-fix")
            continue
        rel = path
        changed.append(str(rel))
        if args.apply:
            path.write_text(fixed, encoding="utf-8", newline="\n")

    if args.apply and args.pass3:
        pass3 = ROOT / "scripts" / "fix_mojibake_pass3.py"
        if pass3.is_file():
            import subprocess

            subprocess.call([sys.executable, str(pass3)], cwd=str(ROOT))

    print(f"fix_mojibake: changed={len(changed)} skipped={len(skipped)} apply={args.apply}")
    for item in changed[:80]:
        print(f"  fixed: {item}")
    if len(changed) > 80:
        print(f"  ... and {len(changed) - 80} more")
    for item in skipped[:30]:
        print(f"  skip: {item}")
    return 0 if not skipped or args.apply else 0


if __name__ == "__main__":
    sys.exit(main())
