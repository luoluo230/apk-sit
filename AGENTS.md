# Design-First Delivery Rules

These rules apply to the entire repository.

## Scope

- These rules are not only for the Agent module.
- Any module implemented from a design image, screenshot, mockup, or detailed visual reference must follow this file.

## Non-negotiables

- When the user provides a design image, implementation must match the design **pixel-level in all visible dimensions**: layout, spacing, typography (family/size/weight/line-height), colors, icons, borders, shadows, radius, copy text, and interaction feedback states — **not** merely "close enough" in structure.
- **Do not deliver any version to the user as a finished product until browser-rendered result passes side-by-side comparison against archived design images in `docs/design_assets/`. Even small visible differences block completion.**
- Design-faithful delivery is a hard requirement, not a best effort. Follow `.cursor/skills/design-faithful-ui/SKILL.md` and `.cursor/rules/design-faithful-ui-rule.md` for all design-driven work.
- Do not replace a concrete design with a generic admin layout or a reused shell just because it is faster.
- If a page is being rewritten to match a design, do not keep legacy UI structure or compatibility code unless the user explicitly requires backward compatibility.
- Do not leave mojibake, broken encoding, corrupted Chinese text, or mixed-language garbage in templates, scripts, styles, or docs.
- Do not ship visually complete but behaviorally fake features. If a button, card, tab, menu, modal, KPI block, or functional section is claimed implemented, it must be real and interactive within the agreed scope.
- Do not ship frontend-only features without real backend effect when the feature is in scope, and do not ship backend-only features without usable UI when the user asked for the full workflow.
- Where actions, statuses, risks, or severities differ, use semantic color differentiation that matches the function and still fits the overall interface style.
- Any UI that claims to show realtime parameters, live progress, queue state, rolling metrics, or monitoring curves must be backed by real live sampling or in-memory runtime state.
- Do not synthesize realtime displays from persisted snapshots, disk-restored state, or repeated fallback values just to make the page look alive.

## Required workflow for design-driven work

- First check whether a detailed spec already exists under `docs/design_specs/`.
- If no detailed spec exists, create one before implementation based on:
  - the current product behavior
  - the provided design
  - the required interactions and empty/loading/error states
- Treat the design spec and the provided design images as the source of truth for the module.
- If local copies of the design images do not yet exist, reserve them under `docs/design_assets/` and record the expected filenames in the matching spec.
- Before writing code, extract the design into an implementation checklist that covers **all 11 visual dimensions** (see design-faithful-ui skill):
  - layout and column proportions
  - spacing (padding / margin / gap)
  - font family, weight, line-height, letter-spacing
  - font size hierarchy per region
  - typography alignment and wrapping
  - colors, gradients, borders, radius, shadows, semantic state colors
  - icons (every icon slot filled; source documented if using open-source substitutes)
  - responsive behavior at spec-defined breakpoints
  - hover / active / selected / disabled visual effects
  - loading / empty / error / success feedback copy and style
  - all visible text matching the design exactly
- Also cover in the checklist:
  - page shell and width behavior
  - left navigation structure and active states
  - top bar / breadcrumb / title area
  - primary and secondary button groups
  - KPI cards, filters / search / batch toolbar
  - main content primary state, pagination, tables / charts / summary cards
  - which visible actions are real, what backend flow each one triggers, and how success/failure is surfaced
  - which values are realtime, where live samples come from, and refresh cadence
  - how status, risk, severity, and action types are visually distinguished
- Record that checklist in the module spec or update the existing module spec before implementation.
- If the running page does not match the edited template, verify the actual serving process, route, cache-busting query strings, and stale service instances before continuing visual tweaks.
- When backend aggregation, view-model shape, or routing are changed, verify the real runtime entrypoint that feeds the page, not only helper functions or internal builders.
- If there are multiple possible data entrypoints, verify the exact endpoint used by the browser page before declaring a fix complete.
- If a page includes realtime metrics or progress displays, verify the browser is receiving live updates from runtime memory or active sampling rather than replaying persisted snapshots.

