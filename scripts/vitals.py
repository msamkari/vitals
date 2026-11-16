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
Config paths must stay inside the project root (anything resolving outside is reported as FAIL and never read). Text read from project files is stripped of control characters and truncated before it is printed. --report refuses to overwrite any file that is not exactly a previous vitals report (first line `# vitals `, at most 10000 lines, every line empty or starting with [PASS]/[WARN]/[FAIL]/#), refuses the config file or anything named like it, and refuses a path that goes through a link.
Globs and require patterns are matched by a bounded walker: symlinks and junctions are never entered, and the entry cap and the 30 s limit apply even when nothing matches. Absolute, UNC, drive and `..` config paths are reported as FAIL (outside the project root) without touching the file system.
"""
import argparse
import datetime as dt
import fnmatch
import glob
import json
import os
import re
import stat
import sys
import time
import unicodedata

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


MAX_FILES = 20000          # per glob: results; entries scanned are capped at MAX_FILES * SCAN_FACTOR
SCAN_FACTOR = 10
MAX_SECONDS = 30           # wall clock for the whole run
REPORT_MAX_LINES = 10000
REPORT_MAX_LINE_CHARS = 5000
_REPORT_PREFIXES = ("[PASS]", "[WARN]", "[FAIL]", "#")
_STRIP_CATEGORIES = ("Cc", "Cf", "Zl", "Zp", "Cs", "Co")


def _now():
    return time.monotonic()


def clean(s, n=80):
    """Text that comes from config or files is data: remove every control, format, line/paragraph-separator, surrogate and
    private-use character (Unicode categories Cc, Cf, Zl, Zp, Cs, Co), collapse whitespace and cap the length before printing.
    Line breaks and tabs become a single space; every other such character is dropped."""
    out = []
    for ch in str(s):
        cat = unicodedata.category(ch)
        if cat in _STRIP_CATEGORIES:
            if ch.isspace() or ch in "\u2028\u2029\x85":
                out.append(" ")
            continue
        out.append(ch)
    s = " ".join("".join(out).split())
    return s if len(s) <= n else s[: max(n - 3, 0)] + "..."


def lexical_outside(rel):
    """True when a config path cannot stay inside the project root, judged from the text alone (nothing is touched, so a
    UNC path never makes the OS contact another machine): absolute, rooted, drive/UNC, '..' segments, NUL."""
    if not isinstance(rel, str):
        raise TypeError("paths in the config must be strings")
    if "\x00" in rel or rel.startswith(("/", "\\")) or os.path.isabs(rel) or os.path.splitdrive(rel)[0] or re.match(r"[A-Za-z]:", rel):
        return True
    return ".." in re.split(r"[\\/]+", rel)


def is_link(p):
    """True for a symlink or a directory junction. A Windows reparse point that is not a link (a cloud placeholder) is ordinary."""
    try:
        st = os.lstat(p)
    except (OSError, ValueError):
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    if getattr(st, "st_file_attributes", 0) & 0x400:
        try:
            os.readlink(p)
            return True
        except (OSError, ValueError):
            return False
    return False


class ScanLimit(Exception):
    pass


def _has_magic(seg):
    return re.search(r"[*?\[]", seg) is not None


def walk_glob(base, pattern, deadline, max_scan):
    """Yield paths below `base` matching a relative glob (`*`, `?`, `[..]`, `**`), like glob.glob(recursive=True) except:
    symlinks and junctions are never followed (a matching link is still yielded, but never entered), and every directory
    entry visited counts against `max_scan` and the `deadline` even when nothing matches (ScanLimit). Names starting with
    '.' are matched only by a pattern that starts with '.', and `**` skips them, as glob does."""
    segs = [x for x in re.split(r"[\\/]+", pattern) if x]
    want_dir = bool(pattern) and pattern[-1] in "/\\"
    state = {"n": 0}

    def tick():
        state["n"] += 1
        if state["n"] > max_scan or _now() > deadline:
            raise ScanLimit()

    def entries(d):
        try:
            with os.scandir(d) as it:
                for e in it:
                    tick()
                    yield e
        except (OSError, ValueError):
            return

    def descend_ok(path):
        return os.path.isdir(path) and not is_link(path)

    def rec(d, i):
        if i == len(segs):
            if not want_dir or os.path.isdir(d):
                yield d
            return
        seg = segs[i]
        last = i == len(segs) - 1
        if seg == "**":
            if not last:
                yield from rec(d, i + 1)
            for e in entries(d):
                if e.name.startswith("."):
                    continue
                if last:
                    if not want_dir or e.is_dir():
                        yield e.path
                if e.is_dir(follow_symlinks=False) and not is_link(e.path):
                    yield from rec(e.path, i)
        elif _has_magic(seg):
            for e in entries(d):
                if e.name.startswith(".") and not seg.startswith("."):
                    continue
                if not fnmatch.fnmatch(e.name, seg):
                    continue
                if last:
                    yield from rec(e.path, i + 1)
                elif e.is_dir(follow_symlinks=False) and not is_link(e.path):
                    yield from rec(e.path, i + 1)
        else:
            nxt = os.path.join(d, seg)
            if last:
                if os.path.lexists(nxt):
                    yield from rec(nxt, i + 1)
            elif descend_ok(nxt):
                yield from rec(nxt, i + 1)

    if not os.path.isdir(base):
        return
    yield from rec(base, 0)


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
    deadline = _now() + MAX_SECONDS
    Rr = os.path.realpath(R)

    def inside(p):
        try:
            return os.path.commonpath([Rr, os.path.realpath(p)]) == Rr
        except ValueError:
            return False

    def J(rel):
        """Join a config path to the root; None when it would leave the project root (judged from the text first, so an absolute
        or UNC path is never even looked up, then by real path so links that lead out are caught)."""
        if lexical_outside(rel):
            return None
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
        if lexical_outside(p):
            add("FAIL", "glob " + clean(p), "outside the project root")
            return []
        if p.count("**") > 2:
            add("FAIL", "glob " + clean(p), "too many ** segments (limit 2)")
            return []
        res, seen = [], set()
        try:
            for x in walk_glob(R, p, deadline, MAX_FILES * SCAN_FACTOR):
                if x in seen:
                    continue
                seen.add(x)
                if len(res) >= MAX_FILES:
                    add("FAIL", "glob " + clean(p), "scan limit reached (%d files / %d s); narrow the pattern" % (MAX_FILES, MAX_SECONDS))
                    break
                if inside(x):
                    res.append(x)
        except ScanLimit:
            add("FAIL", "glob " + clean(p), "scan limit reached (%d entries / %d s); narrow the pattern" % (MAX_FILES * SCAN_FACTOR, MAX_SECONDS))
        except OSError as e:
            add("FAIL", "glob " + clean(p), "cannot scan: %s" % clean(e))
        return res

    def first_match(base, pattern):
        """(found, limit_hit): does a relative pattern match anything below base, with the same bounds as g()."""
        try:
            for x in walk_glob(base, pattern, deadline, MAX_FILES * SCAN_FACTOR):
                if inside(x):
                    return True, False
            return False, False
        except ScanLimit:
            return False, True

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
        mname = ep.get("manifest")
        if mname:
            mp = J(mname)
            if mp is None:
                add("FAIL", "manifest " + clean(mname), "outside the project root")
            elif os.path.isfile(mp):
                with open(mp, encoding="utf-8-sig", errors="replace") as fh:
                    man = fh.read(5000000)
        dirs = sorted(x for x in g(ep["glob"]) if os.path.isdir(x) and not os.path.basename(x).startswith("_"))
        if not dirs:
            add("WARN", "items " + clean(ep["glob"]), "no matching folders")
        for d in dirs:
            n = os.path.basename(d)
            miss, outside, limit = [], [], False
            for r in lst(ep.get("require"), "require"):
                if lexical_outside(r):
                    outside.append(r)
                    continue
                found, hit = first_match(d, r)
                limit = limit or hit
                if not found and not hit:
                    miss.append(r)
            problems = []
            if miss:
                problems.append("missing: " + clean(", ".join(miss)))
            if outside:
                problems.append("outside the project root: " + clean(", ".join(outside)))
            if limit:
                problems.append("scan limit reached (%d entries / %d s)" % (MAX_FILES * SCAN_FACTOR, MAX_SECONDS))
            add("FAIL" if problems else "PASS", "item " + clean(n), "; ".join(problems) if problems else "files ok")
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
        state = []
        for x in lst(sf["state"], "state"):
            sp = J(x)
            if sp is None:
                add("FAIL", "state file " + clean(x), "outside the project root")
            elif os.path.isfile(sp):
                state.append(sp)
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
        add("PASS" if age <= n["max_days"] else "WARN", label, "newest %.1f d old (max %s)" % (age, clean(n["max_days"], 20)))

    for sy in cfg.get("sync", []):
        label = clean(sy.get("label", sy["target"]))
        t = J(sy["target"])
        if t is None:
            add("FAIL", label, "target outside the project root")
            continue
        if not os.path.isfile(t):
            add("WARN", label, "target missing")
            continue
        newer = []
        for x in lst(sy["sources"], "sources"):
            xp = J(x)
            if xp is None:
                add("FAIL", label, "source outside the project root: " + clean(x))
            elif os.path.isfile(xp) and mt(xp) > mt(t) + 60:
                newer.append(x)
        add("WARN" if newer else "PASS", label, ("sources newer than target: " + clean(", ".join(newer))) if newer else "in sync")

    fails = sum(1 for l, _, _ in out if l == "FAIL")
    warns = sum(1 for l, _, _ in out if l == "WARN")
    head = "# vitals %s - %s - FAIL %d / WARN %d / total %d" % (clean(os.path.basename(R)), today, fails, warns, len(out))
    # last line of defence: whatever was echoed, one result is exactly one line that starts with its own level tag
    lines = [head] + ["[%s] %s" % (l, clean(n, 300)) + (": " + clean(e, 500) if e else "") for l, n, e in out]
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


def _path_has_link(p):
    """True when any existing component of the absolute path `p` is a symlink or junction."""
    drive, rest = os.path.splitdrive(p)
    cur = drive + os.sep if (drive or p.startswith(os.sep)) else ""
    for part in [x for x in re.split(r"[\\/]+", rest) if x]:
        cur = os.path.join(cur, part) if cur else part
        if os.path.lexists(cur) and is_link(cur):
            return True
    return False


def _is_previous_report(path):
    """True only for a regular file that looks exactly like one of our reports: first line starts with '# vitals ', at most
    REPORT_MAX_LINES lines, every line empty or starting with [PASS], [WARN], [FAIL] or '#'."""
    count = 0
    try:
        with open(path, encoding="utf-8-sig") as fh:
            while True:
                line = fh.readline(REPORT_MAX_LINE_CHARS + 1)
                if not line:
                    break
                count += 1
                if count > REPORT_MAX_LINES or len(line) > REPORT_MAX_LINE_CHARS:
                    return False
                body = line.rstrip("\r\n")
                if count == 1 and not body.startswith("# vitals "):
                    return False
                if body and not body.startswith(_REPORT_PREFIXES):
                    return False
    except (OSError, UnicodeDecodeError, ValueError):
        return False
    return count >= 1


def report_error(report, config_path):
    """None when `report` may be written; otherwise the message to print. Refuses: a path that goes through a link, the config
    (or anything named like it, or an alternate stream of it), and any existing file that is not a previous vitals report."""
    rp = os.path.abspath(report)
    if os.name == "nt" and ":" in os.path.basename(rp):
        return "refusing to write %s: a ':' in the file name (alternate data stream) is not allowed" % rp
    n_rp, n_cfg = os.path.normcase(rp), os.path.normcase(os.path.abspath(config_path))
    named_like_config = os.path.basename(n_rp).startswith("inventory.config.json")
    if n_rp == n_cfg or n_rp.startswith((n_cfg + os.sep, n_cfg + "/", n_cfg + ":")) or named_like_config:
        return "refusing to write %s: it is (or is named like) the project's config file" % rp
    if _path_has_link(rp):
        return "refusing to write %s: the path goes through a link (symlink or junction)" % rp
    if os.path.lexists(rp):
        if not os.path.isfile(rp):
            return "refusing to overwrite %s: it is not a regular file" % rp
        try:
            if os.path.exists(config_path) and os.path.samefile(rp, config_path):
                return "refusing to write %s: it is the project's config file" % rp
        except OSError:
            pass
        if not _is_previous_report(rp):
            return "refusing to overwrite %s: it is not a previous vitals report (choose a new file name)" % rp
    return None


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
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError) as e:
        print("invalid config or data (%s: %s)" % (type(e).__name__, clean(e, 200)), file=sys.stderr)
        return 1
    except OSError as e:
        print("cannot read the config or a project file: %s" % clean(e, 200), file=sys.stderr)
        return 1
    txt = "\n".join(lines)
    print(txt)
    if a.report:
        cfgp = os.path.abspath(a.config) if a.config else os.path.join(os.path.abspath(a.root), DEFAULT_CONFIG)
        err = report_error(a.report, cfgp)
        if err:
            print(err, file=sys.stderr)
            return 1
        rp = os.path.abspath(a.report)
        try:
            with open(rp, "w", encoding="utf-8") as fh:
                fh.write(txt + "\n")
        except OSError as e:
            print("cannot write the report %s: %s" % (rp, clean(e, 200)), file=sys.stderr)
            return 1
    return 2 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
