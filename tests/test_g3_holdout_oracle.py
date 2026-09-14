"""G3 holdout oracle — parser output vs independently annotated
expectations (Poppler pdftotext, manual). Skips cleanly without the
private corpus; the oracle file itself IS redistributed."""
import json
import os
import sys
import unittest
import warnings
import logging

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ownership_radar import pspdf, acpdf  # noqa: E402

ORACLE = os.path.join(ROOT, "corpus", "oracle",
                      "g3_holdout_expected.json")
G3 = os.path.join(ROOT, "corpus", "g3")

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)


def _load():
    with open(ORACLE, encoding="utf-8") as f:
        return json.load(f)


def _pdf(split_dir, stem):
    p = os.path.join(G3, split_dir, stem + ".pdf")
    return open(p, "rb").read() if os.path.isfile(p) else None


def _available():
    o = _load()
    return all(_pdf("ps_holdout", k) for k in o["ps"]) and \
        all(_pdf("ac_holdout", k) for k in o["ac"])


CORPUS_AVAILABLE = _available() if os.path.isfile(ORACLE) else False
SKIP_MSG = "LOCAL_CNMV_CORPUS_NOT_AVAILABLE"


@unittest.skipUnless(CORPUS_AVAILABLE, SKIP_MSG)
class TestPsHoldoutOracle(unittest.TestCase):
    """Field-level comparison: pspdf vs Poppler-annotated oracle."""

    def test_all_ps_holdout(self):
        mismatches = []
        for stem, exp in _load()["ps"].items():
            p = pspdf.parse_pdf(_pdf("ps_holdout", stem))
            got = {
                "template": p["regulatory_template"],
                "obliged_subject": p["obliged_subject_name_raw"],
                "residence": p["obliged_subject_residence_raw"],
                "threshold_date": p["threshold_date_raw"],
                "cur_pct_shares":
                    (p["position_current"] or {}).get("pct_shares_raw"),
                "cur_pct_instr":
                    (p["position_current"] or {}).get("pct_instruments_raw"),
                "cur_pct_total":
                    (p["position_current"] or {}).get("pct_total_raw"),
                "issuer_total_vr": p["issuer_total_voting_rights_raw"],
                "prev_pct_shares":
                    (p["position_previous"] or {}).get("pct_shares_raw"),
                "prev_pct_instr":
                    (p["position_previous"] or {}).get(
                        "pct_instruments_raw"),
                "prev_pct_total":
                    (p["position_previous"] or {}).get("pct_total_raw"),
                "rows_7a": len(p["shares_rows"]),
                "rows_7b1": len(p["instruments_a_rows"]),
                "rows_7b2": len(p["instruments_b_rows"]),
            }
            for k, v in exp.items():
                if k == "reason_other_text_contains":
                    if v not in (p.get("reason_other_text_raw") or ""):
                        mismatches.append((stem, k, v,
                                           p.get("reason_other_text_raw")))
                elif k == "b2_first_type_contains":
                    t = (p["instruments_b_rows"][0]
                         .get("instrument_type_raw") or "") \
                        if p["instruments_b_rows"] else ""
                    if v not in t:
                        mismatches.append((stem, k, v, t))
                elif got.get(k) != v:
                    mismatches.append((stem, k, v, got.get(k)))
        self.assertEqual(mismatches, [])


@unittest.skipUnless(CORPUS_AVAILABLE, SKIP_MSG)
class TestAcHoldoutOracle(unittest.TestCase):
    """Field-level comparison: acpdf vs Poppler-annotated oracle."""

    def test_all_ac_holdout(self):
        mismatches = []
        for stem, exp in _load()["ac"].items():
            p = acpdf.parse_pdf(_pdf("ac_holdout", stem))
            ta = p.get("total_acquisitions") or {}
            tt = p.get("total_transmissions") or {}
            fp = p.get("final_position") or {}
            got = {
                "template": p["regulatory_template"],
                "notification_date": p["notification_date_raw"],
                "issuer_voting_rights": p["issuer_voting_rights_raw"],
                "op_count": len(p["operations"]),
                "tot_acq_vr_direct": ta.get("vr_direct_raw"),
                "tot_acq_vr_indirect": ta.get("vr_indirect_raw"),
                "tot_acq_pct_direct": ta.get("pct_direct_raw"),
                "tot_acq_pct_indirect": ta.get("pct_indirect_raw"),
                "tot_tr_vr_direct": tt.get("vr_direct_raw"),
                "tot_tr_vr_indirect": tt.get("vr_indirect_raw"),
                "tot_tr_pct_direct": tt.get("pct_direct_raw"),
                "tot_tr_pct_indirect": tt.get("pct_indirect_raw"),
                "final_total_vr": fp.get("vr_total_raw"),
                "final_pct_total": fp.get("pct_total_raw"),
            }
            for k, v in exp.items():
                if got.get(k) != v:
                    mismatches.append((stem, k, v, got.get(k)))
        self.assertEqual(mismatches, [])


if __name__ == "__main__":
    unittest.main()