## Implementation constraints

- Prefer clean rewrites over patching old UI when the old structure conflicts with the new design.
- During a rewrite, remove obsolete logic instead of carrying old branches "just in case".
- Keep modules split by responsibility. Avoid pushing all page behavior into one script.
- Keep code easy for AI and humans to extend: short functions, clear names, low nesting, minimal coupling.
- Avoid unrelated refactors while implementing a design-driven module.
- Do not let this module's CSS or JS leak into unrelated modules.
- Do not leave decorative-only controls that look clickable but do nothing.
- Do not consider a feature complete unless the frontend interaction, backend business handling, and user-facing feedback are all connected for the intended path.
- Do not flatten all actions into one undifferentiated visual treatment when the interface should communicate function, state, or risk.

## Validation requirements

- Run syntax validation on every changed JS file.
- Run Python compile validation on every changed Python route/controller file.
- Check changed files for visible encoding problems before declaring work done.
- Check the rendered module for stale shells, width bugs, overflow, and responsive breakpoints before declaring visual work done.
- When Chrome or Browser automation is available, use it to inspect the rendered local page after major UI changes instead of relying on source inspection alone.
- For design-driven pages, validate the real rendered page against the design in the browser before declaring the task complete. **Fill the screenshot comparison checklist in the module spec; any FAIL item blocks "done".**
- Do not use completion language ("基本完成", "差不多", "骨架完成", "约 xx%") for design-driven work unless every checklist item is PASS.
- For interaction-driven pages, verify that visible in-scope actions actually work end to end, not only that the matching endpoints exist.
- Verify that frontend behavior and backend business logic are aligned for the implemented scope.
- Verify that status- and action-based color differentiation is present where needed and remains consistent with the overall page style.
- For realtime KPI, chart, and progress sections, verify that values change from live runtime sampling and do not flatten into synthetic placeholder curves.
- If the user reports visual mismatch, re-check runtime serving/caching assumptions before making more speculative style edits.

## Git workflow

- Before starting a new implementation pass, inspect `git status`.
- If there are pre-existing local modifications, checkpoint them first.
- Before starting any new modification pass for a user-reported issue or redesign, create a baseline commit for the current local state and push that baseline to the remote branch.
- If baseline push cannot be completed because of auth, remote, or branch issues, stop and explicitly report that block before continuing implementation.
- Never rewrite history unless the user explicitly asks.

## Token-efficiency rules

- Reuse existing specs and design docs instead of re-deriving requirements from scratch each turn.
- Keep design specs concise, structured, and implementation-facing.
- When a module already has a spec, update only the relevant sections instead of recreating the whole document.
- Avoid re-reading large files after successful patch application unless new context is required.

## Delivery checklist

- Confirm which spec file governs the module.
- Confirm which design image file(s) or thread images are the source of truth.
- Confirm whether the task is a rewrite or an incremental extension.
- Confirm that a baseline commit and remote push were completed before this modification pass, or explicitly report why they were blocked.
- Confirm the runtime is serving the newest route/template version.
- Confirm the exact runtime endpoint / controller / data entrypoint that the page is consuming.
- For UI work, inspect the running page after major changes and compare the rendered result to the design, not only the source code.
- For design-driven UI work, explicitly list:
  - what matched the design
  - what still differed
  - whether any remaining difference blocks a "1:1 complete" claim
- For feature work, explicitly list:
  - which visible actions were verified as real end-to-end behavior
  - whether frontend and backend business scope were aligned
  - whether semantic color differentiation was added or verified where the design/behavior required it
- Validate changed JS and Python files.
- Summarize:
  - changed files
  - validation commands run
  - how to review the module

## Priority note

- Higher-priority system, developer, or user instructions override this file when they conflict.
