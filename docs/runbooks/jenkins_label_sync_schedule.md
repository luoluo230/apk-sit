# Jenkins 节点 label 对账 — 调度入口（GAP-P1-05-OPT-01）

本机/DevStack **不得**冒充生产 cron 已落地；此处仅定义可复验的**调度入口**与运维安装方式。

## 入口命令

从仓库根目录：

```powershell
py -3 portals/common/core/scripts/jenkins_sync_node_labels_gate.py
```

等价于调用 `jenkins_manager.sync_node_labels(dry_run=False)` 并写入 `docs/evidence/<date>/GAP-P1-05-OPT-01.json`。

## Windows 任务计划（示例）

```powershell
$Action = New-ScheduledTaskAction -Execute "py.exe" -Argument "-3 portals\common\core\scripts\jenkins_sync_node_labels_gate.py" -WorkingDirectory "E:\web\apk-site"
$Trigger = New-ScheduledTaskTrigger -Daily -At 03:15
Register-ScheduledTask -TaskName "apk-site-jenkins-label-sync" -Action $Action -Trigger $Trigger -Description "P1-05 Jenkins label reconcile"
```

安装后需在 evidence 中记录任务存在（`schtasks /Query /TN apk-site-jenkins-label-sync` 输出）方可升 **DONE**。

## Linux cron（示例）

```cron
15 3 * * * cd /opt/apk-site && /usr/bin/python3 portals/common/core/scripts/jenkins_sync_node_labels_gate.py >> /var/log/apk-site-label-sync.log 2>&1
```

## 升 DONE 门槛

| 项 | 要求 |
|----|------|
| 脚本 | `jenkins_sync_node_labels_gate.py` exit 0 |
| 调度 | 生产或 staging 上已注册定时任务（非仅文档） |
| 证据 | `docs/evidence/…/GAP-P1-05-OPT-01.json` + 调度查询输出 |

未装调度时最高 **PARTIAL**（脚本 + runbook 仅算入口就绪）。
