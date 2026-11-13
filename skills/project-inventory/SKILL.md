---
name: project-inventory
description: Run a lightweight, offline continuity check on a project (required files, folder contracts, expiring facts, state files older than the work, derived files drifting from their sources). Use before finishing work in a project, before publishing, or when the user says "project inventory", "check project state" or "جرد المشروع".
---

# project-inventory

1. Find the project root (the folder that holds `Jobs/inventory.config.json`). If the config is missing, copy `${CLAUDE_PLUGIN_ROOT}/examples/inventory.config.example.json` to `<root>/Jobs/inventory.config.json`, adapt it with the user, and do not run before they agree.
2. Run (read-only, offline):

```
python -X utf8 "${CLAUDE_PLUGIN_ROOT}/scripts/project_inventory.py" "<project root>" [--report <file>]
```

Use `python3` if `python` is not available; `--config <file>` points to a config stored elsewhere.
3. Exit 0 = no FAIL, 2 = at least one FAIL, 1 = tool error (config missing or invalid). WARN never fails.
4. Fix every WARN/FAIL by updating the stale files (in the order your project uses, for example log, then manifest, then handover last). Never edit the config to hide a problem.

Config keys are documented at the top of `scripts/project_inventory.py` and in the README.
