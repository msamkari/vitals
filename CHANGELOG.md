# Changelog

## 0.2.1 (2026-11-15)
Found by an adversarial test round (22 findings; fixed here):
- `--report` no longer overwrites a file that is not a previous vitals report (it had replaced the project's config).
- The skill now declares `allowed-tools: Bash(python -X utf8 ${CLAUDE_PLUGIN_ROOT}/scripts/vitals.py *)` and the command is written unquoted, so a run does not prompt.
- Config paths that resolve outside the project root are reported as FAIL and never read; text from project files (fact ids, labels, names) is cleaned and truncated before printing.
- Link loops and runaway globs are bounded (20000 files, 30 s, at most two `**` segments); a symlink loop no longer crashes with a traceback.
- A malformed facts file fails only that file; wrong-typed config values give a clear error; a UTF-8 BOM in config or facts files is accepted; a file vanishing mid-run is not reported as a missing config; `manifest mentions` matches whole words.

## 0.2.0 (2026-11-13)
- New `--init` / `--init --write`: propose or create a starter `Jobs/inventory.config.json` from well-known files that exist. Never reads file contents and never overwrites an existing config.
- The skill now offers the proposal when a project has no config.
- Writes use exclusive creation; write errors, missing roots and `--init` combined with `--config`/`--report` exit 1 with a clear message.
- Docs corrected: the tool is read-only except `--report` and the explicit `--init --write`.
- 17 unit tests (7 new for `--init`).

## 0.1.0 (2026-11-13)
- Plugin name: vitals (was a private tool called project_inventory).
- First plugin release, generalized from a private single-file tool.
- Config key `items` added (legacy `episodes` still accepted); messages in English.
- Tool errors (missing or invalid config, bad arguments, bad `--today`) exit 1 with a message instead of a traceback; argparse usage errors no longer exit 2.
- Checks that used to be skipped silently (no matching item folders, no state or work files) now WARN.
- Root path is glob-escaped; the archive filter looks at the relative path only.
- `run()` is importable; 10 unit tests (stdlib `unittest`); CI matrix Python 3.8 and 3.12 on Linux and Windows.
