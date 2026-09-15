"""G4 ledger tests — synthetic semantic rows + controlled observation
times. No real CNMV documents, no PDF dependency.

Covers the mandatory temporal scenarios (late observation,
cancellation, three-hop chains, rebuild), the source/derived
separation and identity determinism.
"""
import copy
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ownership_radar import ledger, store, pspdf, acpdf, nodpdf  # noqa
from test_g3_invariants import PS_DOC, AC_DOC  # noqa

T0 = "2026-01-01T00:00:00+00:00"
T1 = "2026-02-01T00:00:00+00:00"
T2 = "2026-03-01T00:00:00+00:00"


def _notice(cx, key, issuer, surface="ps", filing="2024-03-13"):
    cx.execute(
        "INSERT OR IGNORE INTO notice(notice_key,source_surface,"
        "source_registration_number,notice_type,issuer_id,"
        "filing_date,notice_status) VALUES(?,?,?,?,?,?,?)",
        (key, surface, key.split(":")[1],
         {"ps": "UNCLASSIFIED", "ac": "TREASURY_STOCK",
          "nod": "PDMR_NOTIFICATION"}[surface],
         issuer, filing, "ACTIVE"))


def _obs(cx, key, at, sha=None):
    cx.execute(
        "INSERT INTO notice_observation(run_id,notice_key,"
        "observed_at,raw_sha256,status_observed,present_in_source) "
        "VALUES('t',?,?,?,?,1)", (key, at, sha or "raw" + key,
                                 "ACTIVE"))


def _ps(cx, key, issuer="SAN", at=T0, filing="2024-03-13", doc=None):
    _notice(cx, key, issuer, "ps", filing)
    _obs(cx, key, at)
    store.store_ps_semantic(cx, key, pspdf.parse_lines(doc or PS_DOC()))


def _ac(cx, key, issuer="SAN", at=T0, filing="2021-04-01", doc=None):
    _notice(cx, key, issuer, "ac", filing)
    _obs(cx, key, at)
    store.store_ac_semantic(cx, key, acpdf.parse_lines(doc or AC_DOC()))


def _nod(cx, key, issuer="SAN", at=T0, nature="Compra",
         filing="2024-03-13"):
    from test_nod_parser import doc as nod_doc
    _notice(cx, key, issuer, "nod", filing)
    _obs(cx, key, at)
    r = nodpdf.parse_lines(nod_doc([
        ["ES0000000001", "Acción", nature, "10/03/2024", "XMAD",
         "100,00", "10,50", "EUR"]],
        tail=[["100,00", "10,50"]]))
    store.store_semantic(cx, key, r)


def _db():
    d = tempfile.mkdtemp()
    return store.init_db(os.path.join(d, "t.sqlite"))


class TestSourceFacts(unittest.TestCase):

    def test_fact_identity_deterministic(self):
        cx = _db()
        _ps(cx, "ps:1")
        ledger.materialize(cx)
        ids1 = [r[0] for r in cx.execute(
            "SELECT fact_id FROM source_fact")]
        ledger.materialize(cx)
        ids2 = [r[0] for r in cx.execute(
            "SELECT fact_id FROM source_fact")]
        self.assertEqual(sorted(ids1), sorted(ids2))
        # material change -> different fact_id
        doc = PS_DOC(pct_total="9,999")
        _ps(cx, "ps:1b", doc=doc)
        ledger.materialize(cx)
        f1 = cx.execute("SELECT fact_id FROM source_fact WHERE "
                        "notice_key='ps:1'").fetchone()[0]
        f2 = cx.execute("SELECT fact_id FROM source_fact WHERE "
                        "notice_key='ps:1b'").fetchone()[0]
        self.assertNotEqual(f1, f2)
        self.assertIn(f1, ids1)

    def test_duplicate_rows_get_stable_ids(self):
        # two byte-identical AC ops in one notice: dup_index splits
        # them; order in storage never matters
        cx = _db()
        doc = AC_DOC()
        doc[0].insert(19, copy.deepcopy(doc[0][18]))
        _ac(cx, "ac:dup", doc=doc)
        ledger.materialize(cx)
        n = cx.execute("SELECT COUNT(*) FROM source_fact WHERE "
                       "notice_key='ac:dup' AND fact_type="
                       "'TREASURY_OPERATION'").fetchone()[0]
        self.assertEqual(n, 3)


