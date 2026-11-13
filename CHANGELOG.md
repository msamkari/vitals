# Changelog

## 0.1.0 (unreleased)
- First plugin release, generalized from a private single-file tool.
- Config key `items` added (legacy `episodes` still accepted); messages in English.
- Tool errors (missing or invalid config, bad arguments, bad `--today`) exit 1 with a message instead of a traceback; argparse usage errors no longer exit 2.
- Checks that used to be skipped silently (no matching item folders, no state or work files) now WARN.
- Root path is glob-escaped; the archive filter looks at the relative path only.
- `run()` is importable; 10 unit tests (stdlib `unittest`); CI matrix Python 3.8 and 3.12 on Linux and Windows.
