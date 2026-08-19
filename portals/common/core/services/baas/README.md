# BaaS 服务端业务模块

轻量级休闲游戏后端：**按功能模块拆分**，每个模块独立 service 文件 + 统一 registry 配置 + 统一错误码。

## 目录结构

```
services/baas/
├── registry.py          # 功能目录、默认开关、默认配置、端点映射（单一真相源）
├── bootstrap_service.py # 客户端 bootstrap 载荷
├── service_crud.py      # 服务 CRUD、feature_flags / feature_configs
├── feature_guard.py     # 功能门控、玩家登录校验（各模块入口复用）
├── errors.py            # 统一错误码（packages/baas_shared/error_codes.json）
├── auth_service.py      # login — 游客/密码登录
├── announce_service.py  # announce — 公告
├── mail_service.py      # mail — 邮件
├── cloudsave_service.py # cloudsave — 云存档
├── retention_services.py# leaderboard / economy / achievement / gift
├── social_services.py   # guild / battlepass / periodic_task
├── compliance_service.py# compliance — 防沉迷
├── pve_service.py       # pve — PVE 推图（含 battle_antifraud）
├── arena_service.py     # arena — 异步竞技场
├── room_service.py      # pvp — 实时房间
└── gm_service.py        # GM 运营工具
```

## 新业务模块接入（服务端）

1. 在 `registry.py` 的 `FEATURE_CATALOG` 增加一项（key / label / phase / group / default_enabled）
2. 在 `default_feature_configs()` 增加默认 JSON 配置
3. 在 `public_endpoints_for_features()` 的 `mapping` 增加 API 前缀
4. 新建 `xxx_service.py`，入口调用：
   ```python
   from services.baas.feature_guard import require_feature, require_player, load_feature_config

   def my_action(service_id: str, player_id: str):
       require_feature(service_id, "my_feature")
       pid = require_player(player_id)
       cfg = load_feature_config(service_id, "my_feature")
   ```
5. 在 `routes/baas/public_api.py` 注册 REST 路由
6. 在 `packages/baas_shared/error_codes.json` 增加 `BAAS_MY_FEATURE_DISABLED` 等业务码
7. 运行 `py -3 scripts/generate_baas_error_artifacts.py` 同步客户端错误表

## 功能开关

- 管理台：项目 → 休闲 BaaS 服务 → 功能开关
- 存储：`baas_services.feature_flags` + `baas_feature_configs`
- 客户端 bootstrap 下发 `feature_flags` 与 `endpoints`

## 鉴权

| 层级 | Header |
|------|--------|
| 服务级 | `X-Baas-Service-Id` + `X-Baas-Api-Key` |
| 玩家级 | 上述 + `Authorization: Bearer` + `X-Baas-Player-Id` |

## 测试

```powershell
cd portals/common/core
py -3 -m pytest tests/test_baas_pve_arena.py tests/test_baas_public_api.py -q
py -3 scripts/run_baas_production_readiness_e2e.py --skip-unity
```

## 相关文档

- 部署：`docs/runbooks/baas_server_deploy_step_by_step.md`
- 客户端接入：`docs/runbooks/baas_client_onboarding.md`
- 错误码：`docs/baas_error_codes.md`
