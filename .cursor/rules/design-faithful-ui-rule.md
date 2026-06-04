# Design Faithful UI Rule

## Purpose

- This is the single design-rule entrypoint for any module implemented from a design image.
- When the user names `design-faithful-ui`, this rule is automatically active.
- This rule exists to prevent "close enough" delivery and force rendered-result validation.

## Automatic companions

- This rule runs together with:
  - `AGENTS.md`
  - `.cursor/rules/safe-change-workflow.md`
  - `docs/design_specs/README.md`
  - `docs/design_specs/_design-module-spec-template.md`
  - `docs/design_assets/README.md`
- If a matching module spec already exists in `docs/design_specs/*.md`, it must be read first.
- If no module spec exists, it must be created before code changes.

## Hard requirements

- The design is a hard acceptance target, not inspiration.
- The implementation must be accepted against the rendered page, not only against source code.
- The implementation must not be called complete until rendered-result differences are cleared or explicitly listed as blocking differences.
- It is not acceptable to stop at:
  - matching only the outer shell
  - matching only high-level layout
  - matching only data behavior
  - matching only code structure
- It is not acceptable to ignore obvious visual mismatches that are visible in a browser screenshot.

## Required pre-implementation design analysis

- Before coding, convert the design into a checklist and place it in the module spec.
- That checklist must include at least:
  - page shell width and alignment
  - left navigation width, grouping, active state, icons
  - top toolbar / breadcrumb / title area
  - primary and secondary button size, order, spacing, icon treatment
  - KPI card count, size, icon style, typography hierarchy
  - filters, search, view switch, and batch toolbar layout
  - main content primary state
  - card layout, card content, card actions, borders, hover states
  - tables, charts, tabs, and summary cards
  - empty, loading, error, hover, active, disabled, selected states
- If this checklist does not exist yet, do not start implementation.

## Required implementation flow

- Read `AGENTS.md`.
- Read this rule.
- Read or create the module design spec.
- Inspect `git status`.
- Create a baseline commit and push it to the current remote branch before starting the new implementation pass.
- If the push fails, stop and report the block.
- Decide whether the page needs a rewrite; if the old shell conflicts with the design, rewrite rather than patch around it.
- If the change touches any of these, verify the real runtime entrypoint before claiming a fix:
  - routes
  - template selection
  - aggregation
  - controller/view-model
  - cache-busting version
  - service process

## Browser validation gate

- If Chrome automation or Browser automation is available, it must be used after major UI changes.
- The rendered local page must be inspected in the browser before the task can be called complete.
- Source inspection alone is not sufficient.
- If the browser result differs from the design in obvious ways, keep working; do not report completion.

## Required post-implementation comparison

- After implementation, produce a mental or written diff between:
  - current rendered result
  - target design
- That comparison must explicitly cover:
  - left navigation
  - top bar
  - hero/title block
  - button groups
  - KPI cards
  - filters and toolbars
  - primary content state
  - pagination
  - detail summary cards
  - tabs
  - tables
  - charts
- If any one of those still obviously differs, "1:1 complete" is not allowed.

## Hard blockers for claiming completion

- Any of the following blocks a "done" claim:
  - wrong primary state versus design
  - wrong navigation structure or icon treatment
  - wrong button order, size, or spacing
  - wrong KPI visual hierarchy
  - wrong card density or card composition
  - wrong tab spacing / underline / active state
  - wrong table widths / alignment / action buttons
  - obvious browser-visible mismatch that would be clear to a human without code inspection
  - unverified runtime process, route, or cache version
  - skipped baseline commit/push

## Lessons from this task, now mandatory

- Do not change only helper functions while forgetting the actual page-facing endpoint.
- Do not treat "rendered something similar" as success.
- Do not rely on code inspection to decide whether a design is matched.
- Do not skip browser-based self-verification when automation is available.
- Do not wait for the user to point out obvious mismatches that should have been caught during inspection.
- Do not stop after data-model correctness if the design is still clearly wrong.

## Code constraints

- Do not put all page logic into one script.
- Keep templates, styles, scripts, routes, and services separated by responsibility.
- Use clean names and shallow functions.
- Do not leak styles or scripts into unrelated modules.
- Do not ship visible encoding issues.
