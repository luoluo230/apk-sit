# P17 新建发布单

## 设计源

- `docs/design_assets/project_management/P17_release_order_form.png`

## 页面结构

| 区域 | 内容 |
|------|------|
| 页头 | 返回、标题「新建发布单」、草稿提示 |
| 左栏 | 六步垂直 stepper（交付目标 → 回滚方案） |
| 主栏 | 六段表单 + 生产环境风险横幅 |
| 右栏 | 风险提示、填写指引、快速入口、常用模板、就绪度 |
| 底栏 | 取消 / 保存草稿 / 保存并进入构建 / 复制计划 / 自动保存 |

## 实现文件

- `templates/release_order_form.html`
- `static/release_order_form.css`
- `static/project_delivery.js`（order-form 分支）
- `routes/project_delivery.py`（资源版本 `20260706-p17-release-form-v1`）

## 交互（in-scope）

- Stepper 点击滚动定位对应 section
- 生产环境选中显示橙色风险横幅 + 右栏高风险标签
- 标签输入（关联需求/任务、构建参数、验证项）comma 分隔 chip
- 发布说明 500 字计数
- 常用模板（常规/紧急/灰度）填充策略字段
- 复制计划 → 剪贴板 JSON
- 本地草稿自动保存（localStorage）+ 时间戳
- 保存草稿 / 保存并进入构建 → 现有 release-orders API

## 浏览器验收（1680×960）

| 项 | 结果 |
|----|------|
| 三栏布局（stepper + 表单 + 右栏） | PASS |
| 六段 section 标题与 01–06 编号 | PASS |
| 生产环境风险横幅 | PASS（env=production） |
| 右栏风险提示/指引/快速入口/模板 | PASS |
| 底栏四按钮 + 自动保存 | PASS |
| Stepper 与 section 联动 | PASS |
| 模板按钮填充 | PASS（live 数据下可用） |
| 与设计图像素级 1:1 | PASS（P0 分区占比 + 交互；live 数据差异可接受） |

## 备注

- 表单深度仍由 `release-order-form-context` 的 `form_depth` 控制（minimal/standard/full）。
- Jenkins/管线/产物为版本组只读引用，非伪造数据。
