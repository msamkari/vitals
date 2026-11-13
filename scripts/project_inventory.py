# -*- coding: utf-8 -*-
"""project_inventory.py <project_root> [--config FILE] [--report FILE] [--today YYYY-MM-DD]

Deterministic, offline continuity check for any project. No network, no writes
(except --report). Default config: <root>/Jobs/inventory.config.json

Config keys (all optional):
  required_files   list of paths that must exist
  items            {"glob": "Items/*", "require": ["facts.json", "script_v*.md"], "manifest": "Jobs/state_manifest.json"}
                   (legacy key "episodes" is accepted as an alias)
  facts_files      glob of JSON files {"facts": [{"id", "date_verified", "expires_after_days"}]}
  facts_soon_days  warn this many days before a fact expires (default 5)
  state_fresh      {"state": [...], "work": [...globs...], "grace_minutes": 5}
  newest_age       [{"glob": "...", "max_days": 10, "label": "..."}]
  sync             [{"target": "file", "sources": ["file", ...], "label": "..."}]

Output: [PASS|WARN|FAIL] name: evidence. Exit code 0 = no FAIL, 2 = at least one FAIL,
1 = tool error (config missing/invalid, bad arguments). WARN never changes the exit code.
--today affects fact expiry only; newest_age always uses the current time.
Config paths are trusted input: use relative paths inside the project root.
"""
import argparse
import datetime as dt
import glob
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def run(root, config_path=None, today=None):
    """Return (lines, fails, warns) for a project root."""
    R = os.path.abspath(root)
    today = today or dt.date.today()
    cfg_file = config_path or os.path.join(R, "Jobs", "inventory.config.json")
    with open(cfg_file, encoding="utf-8") as fh:
        cfg = json.load(fh)
    out = []

    def add(level, name, ev=""):
        out.append((level, name, ev))

    def g(p):
        return glob.glob(os.path.join(glob.escape(R), p), recursive=True)

    def mt(p):
        return os.path.getmtime(p)

    for f in cfg.get("required_files", []):
        add("PASS" if os.path.exists(os.path.join(R, f)) else "FAIL", "required: " + f)

    ep = cfg.get("items") or cfg.get("episodes")
    if ep:
        man = ""
        mp = os.path.join(R, ep.get("manifest", ""))
        if ep.get("manifest") and os.path.isfile(mp):
            with open(mp, encoding="utf-8") as fh:
                man = fh.read()
        dirs = sorted(x for x in g(ep["glob"]) if os.path.isdir(x) and not os.path.basename(x).startswith("_"))
        if not dirs:
            add("WARN", "items " + ep["glob"], "no matching folders")
        for d in dirs:
            n = os.path.basename(d)
            miss = [r for r in ep.get("require", []) if not glob.glob(os.path.join(d, r))]
            add("PASS" if not miss else "FAIL", "item " + n, ("missing: " + ", ".join(miss)) if miss else "files ok")
            if man:
                add("PASS" if n in man else "WARN", "manifest mentions " + n)

    ff = cfg.get("facts_files")
    if ff:
        soon = cfg.get("facts_soon_days", 5)
        for f in sorted(g(ff)):
            rel = os.path.relpath(f, R)
            try:
                with open(f, encoding="utf-8") as fh:
                    d = json.load(fh)
            except Exception as e:
                add("FAIL", "facts " + rel, "unreadable: %s" % e)
                continue
            bad, near = [], []
            for x in d.get("facts", []):
                try:
                    exp = dt.date.fromisoformat(x["date_verified"]) + dt.timedelta(days=int(x["expires_after_days"]))
                except Exception:
                    bad.append(str(x.get("id", "?")) + "(date?)")
                    continue
                if exp < today:
                    bad.append("%s expired %s" % (x.get("id"), exp))
                elif (exp - today).days <= soon:
                    near.append("%s -> %s" % (x.get("id"), exp))
            add("FAIL" if bad else ("WARN" if near else "PASS"), "facts " + rel, "; ".join(bad + near) or "all valid")

    sf = cfg.get("state_fresh")
    if sf:
        state = [os.path.join(R, s) for s in sf["state"] if os.path.isfile(os.path.join(R, s))]
        work = [w for p in sf["work"] for w in g(p) if os.path.isfile(w) and "_archive" not in os.path.relpath(w, R).lower()]
        if state and work:
            oldest_state = min(mt(s) for s in state)
            newest = max(work, key=mt)
            gap = (mt(newest) - oldest_state) / 60
            ok = gap <= sf.get("grace_minutes", 5)
            add("PASS" if ok else "FAIL", "state files fresher than work",
                "ok" if gap <= 0 else "newest work %s is %.0f min after oldest state file" % (os.path.relpath(newest, R), gap))
        else:
            add("WARN", "state files fresher than work", "skipped: no state files or no work files found")

    for n in cfg.get("newest_age", []):
        fs = g(n["glob"])
        label = n.get("label", n["glob"])
        if not fs:
            add("WARN", label, "no files")
            continue
        age = (dt.datetime.now().timestamp() - max(mt(f) for f in fs)) / 86400
        add("PASS" if age <= n["max_days"] else "WARN", label, "newest %.1f d old (max %s)" % (age, n["max_days"]))

    for s in cfg.get("sync", []):
        label = s.get("label", s["target"])
        t = os.path.join(R, s["target"])
        if not os.path.isfile(t):
            add("WARN", label, "target missing")
            continue
        newer = [x for x in s["sources"] if os.path.isfile(os.path.join(R, x)) and mt(os.path.join(R, x)) > mt(t) + 60]
        add("WARN" if newer else "PASS", label, ("sources newer than target: " + ", ".join(newer)) if newer else "in sync")

    fails = sum(1 for l, _, _ in out if l == "FAIL")
    warns = sum(1 for l, _, _ in out if l == "WARN")
    head = "# project_inventory %s - %s - FAIL %d / WARN %d / total %d" % (os.path.basename(R), today, fails, warns, len(out))
    lines = [head] + ["[%s] %s" % (l, n) + (": " + e if e else "") for l, n, e in out]
    return lines, fails, warns


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
    a = ap.parse_args(argv)
    try:
        lines, fails, _ = run(a.root, a.config, dt.date.fromisoformat(a.today))
    except FileNotFoundError as e:
        print("config not found: %s (create Jobs/inventory.config.json, see examples/)" % e.filename, file=sys.stderr)
        return 1
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        print("invalid config or data (%s: %s)" % (type(e).__name__, e), file=sys.stderr)
        return 1
    txt = "\n".join(lines)
    print(txt)
    if a.report:
        with open(a.report, "w", encoding="utf-8") as fh:
            fh.write(txt + "\n")
    return 2 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
