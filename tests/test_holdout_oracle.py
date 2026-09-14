"""Holdout oracle test — compares nodpdf output against expected values
hand-annotated from the official PDFs via an INDEPENDENT extraction
engine (poppler pdftotext). Requires the private corpus; SKIPs on a
clean clone. This is the accuracy oracle for gates G2-03..G2-12 on
holdout data — determinism alone would not prove exactness.
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ownership_radar import nodpdf

MANIFEST = os.path.join(ROOT, "corpus", "manifest.json")
ORACLE = os.path.join(ROOT, "corpus", "oracle", "holdout_expected.json")

def _corpus_present():
    if not (os.path.isfile(MANIFEST) and os.path.isfile(ORACLE)):
        return False
    with open(MANIFEST, encoding="utf-8") as f:
        m = json.load(f)
    return all(os.path.isfile(os.path.join(ROOT, e["file"]))
               for e in m.get("holdout", []))


AVAILABLE = _corpus_present()


@unittest.skipUnless(AVAILABLE, "LOCAL_CNMV_CORPUS_NOT_AVAILABLE")
class TestHoldoutOracle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(ORACLE, encoding="utf-8") as f:
            cls.oracle = json.load(f)["notices"]
        with open(MANIFEST, encoding="utf-8") as f:
            m = json.load(f)
        cls.files = {e["notice_key"]: e["file"] for e in m["holdout"]}
        cls.parsed = {}
        for key, rel in cls.files.items():
            with open(os.path.join(ROOT, rel), "rb") as f:
                cls.parsed[key] = nodpdf.parse_pdf(f.read())

    def test_oracle_covers_all_holdout(self):
        self.assertEqual(set(self.oracle), set(self.files))

    def test_notice_level_fields(self):
        for key, exp in self.oracle.items():
            with self.subTest(key=key):
                p = self.parsed[key]
                self.assertEqual(p["parse_status"], nodpdf.PARSED)
                self.assertEqual(p["notifying_party_name_raw"], exp["party"])
                self.assertEqual(p["closely_associated"], exp["ca"])
                self.assertEqual(p["notification_kind"], exp["kind"])
                self.assertEqual(p["issuer_name_document"], exp["issuer"])
                self.assertEqual(p["issuer_lei_document"], exp["lei"])
                if exp.get("related_name"):
                    self.assertEqual(p["related_pdmr_name_raw"],
                                     exp["related_name"])
                    self.assertEqual(p["related_pdmr_position_raw"],
                                     exp["related_pos"])

    def test_events_and_executions_exact(self):
        for key, exp in self.oracle.items():
            with self.subTest(key=key):
                evs = self.parsed[key]["events"]
                self.assertEqual(len(evs), len(exp["events"]))
                for ev, ee in zip(evs, exp["events"]):
                    self.assertEqual(ev["instrument_code_raw"], ee["code"])
                    self.assertEqual(ev["instrument_type_raw"], ee["itype"])
                    self.assertEqual(ev["transaction_nature_raw"],
                                     ee["nature"])
                    self.assertEqual(ev["transaction_date"], ee["date"])
                    self.assertEqual(ev["venue_raw"], ee["venue"])
                    self.assertEqual(
                        [[e["volume_raw"], e["price_raw"], e["currency"]]
                         for e in ev["executions"]], ee["execs"])
                    self.assertEqual(
                        [ev["declared_aggregate_volume"],
                         ev["declared_aggregate_price"]], ee["agg"])
                    self.assertEqual(ev["aggregate_qa"], "MATCH")


if __name__ == "__main__":
    unittest.main()
