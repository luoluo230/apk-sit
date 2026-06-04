# Design Assets

这个目录用于保存用户提供的设计图、截图、视觉稿、本地导出的参考图片。

## 使用规则

- 一个模块一组设计图
- 文件名尽量稳定、可预测、可复用
- 如果当前只有线程截图，没有本地文件：
  - 先在对应 `docs/design_specs/*.md` 中记录“线程设计图为准”
  - 再在这里预留目标文件名

## 推荐命名

- `agent-center.png`
- `agent-detail.png`
- `approval-center.png`
- `project-workspace.png`
- `module-name-state-empty.png`
- `module-name-state-error.png`

## 配套约束

- 开发前先看设计图，再看代码
- 继续开发同模块时，优先复用已有设计图和设计文档
- 如果设计图更新，先更新设计文档，再继续写代码
