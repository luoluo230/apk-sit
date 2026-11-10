# Channel ID SSOT（OPEN-2026-11-10-19）

## 规则

- **规范 ID**：项目内渠道主键以 
esolve_channel_id(project_id, raw) 解析后的字符串为准（services/release/scope_ids.py）。
- **兼容输入**：路由/表单可接受历史数字或别名；写入 release_order / version / scope 前必须 resolve。
- **禁止**：新 API 同时返回未解释的「数字 id」与「字符串 id」作为并列主键而不标注 canonical。

## 验收

- 本仓调用点经 
esolve_channel_id 或显式文档 Out。
- 证据：docs/evidence/YYYY-MM-DD/OPEN-2026-11-10-19.json
