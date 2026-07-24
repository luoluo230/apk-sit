# REF：领域模型、维护决策表与行业对照

> **类型**：只读参考，非实施 Plan。  
> 来源：[`full_stack_expert_review.md`](../full_stack_expert_review.md) §1–2、§6–7、§10–11。

---

## 1. 三产品与 Scope

```text
产品 A Delivery  → Scope → ReleaseOrder → Bundle → runtime-bootstrap
产品 B Build Grid → Jenkins Job / build_node
产品 C Ops        → cluster.json → Agent → GameServer 启停
```

**Scope 主键**：

```text
scope_id = {project_slug}:{env_key}:{channel_id}:{platform}
```

---

## 2. 七层配置归属

详见 [`build_release_ownership.md`](../../design_specs/build_release_ownership.md)。

```text
Global Catalog → Project → Environment → Channel Binding
  → Version Group（构建 SSOT）→ VersionCode → Release Order
```

---

## 3. 维护决策表

| 我要… | 改 Web | 改 maclient | 改 game-server |
|-------|--------|-------------|----------------|
| 新建项目 | `project_service` + projects | — | — |
| 加全局渠道 | `channels.json` + admin UI | `HotUpdateConfigSyncCli` | — |
| 项目启用渠道 | `project.channels` | — | — |
| 环境隐藏渠道 | `release_environments[].disabled_channels` | — | — |
| 加平台（仅 UI） | `platforms.py` + project.platforms | — | — |
| 加平台（能构建） | build_grid + Jenkins + version group API | Editor CLI | — |
| 改 Jenkins 管线 | `version_groups[].pipeline_template` | Registry/CLI | — |
| 改客户端网关 | topology + bootstrap | ProtocolNetworkSettings | cluster.json |
| 启停游戏服 | Ops Agent | — | cluster / Agent |
| 客户端发版 | ReleaseOrder Journey | bootstrap | — |
| 服务端发版 | **P2-01 Server Release Plane**（当前未实现） | — | 制品 + 滚动重启 |

---

## 4. 大厂对照（摘要）

| 维度 | 腾讯 | 网易 | 米哈游 | 本项目 |
|------|------|------|--------|--------|
| 配置中心 | Rainbow/CMDB | 配置平台+Homer | launcher 配置 | JSON+SQLite |
| 客户端发布 | Puffer+MSDK | CDN+NPK | OSS+bootstrap | runtime-bootstrap ✅ |
| 服务端发布 | K8s+配置热更 | 独立管线 | rolling | ❌ 未纳入 ReleaseOrder |
| 构建 | 蓝盾+机池 | DevCloud | Unity 农场 | Jenkins+build_grid |

---

## 5. 关键文件索引

| 层级 | 路径 |
|------|------|
| Web 入口 | `portals/common/core/app_new.py` |
| SQLite 发布域 | `portals/common/core/models/db.py` |
| 项目 JSON | `portals/common/core/data/projects.py` |
| Scope | `data/delivery_scope.py`, `services/release/scope_ids.py` |
| 发布 | `services/release/order_publish_flow.py` |
| Ops 巨石 | `services/ops/helpers.py` |
| 构建网格 | `services/build/build_grid.py` |
| 客户端 | `maclient/Assets/Src/Main.cs` |
| 游戏服 | `maclient/game-server/config/cluster.json` |

---

## 6. 若只记三件事

1. 发版围绕 **Scope**，不是「项目一个按钮」。
2. **Delivery / Build Grid / Ops** 三平面平行，Web 编排但不自动部署服。
3. 配置 SSOT 分裂 — 改一项先查七层归属表。
