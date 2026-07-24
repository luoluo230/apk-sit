# Architecture Plan — Coding Standards

> Applies to all Plan implementation in apk-site, maclient, game-server.

## 1. Readability

- **Names**: `verb_noun` for functions (`ensure_runtime_for_scope`), `noun_service` for modules
- **Functions**: one clear purpose; prefer ≤50 lines; extract when nesting >3 levels
- **Parameters**: ≤5 args; use dataclass/dict payload for onboarding/API bulk input
- **Early return**: guard clauses first; avoid deep if/else pyramids
- **Types**: Python 3.10+ `dict[str, Any]` in services; public functions typed

## 2. Simplicity

- Minimum diff that satisfies **current Plan Step** only
- No speculative abstractions ("future platform plugin framework")
- Reuse existing helpers (`scope_ids`, `normalize_release_env_key`, `build_grid`) before new utils
- Prefer explicit code over clever metaprogramming

## 3. Comments & docstrings

**Write comments when**:

- Business invariant not obvious from code ("production publish requires approved status")
- Migration / compat shim with removal date
- External contract (Jenkins env var names, bootstrap field ownership)

**Do not write**:

- Comments that restate the code (`# increment i`)
- Large blocks of commented-out code — delete or restore from git

**Module docstring** (top of every new service file):

```python
# -*- coding: utf-8 -*-
"""One-line purpose.

Plan: P1-01 Step 3 — topology scoped load/save extracted from helpers.
"""
```

**Public API docstring**: args, returns, raises `ValueError` when relevant — one short paragraph.

## 4. Encoding & Chinese text

- All source files: **UTF-8** (`# -*- coding: utf-8 -*-` on Python)
- User-facing strings: **简体中文**; store in `translations/zh_CN/messages.json` for Portal UI
- Forbidden in committed files: mojibake (`Ã©`, `ï¿½`, ``), mixed EN/ZH garbage labels
- PowerShell: avoid `$` inside double-quoted regex; use single-quoted strings or `[regex]::Escape`
- Before finish: eyeball diff on Chinese lines; run `encoding_gate.py` when touching release modules

## 5. File & module size limits

| Artifact | Soft limit | Action when exceeded |
|----------|------------|----------------------|
| Python service module | 400 lines | Split by subdomain in same Step or next Step |
| Python route file | 300 lines | Extract blueprint / api_ module |
| JS page script | 500 lines | Split: state / api / render / events |
| Shell pipeline | 200 lines | Extract `*_common.sh` shared functions |
| Single function | 50 lines | Extract named helpers |

**Never** append a full new feature to `helpers.py`, `version_service.py`, `project_delivery.js` — Plan explicitly requires split.

## 6. Layering (apk-site)

```text
routes/          → HTTP, auth check, CSRF, JSON encode
services/        → business rules, orchestration
repositories/    → CRUD, SQL, JSON mirror
models/db.py     → schema, migrations
data/            → catalogs, pure functions on config
```

- Routes **must not** import `models/db` cursors directly except legacy; new code uses repositories
- Services **must not** render HTML templates
- Cross-domain: call other **services**, not reach into private `_foo` from helpers

## 7. Error handling

- User errors: `ValueError` with **中文** message (operational) or i18n key
- API: consistent `{ok: false, error: "..."}` / HTTP 400
- Never swallow errors on: publish, precheck, webhook auth, Agent dispatch
- Log internal detail; expose safe message to UI

## 8. Tests

- Name: `test_<plan_id>_<behavior>.py` or extend existing `test_*` in same domain
- Refactor Steps: characterization tests before moving code
- Each Step lists pytest path in Plan — run before Step sign-off

## 9. Security (P0 Plans)

- No default passwords in code paths
- Secrets from env only; document in runbook
- Webhook: HMAC verification module, not copy-paste digest in each route

## 10. C# / Unity (maclient Plans)

- Editor CLI: one class per `ExecuteFromCommandLine` entry
- Runtime: bootstrap changes stay in `Framework/Bootstrap/`
- No new fallback paths without Plan P2-02 approval

## 11. Shell / Jenkins

- Shared functions in `commercial_pipeline_common.sh`
- Platform pipelines: thin wrappers calling common + platform-specific blocks
- `set -euo pipefail` on new bash scripts