class TestEvents(unittest.TestCase):

    def test_nod_nature_mapping_exact(self):
        cx = _db()
        _nod(cx, "nod:buy", nature="Compra")
        _nod(cx, "nod:sell", nature="Venta")
        _nod(cx, "nod:gift", nature="Donación")
        ledger.materialize(cx)
        got = {r[0]: r[1] for r in cx.execute(
            "SELECT source_notice_key,event_type FROM ledger_event "
            "WHERE event_type LIKE 'INSIDER_%'")}
        self.assertEqual(got["nod:buy"], "INSIDER_ACQUISITION")
        self.assertEqual(got["nod:sell"], "INSIDER_DISPOSAL")
        self.assertEqual(got["nod:gift"], "INSIDER_TRANSACTION_OTHER")
        # raw nature preserved inside payload
        p = cx.execute("SELECT payload_json FROM ledger_event WHERE "
                       "source_notice_key='nod:gift' AND event_type="
                       "'INSIDER_TRANSACTION_OTHER'").fetchone()[0]
        import json
        self.assertEqual(json.loads(p)["instrument"]
                         ["transaction_nature_raw"], "Donación")

    def test_ps_never_emits_trade_events(self):
        cx = _db()
        _ps(cx, "ps:1")
        ledger.materialize(cx)
        types = [r[0] for r in cx.execute(
            "SELECT event_type FROM ledger_event")]
        self.assertIn("SIGNIFICANT_HOLDING_POSITION_DISCLOSED", types)
        for t in types:
            self.assertNotIn("BUY", t)
            self.assertNotIn("SELL", t)

    def test_ps_position_change_is_not_buy_sell(self):
        # Scenario E: two different positions -> two disclosures,
        # zero transaction-type events
        cx = _db()
        _ps(cx, "ps:1", at=T0)
        _ps(cx, "ps:2", at=T1, doc=PS_DOC(pct_total="6,000"))
        ledger.materialize(cx)
        n = cx.execute("SELECT COUNT(*) FROM ledger_event WHERE "
                       "event_type='SIGNIFICANT_HOLDING_"
                       "POSITION_DISCLOSED'").fetchone()[0]
        self.assertEqual(n, 2)
        bad = cx.execute("SELECT COUNT(*) FROM ledger_event WHERE "
                         "event_type LIKE '%BUY%' OR event_type LIKE "
                         "'%SELL%' OR event_type LIKE '%THRESHOLD%'") \
            .fetchone()[0]
        self.assertEqual(bad, 0)

    def test_ac_flow_and_position_distinct(self):
        # Scenario F: 2 ops + 1 position -> never summed together
        cx = _db()
        _ac(cx, "ac:1")
        ledger.materialize(cx)
        ops = cx.execute("SELECT COUNT(*) FROM ledger_event WHERE "
                         "event_type='TREASURY_OPERATION_REPORTED'") \
            .fetchone()[0]
        pos = cx.execute("SELECT COUNT(*) FROM ledger_event WHERE "
                         "event_type='TREASURY_STOCK_POSITION_"
                         "DISCLOSED'").fetchone()[0]
        self.assertEqual((ops, pos), (2, 1))

    def test_event_basis_always_explicit(self):
        cx = _db()
        _ps(cx, "ps:1"); _ac(cx, "ac:1"); _nod(cx, "nod:1")
        ledger.materialize(cx)
        bad = cx.execute(
            "SELECT COUNT(*) FROM ledger_event WHERE event_basis NOT "
            "IN ('SOURCE_DECLARED','DETERMINISTIC_DERIVATION')") \
            .fetchone()[0]
        self.assertEqual(bad, 0)
        # every derived event names its rule
        orphans = cx.execute(
            "SELECT COUNT(*) FROM ledger_event e LEFT JOIN "
            "derivation_rule r ON e.rule_id=r.rule_id "
            "WHERE r.rule_id IS NULL").fetchone()[0]
        self.assertEqual(orphans, 0)

    def test_event_identity_deterministic(self):
        cx = _db()
        _ps(cx, "ps:1")
        ledger.materialize(cx)
        e1 = [r[0] for r in cx.execute("SELECT event_id FROM "
                                       "ledger_event")]
        ledger.materialize(cx)
        e2 = [r[0] for r in cx.execute("SELECT event_id FROM "
                                       "ledger_event")]
        self.assertEqual(sorted(e1), sorted(e2))


