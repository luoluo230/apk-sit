---
name: design-faithful-ui
description: 用于任何“用户给了设计图、截图、视觉稿，需要严格按图实现页面和交互”的开发任务。适用于所有模块。执行时自动同时启用仓库规则、设计图规则、安全改动流程和设计文档流程；若模块文档不存在则直接创建，无需再次询问用户。
---

# Design Faithful UI

## Single entry

- If the user names this skill, use it as the only workflow entrypoint.
- Do not ask again whether to use rules, specs, design docs, or validation steps.
- This skill automatically activates:
  - `AGENTS.md`
  - `.cursor/rules/design-faithful-ui-rule.md`
  - `.cursor/rules/safe-change-workflow.md`
  - the relevant module spec in `docs/design_specs/`

## Files that must be used

### Rules

- `AGENTS.md`
- `.cursor/rules/design-faithful-ui-rule.md`
- `.cursor/rules/safe-change-workflow.md`

### Documentation

- `docs/design_specs/README.md`
- `docs/design_specs/_design-module-spec-template.md`
- `docs/design_assets/README.md`
- the current module spec under `docs/design_specs/*.md`

## Non-negotiable mindset

- The design is the acceptance target.
- Matching code structure is not enough.
- Matching the outer shell is not enough.
- Matching runtime data is not enough.
- The rendered browser result must match the design.
- If obvious differences remain, the task is not complete.

## Mandatory execution order

1. Read:
   - `AGENTS.md`
   - `.cursor/rules/design-faithful-ui-rule.md`
   - `.cursor/rules/safe-change-workflow.md`
2. Open the module spec under `docs/design_specs/`.
3. If the module spec does not exist, create it immediately.
4. Before coding, write or update the module spec with a design-analysis checklist that includes:
   - shell width and alignment
   - left navigation
   - top bar / breadcrumb / title area
   - button groups
   - KPI cards
   - filters / search / batch tools
   - main content primary state
   - tabs / tables / charts / pagination
   - empty / loading / error / hover / active / disabled / selected states
5. Check `git status`.
6. Create a baseline commit for the current state and push it to the remote branch before starting the new implementation pass.
7. If the baseline push fails, stop and report the block.
8. Decide whether to rewrite or extend; if the design conflicts with the old shell, rewrite.
9. Implement with clear separation between template, style, script, route, and data shaping.
10. If the change touches route, controller, aggregation, template selection, process, or cache version:
   - verify the real runtime entrypoint
   - verify the real process is serving the code
   - verify cache-busting versions are updated
11. After coding, run syntax and compile checks.
12. After coding, use browser automation to inspect the rendered local page when the tool is available.
13. Compare the rendered page against the design section by section.
14. Only if differences are cleared may the task be called complete.

## Browser self-verification

- If Chrome automation is available, use it.
- If Browser automation is available, use it.
- Do not rely only on source files when a browser automation tool is present.
- Use the browser check to catch:
  - wrong spacing
  - wrong widths
  - wrong button placement
  - wrong card count or density
  - wrong icon treatment
  - wrong table alignment
  - overflow or stale shell issues

## Required acceptance checklist

Before claiming completion, verify:

- The rendered page uses the intended route and template.
- The intended service process is serving the updated code.
- Static resource cache versions were bumped when needed.
- The rendered page has no obvious visual mismatch against the design.
- The primary state matches the design primary state.
- The navigation, buttons, KPI cards, filters, content area, pagination, tabs, tables, and charts match the design.
- Changed JS passes syntax checks.
- Changed Python passes compile checks.
- Changed files are free of visible encoding issues.

## Forbidden shortcuts

- Do not stop at "close enough".
- Do not stop at "the data is correct now".
- Do not stop at "the template looks right in code".
- Do not skip browser verification when the tool is available.
- Do not skip the design-analysis checklist.
- Do not skip the baseline commit and push.
- Do not say "done" while obvious differences remain.
- Do not wait for the user to point out mismatches that should have been caught in your own review.

## Delivery requirements

- State which design spec governed the implementation.
- State which design images or thread screenshots were used.
- State that baseline commit and remote push happened before the implementation pass, or report the blocker.
- State which runtime entrypoints, process ids, and cache versions were checked.
- State whether browser verification was performed.
- State whether differences were fully cleared.
- If any difference remains, list it explicitly and do not claim 1:1 completion.
