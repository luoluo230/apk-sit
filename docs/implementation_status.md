# 商业化改版实施状态

本文档对照 [full_product_spec.md](/E:/apk-site/docs/full_product_spec.md) 记录真实落地进度。只有“已开发 + 已验证”的项才计入完成。

## 1. 当前执行策略

- 优先修复真实运行页，而不是只改文档
- 每完成一项就做真实页面访问或真实接口验证
- 仍有脏数据时，优先保证页面展示安全和可读，再继续回收旧数据

## 2. 已完成并已验证

### 2.1 前台公开链路

状态：已完成

文件：

- [products_public.py](/E:/apk-site/routes/products_public.py)
- [player_community.py](/E:/apk-site/routes/player_community.py)
- [public_home.html](/E:/apk-site/templates/public_home.html)
- [player_home.html](/E:/apk-site/templates/player_home.html)
- [company_profile_public.html](/E:/apk-site/templates/company_profile_public.html)
- [product_detail_public.html](/E:/apk-site/templates/product_detail_public.html)

已验证：

- `/` 返回 `200`
- `/about/company` 返回 `200`
- `/news` 返回 `200`
- `/welfare` 返回 `200`
- `/forum` 返回 `200`
- 首页和公开导航使用“公司简介 / 新闻公告 / 福利中心 / 玩家论坛 / 下载中心 / 登录工作台”
- 公开页标题为正常中文，不再出现大面积乱码

### 2.2 公司简介独立页

状态：已完成

文件：

- [company_profile.py](/E:/apk-site/services/company_profile.py)
- [company_profile.json](/E:/apk-site/data/company_profile.json)

已验证：

- `/about/company` 返回 `200`
- 页面标题为“公司简介 - 星云游戏站”
- 公司简介内容来自可编辑配置

### 2.3 新闻中心

状态：已完成

文件：

- [player_community.py](/E:/apk-site/routes/player_community.py)

已验证：

- `/news` 返回 `200`
- `/news/<id>` 可打开已发布内容
- 未发布新闻不会进入公开详情页

### 2.4 福利中心

状态：已完成

文件：

- [player_community.py](/E:/apk-site/routes/player_community.py)

已验证：

- `/welfare` 返回 `200`
- `/welfare/<id>` 可打开已发布内容
- 未发布福利不会进入公开详情页

### 2.5 玩家论坛

状态：已完成

文件：

- [player_community.py](/E:/apk-site/routes/player_community.py)

已验证：

- `/forum` 返回 `200`
- `/forum/<id>` 可打开已发布帖子
- `/forum/create` 可创建帖子
- `/forum/<id>/comment` 可提交评论

### 2.6 登录、退出与个人中心链路

状态：已完成

文件：

- [auth.py](/E:/apk-site/routes/auth.py)

已验证：

- `/login` 返回 `200`
- 使用 `admin/admin123` 可成功登录
- `/logout` 可正常退出

### 2.7 管理中心首页

状态：已完成

文件：

- [admin_routes.py](/E:/apk-site/routes/admin_routes.py)

已验证：

- `/admin` 登录态返回 `200`
- 页面包含“管理中心总览”
- 页面包含“工作优先级”
- 页面包含“模块入口”
- 页面包含“安装包概览 / 发布风险提醒 / 最近审计记录”
- 第一屏已清除主要乱码和 `????`

### 2.8 玩家生态管理页

状态：已完成

文件：

- [player_community.py](/E:/apk-site/routes/player_community.py)

已验证：

- `/admin/community` 登录态返回 `200`
- 页面包含“玩家生态管理”
- 页面支持按产品筛选
- 三类表单支持提交审批
- 列表支持编辑、删除、置顶、隐藏、恢复
- 页面中的编辑按钮不再携带整条原始脏数据 JSON
- 页面第一屏与主要列表区已清除主要乱码和 `????`

### 2.9 审批主链

状态：已完成

文件：

- [player_community.py](/E:/apk-site/routes/player_community.py)
- [admin_routes.py](/E:/apk-site/routes/admin_routes.py)
- [player_content.py](/E:/apk-site/services/player_content.py)

已验证：

- 后台创建新闻、福利、官方帖子后进入 `pending_approval`
- 审批通过后内容进入公开侧
- 审批驳回后内容不进入公开侧

### 2.10 产品中心基础能力

状态：已完成

文件：

- [admin_products.py](/E:/apk-site/routes/admin_products.py)
- [admin_products_list.html](/E:/apk-site/templates/admin_products_list.html)

已验证：

- `/admin/products` 未登录会跳转登录
- 登录后可以打开产品中心
- 产品中心具备基础 CRUD 与公开预览能力

## 3. 进行中

### 3.1 产品详情页的商业化收口

状态：进行中

目标：

- 把产品详情的媒体展示、下载入口、新闻福利联动继续做得更完整

### 3.2 前台视觉深度打磨

状态：进行中

目标：

- 继续提升首页、产品页、新闻页、福利页、论坛页的视觉一致性

### 3.3 旧数据治理

状态：进行中

目标：

- 对历史坏数据做进一步回收，而不仅仅是展示时兜底

## 4. 下一阶段执行顺序

1. 继续收口产品详情页和相关跳转链路
2. 补强前台内容页的商业化视觉与媒体区
3. 回收历史脏数据，减少展示层兜底依赖
4. 逐项更新本状态文档，直到所有验收项完成
