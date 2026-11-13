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
SCRIPT = os.path.join(HERE, "..", "scripts", "project_inventory.py")
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import project_inventory as pi  # noqa: E402


def w(root, rel, text="x"):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)
    return p


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
            src = w(r, "s.md")
            os.utime(t, (time.time() - 600, time.time() - 600))
            cfg(r, {"sync": [{"target": "t.md", "sources": ["s.md"], "label": "drift"}]})
            lines, fails, warns = pi.run(r)
            self.assertEqual((fails, warns), (0, 1))

    def test_cli_exit_codes_and_missing_config(self):
        with tempfile.TemporaryDirectory() as r:
            p = subprocess.run([sys.executable, "-X", "utf8", SCRIPT, r], capture_output=True, text=True)
            self.assertEqual(p.returncode, 1)
            cfg(r, {"required_files": ["nope"]})
            p = subprocess.run([sys.executable, "-X", "utf8", SCRIPT, r], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(p.returncode, 2)
            cfg(r, {"required_files": []})
            p = subprocess.run([sys.executable, "-X", "utf8", SCRIPT, r], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(p.returncode, 0)

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
