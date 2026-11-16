# Changelog

## 0.2.3 (2026-11-15)
Round-2 adversarial findings, fixed here:
- Root confinement for every config path: `items.require`, `items.manifest`, `state_fresh` state files, `sync` targets and sources and every glob are judged from their text first (absolute, rooted, UNC, drive-letter, `..`, NUL) and reported as `FAIL ... outside the project root`; such a path is never looked up, so there is no existence oracle and a UNC entry cannot make the OS contact another host. Silent skips of outside entries became FAILs.
- Bounded traversal: globs are matched by an own `os.scandir` walker (same results as `glob` on plain trees, checked by a test; `*`, `?`, `[..]`, `**`, hidden-name and case rules as before) that never follows symlinks or junctions and counts every entry against a cap (20000 x 10) and the 30 s deadline, so a pattern that matches nothing is bounded too. `require` patterns use the same walker. Behaviour change: `**` in `require` now recurses (it used to act like `*`), and a symlinked folder is no longer entered by a glob.
- Output hygiene: `clean()` now removes every character of Unicode categories Cc, Cf, Zl, Zp, Cs and Co (line breaks and tabs become one space), collapses whitespace, and is applied to everything echoed from config or files (glob strings, labels, names, `max_days`, error text); a final pass makes sure one result is one line, so a glob containing newlines cannot forge a `[PASS]` line.
- `--report`: refuses to overwrite any file unless its first line starts with `# vitals ` and it has at most 10000 lines, each empty or starting with `[PASS]`, `[WARN]`, `[FAIL]` or `#` (lines over 5000 characters count as foreign); refuses the config file, anything named `inventory.config.json...`, a hard link to the config, any path that goes through a symlink or junction, and on Windows a `:` in the file name; a missing folder or an unwritable target gives one clear line instead of a traceback. A `--config` that is a directory or a 200000-deep JSON also gives one line.
- Tests: 27 -> 51 (the Windows-only junction/ADS tests are skipped elsewhere).
- Known limits: a race between the report check and the write is not closed; a very large tree can use most of the 30 s; macOS `/tmp` and any folder reached through a link cannot be a report target; Windows 8.3 short names and `readme.md.` / `nul` quirks (round-2 V6) are unchanged; wrong-typed config values still abort the whole run with one line (V7); Python 3.8 is covered by syntax and CI only, not run locally.

## 0.2.2 (2026-11-15)
- Added the plugin icon (square PNG, 1024 px), generated with Gemini and chosen by the author; clears the ICON_MISSING validator warning.

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
