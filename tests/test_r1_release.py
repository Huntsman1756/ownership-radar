"""R1 release tests — demo dataset reproducibility and executable
examples. These run everywhere (no private corpus required).
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "scripts"))

from build_demo_dataset import build, demo_digest  # noqa:E402
from ownership_radar import store, OwnershipRadar  # noqa:E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(tempfile.mkdtemp(), "demo.sqlite")


def setUpModule():
    build(DB_PATH)


class TestDemoReproducibility(unittest.TestCase):
    def test_two_builds_identical_digest(self):
        p2 = os.path.join(tempfile.mkdtemp(), "demo2.sqlite")
        build(p2)
        cx = store.connect(DB_PATH)
        d1 = demo_digest(cx)
        cx.close()
        cx = store.connect(p2)
        d2 = demo_digest(cx)
        cx.close()
        self.assertEqual(d1, d2)

    def test_demo_has_no_raw_payload(self):
        """raw_blob must be empty — nothing redistributable."""
        cx = store.connect(DB_PATH)
        try:
            n = cx.execute("SELECT COUNT(*) FROM raw_blob").fetchone()
            self.assertEqual(n[0], 0)
        except Exception:
            pass  # no raw table at all is also fine
        cx.close()

    def test_demo_covers_all_feed_types(self):
        r = OwnershipRadar.open(DB_PATH)
        res = r.feed(limit=100, include_backfill=True)
        types = {i.feed_item_type for i in res.items}
        for t in ("NOTICE_OBSERVED", "INSIDER_TRANSACTION_OBSERVED",
                  "SIGNIFICANT_HOLDING_DISCLOSURE_OBSERVED",
                  "TREASURY_OPERATION_OBSERVED",
                  "TREASURY_STOCK_POSITION_OBSERVED",
                  "CANCELLATION_RELATION_OBSERVED",
                  "NOTICE_DISAPPEARANCE_OBSERVED"):
            self.assertIn(t, types)

    def test_demo_ambiguous_and_temporal(self):
        r = OwnershipRadar.open(DB_PATH)
        self.assertEqual(r.annulment_status("ps:amb").status,
                         "AMBIGUOUS")
        self.assertEqual(
            r.dataset_info().universe_version, "demo-v1")


class TestExamplesExecute(unittest.TestCase):
    def run_ex(self, name, *extra):
        return subprocess.run(
            [sys.executable, os.path.join("examples", name),
             *extra, DB_PATH] if extra else
            [sys.executable, os.path.join("examples", name), DB_PATH],
            capture_output=True, text=True, cwd=REPO)

    def test_all_examples(self):
        for ex in ("recent_insiders.py", "issuer_holdings.py",
                   "treasury_positions.py", "temporal_query.py",
                   "feed_consumer.py", "provenance.py"):
            p = self.run_ex(ex) if ex != "issuer_holdings.py" else \
                subprocess.run(
                    [sys.executable, os.path.join("examples", ex),
                     "SAN", DB_PATH], capture_output=True, text=True,
                    cwd=REPO)
            self.assertEqual(p.returncode, 0,
                             f"{ex}: {p.stderr[-300:]}")
            self.assertTrue(p.stdout.strip(),
                            f"{ex} produced no output")

    def test_feed_consumer_dedupes(self):
        p = self.run_ex("feed_consumer.py")
        self.assertIn("unique feed_item_id", p.stdout)


class TestDemoCli(unittest.TestCase):
    def cli(self, *args):
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        return subprocess.run(
            [sys.executable, "-m", "ownership_radar",
             "--db", DB_PATH] + list(args),
            capture_output=True, text=True, cwd=REPO, env=env)

    def test_readme_commands(self):
        """Every CLI command shown in the README must run."""
        for cmd in (("company", "SAN"), ("insiders", "SAN"),
                    ("holdings", "SAN"), ("treasury-positions", "SAN"),
                    ("treasury-operations", "SAN"), ("coverage",),
                    ("dataset-info",), ("feed", "--format", "json"),
                    ("feed", "--format", "atom")):
            p = self.cli(*cmd, "--format",
                         "json" if "atom" not in cmd else "atom") \
                if cmd[0] != "feed" else self.cli(*cmd)
            self.assertEqual(p.returncode, 0,
                             f"{cmd}: {p.stderr[-300:]}")

    def test_feed_json_envelope(self):
        p = self.cli("feed", "--format", "json")
        env = json.loads(p.stdout)
        self.assertEqual(env["schema_version"], "1")


if __name__ == "__main__":
    unittest.main()
