# 设计实现文档使用说明

这个目录用于保存“按设计图实现模块”时的详细开发文档。

## 什么时候要建文档

- 用户给了设计图、截图、视觉稿、线框图
- 页面需要重写
- 新模块要按固定视觉和交互实现
- 同一个模块后续还会继续扩展

## 命名建议

- 一个模块一个文档
- 使用英文短横线命名或清晰的模块描述
- 示例：
  - `agent-center-and-detail.md`
  - `approval-center.md`
  - `project-workspace.md`

## 使用顺序

1. 先看有没有现成文档
2. 没有就基于 `_design-module-spec-template.md` 新建
3. **填完 token 表 / 尺寸表 / 图标清单 / 文案清单 / 11 维对照表** 再写代码
4. 同模块继续开发时，先更新文档，再改代码

## 强制要求（零容差）

- **四张表 + 11 维对照未填完 → 禁止写 UI 代码**
- 设计图必须归档在 `docs/design_assets/` 并在 spec 中引用
- 交付前必须填「**专业验收判定表**」，**全部 PASS 且报告结论为「通过验收」**才可向用户交付成品
- 差一点都不可声称 1:1 或「可以验收」
- 工作流：`.cursor/skills/design-faithful-ui/SKILL.md`（**Phase A0 读图 → Phase A 填表 → Phase B 实现 → Phase C 验收+立即修复**）
- 规则：`.cursor/rules/design-faithful-ui-rule.md`

## 推荐配套

- 设计图：`docs/design_assets/`
- 模板：`docs/design_specs/_design-module-spec-template.md`
- 规则：`.cursor/rules/design-faithful-ui-rule.md`
- 技能：`.cursor/skills/design-faithful-ui/SKILL.md`
- 仓库级：`AGENTS.md`
