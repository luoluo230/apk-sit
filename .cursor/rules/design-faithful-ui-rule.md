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
- The implementation must not be visually real but behaviorally fake.
- If a feature is claimed implemented, the UI, route, backend logic, feedback, and state transitions for that feature must all work within the agreed scope.
- It is not acceptable to ship buttons, menus, KPI cards, tabs, sections, or dialogs that look interactive but have no real behavior unless the user explicitly approves a placeholder.
- Frontend and backend business behavior must stay aligned; do not leave API-only features without usable UI in scope, and do not leave UI-only features without real backend effect in scope.
- Where state, severity, risk, or function differ, the design should use semantic color differentiation that still fits the overall page style.
- It is not acceptable to stop at:
  - matching only the outer shell
  - matching only high-level layout
  - matching only data behavior
  - matching only code structure
  - matching only the interactive shell without real execution
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
  - which actions are real, what they trigger, and how success/failure is surfaced
  - frontend/backend ownership and handoff for each in-scope interaction
  - semantic color rules for status, severity, risk, and action types
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
- Real clicks and in-scope actions must be exercised in the browser when the feature includes interaction.
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
  - whether visible actions are real and produce the expected user-facing result
  - whether status/function/risk color usage is consistent and style-compatible
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
  - fake or dead interaction on any visible in-scope control
  - frontend/backend scope mismatch for an implemented feature
  - missing or misleading semantic color treatment for statuses or risky actions
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
- Do not accept fake buttons or fake cards just because the backend endpoint exists.
- Do not accept backend capability without a usable interface when that interface is in scope for the task.
- Do not flatten all actions into one generic visual treatment when the design should communicate state or risk.

## Code constraints

- Do not put all page logic into one script.
- Keep templates, styles, scripts, routes, and services separated by responsibility.
- Use clean names and shallow functions.
- Do not leak styles or scripts into unrelated modules.
- Do not ship visible encoding issues.
