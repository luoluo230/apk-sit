# Business Test Run

- plan_id: 
- plan_name: 登录选服创角
- transport: websocket
- passed: True
- started: 2026-06-08T10:02:11.1783665Z
- finished: 2026-06-08T10:02:12.7906652Z

## Steps
### s1 Login_c2s (ok)
- message_id: 10001
- latency_ms: 8
- data_type: Login_s2c, HotUpdate

**Client request:**
```json
{"Username":"biztest_20260608100211","Password":"123456","Device":{"Platform":"BusinessTest","DeviceId":"4cbb2d89a5bf4774a879a66d8540dada","ClientVersion":"1.0"}}
```

**Server response:**
```json
{"Success":true,"Message":"Account created. Please select a server.","Token":{"Token":"411fd9bb964c4a338678643ec33da50f","ExpireAt":1780919886},"Profile":null,"AutoLogin":false,"LastServerId":null,"ServerList":[{"ServerId":"s1","Name":"Dawn City","Region":"CN-1","Status":"Online","IsRecommended":true,"OnlinePlayers":5230},{"ServerId":"s2","Name":"Starfall Valley","Region":"CN-2","Status":"Busy","IsRecommended":false,"OnlinePlayers":8120},{"ServerId":"s3","Name":"Everwood","Region":"CN-3","Status":"Maintenance","IsRecommended":false,"OnlinePlayers":0}]}
```

### s2 SelectServer_c2s (ok)
- message_id: 10003
- latency_ms: 1
- data_type: SelectServer_s2c, HotUpdate

**Client request:**
```json
{"Token":"411fd9bb964c4a338678643ec33da50f","ServerId":"game-cn-1"}
```

**Server response:**
```json
{"Success":true,"Message":"Server selected. Create a character next.","ServerId":"game-cn-1","Profile":null}
```

### s3 CreateRole_c2s (ok)
- message_id: 10005
- latency_ms: 1
- data_type: CreateRole_s2c, HotUpdate

**Client request:**
```json
{"Token":"411fd9bb964c4a338678643ec33da50f","ServerId":"game-cn-1","Nickname":"fx_619f0846","Avatar":"default"}
```

**Server response:**
```json
{"Success":true,"Message":"Character created successfully.","Profile":{"PlayerId":175198285226,"Nickname":"fx_82187431","Level":1,"Experience":0,"Gold":1000,"Diamonds":100,"ClearedStage":0,"VipLevel":0,"CombatPower":500,"GuildName":"Adventurers","CurrentStage":0,"ArenaRank":120,"AvatarUrl":"https://cdn.ma-game.com/avatar/default.png","Country":"Unknown"}}
```

### s4 GetPlayerProfile_c2s (ok)
- message_id: 10011
- latency_ms: 1
- data_type: GetPlayerProfile_s2c, HotUpdate

**Client request:**
```json
{"Token":"411fd9bb964c4a338678643ec33da50f","ServerId":"game-cn-1"}
```

**Server response:**
```json
{"Profile":{"PlayerId":175198285226,"Nickname":"fx_82187431","Level":1,"Experience":0,"Gold":1000,"Diamonds":100,"ClearedStage":0,"VipLevel":0,"CombatPower":500,"GuildName":"冒险者公会","CurrentStage":0,"ArenaRank":120,"AvatarUrl":"https://cdn.ma-game.com/avatar/default.png","Country":"Unknown"}}
```

