# 三态 + 公用（唯一入口）

项目已严格收敛：根目录仅保留 `data/` 与 `portals/`。

## 目录结构
- `intranet/`：内网态（admin）
  - `wsgi.py`
  - `start_admin.bat`
- `extranet/`：外网态（player）
  - `wsgi.py`
  - `start_player.bat`
- `forum/`：玩家论坛态（forum）
  - `wsgi.py`
  - `start_forum.bat`
- `common/`：公用代码与资源
  - `core/`：应用核心代码
  - `docs/`：文档
  - `artifacts/`：构建/发布产物
  - `reports/`：报告与日志归档
  - `tmp/`：临时文件
  - `archives/`：归档

## 新启动方式

### Windows（推荐）
- 内网：运行 `portals\\intranet\\start_admin.bat`
- 外网：运行 `portals\\extranet\\start_player.bat`
- 论坛：运行 `portals\\forum\\start_forum.bat`

### 命令行（跨平台）
- 内网：
  - `python -m waitress --listen=0.0.0.0:5003 portals.intranet.wsgi:app`
- 外网：
  - `python -m waitress --listen=0.0.0.0:5004 portals.extranet.wsgi:app`
- 论坛：
  - `python -m waitress --listen=0.0.0.0:5005 portals.forum.wsgi:app`

## 说明
- 原根目录兼容壳（`admin_wsgi.py`、`start_admin.bat` 等）已移除。
- 如需查看原项目入口说明，见 `common/docs/README_ROOT.md`。