class TestTemporalSemantics(unittest.TestCase):

    def test_scenario_a_late_observation(self):
        # effective 2024, observed 2026: AS_KNOWN_AT(2024) knows
        # nothing; reconstructed history does
        cx = _db()
        _nod(cx, "nod:late", at="2026-09-14T00:00:00+00:00")
        ledger.materialize(cx)
        r = ledger.events_for_issuer(
            cx, "SAN", mode="AS_KNOWN_AT", known_at="2024-03-15")
        self.assertEqual(r["status"], ledger.NO_OBSERVATION_HISTORY)
        self.assertEqual(r["events"], [])
        r2 = ledger.events_for_issuer(
            cx, "SAN", effective_at="2024-03-15")
        self.assertTrue(any(e["event_type"] == "INSIDER_ACQUISITION"
                            for e in r2["events"]))
        # known after observation -> visible
        r3 = ledger.events_for_issuer(
            cx, "SAN", mode="AS_KNOWN_AT",
            known_at="2026-10-01T00:00:00+00:00")
        self.assertTrue(any(e["event_type"] == "INSIDER_ACQUISITION"
                            for e in r3["events"]))

    def test_scenario_b_cancellation(self):
        cx = _db()
        _ps(cx, "ps:A", at=T0)
        _ps(cx, "ps:B", at=T1)
        cx.execute("INSERT INTO notice_relation VALUES(?,?,?,?,?,?)",
                   ("ps:B", "ps:A", "ANNULS", "ev", "t", "s"))
        cx.commit()
        ledger.materialize(cx)
        self.assertEqual(ledger.status_as_known_at(cx, "ps:A", T0),
                         "ACTIVE")
        self.assertEqual(ledger.status_as_known_at(cx, "ps:A", T2),
                         "CANCELLED")
        # historical fact A still exists and is queryable
        n = cx.execute("SELECT COUNT(*) FROM source_fact WHERE "
                       "notice_key='ps:A'").fetchone()[0]
        self.assertEqual(n, 1)
        # NOTICE_CANCELLED event emitted for A
        ev = cx.execute("SELECT event_type,effective_date FROM "
                        "ledger_event WHERE source_notice_key='ps:A' "
                        "AND event_type='NOTICE_CANCELLED'").fetchone()
        self.assertIsNotNone(ev)

    def test_scenario_c_three_hop_chain(self):
        cx = _db()
        for k, at in (("ps:A", T0), ("ps:B", T1), ("ps:C", T2)):
            _ps(cx, k, at=at)
        for a, b in (("ps:B", "ps:A"), ("ps:C", "ps:B")):
            cx.execute("INSERT INTO notice_relation "
                       "VALUES(?,?,?,?,?,?)", (a, b, "ANNULS",
                                              "e", "t", "s"))
        cx.commit()
        ledger.materialize(cx)
        term, errs = ledger.resolve_annulment_chains(cx)
        self.assertEqual(errs, [])
        self.assertEqual(term["ps:A"], "ps:C")
        self.assertEqual(term["ps:B"], "ps:C")
        st = ledger.state_for_issuer(cx, "SAN")
        keys = [h["notice_key"] for h in st["significant_holdings"]]
        self.assertEqual(keys, ["ps:C"])

    def test_cycle_is_error_not_silent(self):
        cx = _db()
        _ps(cx, "ps:A"); _ps(cx, "ps:B")
        for a, b in (("ps:B", "ps:A"), ("ps:A", "ps:B")):
            cx.execute("INSERT INTO notice_relation "
                       "VALUES(?,?,?,?,?,?)", (a, b, "ANNULS",
                                              "e", "t", "s"))
        cx.commit()
        ledger.materialize(cx)
        term, errs = ledger.resolve_annulment_chains(cx)
        self.assertTrue(errs)
        self.assertEqual(errs[0]["error"],
                         ledger.RELATION_GRAPH_ERROR)

    def test_scenario_d_rebuild_identical(self):
        cx = _db()
        _ps(cx, "ps:1"); _ac(cx, "ac:1"); _nod(cx, "nod:1")
        ledger.materialize(cx)
        d1 = ledger.ledger_digest(cx)
        ledger.materialize(cx)
        d2 = ledger.ledger_digest(cx)
        self.assertEqual(d1, d2)
        # drop + rebuild (fact_version_relation is a view since G6-A —
        # no storage to drop; the digest still covers its logical rows)
        for t in ("source_fact", "ledger_event", "derivation_rule"):
            cx.execute(f"DELETE FROM {t}")
        cx.commit()
        ledger.materialize(cx)
        self.assertEqual(ledger.ledger_digest(cx), d1)


