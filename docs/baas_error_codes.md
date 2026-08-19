# BaaS Error Codes

Single source: `packages/baas_shared/error_codes.json`. Regenerate with:

```powershell
py -3 scripts/generate_baas_error_artifacts.py
```

## Envelope

```json
{ "ok": false, "error_code": "BAAS_ROOM_NOT_FOUND", "error": "房间不存在", "details": {} }
```

## Transport codes (client network layer)

| Code | 中文 | client_action | retry |
|------|------|---------------|-------|
| 1001 | 连接失败 | retry | True |
| 1002 | 连接已断开 | reconnect | True |
| 1003 | 重连失败 | retry | True |
| 1004 | 心跳超时 | reconnect | True |
| 1005 | 发送队列溢出 | backoff | True |
| 1006 | 请求超时 | retry | True |
| 1007 | 请求失败 | retry | True |
| 1008 | 登录已过期 | relogin | False |
| 1009 | 服务器维护中 | wait | True |
| 1010 | 服务器繁忙 | retry | True |

## Business codes

| error_code | HTTP | 中文 | category | client_action | retry |
|------------|------|------|----------|---------------|-------|
| `BAAS_ACHIEVEMENT_DISABLED` | 403 | 成就功能未启用 | feature | toast | False |
| `BAAS_ACHIEVEMENT_NOT_COMPLETE` | 400 | 成就未完成 | achievement | toast | False |
| `BAAS_AUTH_ACCOUNT_BANNED` | 403 | 账号已被封禁 | auth | logout | False |
| `BAAS_AUTH_ACCOUNT_EXISTS` | 409 | 账号已存在 | auth | toast | False |
| `BAAS_AUTH_ACCOUNT_NOT_FOUND` | 400 | 账号不存在 | auth | toast | False |
| `BAAS_AUTH_CREDENTIALS_REQUIRED` | 400 | 用户名和密码必填 | validation | fix_input | False |
| `BAAS_AUTH_GUEST_DISABLED` | 403 | 游客登录未启用 | feature | toast | False |
| `BAAS_AUTH_INVALID_CREDENTIALS` | 401 | 服务凭证无效 | auth | check_config | False |
| `BAAS_AUTH_LOGIN_DISABLED` | 403 | 登录功能未启用 | feature | toast | False |
| `BAAS_AUTH_MISSING_KEY` | 401 | 缺少 X-Baas-Api-Key | auth | check_config | False |
| `BAAS_AUTH_PASSWORD_DISABLED` | 403 | 账号密码登录未启用 | feature | toast | False |
| `BAAS_AUTH_PASSWORD_TOO_SHORT` | 400 | 密码至少 6 个字符 | validation | fix_input | False |
| `BAAS_AUTH_PASSWORD_WRONG` | 400 | 密码错误 | auth | fix_input | False |
| `BAAS_AUTH_PLAYER_REQUIRED` | 401 | 需要玩家 Authorization | auth | login | False |
| `BAAS_AUTH_SERVICE_MISMATCH` | 400 | service_id 不匹配 | auth | check_config | False |
| `BAAS_AUTH_SESSION_INVALID` | 401 | 会话无效 | auth | relogin | False |
| `BAAS_AUTH_TOKEN_EXPIRED` | 401 | 登录已过期 | auth | relogin | False |
| `BAAS_AUTH_UNAUTHORIZED` | 401 | 未授权 | auth | relogin | False |
| `BAAS_AUTH_USERNAME_TOO_SHORT` | 400 | 用户名至少 3 个字符 | validation | fix_input | False |
| `BAAS_BATTLEPASS_ALREADY_CLAIMED` | 409 | 已领取 | battlepass | toast | False |
| `BAAS_BATTLEPASS_DISABLED` | 403 | 战令功能未启用 | feature | toast | False |
| `BAAS_BATTLEPASS_LEVEL_LOW` | 400 | 等级不足 | battlepass | toast | False |
| `BAAS_BATTLE_HOST_FINISH_ONLY` | 403 | 仅房主可结束对局 | room | toast | False |
| `BAAS_BATTLE_NOT_IN` | 403 | 不在对局中 | room | back_lobby | False |
| `BAAS_BATTLE_NOT_RUNNING` | 400 | 对局未进行中 | room | toast | False |
| `BAAS_BATTLE_NOT_STARTED` | 400 | 对局未开始 | room | wait | True |
| `BAAS_BOOTSTRAP_INVALID_PROJECT` | 401 | 项目凭证无效 | bootstrap | check_config | False |
| `BAAS_BOOTSTRAP_NOT_BAAS_MODE` | 400 | 项目未启用轻度 BaaS 模式 | bootstrap | check_config | False |
| `BAAS_BOOTSTRAP_PARAMS_REQUIRED` | 400 | game_id、game_key、env_key、channel 必填 | bootstrap | check_config | False |
| `BAAS_BOOTSTRAP_PLATFORM_INVALID` | 400 | platform 无效 | bootstrap | check_config | False |
| `BAAS_CLOUDSAVE_DISABLED` | 403 | 云存档功能未启用 | feature | toast | False |
| `BAAS_CLOUDSAVE_KEY_LIMIT` | 400 | 存档 key 数量已达上限 | cloudsave | toast | False |
| `BAAS_CLOUDSAVE_KEY_REQUIRED` | 400 | key 必填 | validation | fix_input | False |
| `BAAS_CLOUDSAVE_TOO_LARGE` | 413 | 存档数据过大 | cloudsave | toast | False |
| `BAAS_CLOUDSAVE_VERSION_CONFLICT` | 409 | 版本冲突 | cloudsave | merge_prompt | False |
| `BAAS_COMPLIANCE_DISABLED` | 403 | 防沉迷未启用 | feature | toast | False |
| `BAAS_COMPLIANCE_ID_INVALID` | 400 | 证件号无效 | compliance | fix_input | False |
| `BAAS_ECONOMY_DISABLED` | 403 | 经济系统未启用 | feature | toast | False |
| `BAAS_FEATURE_ROOM_DISABLED` | 403 | 房间/对战功能未启用 | feature | toast | False |
| `BAAS_FIELD_REQUIRED` | 400 | key 必填 | validation | fix_input | False |
| `BAAS_FORBIDDEN` | 403 | 无权限 | auth | toast | False |
| `BAAS_FRAMEWORK_NOT_DEPLOYED` | 503 | BaaS 服务器框架未部署 | bootstrap | wait | True |
| `BAAS_GAMESERVER_BRIDGE_FAILED` | 502 | GameServer 桥接失败 | bridge | retry | True |
| `BAAS_GIFT_ALREADY_REDEEMED` | 409 | 已兑换过该礼包 | gift | toast | False |
| `BAAS_GIFT_CODE_REQUIRED` | 400 | 兑换码必填 | gift | fix_input | False |
| `BAAS_GIFT_CODE_TOO_SHORT` | 400 | 兑换码至少 4 位 | gift | fix_input | False |
| `BAAS_GIFT_DISABLED` | 403 | 礼包功能未启用 | feature | toast | False |
| `BAAS_GIFT_EXHAUSTED` | 400 | 兑换码已用完 | gift | toast | False |
| `BAAS_GIFT_EXPIRED` | 400 | 兑换码已过期 | gift | toast | False |
| `BAAS_GIFT_INVALID` | 400 | 兑换码无效 | gift | fix_input | False |
| `BAAS_GIFT_PERSONAL_FORBIDDEN` | 403 | 个人兑换码不可使用 | gift | toast | False |
| `BAAS_GIFT_PERSONAL_LIMIT` | 400 | 已达个人兑换上限 | gift | toast | False |
| `BAAS_GIFT_PLAYER_ONLY` | 403 | 兑换码仅限指定玩家使用 | gift | toast | False |
| `BAAS_GUILD_ALREADY_MEMBER` | 409 | 已在公会中 | guild | toast | False |
| `BAAS_GUILD_DISABLED` | 403 | 公会功能未启用 | feature | toast | False |
| `BAAS_GUILD_FULL` | 400 | 公会已满 | guild | toast | False |
| `BAAS_GUILD_NAME_REQUIRED` | 400 | 公会名必填 | guild | fix_input | False |
| `BAAS_GUILD_NOT_FOUND` | 404 | 公会不存在 | guild | refresh | False |
| `BAAS_IP_REQUIRED` | 400 | IP 必填 | validation | fix_input | False |
| `BAAS_JSON_PARSE_FAILED` | 200 | 响应解析失败 | client | retry | True |
| `BAAS_LEADERBOARD_DISABLED` | 403 | 排行榜功能未启用 | feature | toast | False |
| `BAAS_MAIL_DISABLED` | 403 | 邮件功能未启用 | feature | toast | False |
| `BAAS_MAIL_NOT_FOUND` | 404 | 邮件不存在 | mail | refresh | False |
| `BAAS_NOT_LOGGED_IN` | 401 | 未登录 | auth | login | False |
| `BAAS_PLAYER_ID_REQUIRED` | 400 | player_id 必填 | validation | fix_input | False |
| `BAAS_PLAYER_NOT_FOUND` | 404 | 玩家不存在 | player | toast | False |
| `BAAS_PLAYER_NO_SESSION` | 400 | 玩家无有效 session token，可能未在线登录过 | player | toast | False |
| `BAAS_PROJECT_FIELDS_REQUIRED` | 400 | 项目 ID 与名称必填 | admin | fix_input | False |
| `BAAS_PROJECT_ID_EXISTS` | 409 | 项目 ID 已存在 | admin | fix_input | False |
| `BAAS_PROJECT_NOT_FOUND` | 404 | 项目不存在 | admin | toast | False |
| `BAAS_REPLAY_NOT_FOUND` | 404 | 回放不存在 | room | toast | False |
| `BAAS_REWARD_REQUIRED` | 400 | 至少发放一项道具 | validation | fix_input | False |
| `BAAS_ROOM_BATTLE_STARTED` | 409 | 对局已开始，请使用重连接口 | room | reconnect | False |
| `BAAS_ROOM_CANNOT_KICK_HOST` | 400 | 不能踢出房主 | room | toast | False |
| `BAAS_ROOM_CLOSED` | 400 | 房间已关闭 | room | back_lobby | False |
| `BAAS_ROOM_FULL` | 400 | 房间已满 | room | rematch | False |
| `BAAS_ROOM_HOST_ONLY` | 403 | 仅房主可踢人 | room | toast | False |
| `BAAS_ROOM_HOST_START_ONLY` | 403 | 仅房主可开始对局 | room | toast | False |
| `BAAS_ROOM_NOT_ENOUGH_PLAYERS` | 400 | 玩家人数不足，无法开始对局 | room | toast | False |
| `BAAS_ROOM_NOT_FOUND` | 404 | 房间不存在 | room | back_lobby | False |
| `BAAS_ROOM_NOT_JOINED` | 403 | 不在房间内 | room | back_lobby | False |
| `BAAS_ROOM_PASSWORD_WRONG` | 403 | 房间密码错误 | room | fix_input | False |
| `BAAS_ROOM_PLAYER_NOT_IN` | 400 | 玩家不在该房间 | room | back_lobby | False |
| `BAAS_ROOM_PLAYER_NOT_INSIDE` | 400 | 玩家不在房间内 | room | back_lobby | False |
| `BAAS_ROOM_SPECTATOR_FULL` | 400 | 观战人数已满 | room | toast | False |
| `BAAS_SERVER_MODE_INVALID` | 400 | server_mode 无效 | admin | fix_input | False |
| `BAAS_SERVICE_HAS_PLAYERS` | 409 | 服务仍有玩家数据，请先禁用或迁移 | admin | toast | False |
| `BAAS_SERVICE_ID_EXISTS` | 409 | 服务 ID 已存在 | admin | fix_input | False |
| `BAAS_SERVICE_ID_INVALID` | 400 | 服务 ID 须为 3–64 位小写字母、数字、下划线或连字符，且以字母或数字开头 | admin | fix_input | False |
| `BAAS_SERVICE_IMMUTABLE` | 400 | 名称与 ID 创建后不可修改 | admin | toast | False |
| `BAAS_SERVICE_NAME_REQUIRED` | 400 | 服务名称不能为空 | admin | fix_input | False |
| `BAAS_SERVICE_NOT_FOUND` | 404 | 休闲服务不存在 | bootstrap | check_config | False |
| `BAAS_SERVICE_PROJECT_REQUIRED` | 400 | project_id required | admin | fix_input | False |
| `BAAS_SESSION_TOKEN_REQUIRED` | 400 | session_or_token 必填 | validation | fix_input | False |
| `BAAS_SHOP_ITEM_NOT_FOUND` | 404 | 商品不存在 | shop | refresh | False |
| `BAAS_TARGET_ID_REQUIRED` | 400 | target_id 必填 | validation | fix_input | False |
| `BAAS_TASK_DISABLED` | 403 | 周期任务未启用 | feature | toast | False |
| `BAAS_TASK_NOT_COMPLETE` | 400 | 任务未完成 | task | toast | False |
| `BAAS_TOPOLOGY_NOT_DEPLOYED` | 503 | 拓扑服务器框架未部署 | bootstrap | wait | True |
| `BAAS_UNKNOWN` | 400 | 未知错误 | internal | toast | False |
| `BAAS_VALIDATION_FAILED` | 400 | 参数校验失败 | validation | fix_input | False |
| `BAAS_WALLET_INSUFFICIENT` | 400 | 余额不足 | wallet | top_up | False |
