# -*- coding: utf-8 -*-
"""vitals.py <project_root> [--config FILE] [--report FILE] [--today YYYY-MM-DD]

Deterministic, offline continuity check for any project. No network. Writes only the
optional --report file and, on explicit request, a new Jobs/inventory.config.json (--init --write). Default config: <root>/Jobs/inventory.config.json

Config keys (all optional):
  required_files   list of paths that must exist
  items            {"glob": "Items/*", "require": ["facts.json", "script_v*.md"], "manifest": "Jobs/state_manifest.json"}
                   (legacy key "episodes" is accepted as an alias)
  facts_files      glob of JSON files {"facts": [{"id", "date_verified", "expires_after_days"}]}
  facts_soon_days  warn this many days before a fact expires (default 5)
  state_fresh      {"state": [...], "work": [...globs...], "grace_minutes": 5}
  newest_age       [{"glob": "...", "max_days": 10, "label": "..."}]
  sync             [{"target": "file", "sources": ["file", ...], "label": "..."}]

Starter config: `vitals.py <root> --init` prints a proposal from files that exist; add --write to create
Jobs/inventory.config.json (never overwrites).

Output: [PASS|WARN|FAIL] name: evidence. Exit code 0 = no FAIL, 2 = at least one FAIL,
1 = tool error (config missing/invalid, bad arguments; with --init: config already exists,
root not found, nothing recognizable, or write failed). WARN never changes the exit code.
--today affects fact expiry only; newest_age always uses the current time.
Config paths must stay inside the project root (anything resolving outside is reported as FAIL and never read). Text read from project files is stripped of control characters and truncated before it is printed. --report refuses to overwrite a file that is not a previous vitals report.
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


MAX_FILES = 20000          # per glob: a runaway pattern or a link loop must not hang the run
MAX_SECONDS = 30           # wall clock for the whole run


def clean(s, n=80):
    """Text that comes from files is data: strip control characters and cap the length before it is printed."""
    s = re.sub(r"[\x00-\x1f\x7f]+", " ", str(s))
    return s if len(s) <= n else s[: n - 1] + "..."


def run(root, config_path=None, today=None):
    """Return (lines, fails, warns) for a project root."""
    R = os.path.abspath(root)
    today = today or dt.date.today()
    cfg_file = config_path or os.path.join(R, "Jobs", "inventory.config.json")
    with open(cfg_file, encoding="utf-8-sig") as fh:   # utf-8-sig: Notepad and Windows PowerShell write a BOM
        cfg = json.load(fh)
    if not isinstance(cfg, dict):
        raise TypeError("config must be a JSON object")
    out = []
    deadline = time.time() + MAX_SECONDS
    Rr = os.path.realpath(R)

    def inside(p):
        try:
            return os.path.commonpath([Rr, os.path.realpath(p)]) == Rr
        except ValueError:
            return False

    def J(rel):
        """Join a config path to the root; None when it would leave the project root."""
        p = os.path.join(R, rel)
        return p if inside(p) else None

    def lst(v, key):
        if v is None:
            return []
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise TypeError("%s must be a list of strings" % key)
        return v

    def add(level, name, ev=""):
        out.append((level, name, ev))

    def g(p):
        if p.count("**") > 2:
            add("FAIL", "glob " + clean(p), "too many ** segments (limit 2)")
            return []
        res = []
        try:
            for x in glob.iglob(os.path.join(glob.escape(R), p), recursive=True):
                if len(res) >= MAX_FILES or time.time() > deadline:
                    add("FAIL", "glob " + clean(p), "scan limit reached (%d files / %d s); narrow the pattern" % (MAX_FILES, MAX_SECONDS))
                    break
                if inside(x):
                    res.append(x)
        except OSError as e:
            add("FAIL", "glob " + clean(p), "cannot scan: %s" % clean(e))
        return res

    def mt(p):
        try:
            return os.path.getmtime(p)
        except OSError:
            return 0.0

    for f in lst(cfg.get("required_files"), "required_files"):
        p = J(f)
        if p is None:
            add("FAIL", "required: " + clean(f), "outside the project root")
        else:
            add("PASS" if os.path.exists(p) else "FAIL", "required: " + clean(f))

    ep = cfg.get("items") or cfg.get("episodes")
    if ep:
        man = ""
        mp = J(ep.get("manifest", ""))
        if ep.get("manifest") and mp and os.path.isfile(mp):
            with open(mp, encoding="utf-8-sig", errors="replace") as fh:
                man = fh.read()
        dirs = sorted(x for x in g(ep["glob"]) if os.path.isdir(x) and not os.path.basename(x).startswith("_"))
        if not dirs:
            add("WARN", "items " + ep["glob"], "no matching folders")
        for d in dirs:
            n = os.path.basename(d)
            miss = [r for r in lst(ep.get("require"), "require") if not glob.glob(os.path.join(glob.escape(d), r))]
            add("PASS" if not miss else "FAIL", "item " + clean(n), ("missing: " + clean(", ".join(miss))) if miss else "files ok")
            if man:
                add("PASS" if re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", man) else "WARN", "manifest mentions " + clean(n))

    ff = cfg.get("facts_files")
    if ff:
        soon = cfg.get("facts_soon_days", 5)
        for f in sorted(g(ff)):
            rel = clean(os.path.relpath(f, R))
            try:
                with open(f, encoding="utf-8-sig") as fh:
                    d = json.load(fh)
            except Exception as e:
                add("FAIL", "facts " + rel, "unreadable: %s" % clean(e))
                continue
            if not isinstance(d, dict) or not isinstance(d.get("facts", []), list):
                add("FAIL", "facts " + rel, 'unexpected shape (expected {"facts": [...]})')
                continue
            bad, near = [], []
            for x in d.get("facts", []):
                if not isinstance(x, dict):
                    bad.append("?(entry?)")
                    continue
                fid = clean(x.get("id", "?"), 40)
                try:
                    exp = dt.date.fromisoformat(x["date_verified"]) + dt.timedelta(days=int(x["expires_after_days"]))
                except Exception:
                    bad.append(fid + "(date?)")
                    continue
                if exp < today:
                    bad.append("%s expired %s" % (fid, exp))
                elif (exp - today).days <= soon:
                    near.append("%s -> %s" % (fid, exp))
            add("FAIL" if bad else ("WARN" if near else "PASS"), "facts " + rel, "; ".join(bad + near) or "all valid")

    sf = cfg.get("state_fresh")
    if sf:
        state = [J(x) for x in lst(sf["state"], "state") if J(x) and os.path.isfile(J(x))]
        work = [w for p in lst(sf["work"], "work") for w in g(p) if os.path.isfile(w) and "_archive" not in os.path.relpath(w, R).lower()]
        if state and work:
            oldest_state = min(mt(s) for s in state)
            newest = max(work, key=mt)
            gap = (mt(newest) - oldest_state) / 60
            ok = gap <= sf.get("grace_minutes", 5)
            add("PASS" if ok else "FAIL", "state files fresher than work",
                "ok" if gap <= 0 else "newest work %s is %.0f min after oldest state file" % (clean(os.path.relpath(newest, R)), gap))
        else:
            add("WARN", "state files fresher than work", "skipped: no state files or no work files found")

    for n in cfg.get("newest_age", []):
        fs = g(n["glob"])
        label = clean(n.get("label", n["glob"]))
        if not fs:
            add("WARN", label, "no files")
            continue
        age = (dt.datetime.now().timestamp() - max(mt(f) for f in fs)) / 86400
        add("PASS" if age <= n["max_days"] else "WARN", label, "newest %.1f d old (max %s)" % (age, n["max_days"]))

    for s in cfg.get("sync", []):
        label = clean(s.get("label", s["target"]))
        t = J(s["target"])
        if not t or not os.path.isfile(t):
            add("WARN", label, "target missing")
            continue
        newer = [x for x in lst(s["sources"], "sources") if J(x) and os.path.isfile(J(x)) and mt(J(x)) > mt(t) + 60]
        add("WARN" if newer else "PASS", label, ("sources newer than target: " + clean(", ".join(newer))) if newer else "in sync")

    fails = sum(1 for l, _, _ in out if l == "FAIL")
    warns = sum(1 for l, _, _ in out if l == "WARN")
    head = "# vitals %s - %s - FAIL %d / WARN %d / total %d" % (clean(os.path.basename(R)), today, fails, warns, len(out))
    lines = [head] + ["[%s] %s" % (l, n) + (": " + e if e else "") for l, n, e in out]
    return lines, fails, warns


DEFAULT_CONFIG = os.path.join("Jobs", "inventory.config.json")
_CANDIDATE_REQUIRED = ["CLAUDE.md", "README.md", "MDs/HANDOVER.md", "HANDOVER.md",
                       "Jobs/state_manifest.json", "Jobs/series_log.md"]
_CANDIDATE_STATE = ["MDs/HANDOVER.md", "HANDOVER.md", "Jobs/state_manifest.json"]
_CANDIDATE_WORK = ["Jobs/series_log.md", "CHANGELOG.md"]


def detect_config(root):
    """Propose a starter config from files that already exist. Never reads file contents."""
    R = os.path.abspath(root)

    def have(rel):
        return os.path.isfile(os.path.join(R, rel))

    cfg = {"required_files": [f for f in _CANDIDATE_REQUIRED if have(f)]}
    state = [f for f in _CANDIDATE_STATE if have(f)]
    work = [f for f in _CANDIDATE_WORK if have(f)]
    if not work and glob.glob(os.path.join(glob.escape(R), "Jobs", "*.md")):
        work = ["Jobs/*.md"]
    if state and work:
        cfg["state_fresh"] = {"state": state, "work": work, "grace_minutes": 5}
    return cfg


def init_config(root, write=False):
    """Return (exit_code, message). Never overwrites an existing config."""
    R = os.path.abspath(root)
    if not os.path.isdir(R):
        return 1, "root not found: %s" % R
    target = os.path.join(R, DEFAULT_CONFIG)
    cfg = detect_config(R)
    if not cfg["required_files"] and "state_fresh" not in cfg:
        return 1, "nothing recognizable found in %s; copy examples/inventory.config.example.json instead" % R
    text = json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"
    if os.path.lexists(target):
        what = "config already exists" if os.path.isfile(target) else "path exists and is not a regular file"
        return 1, "%s: %s (not overwritten)" % (what, target)
    note = ("Note: state_fresh makes the first run FAIL if your work files are newer than your state files; "
            "that is the check doing its job (update the state files, never the config).")
    if not write:
        return 0, "# proposed %s (nothing written; add --write to create it)\n%s%s" % (DEFAULT_CONFIG, text, note if "state_fresh" in cfg else "")
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "x", encoding="utf-8", newline="\n") as fh:  # "x": fails if it appeared meanwhile
            fh.write(text)
    except FileExistsError:
        return 1, "config already exists: %s (not overwritten)" % target
    except OSError as e:
        return 1, "could not write %s: %s" % (target, e)
    return 0, "created %s\n%s%s" % (target, text, note if "state_fresh" in cfg else "")


def main(argv=None):
    class _Parser(argparse.ArgumentParser):
        def error(self, message):  # usage errors exit 1: exit code 2 is reserved for FAIL findings
            self.print_usage(sys.stderr)
            print("error: " + message, file=sys.stderr)
            sys.exit(1)

    ap = _Parser(description="Offline project continuity check")
    ap.add_argument("root")
    ap.add_argument("--config")
    ap.add_argument("--report")
    ap.add_argument("--today", default=dt.date.today().isoformat())
    ap.add_argument("--init", action="store_true", help="propose a starter config from existing files (prints only)")
    ap.add_argument("--write", action="store_true", help="with --init: create Jobs/inventory.config.json (never overwrites)")
    a = ap.parse_args(argv)
    if a.write and not a.init:
        ap.error("--write only works with --init")
    if a.init and (a.config or a.report):
        ap.error("--init cannot be combined with --config or --report")
    if a.init:
        code, msg = init_config(a.root, a.write)
        print(msg, file=sys.stderr if code else sys.stdout)
        return code
    try:
        lines, fails, _ = run(a.root, a.config, dt.date.fromisoformat(a.today))
    except FileNotFoundError as e:
        cfgp = os.path.abspath(a.config) if a.config else os.path.join(os.path.abspath(a.root), DEFAULT_CONFIG)
        if os.path.abspath(str(e.filename)) == cfgp:
            print("config not found: %s (create Jobs/inventory.config.json, see examples/)" % e.filename, file=sys.stderr)
        else:
            print("a file disappeared during the run: %s (run again)" % e.filename, file=sys.stderr)
        return 1
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        print("invalid config or data (%s: %s)" % (type(e).__name__, e), file=sys.stderr)
        return 1
    txt = "\n".join(lines)
    print(txt)
    if a.report:
        rp = os.path.abspath(a.report)
        if os.path.lexists(rp):
            try:
                with open(rp, encoding="utf-8-sig") as fh:
                    first = fh.readline()
            except (OSError, UnicodeDecodeError):
                first = ""
            if not first.startswith("# vitals "):
                print("refusing to overwrite %s: it is not a previous vitals report (choose a new file name)" % rp, file=sys.stderr)
                return 1
        with open(rp, "w", encoding="utf-8") as fh:
            fh.write(txt + "\n")
    return 2 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