class TestProvenance(unittest.TestCase):

    def test_provenance_chain_complete(self):
        cx = _db()
        _ps(cx, "ps:1"); _ac(cx, "ac:1"); _nod(cx, "nod:1")
        _ps(cx, "ps:dead", at=T0)
        _ps(cx, "ps:repl", at=T1)
        cx.execute("INSERT INTO notice_relation VALUES(?,?,?,?,?,?)",
                   ("ps:repl", "ps:dead", "ANNULS", "e", "t", "s"))
        cx.commit()
        ledger.materialize(cx)
        orphan = 0
        for (eid,) in cx.execute("SELECT event_id FROM ledger_event"):
            p = ledger.provenance(cx, eid)
            if not p or not p["notice"] or not p["observations"]:
                orphan += 1
        self.assertEqual(orphan, 0)
        # raw sha reachable
        eid = cx.execute("SELECT event_id FROM ledger_event WHERE "
                         "event_type='SIGNIFICANT_HOLDING_POSITION_"
                         "DISCLOSED' LIMIT 1").fetchone()[0]
        p = ledger.provenance(cx, eid)
        # synthetic parse_lines() fixtures carry no doc_sha256 (that is
        # set by parse_pdf on real bytes); the observed raw_sha256
        # comes from the G1 observation layer and must be reachable
        self.assertTrue(p["observations"][0]["raw_sha256"])
        self.assertEqual(p["semantic_parse"]["table"],
                         "ps_notice_semantic")
        self.assertEqual(p["ledger_event"]["rule_id"],
                         "PS_DISCLOSURE_TO_POSITION_EVENT/v1")


class TestProjection(unittest.TestCase):

    def test_current_authoritative_uses_relations_only(self):
        cx = _db()
        _ps(cx, "ps:old", at=T0)
        _ps(cx, "ps:new", at=T1, doc=PS_DOC(pct_total="7,000"))
        cx.execute("INSERT INTO notice_relation VALUES(?,?,?,?,?,?)",
                   ("ps:new", "ps:old", "ANNULS", "e", "t", "s"))
        cx.commit()
        ledger.materialize(cx)
        st = ledger.state_for_issuer(cx, "SAN")
        self.assertEqual(len(st["significant_holdings"]), 1)
        self.assertEqual(st["significant_holdings"][0]["notice_key"],
                         "ps:new")
        # as known before the annulling notice existed -> old is live
        st0 = ledger.state_for_issuer(cx, "SAN", known_at=T0)
        self.assertEqual(st0["significant_holdings"][0]["notice_key"],
                         "ps:old")

    def test_no_fuzzy_subject_merge(self):
        # same issuer, two different raw names -> two entries, never
        # merged
        cx = _db()
        _ps(cx, "ps:1", at=T0)
        doc = PS_DOC()
        doc[0][13] = doc[0][13].__class__([
            {"x0": 0.0, "x1": 40.0, "t": "OTRO SUJETO, S.A."}])
        _ps(cx, "ps:2", at=T1, doc=doc)
        ledger.materialize(cx)
        st = ledger.state_for_issuer(cx, "SAN")
        self.assertEqual(len(st["significant_holdings"]), 2)
        quals = {h["identity_quality"] for h in
                 st["significant_holdings"]}
        self.assertEqual(quals, {"ISSUER_SCOPED_RAW_NAME"})


if __name__ == "__main__":
    unittest.main()
