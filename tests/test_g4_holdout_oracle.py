"""G4 holdout oracle — ledger events vs hand-annotated expectations.

Expectations (corpus/oracle/g4_holdout_expected.json) were written
from the declared semantic rows and G1 notice_relations, independent
of the event builder. Skips cleanly without the local corpus DB.
"""
import json
import os
import sqlite3
import sys
import unittest
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ownership_radar import ledger, store  # noqa: E402

DB = os.path.join(ROOT, "corpus", "corpus.sqlite")
ORACLE = os.path.join(ROOT, "corpus", "oracle",
                      "g4_holdout_expected.json")
CORPUS_AVAILABLE = os.path.isfile(DB) and os.path.isfile(ORACLE) and \
    os.path.isdir(os.path.join(ROOT, "corpus", "g3"))


@unittest.skipUnless(CORPUS_AVAILABLE,
                     "LOCAL_CNMV_CORPUS_NOT_AVAILABLE")
class TestG4HoldoutOracle(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.cx = store.init_db(DB)
        ledger.materialize(cls.cx)

    def test_event_expectations(self):
        exp = json.load(open(ORACLE, encoding="utf-8"))
        mism = []
        for nk, want in exp["notices"].items():
            rows = self.cx.execute(
                "SELECT event_type,effective_date,payload_json FROM "
                "ledger_event WHERE source_notice_key=?",
                (nk,)).fetchall()
            got = Counter(r[0] for r in rows)
            for k, v in want.items():
                if k in ("effective_dates",
                         "position_effective_date",
                         "disclosure_subject", "annulled_by",
                         "annuls"):
                    continue
                if got.get(k, 0) != v:
                    mism.append((nk, k, v, got.get(k, 0)))
            if "effective_dates" in want:
                eds = sorted(r[1] for r in rows
                             if not r[0].startswith("NOTICE_"))
                if eds != sorted(want["effective_dates"]):
                    mism.append((nk, "effective_dates",
                                 want["effective_dates"], eds))
            if "position_effective_date" in want:
                p = [r[1] for r in rows if r[0] ==
                     "TREASURY_STOCK_POSITION_DISCLOSED"]
                if p != [want["position_effective_date"]]:
                    mism.append((nk, "position_effective_date",
                                 want["position_effective_date"], p))
            if "disclosure_subject" in want:
                p = [json.loads(r[2])["subject"] for r in rows
                     if r[0] ==
                     "SIGNIFICANT_HOLDING_POSITION_DISCLOSED"]
                if p != [want["disclosure_subject"]]:
                    mism.append((nk, "disclosure_subject",
                                 want["disclosure_subject"], p))
        self.assertEqual(mism, [])

    def test_chains(self):
        exp = json.load(open(ORACLE, encoding="utf-8"))
        term, errs = ledger.resolve_annulment_chains(self.cx)
        self.assertEqual(errs, [])
        self.assertEqual(term["ps:2020135555"], "ps:2021016444")
        self.assertEqual(term["ps:2021012946"], "ps:2021016444")
        self.assertEqual(term["ps:2021016415"], "ps:2021016444")
        self.assertEqual(term["ac:2025093199"], "ac:2025116464")
        # cancelled-with-facts notice still exposes its history
        n = self.cx.execute(
            "SELECT COUNT(*) FROM source_fact WHERE notice_key="
            "'ac:2025093199'").fetchone()[0]
        self.assertEqual(n, 26)
        # and its cancellation event exists
        self.assertEqual(self.cx.execute(
            "SELECT COUNT(*) FROM ledger_event WHERE "
            "source_notice_key='ac:2025093199' AND event_type="
            "'NOTICE_CANCELLED'").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
