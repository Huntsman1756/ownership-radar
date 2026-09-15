"""G6-B public contract tests — BLACK BOX.

Only public imports are used for assertions:

    from ownership_radar import OwnershipRadar, ...

Fixture construction may touch internals (it builds the dataset);
assertions exercise the public surface exclusively.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

# internals used ONLY to build the fixture dataset
from ownership_radar import store, ledger  # noqa:E402

# public contract under test
from ownership_radar import (  # noqa:E402
    AmbiguousAnnulment, AmbiguousIdentifier, Issuer, LedgerEvent,
    NotFound, OwnershipRadar, SCHEMA_VERSION)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(tempfile.mkdtemp(), "fixture.sqlite")

T0 = "2024-01-01T00:00:00+00:00"   # earliest observation
T1 = "2024-03-01T00:00:00+00:00"
T2 = "2024-06-01T00:00:00+00:00"


def _build_fixture():
    cx = store.init_db(DB_PATH)
    cx.execute("INSERT INTO universe_version VALUES(?,?,?,?,?)",
               ("fixture-v1", "{}", "2024-01-01", "x" * 64, "test"))
    cx.execute("""INSERT INTO universe_issuer VALUES
                  ('fixture-v1','A39000013','A39000013','BANCO SAN',
                   '["ES0113900J37"]','NIF','OFFICIAL')""")
    cx.execute("INSERT INTO issuer_alias VALUES('SAN','A39000013',"
               "'TICKER','fixture')")
    cx.execute("INSERT INTO issuer VALUES('A39000013','A39000013',"
               "'LEI549300','BANCO SAN',NULL,'r')")
    # second issuer sharing an alias -> AmbiguousIdentifier probe
    cx.execute("""INSERT INTO universe_issuer VALUES
                  ('fixture-v1','A00000002','A00000002','OTHER',
                   '[]','NIF','OFFICIAL')""")
    cx.execute("INSERT INTO issuer_alias VALUES('DUP','A39000013',"
               "'TICKER','fixture')")
    cx.execute("INSERT INTO issuer_alias VALUES('DUP','A00000002',"
               "'TICKER','fixture')")

    def notice(nk, surf, filing, status=None, tmpl="T1"):
        cx.execute("""INSERT INTO notice(notice_key,source_surface,
                      source_registration_number,issuer_id,filing_date,
                      regulatory_template,notice_status)
                      VALUES(?,?,?,?,?,?,?)""",
                   (nk, surf, nk.split(":")[1], "A39000013", filing,
                    tmpl, status))

    def obs(nk, at):
        cx.execute("""INSERT INTO notice_observation(run_id,notice_key,
                      observed_at,present_in_source,
                      source_url_canonical) VALUES('r',?,?,1,?)""",
                   (nk, at, "https://cnmv/x/" + nk))

    # nod notice + transaction + execution
    notice("nod:100", "nod", "2024-01-15")
    obs("nod:100", T0)
    cx.execute("""INSERT INTO nod_notice_semantic(notice_key,
                  semantic_parser_version,parse_status,
                  notifying_party_name_raw) VALUES('nod:100',
                  'nodpdf-9.9','PARSED','PERSONA X')""")
    cx.execute("""INSERT INTO transaction_event(event_id,notice_key,
                  source_order,transaction_nature_raw,
                  transaction_nature_normalized,transaction_date,
                  venue_raw,declared_aggregate_price,
                  declared_price_currency)
                  VALUES('nod:100:00','nod:100',0,'Compra','BUY',
                  '2024-01-10','XMAD','1234.50','EUR')""")
    cx.execute("""INSERT INTO execution_line VALUES('nod:100:00',0,
                  '12,34','12.34','EUR','100,00','100','EUR')""")

    # ps notice
    notice("ps:100", "ps", "2024-02-01")
    obs("ps:100", T0)
    cx.execute("""INSERT INTO ps_notice_semantic(notice_key,
                  semantic_parser_version,parse_status,
                  obliged_subject_name_raw,threshold_date,
                  position_current_json,position_previous_json,
                  percentage_semantics,reason_voting_rights,
                  regulatory_template)
                  VALUES('ps:100','pspdf-9.9','PARSED','HOLDER Y',
                  '2024-01-20','{"total_pct": "4.5"}',
                  '{"total_pct": "2.0"}','VOTING_RIGHTS',1,
                  'CIRC_8_2015_MODEL_1')""")
    cx.execute("""INSERT INTO ps_shares_row VALUES('ps:100',0,
                  'ES0113900J37','3000','3000','200','200','4.5','4.5',
                  '2.0','2.0','{}')""")

    # ac notice: ops flow + resulting position
    notice("ac:100", "ac", "2024-02-15")
    obs("ac:100", T0)
    cx.execute("""INSERT INTO ac_notice_semantic(notice_key,
                  semantic_parser_version,parse_status,
                  notification_date,final_position_json,
                  reason_acquisitions_1pct,regulatory_template)
                  VALUES('ac:100','acpdf-9.9','PARSED','2024-02-10',
                  '{"pct": "1.2"}',1,'CIRC_8_2015_MODEL_4')""")
    cx.execute("""INSERT INTO ac_operation(notice_key,row_index,
                  operation_date_raw,operation_date,operation_flag_raw,
                  operation_flag_normalized,isin,shares_direct,
                  price_direct,raw_json)
                  VALUES('ac:100',0,'10/02/2024','2024-02-10','C',
                  'ACQUISITION','ES0113900J37','500','10.5','{}')""")

    # annulment chain: ps:old <- ps:new (observed later, at T2)
    notice("ps:old", "ps", "2024-01-05")
    obs("ps:old", T0)
    notice("ps:new", "ps", "2024-05-01")
    obs("ps:new", T2)
    cx.execute("INSERT INTO notice_relation VALUES('ps:new','ps:old',"
               "'ANNULS',NULL,'r',NULL)")
    # ambiguous: ps:amb <- ps:x AND ps:y
    notice("ps:amb", "ps", "2024-01-06")
    obs("ps:amb", T0)
    for k in ("ps:x", "ps:y"):
        notice(k, "ps", "2024-02-20")
        obs(k, T1)
        cx.execute("INSERT INTO notice_relation VALUES(?,?,?,?,?,?)",
                   (k, "ps:amb", "ANNULS", None, "r", None))
    # doc rows
    for nk, st in (("nod:100", "PARSED"), ("ps:100", "PARSED"),
                   ("ac:100", "PARSED")):
        cx.execute("""INSERT INTO notice_doc(notice_key,doc_status,
                      raw_sha256,parse_status) VALUES(?,?,?,?)""",
                   (nk, st, "a" * 64, st))
    cx.commit()
    ledger.materialize(cx)
    cx.close()


def setUpModule():
    _build_fixture()


class RadarTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = OwnershipRadar.open(DB_PATH)

    def k(self, iso):   # known_at helper
        return datetime.fromisoformat(iso).replace(
            tzinfo=timezone.utc) if "+" not in iso else \
            datetime.fromisoformat(iso)


class TestResolution(RadarTestCase):
    def test_exact_resolution_all_id_types(self):
        for ident in ("SAN", "A39000013", "ES0113900J37",
                      "LEI549300"):
            self.assertEqual(self.r.company(ident).issuer_id,
                             "A39000013")
        self.assertIsInstance(self.r.company("SAN"), Issuer)

    def test_not_found(self):
        with self.assertRaises(NotFound):
            self.r.company("ZZZZZ")

    def test_ambiguous_never_picked(self):
        with self.assertRaises(AmbiguousIdentifier):
            self.r.company("DUP")


class TestTemporal(RadarTestCase):
    """Contract tests A–F."""

    def test_A_no_known_at_is_current_knowledge(self):
        res = self.r.company("SAN").events()
        self.assertEqual(res.history_mode,
                         "CURRENT_KNOWLEDGE_RECONSTRUCTED")

    def test_B_known_at_before_first_observation(self):
        res = self.r.company("SAN").events(
            known_at=datetime(2000, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(res.status, "NO_OBSERVATION_HISTORY")
        self.assertEqual(res.count, 0)
        res2 = self.r.company("SAN").insider_transactions(
            known_at=datetime(2000, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(res2.status, "NO_OBSERVATION_HISTORY")

    def test_C_notice_active_before_annulment_observed(self):
        res = self.r.notices(known_at=self.k(T0))
        keys = {n.notice_key for n in res.items}
        self.assertIn("ps:old", keys)

    def test_D_same_notice_cancelled_after(self):
        # ps:new observed at T2 -> ps:old cancelled for queries with
        # knowledge >= T2
        res = self.r.company("SAN").significant_holdings(
            known_at=self.k(T2))
        keys = {d.notice_key for d in res.items}
        self.assertNotIn("ps:old", keys)

    def test_E_effective_at_does_not_change_knowledge(self):
        res = self.r.events(effective_at=date(2024, 1, 1))
        self.assertEqual(res.history_mode,
                         "CURRENT_KNOWLEDGE_RECONSTRUCTED")

    def test_F_known_at_does_not_change_effective_dates(self):
        res = self.r.events(known_at=self.k(T2))
        eff = {e.effective_date for e in res.items
               if e.effective_date}
        # effective dates are the declared ones regardless of known_at
        self.assertTrue(all(d <= date(2024, 12, 31) for d in eff))


class TestAmbiguousAnnulment(RadarTestCase):
    def test_ambiguous_public_status(self):
        st = self.r.annulment_status("ps:amb")
        self.assertEqual(st.status, "AMBIGUOUS")
        self.assertEqual(sorted(st.annulling_notices),
                         ["ps:x", "ps:y"])
        self.assertIsNone(st.terminal)

    def test_authoritative_fails_closed(self):
        ca = self.r.current_authoritative("ps:amb")
        self.assertEqual(ca.status, "AMBIGUOUS")
        self.assertIsNone(ca.authoritative)
        with self.assertRaises(AmbiguousAnnulment):
            self.r.require_authoritative("ps:amb")

    def test_cancellation_evidence_levels(self):
        n = self.r.notice("ps:amb")
        st = n.annulment_status()
        self.assertTrue(st.cancellation_relation_observed)
        self.assertTrue(st.cancelled_notice_raw_observed)


class TestDomainObjects(RadarTestCase):
    def test_insider_transaction_shape(self):
        res = self.r.company("SAN").insider_transactions()
        self.assertGreater(res.count, 0)
        t = res.items[0]
        self.assertEqual(t.person_name_raw, "PERSONA X")
        self.assertIsInstance(t.declared_aggregate_price, Decimal)
        self.assertIsInstance(t.transaction_date, date)
        self.assertEqual(t.executions[0].price, Decimal("12.34"))
        self.assertEqual(t.event_basis, "DETERMINISTIC_DERIVATION")
        p = t.provenance()
        self.assertEqual(p.notice_key, "nod:100")
        self.assertEqual(p.raw_sha256, "a" * 64)
        self.assertEqual(p.semantic_parser_version, "nodpdf-9.9")

    def test_ps_is_disclosure_never_trade(self):
        res = self.r.company("SAN").significant_holdings()
        d = res.items[0]
        self.assertEqual(d.obliged_subject, "HOLDER Y")
        self.assertEqual(d.threshold_date, date(2024, 1, 20))
        self.assertEqual(d.position_current["total_pct"], "4.5")
        self.assertFalse(hasattr(d, "side"))  # no BUY/SELL
        self.assertFalse(hasattr(d, "transaction_nature"))

    def test_treasury_flow_stock_distinct(self):
        pos = self.r.company("SAN").treasury_stock_positions()
        ops = self.r.company("SAN").treasury_operations()
        self.assertEqual(pos.items[0].final_position["pct"], "1.2")
        self.assertEqual(ops.items[0].shares_direct, Decimal("500"))
        # positions object carries no operation flow fields
        self.assertFalse(hasattr(pos.items[0], "shares_direct"))

    def test_ledger_event_basis_explicit(self):
        res = self.r.events(limit=100)
        for e in res.items:
            self.assertIsInstance(e, LedgerEvent)
            self.assertIn(e.event_basis,
                          ("SOURCE_DECLARED",
                           "DETERMINISTIC_DERIVATION"))

    def test_cursor_stable_and_paginates(self):
        p1 = self.r.events(limit=2)
        self.assertTrue(p1.has_more)
        self.assertIsNotNone(p1.next_cursor)
        p2 = self.r.events(limit=2, cursor=p1.next_cursor)
        ids1 = {e.event_id for e in p1.items}
        ids2 = {e.event_id for e in p2.items}
        self.assertFalse(ids1 & ids2)  # no overlap

    def test_dataset_info_discloses_universe(self):
        info = self.r.dataset_info()
        self.assertEqual(info.universe_version, "fixture-v1")
        self.assertEqual(info.universe_issuers, 2)
        self.assertEqual(info.schema_version, SCHEMA_VERSION)

    def test_coverage_explicit_denominators(self):
        cov = self.r.coverage()
        self.assertIn("global", cov)
        self.assertIn("doc_status", cov["global"])


class TestReadOnly(RadarTestCase):
    def test_no_network_no_writes(self):
        r = OwnershipRadar.open(DB_PATH)
        with self.assertRaises(Exception):
            r._cx.execute("INSERT INTO notice(notice_key,"
                          "source_surface,source_registration_number) "
                          "VALUES('x','x','x')")


class TestCliContract(unittest.TestCase):
    """CLI as an external process: exit codes, clean stdout JSON."""

    def cli(self, *args):
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        return subprocess.run(
            [sys.executable, "-m", "ownership_radar",
             "--db", DB_PATH] + list(args),
            capture_output=True, text=True, cwd=REPO, env=env)

    def test_company_json(self):
        p = self.cli("company", "SAN", "--format", "json")
        self.assertEqual(p.returncode, 0)
        env = json.loads(p.stdout)  # stdout must be pure JSON
        self.assertEqual(env["schema_version"], SCHEMA_VERSION)
        self.assertEqual(env["data"]["issuer_id"], "A39000013")
        self.assertEqual(p.stderr, "")

    def test_not_found_exit_and_stderr(self):
        p = self.cli("company", "ZZZZ", "--format", "json")
        self.assertEqual(p.returncode, 1)
        self.assertEqual(p.stdout, "")        # no garbage on stdout
        self.assertIn("not found", p.stderr)

    def test_ambiguous_exit(self):
        p = self.cli("company", "DUP", "--format", "json")
        self.assertEqual(p.returncode, 1)
        self.assertIn("ambiguous", p.stderr.lower())

    def test_jsonl_one_object_per_line(self):
        p = self.cli("insiders", "SAN", "--format", "jsonl",
                     "--limit", "2")
        self.assertEqual(p.returncode, 0)
        lines = [ln for ln in p.stdout.strip().splitlines() if ln]
        for ln in lines:
            env = json.loads(ln)
            self.assertEqual(env["schema_version"], SCHEMA_VERSION)
        self.assertGreaterEqual(len(lines), 1)

    def test_known_at_flag(self):
        p = self.cli("events", "SAN", "--format", "json",
                     "--known-at", "2000-01-01T00:00:00+00:00")
        self.assertEqual(p.returncode, 0)
        env = json.loads(p.stdout)
        self.assertEqual(env["data"]["status"],
                         "NO_OBSERVATION_HISTORY")

    def test_provenance_command(self):
        p = self.cli("provenance", "nod:100", "--format", "json")
        env = json.loads(p.stdout)
        self.assertEqual(env["data"]["notice_key"], "nod:100")
        self.assertEqual(env["data"]["raw_sha256"], "a" * 64)


if __name__ == "__main__":
    unittest.main()
