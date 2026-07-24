# Plan Step Gate Checklist

Copy per Step; all must PASS before moving to next Step.

```text
Plan ID: ___________   Step: ___________   Date: ___________

READ
[ ] Plan Step scope (In/Out) understood
[ ] Dependencies from plans/README.md satisfied
[ ] build_release_ownership.md field ownership respected

DESIGN
[ ] New files listed with layer (route/service/repo/static)
[ ] No logic added to forbidden monoliths (helpers/version_service/project_delivery.js)
[ ] Rollback strategy from Plan noted

CODE
[ ] UTF-8; user Chinese OK; no mojibake
[ ] Functions focused; new service file has module docstring
[ ] Comments only for non-obvious business / compat

VALIDATE
[ ] python -m py_compile (changed .py)
[ ] node --check (changed .js)
[ ] pytest paths from Plan — pass count: ___
[ ] Plan Step acceptance bullets — all checked

DELIVER
[ ] Delivery report uses skill template
[ ] DoD not claimed unless all Steps in Plan scope done
```
