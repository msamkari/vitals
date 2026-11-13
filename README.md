# vitals

> Your project's vitals, offline.

A Claude Code plugin that runs a **deterministic, offline continuity check** on any project folder: are the required files there, does every item folder follow its contract, are recorded facts still valid, are the state files at least as fresh as the work, and has a derived file drifted from its sources.

- No network. No dependencies (Python 3.8+ standard library only).
- Read-only (writes a report only if you pass `--report`).
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

Exit code: `0` no FAIL, `2` at least one FAIL, `1` tool error (config missing or invalid, bad arguments). WARN never fails. `--today` affects fact expiry only. Use `python3` where `python` is not available. `facts_files` is a single glob string.

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

Never executes project files, never opens network connections, never writes anything except the optional `--report` file, and stores no credentials. Config paths are trusted input: use relative paths inside the project root.

## Tests

```
python -m unittest discover -s tests -v
```

## License

MIT, see [LICENSE](LICENSE).
