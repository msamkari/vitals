---
name: vitals
description: Run a lightweight, offline continuity check on a project (required files, folder contracts, expiring facts, state files older than the work, derived files drifting from their sources). Use before finishing work in a project, before publishing, or when the user says "vitals", "project vitals", "check project state" or "جرد المشروع".
---

# vitals

1. Find the project root. If `<root>/Jobs/inventory.config.json` is missing, propose one: run `python -X utf8 "${CLAUDE_PLUGIN_ROOT}/scripts/vitals.py" "<root>" --init` (prints only), show the proposal to the user, and only after they agree run the same command with `--write` (it never overwrites). If `--init` exits 1, show its message and do not invent or write a config. The proposal may make the first run FAIL on state freshness: that is the check working, so fix the state files, not the config. Then offer to extend it by hand (item folders, facts, sync rules: see `${CLAUDE_PLUGIN_ROOT}/examples/inventory.config.example.json`).
2. Run (read-only, offline):

```
python -X utf8 "${CLAUDE_PLUGIN_ROOT}/scripts/vitals.py" "<project root>" [--report <file>]
```

Use `python3` if `python` is not available; `--config <file>` points to a config stored elsewhere.
3. Exit 0 = no FAIL, 2 = at least one FAIL, 1 = tool error (config missing or invalid; with `--init`: config already exists, root not found, nothing recognizable, or write failed). WARN never fails.
4. Fix every WARN/FAIL by updating the stale files (in the order your project uses, for example log, then manifest, then handover last). Never edit the config to hide a problem.

Config keys are documented at the top of `scripts/vitals.py` and in the README.
