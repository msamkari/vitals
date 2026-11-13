# -*- coding: utf-8 -*-
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "vitals.py")
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import vitals as pi  # noqa: E402


def w(root, rel, text="x"):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)
    return p


def slurp(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def cfg(root, d):
    w(root, "Jobs/inventory.config.json", json.dumps(d))


class T(unittest.TestCase):
    def test_required_pass_and_fail(self):
        with tempfile.TemporaryDirectory() as r:
            w(r, "a.md")
            cfg(r, {"required_files": ["a.md", "missing.md"]})
            lines, fails, _ = pi.run(r)
            self.assertEqual(fails, 1)
            self.assertIn("[PASS] required: a.md", lines)
            self.assertIn("[FAIL] required: missing.md", lines)

    def test_items_contract_and_legacy_alias(self):
        with tempfile.TemporaryDirectory() as r:
            w(r, "items/one/facts.json", "{}")
            w(r, "items/one/draft_v1.md")
            w(r, "items/two/facts.json", "{}")
            for key in ("items", "episodes"):
                cfg(r, {key: {"glob": "items/*", "require": ["facts.json", "draft_v*.md"]}})
                lines, fails, _ = pi.run(r)
                self.assertEqual(fails, 1)
                self.assertTrue(any("item two" in l and "FAIL" in l for l in lines))

    def test_facts_expiry(self):
        with tempfile.TemporaryDirectory() as r:
            today = dt.date(2026, 1, 10)
            facts = {"facts": [
                {"id": "old", "date_verified": "2025-01-01", "expires_after_days": 30},
                {"id": "soon", "date_verified": "2026-01-05", "expires_after_days": 7},
                {"id": "ok", "date_verified": "2026-01-09", "expires_after_days": 100}]}
            w(r, "f/facts.json", json.dumps(facts))
            cfg(r, {"facts_files": "f/facts.json"})
            lines, fails, warns = pi.run(r, today=today)
            self.assertEqual(fails, 1)
            self.assertTrue(any("old expired" in l for l in lines))
            self.assertTrue(any("soon ->" in l for l in lines))
            self.assertEqual(warns, 0)

    def test_state_fresher_than_work(self):
        with tempfile.TemporaryDirectory() as r:
            s = w(r, "state.md")
            k = w(r, "work.md")
            old = time.time() - 3600
            os.utime(s, (old, old))
            cfg(r, {"state_fresh": {"state": ["state.md"], "work": ["work.md"], "grace_minutes": 5}})
            _, fails, _ = pi.run(r)
            self.assertEqual(fails, 1)
            os.utime(s, None)
            _, fails, _ = pi.run(r)
            self.assertEqual(fails, 0)

    def test_sync_drift_warns_only(self):
        with tempfile.TemporaryDirectory() as r:
            t = w(r, "t.md")
            w(r, "s.md")
            os.utime(t, (time.time() - 600, time.time() - 600))
            cfg(r, {"sync": [{"target": "t.md", "sources": ["s.md"], "label": "drift"}]})
            lines, fails, warns = pi.run(r)
            self.assertEqual((fails, warns), (0, 1))

    def test_cli_exit_codes_and_missing_config(self):
        with tempfile.TemporaryDirectory() as r:
            p = subprocess.run([sys.executable, "-X", "utf8", SCRIPT, r], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(p.returncode, 1)
            self.assertIn("config not found", p.stderr)
            cfg(r, {"required_files": ["nope"]})
            p = subprocess.run([sys.executable, "-X", "utf8", SCRIPT, r], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(p.returncode, 2)
            cfg(r, {"required_files": []})
            p = subprocess.run([sys.executable, "-X", "utf8", SCRIPT, r], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(p.returncode, 0)

    def test_skips_are_warnings_not_silent_passes(self):
        with tempfile.TemporaryDirectory() as r:
            cfg(r, {"items": {"glob": "none/*"}, "state_fresh": {"state": ["a"], "work": ["b"]}})
            _, fails, warns = pi.run(r)
            self.assertEqual((fails, warns), (0, 2))

    def test_newest_age_and_manifest_warn(self):
        with tempfile.TemporaryDirectory() as r:
            old = w(r, "rep/a.md")
            os.utime(old, (time.time() - 20 * 86400, time.time() - 20 * 86400))
            w(r, "items/one/x.md")
            w(r, "m.json", "{}")
            cfg(r, {"newest_age": [{"glob": "rep/*.md", "max_days": 7, "label": "rep"}],
                    "items": {"glob": "items/*", "require": ["x.md"], "manifest": "m.json"}})
            _, fails, warns = pi.run(r)
            self.assertEqual((fails, warns), (0, 2))

    def test_report_config_and_errors(self):
        def cli(*args):
            return subprocess.run([sys.executable, "-X", "utf8", SCRIPT] + list(args), capture_output=True, text=True, encoding="utf-8")
        with tempfile.TemporaryDirectory() as r:
            w(r, "a.md")
            alt = w(r, "alt.json", json.dumps({"required_files": ["a.md"]}))
            rep = os.path.join(r, "out.txt")
            self.assertEqual(cli(r, "--config", alt, "--report", rep, "--today", "2026-01-01").returncode, 0)
            self.assertTrue(os.path.isfile(rep))
            bad = w(r, "bad.json", "{not json")
            p = cli(r, "--config", bad)
            self.assertEqual(p.returncode, 1)
            self.assertIn("invalid config", p.stderr)
            self.assertEqual(cli(r, "--config", alt, "--today", "nope").returncode, 1)

    def test_init_proposes_then_writes_never_overwrites(self):
        def cli(*args):
            return subprocess.run([sys.executable, "-X", "utf8", SCRIPT] + list(args), capture_output=True, text=True, encoding="utf-8")
        with tempfile.TemporaryDirectory() as r:
            w(r, "CLAUDE.md")
            w(r, "MDs/HANDOVER.md")
            w(r, "Jobs/series_log.md")
            p = cli(r, "--init")
            self.assertEqual(p.returncode, 0)
            self.assertIn("nothing written", p.stdout)
            self.assertFalse(os.path.exists(os.path.join(r, "Jobs", "inventory.config.json")))
            p = cli(r, "--init", "--write")
            self.assertEqual(p.returncode, 0)
            with open(os.path.join(r, "Jobs", "inventory.config.json"), encoding="utf-8") as fh:
                c = json.load(fh)
            self.assertEqual(c["required_files"], ["CLAUDE.md", "MDs/HANDOVER.md", "Jobs/series_log.md"])
            self.assertEqual(c["state_fresh"]["state"], ["MDs/HANDOVER.md"])
            self.assertEqual(cli(r).returncode, 0)  # generated config is valid and passes
            before = slurp(os.path.join(r, "Jobs", "inventory.config.json"))
            p = cli(r, "--init", "--write")
            self.assertEqual(p.returncode, 1)
            self.assertIn("not overwritten", p.stderr)
            self.assertEqual(before, slurp(os.path.join(r, "Jobs", "inventory.config.json")))

    def test_init_empty_project_and_write_without_init(self):
        def cli(*args):
            return subprocess.run([sys.executable, "-X", "utf8", SCRIPT] + list(args), capture_output=True, text=True, encoding="utf-8")
        with tempfile.TemporaryDirectory() as r:
            self.assertEqual(cli(r, "--init", "--write").returncode, 1)
            self.assertFalse(os.path.exists(os.path.join(r, "Jobs")))
            self.assertEqual(cli(r, "--write").returncode, 1)

    def test_init_jobs_glob_fallback(self):
        with tempfile.TemporaryDirectory() as r:
            w(r, "HANDOVER.md")
            w(r, "Jobs/2026_notes.md")
            c = pi.detect_config(r)
            self.assertEqual(c["state_fresh"]["work"], ["Jobs/*.md"])

    def test_init_edge_cases(self):
        def cli(*args):
            return subprocess.run([sys.executable, "-X", "utf8", SCRIPT] + list(args), capture_output=True, text=True, encoding="utf-8")
        with tempfile.TemporaryDirectory() as r:
            p = cli(os.path.join(r, "nope"), "--init")
            self.assertEqual(p.returncode, 1)
            self.assertIn("root not found", p.stderr)
            w(r, "CLAUDE.md")
            w(r, "Jobs", "i am a file")  # Jobs is a file, not a folder
            p = cli(r, "--init", "--write")
            self.assertEqual(p.returncode, 1)
            self.assertNotIn("Traceback", p.stderr)
            self.assertEqual(slurp(os.path.join(r, "Jobs")), "i am a file")
        with tempfile.TemporaryDirectory() as r:
            w(r, "CLAUDE.md")
            os.makedirs(os.path.join(r, "Jobs", "inventory.config.json"))  # target is a directory
            p = cli(r, "--init")
            self.assertEqual(p.returncode, 1)
            self.assertIn("not a regular file", p.stderr)
            self.assertEqual(cli(r, "--init", "--config", "x.json").returncode, 1)
            self.assertEqual(cli(r, "--init", "--report", "x.txt").returncode, 1)

    def test_init_existing_config_without_write_exits_1(self):
        with tempfile.TemporaryDirectory() as r:
            w(r, "CLAUDE.md")
            cfg(r, {"required_files": []})
            code, msg = pi.init_config(r, write=False)
            self.assertEqual(code, 1)
            self.assertIn("already exists", msg)

    def test_detect_config_never_opens_files(self):
        import builtins
        with tempfile.TemporaryDirectory() as r:
            w(r, "CLAUDE.md")
            w(r, "MDs/HANDOVER.md")
            w(r, "Jobs/series_log.md")
            real = builtins.open

            def boom(*a, **k):
                raise AssertionError("open() called during detect_config")
            builtins.open = boom
            try:
                c = pi.detect_config(r)
            finally:
                builtins.open = real
            self.assertIn("state_fresh", c)

    def test_generated_config_fails_when_work_is_newer_than_state(self):
        with tempfile.TemporaryDirectory() as r:
            h = w(r, "HANDOVER.md")
            w(r, "CHANGELOG.md")
            os.utime(h, (time.time() - 3600, time.time() - 3600))
            self.assertEqual(pi.init_config(r, write=True)[0], 0)
            _, fails, _ = pi.run(r)
            self.assertEqual(fails, 1)

    def test_arabic_paths_and_example_config_parses(self):
        with tempfile.TemporaryDirectory() as r:
            w(r, "ملف.md")
            cfg(r, {"required_files": ["ملف.md"]})
            self.assertEqual(pi.run(r)[1], 0)
        ex = os.path.join(HERE, "..", "examples", "inventory.config.example.json")
        with open(ex, encoding="utf-8") as fh:
            json.load(fh)


if __name__ == "__main__":
    unittest.main()
