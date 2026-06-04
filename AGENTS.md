# Design-First Delivery Rules

These rules apply to the entire repository.

## Scope

- These rules are not only for the Agent module.
- Any module implemented from a design image, screenshot, mockup, or detailed visual reference must follow this file.

## Non-negotiables

- When the user provides a design image, implementation must match the design as closely as possible in layout, spacing, hierarchy, states, interactions, and visible text.
- Design-faithful delivery is a hard requirement, not a best effort.
- Do not replace a concrete design with a generic admin layout or a reused shell just because it is faster.
- If a page is being rewritten to match a design, do not keep legacy UI structure or compatibility code unless the user explicitly requires backward compatibility.
- Do not leave mojibake, broken encoding, corrupted Chinese text, or mixed-language garbage in templates, scripts, styles, or docs.

## Required workflow for design-driven work

- First check whether a detailed spec already exists under `docs/design_specs/`.
- If no detailed spec exists, create one before implementation based on:
  - the current product behavior
  - the provided design
  - the required interactions and empty/loading/error states
- Treat the design spec and the provided design images as the source of truth for the module.
- If local copies of the design images do not yet exist, reserve them under `docs/design_assets/` and record the expected filenames in the matching spec.
- If the running page does not match the edited template, verify the actual serving process, route, cache-busting query strings, and stale service instances before continuing visual tweaks.
- When backend aggregation, view-model shape, or routing are changed, verify the real runtime entrypoint that feeds the page, not only helper functions or internal builders.
- If there are multiple possible data entrypoints, verify the exact endpoint used by the browser page before declaring a fix complete.

## Implementation constraints

- Prefer clean rewrites over patching old UI when the old structure conflicts with the new design.
- During a rewrite, remove obsolete logic instead of carrying old branches “just in case”.
- Keep modules split by responsibility. Avoid pushing all page behavior into one script.
- Keep code easy for AI and humans to extend: short functions, clear names, low nesting, minimal coupling.
- Avoid unrelated refactors while implementing a design-driven module.
- Do not let this module's CSS or JS leak into unrelated modules.

## Validation requirements

- Run syntax validation on every changed JS file.
- Run Python compile validation on every changed Python route/controller file.
- Check changed files for visible encoding problems before declaring work done.
- Check the rendered module for stale shells, width bugs, overflow, and responsive breakpoints before declaring visual work done.
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
- Validate changed JS and Python files.
- Summarize:
  - changed files
  - validation commands run
  - how to review the module

## Priority note

- Higher-priority system, developer, or user instructions override this file when they conflict.
