# Design Assets

这个目录保存**设计验收的唯一真相来源**。开发、验收、交付均以这里的图片为准，不以代码注释或口头描述为准。

## 强制规则

1. **先有设计图，后有代码。** 用户提供的截图/视觉稿必须归档到本目录（或在线程中明确路径后由 agent 复制进来）。
2. **文件名稳定可复用**，并在对应 `docs/design_specs/<模块>.md` 中引用。
3. **浏览器渲染结果必须与本目录图片逐区对照**；差一点都不可作为成品交付。
4. 设计图更新 → **先更新 spec 与 token 表，再改代码**。
5. 多状态（空态/错误态/弹窗）→ 每态一张图，分别命名归档。

## 推荐命名

- `<module>-<screen>-reference.png` — 例：`topology-workbench-tools-mode-reference.png`
- `<module>-<state>-reference.png` — 例：`topology-workbench-empty-reference.png`
- `<module>-modal-<name>-reference.png`

## 验收用法

- 实现前：从设计图提取 token、尺寸、图标、文案到 spec
- 实现后：浏览器截图与本目录图片**并排**对比
- 交付时：在 spec「截图对比清单」注明每张 design_assets 文件的 PASS/FAIL

## 禁止

- 只有线程图片、本地无归档，却声称「按设计完成」
- 用旧版设计图验收新版实现而不更新文件名
- 以「数据不同所以看起来不一样」跳过**组件样式**的 1:1 验收

## 配套文档

- 规格：`docs/design_specs/*.md`
- 工作流：`.cursor/skills/design-faithful-ui/SKILL.md`
- 规则：`.cursor/rules/design-faithful-ui-rule.md`
