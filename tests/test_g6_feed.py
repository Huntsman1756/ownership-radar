"""G6-C feed contract tests — BLACK BOX.

Assertions use only `from ownership_radar import ...` and the CLI as
an external process. Fixture construction touches internals solely
to build the dataset.

Covered gates: FEED_IS_OBSERVATION_DRIVEN, BACKFILL_EXCLUDED_BY_
DEFAULT, OBSERVED_EFFECTIVE_DATES_DISTINCT, FEED_ITEM_ID_STABLE,
CURSOR_OPAQUE_VERSIONED, CURSOR_NO_GAPS, CURSOR_NO_PAGE_OVERLAP,
CURSOR_TIES_EXACT, CURSOR_QUERY_BOUND, RECONCILIATION_NOISE_
SUPPRESSED, CANCELLATION_RELATION_EMITTED, AMBIGUOUS_ANNULS_
PRESERVED, DISAPPEARANCE_NON_DESTRUCTIVE, FEED_REBUILD_IDENTICAL,
FEED_OFFLINE, JSON_JSONL_SCHEMA_STABLE, ATOM_SEMANTICS_CORRECT.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

from ownership_radar import store, ledger  # noqa:E402  fixture only
from ownership_radar import (  # noqa:E402  public contract
    CursorDatasetMismatch, InvalidCursor, OwnershipRadar,
    SCHEMA_VERSION, UnsupportedCursorVersion)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(tempfile.mkdtemp(), "feed-fixture.sqlite")

TB = "2024-01-10T00:00:00+00:00"   # BACKFILL observation
T1 = "2024-03-01T00:00:00+00:00"   # INCREMENTAL observation
T2 = "2024-06-01T00:00:00+00:00"   # RECONCILIATION observation


def _build_fixture():
    cx = store.init_db(DB_PATH)
    cx.execute("INSERT INTO universe_version VALUES(?,?,?,?,?)",
               ("fixture-v1", "{}", "2024-01-01", "x" * 64, "test"))
    cx.execute("""INSERT INTO universe_issuer VALUES
                  ('fixture-v1','A39000013','A39000013','BANCO SAN',
                   '["ES0113900J37"]','NIF','OFFICIAL')""")
    cx.execute("INSERT INTO issuer VALUES('A39000013','A39000013',"
               "'LEI549300','BANCO SAN',NULL,'r')")
    for rid, rt, st in (("rb", "BACKFILL", TB),
                        ("ri", "INCREMENTAL", T1),
                        ("rr", "RECONCILIATION", T2),
                        ("rr2", "RECONCILIATION", T2)):
        cx.execute("INSERT INTO crawl_run(run_id,run_type,started_at,"
                   "status,scope,universe_version) VALUES(?,?,?,?,?,?)",
                   (rid, rt, st, "DONE", "f", "fixture-v1"))

    def notice(nk, surf, filing):
        cx.execute("""INSERT INTO notice(notice_key,source_surface,
                      source_registration_number,issuer_id,filing_date,
                      regulatory_template,notice_status)
                      VALUES(?,?,?,?,?, 'T1', 'ACTIVE')""",
                   (nk, surf, nk.split(":")[1], "A39000013", filing))

    def obs(nk, run, at, status=None):
        cx.execute("""INSERT INTO notice_observation(run_id,notice_key,
                      observed_at,present_in_source,status_observed,
                      source_url_canonical)
                      VALUES(?,?,?,?,?,?)""",
                   (run, nk, at, 1 if status is None else 0,
                    status, "https://cnmv/x/" + nk))

    # A: backfilled notice + NOD transaction (effective 2024-01-05,
    # filed 2024-01-08, observed 2024-01-10 — three distinct dates)
    notice("nod:A", "nod", "2024-01-08")
    obs("nod:A", "rb", TB)
    cx.execute("""INSERT INTO nod_notice_semantic(notice_key,
                  semantic_parser_version,parse_status,
                  notifying_party_name_raw)
                  VALUES('nod:A','nodpdf-9.9','PARSED','PERSONA A')""")
    cx.execute("""INSERT INTO transaction_event(event_id,notice_key,
                  source_order,transaction_nature_raw,
                  transaction_nature_normalized,transaction_date,
                  venue_raw,declared_aggregate_price,
                  declared_price_currency)
                  VALUES('nod:A:00','nod:A',0,'Compra','BUY',
                  '2024-01-05','XMAD','100.00','EUR')""")
    cx.execute("""INSERT INTO notice_doc(notice_key,doc_status,
                  raw_sha256,parse_status)
                  VALUES('nod:A','PARSED','a'*0 || printf('%064d',1),
                  'PARSED')""")

    # B: live-noticed notice (first seen in INCREMENTAL at T1)
    notice("nod:B", "nod", "2024-02-28")
    obs("nod:B", "ri", T1)
    # identical re-observation in rr and rr2 — must add NO new item
    obs("nod:B", "rr", T2)
    obs("nod:B", "rr2", T2)

    # C: ANNULS relation first observed in INCREMENTAL
    notice("ps:C", "ps", "2024-02-20")
    obs("ps:C", "ri", T1)
    cx.execute("INSERT INTO notice_relation VALUES('ps:C','nod:A',"
               "'ANNULS',NULL,'ri',NULL)")
    # ambiguous: ps:amb <- ps:x AND ps:y (both observed at T1)
    notice("ps:amb", "ps", "2024-02-21")
    obs("ps:amb", "ri", T1)
    for k in ("ps:x", "ps:y"):
        notice(k, "ps", "2024-02-22")
        obs(k, "ri", T1)
        cx.execute("INSERT INTO notice_relation VALUES(?,?,?,?,?,?)",
                   (k, "ps:amb", "ANNULS", None, "ri", None))
    # D: disappearance first observed in RECONCILIATION
    notice("nod:D", "nod", "2024-01-20")
    obs("nod:D", "ri", T1)
    obs("nod:D", "rr", T2, "SOURCE_DISAPPEARANCE_OBSERVED")
    obs("nod:D", "rr2", T2, "SOURCE_DISAPPEARANCE_OBSERVED")
    cx.commit()
    ledger.materialize(cx)
    cx.close()


def setUpModule():
    _build_fixture()


class FeedTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = OwnershipRadar.open(DB_PATH)

    def all_items(self, **kw):
        items, cur = [], None
        while True:
            res = self.r.feed(cursor=cur, limit=7, **kw)
            items += res.items
            if not res.has_more:
                return items
            cur = res.next_cursor


class TestFeedSemantics(FeedTestCase):
    def test_backfill_excluded_by_default(self):
        items = self.all_items()
        # nod:A's own items were backfilled — excluded; it may still
        # appear as the annulled ENDPOINT of a live relation item
        own = [i for i in items if i.notice_key == "nod:A"
               and i.feed_item_type !=
               "CANCELLATION_RELATION_OBSERVED"]
        self.assertEqual(own, [])
        keys = {i.notice_key for i in items}
        self.assertIn("nod:B", keys)

    def test_include_backfill_shows_reconstructed(self):
        items = self.all_items(include_backfill=True)
        a = [i for i in items if i.notice_key == "nod:A"
             and i.feed_item_type !=
             "CANCELLATION_RELATION_OBSERVED"]
        self.assertTrue(a)
        self.assertTrue(all(
            i.history_class == "RECONSTRUCTED_HISTORICAL"
            for i in a))
        b = [i for i in items if i.notice_key == "nod:B"]
        self.assertTrue(all(i.history_class == "OBSERVED_CURRENT"
                            for i in b))

    def test_observed_effective_dates_distinct(self):
        items = self.all_items(include_backfill=True)
        tx = next(i for i in items
                  if i.feed_item_type ==
                  "INSIDER_TRANSACTION_OBSERVED")
        self.assertEqual(str(tx.effective_date), "2024-01-05")
        self.assertEqual(str(tx.filing_date), "2024-01-08")
        self.assertEqual(tx.observed_at.isoformat(), TB)
        self.assertEqual(tx.event_basis, "DETERMINISTIC_DERIVATION")

    def test_reconciliation_noise_suppressed(self):
        # nod:B re-observed identically in rr + rr2 -> exactly one
        # NOTICE_OBSERVED item, anchored at first observation T1
        items = [i for i in self.all_items()
                 if i.feed_item_type == "NOTICE_OBSERVED"
                 and i.notice_key == "nod:B"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].observed_at.isoformat(), T1)
        self.assertEqual(items[0].run_type, "INCREMENTAL")

    def test_disappearance_streak_single_item(self):
        items = [i for i in self.all_items()
                 if i.feed_item_type ==
                 "NOTICE_DISAPPEARANCE_OBSERVED"]
        self.assertEqual(len(items), 1)
        d = items[0]
        self.assertEqual(d.notice_key, "nod:D")
        self.assertEqual(d.observed_at.isoformat(), T2)
        self.assertFalse(d.summary["cancellation_evidence_present"])
        # disappearance is NOT a cancellation
        self.assertIsNone(d.relation_type)

    def test_cancellation_relation_emitted(self):
        items = [i for i in self.all_items()
                 if i.feed_item_type ==
                 "CANCELLATION_RELATION_OBSERVED"
                 and i.annulled_notice_key == "nod:A"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].annulling_notice_key, "ps:C")
        self.assertEqual(items[0].observed_at.isoformat(), T1)
        self.assertTrue(
            items[0].summary["cancelled_notice_raw_observed"])

    def test_ambiguous_annuls_preserved(self):
        items = [i for i in self.all_items()
                 if i.annulled_notice_key == "ps:amb"]
        self.assertEqual(len(items), 2)  # one per candidate relation
        for i in items:
            self.assertEqual(i.annulment_status, "AMBIGUOUS")
            self.assertEqual(sorted(
                i.summary["annulling_notices"]), ["ps:x", "ps:y"])

    def test_item_id_stable_across_replays(self):
        a = [i.feed_item_id for i in self.all_items()]
        b = [i.feed_item_id for i in self.all_items()]
        self.assertEqual(a, b)
        self.assertTrue(all(i.startswith("v1:") for i in a))


class TestCursor(FeedTestCase):
    def test_opaque_versioned(self):
        res = self.r.feed(limit=1)
        cur = res.next_cursor
        self.assertTrue(cur.startswith("v1."))
        self.assertNotIn("rowid", cur)

    def test_ties_exact_no_gaps_no_overlap(self):
        # all INCREMENTAL items share observed_at=T1
        ids, cur, seen = [], None, set()
        while True:
            res = self.r.feed(cursor=cur, limit=2)
            for i in res.items:
                self.assertNotIn(i.feed_item_id, seen)  # no overlap
                seen.add(i.feed_item_id)
            ids += [i.feed_item_id for i in res.items]
            if not res.has_more:
                break
            cur = res.next_cursor
        full = self.all_items()
        self.assertEqual(len(ids), len(full))
        self.assertEqual(set(ids), {i.feed_item_id for i in full})

    def test_same_cursor_same_page(self):
        r1 = self.r.feed(limit=3)
        r2 = self.r.feed(limit=3)
        self.assertEqual([i.feed_item_id for i in r1.items],
                         [i.feed_item_id for i in r2.items])
        self.assertEqual(r1.next_cursor, r2.next_cursor)

    def test_cursor_survives_reopen(self):
        res = self.r.feed(limit=2)
        r2 = OwnershipRadar.open(DB_PATH)
        res2 = r2.feed(cursor=res.next_cursor, limit=2)
        self.assertEqual(res2.count, 2)

    def test_cursor_query_bound(self):
        res = self.r.feed(limit=2, item_type="NOTICE_OBSERVED")
        with self.assertRaises(CursorDatasetMismatch):
            self.r.feed(cursor=res.next_cursor,
                        item_type="NOTICE_DISAPPEARANCE_OBSERVED")
        res2 = self.r.feed(limit=2, include_backfill=True)
        with self.assertRaises(CursorDatasetMismatch):
            self.r.feed(cursor=res2.next_cursor)

    def test_invalid_and_old_version_cursor(self):
        with self.assertRaises(InvalidCursor):
            self.r.feed(cursor="garbage")
        with self.assertRaises(UnsupportedCursorVersion):
            self.r.feed(cursor="v0.abc")
        with self.assertRaises(InvalidCursor):
            self.r.feed(cursor="v1.@@@")

    def test_cursor_latest_skips_history(self):
        res = self.r.feed(cursor=self.r.feed_cursor_latest(),
                          limit=10)
        self.assertEqual(res.count, 0)
        self.assertFalse(res.has_more)


class TestFeedInternals(FeedTestCase):
    """Fixture-level checks on derived state (not public reads)."""

    def test_rebuild_identical(self):
        cx = store.connect(DB_PATH)
        d1 = ledger.feed_digest(cx)
        ledger.rebuild_feed(cx)
        d2 = ledger.feed_digest(cx)
        self.assertEqual(d1, d2)
        cx.close()


class TestFeedCli(unittest.TestCase):
    def cli(self, *args):
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        return subprocess.run(
            [sys.executable, "-m", "ownership_radar",
             "--db", DB_PATH] + list(args),
            capture_output=True, text=True, cwd=REPO, env=env)

    def test_feed_json(self):
        p = self.cli("feed", "--format", "json", "--limit", "5")
        self.assertEqual(p.returncode, 0)
        env = json.loads(p.stdout)
        self.assertEqual(env["schema_version"], SCHEMA_VERSION)
        self.assertIn("dataset_version", env["data"])
        for it in env["data"]["items"]:
            self.assertTrue(
                it["feed_item_id"].startswith("v1:"))
            self.assertIn(it["history_class"],
                          ("OBSERVED_CURRENT",
                           "RECONSTRUCTED_HISTORICAL"))

    def test_feed_jsonl_cursor_on_stderr(self):
        p = self.cli("feed", "--format", "jsonl", "--limit", "2")
        self.assertEqual(p.returncode, 0)
        lines = [ln for ln in p.stdout.strip().splitlines() if ln]
        for ln in lines:
            env = json.loads(ln)
            self.assertEqual(env["schema_version"], SCHEMA_VERSION)
            self.assertIn("feed_item_id", env["data"])
        self.assertIn("next_cursor=", p.stderr)

    def test_feed_atom_valid_and_semantics(self):
        p = self.cli("feed", "--format", "atom",
                     "--include-backfill", "--limit", "10")
        self.assertEqual(p.returncode, 0)
        root = ET.fromstring(p.stdout)  # must parse cleanly
        ns = {"a": "http://www.w3.org/2005/Atom"}
        entries = root.findall("a:entry", ns)
        self.assertGreater(len(entries), 0)
        for e in entries:
            self.assertTrue(e.find("a:id", ns).text.startswith(
                "urn:ownership-radar:v1:"))
            published = e.find("a:published", ns).text
            body = json.loads(e.find("a:content", ns).text)
            eff = body.get("effective_date")
            if eff:
                # published = observed_at, never effective_date
                self.assertNotEqual(published[:10], eff)

    def test_feed_invalid_cursor_exit(self):
        p = self.cli("feed", "--cursor", "bogus", "--format", "json")
        self.assertEqual(p.returncode, 1)
        self.assertEqual(p.stdout, "")
        self.assertIn("error", p.stderr)

    def test_feed_cursor_latest_command(self):
        p = self.cli("feed-cursor-latest")
        self.assertEqual(p.returncode, 0)
        self.assertTrue(p.stdout.strip().startswith("v1."))
        p2 = self.cli("feed", "--cursor", p.stdout.strip(),
                      "--format", "json")
        self.assertEqual(p2.returncode, 0)
        env = json.loads(p2.stdout)
        self.assertEqual(env["data"]["count"], 0)

    def test_from_latest_flag(self):
        p = self.cli("feed", "--from-latest", "--format", "json")
        self.assertEqual(p.returncode, 0)
        env = json.loads(p.stdout)
        self.assertEqual(env["data"]["count"], 0)


if __name__ == "__main__":
    unittest.main()
