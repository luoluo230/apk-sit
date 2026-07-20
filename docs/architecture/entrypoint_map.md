# 入口地图（主路径）

| 用户意图 | 唯一 URL | API | Service 模块 |
|----------|----------|-----|--------------|
| 选 scope | `/admin/projects/{id}/environments/{env}` | `GET .../environment-detail` | `channel_journey_bff.environment_detail` |
| 构建 | `.../channels/{ch}/build` | `POST .../versions/{vid}/quick-build` | `release_order_service.request_build` |
| 发版 | `.../channels/{ch}/release` | precheck → publish → verify | `release_order_service` + `order_publish_flow`（同文件内） |
| 一键发版 | — | `POST .../delivery-attempts/quick-publish` | `quick_publish_delivery` |
| 客户端读包 | — | `GET /api/public/runtime-bootstrap` | `bundle_service` |

## Legacy（redirect / wrapper）

| Legacy | 替代 |
|--------|------|
| `/admin/build/commercial-release` | `/admin/projects/{id}/overview` |
| `POST .../commercial-release/trigger` | `POST .../quick-build`（带 Deprecation） |
| `POST .../commercial-release/activate` | `precheck` + `publish` via release order |
| `GET /runtime/version-resolve` | `GET /api/public/runtime-bootstrap` |
