# vitals

> Your project's vitals, offline.

A Claude Code plugin that runs a **deterministic, offline continuity check** on any project folder: are the required files there, does every item folder follow its contract, are recorded facts still valid, are the state files at least as fresh as the work, and has a derived file drifted from its sources.

- No network. No dependencies (Python 3.8+ standard library only).
- Read-only by default: it writes only the optional `--report` file, and a new starter config when you explicitly run `--init --write`.
- Configured per project with one JSON file, so nothing is copied between projects.

Arabic: [README.ar.md](README.ar.md)

## Install

```
/plugin marketplace add msamkari/samkari-plugins
/plugin install vitals@samkari-plugins
```

Then ask Claude: "run vitals" (skill `vitals`).

## Use without Claude

```
python -X utf8 scripts/vitals.py <project_root> [--config FILE] [--report FILE]
```

Exit code: `0` no FAIL, `2` at least one FAIL, `1` tool error (config missing or invalid, bad arguments; with `--init`: config already exists, root not found, nothing recognizable, write failed). WARN never fails. `--today` affects fact expiry only. Use `python3` where `python` is not available. `facts_files` is a single glob string.

## Start without a config

```
python -X utf8 scripts/vitals.py <project_root> --init          # prints a proposal, writes nothing
python -X utf8 scripts/vitals.py <project_root> --init --write  # creates Jobs/inventory.config.json (never overwrites)
```

`--init` only looks at which well-known files exist (CLAUDE.md, README.md, HANDOVER, Jobs state/log files); it never reads their contents. Item folders, facts and sync rules are project-specific: add them by hand.

## Config (`<root>/Jobs/inventory.config.json`)

See [examples/inventory.config.example.json](examples/inventory.config.example.json).

| Key | Meaning |
|---|---|
| `required_files` | paths that must exist |
| `items` (alias `episodes`) | folder glob + required files per folder + optional manifest that must mention each folder |
| `facts_files` / `facts_soon_days` | JSON files with `facts[]` (`id`, `date_verified`, `expires_after_days`); expired = FAIL, near expiry = WARN |
| `state_fresh` | state files must not be older than the newest work file by more than `grace_minutes` |
| `newest_age` | newest file of a glob must be younger than `max_days` (WARN) |
| `sync` | target file older than any of its sources = WARN |

Fix findings by updating the stale files, never by editing the config to hide them.

## Safety

Never executes project files, never opens network connections, never writes anything except the optional `--report` file and, on explicit `--init --write`, a new config file that it never overwrites. It stores no credentials. Config paths are checked, not trusted: every path (required files, item requirements, manifest, state, sync, globs) must stay inside the project root; absolute, UNC, drive-letter and `..` paths are reported as FAIL (`outside the project root`) without being looked up. Globs are matched by a bounded walker that never enters symlinks or junctions and stops at 200000 entries or 30 s even when nothing matches (known limit: a very large tree can still use most of those 30 s). All text echoed from the config or from project files has control, format, line-separator, surrogate and private-use characters removed. `--report` overwrites only a file that is exactly a previous vitals report (first line `# vitals `, at most 10000 lines, every line empty or starting with `[PASS]`, `[WARN]`, `[FAIL]` or `#`); it refuses the config file and anything named like it, a path that goes through a symlink or junction anywhere (so a project reached through a linked folder cannot be reported into), and, on Windows, file names containing `:`. A race between the check and the write is not closed.

## Tests

```
python -m unittest discover -s tests -v
```

## License

MIT, see [LICENSE](LICENSE).
