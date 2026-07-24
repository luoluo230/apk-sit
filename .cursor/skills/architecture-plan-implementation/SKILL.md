---
name: architecture-plan-implementation
description: >-
  Implements docs/architecture/plans (P0/P1/P2) and full_stack_expert_review items
  with readable, layered code—no monolith scripts, UTF-8 Chinese copy, Plan Step
  DoD gates. Use when executing architecture plans, Config Registry, Ops split,
  onboarding wizard, build grid, server release plane, or refactoring helpers.py.
---

# Architecture Plan Implementation

## When to use

- User references `docs/architecture/plans/Px-xx_*.md` or `full_stack_expert_review.md`
- Task is **infrastructure / refactor / new service**, not design-pixel UI (use `design-faithful-ui` instead)
- Cross-repo: `apk-site` + optional `maclient` / `game-server`

## Authority chain (read in order)

1. **Active Plan** — `docs/architecture/plans/Px-xx_*.md` (Step list + DoD is law)
2. **Domain** — `docs/design_specs/build_release_ownership.md`, `docs/full_release_chain_architecture.md`
3. **Coding** — [STANDARDS.md](./STANDARDS.md), `.cursor/rules/architecture-plan-*.mdc`
4. **Safety** — `.cursor/rules/safe-change-workflow.md` (syntax gates, minimal scope)

Plan **Out of scope** wins over opportunistic refactors.

---

## Workflow (mandatory)

### Phase A — Align (before any edit)

```
- [ ] A1  Read the Plan doc fully; note Step number in use
- [ ] A2  Read Plan dependencies (README.md graph); do not skip prereqs
- [ ] A3  List In/Out; reject drive-by fixes outside Step
- [ ] A4  Identify layers: route / service / repo / static — no new god files
- [ ] A5  Baseline: git status; note tests to run (Plan §测试与门禁)
```

### Phase B — Implement one Step only

```
- [ ] B1  One Step = one PR-sized change set (Plan PR strategy if present)
- [ ] B2  New logic → service or repository; routes stay thin
- [ ] B3  File size: Python service ≤400 lines new module; extend existing ≤+80 lines unless Plan says split
- [ ] B4  User-visible Chinese: UTF-8, review for mojibake; i18n keys in messages.json when applicable
- [ ] B5  Comments: module docstring + non-obvious business rules only (see STANDARDS)
```

### Phase C — Verify (before claiming Step done)

```
- [ ] C1  Python: python -m py_compile / pytest paths from Plan
- [ ] C2  JS: node --check on changed .js files
- [ ] C3  Encoding: no replacement chars; Chinese renders correctly in diff
- [ ] C4  Step acceptance checklist in Plan — every box
- [ ] C5  Do not mark Plan DoD until all Steps in scope are C-complete
```

Copy [CHECKLIST.md](./CHECKLIST.md) into the session when executing a full Plan.

---

## Architecture rules (non-negotiable)

| Rule | Action |
|------|--------|
| No script monolith | Split by responsibility; one file ≈ one domain (topology, webhook auth, onboarding) |
| No import-time mutable globals | Use repo layer (P0-02); never add new `*_db = load_document` caches |
| Release domain | New release logic → `services/release/`; do not grow `admin_routes.py` / `helpers.py` |
| Ops domain | New ops logic → `services/ops/<module>.py`; `helpers.py` only re-exports during migration |
| Build domain | `services/build/` + `build_grid.py` constants; no platform logic in Journey BFF |
| Routes | Parse input → call service → return JSON/HTML; no business rules in routes |
| Tests | Each Step adds or updates tests named in Plan; behavior lock before refactor |

---

## Module placement guide

| Change type | Location |
|-------------|----------|
| HTTP API | `routes/admin/api_*.py` or `routes/delivery/` |
| Business logic | `services/<domain>/` |
| DB access | `repositories/` or `models/db.py` migrations |
| Constants / catalogs | `data/*.py` or dedicated `*_constants.py` |
| Internal webhook | `routes/internal_*.py` + `services/security/` |
| Frontend | `static/<feature>.js` — split if >400 lines added in one Step |
| Runbook | `docs/runbooks/` |
| Plan progress | Update Plan doc checkbox or linked issue — not AGENTS.md essays |

---

## PR & commit discipline

- Message: `plan(P0-02): step 2 remove projects_db import cache`
- One Step per commit when possible; user must ask before git commit
- Refactor PRs: **zero behavior change** unless Plan says otherwise; tests prove it

---

## Anti-patterns (stop and redesign)

- Adding 200+ lines to `helpers.py`, `version_service.py`, `admin_routes.py`, `project_delivery.js`
- Fixing encoding by re-saving random encodings; use UTF-8 and fix root cause
- Implementing P2 while P0 Step incomplete without user approval
- `except Exception: pass` on publish / ops / webhook paths
- Duplicating channel/platform ID mapping in a third place — extend `scope_ids` or registry

---

## Multi-repo Steps

| Repo | Paths |
|------|-------|
| apk-site | `portals/common/core/`, `jenkins-clone/scripts/`, `scripts/` |
| maclient | `Assets/Src/`, `Assets/Editor/ReleaseTools/`, `docs/framework/` |
| game-server | `game-server/`, `tools/ServerAgent/` |

Parameter contract changes require **both** `Web-Jenkins-Unity-ParameterSpec.md` and pipeline script update in same Step.

---

## Delivery report template (Plan tasks)

```markdown
## Plan {ID} Step {N}

**Scope**: …
**Files**: …
**Validation**: {commands + results}
**Step checklist**: all PASS / FAIL items
**DoD**: not reached / reached
**Next**: Step N+1 or blocked on …
```

---

## Additional resources

- [STANDARDS.md](./STANDARDS.md) — readability, size limits, comments, encoding
- [CHECKLIST.md](./CHECKLIST.md) — printable Step gate
- [plans/README.md](../../docs/architecture/plans/README.md) — dependency graph
