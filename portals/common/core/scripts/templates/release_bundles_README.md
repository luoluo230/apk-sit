# release_bundles — 本地构建产物（勿当源码发版）

**DO NOT SHIP** 本目录内容作为 UTF-8 源码门禁或商业交付物。

- 由 `scripts/build_split_deploy_bundles.py` 生成，可能含历史导出乱码、二进制或第三方镜像。
- `scripts/encoding_gate.py` 通过 `SKIP_DIR_NAMES` **刻意跳过** `release_bundles/`（见该文件注释）。
- 生产部署请使用仓库内 `portals/common/core` 真源 + 正式构建流水线，勿直接上传本目录。

如需编码审计，只扫 `portals/common/core/{routes,services,templates,static}` 真源树。
