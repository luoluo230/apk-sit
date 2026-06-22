# PR Documentation Checklist (T0-09 – T0-11)

Use this checklist before opening or merging a PR that touches architecture, release, or cross-repo contracts.

## T0-09 — Scope & spec linkage

- [ ] PR description links the governing spec (`docs/design_specs/…` or `arch-docs/…`).
- [ ] Task ID from `arch-docs/TASK-BACKLOG.md` cited when applicable.
- [ ] User-visible copy matches design/spec text (no placeholder lorem).

## T0-10 — Runtime & validation evidence

- [ ] Changed Python files pass `python -m py_compile …`.
- [ ] Changed JS files pass syntax check / lint where configured.
- [ ] Ops or release paths include how to verify locally (script name + port).
- [ ] For cross-repo changes: note which repo must merge first.

## T0-11 — Architecture doc sync

- [ ] If behavior changed, update the relevant `arch-docs/*.md` section or mark backlog item status.
- [ ] New endpoints/modules listed in module map or API inventory.
- [ ] Breaking changes called out with migration steps.
- [ ] Screenshots or acceptance notes attached for UI-facing work.

## Quick review template

```markdown
## Summary
…

## Spec / task
- Spec: …
- Task ID: …

## Test plan
- [ ] …

## Doc sync
- [ ] arch-docs updated / N/A
```
