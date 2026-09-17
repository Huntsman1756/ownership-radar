"""Regression tests for public-API and ingestion bugs found in audit.

Fixture construction touches internals (it builds the dataset);
assertions exercise the public surface / public error contract.
"""
import base64
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

# internals used ONLY to build the fixture dataset
from ownership_radar import ingest, pipeline, public_cli, store  # noqa:E402

# public contract under test
from ownership_radar import OwnershipRadar  # noqa:E402
from ownership_radar.api import (CursorDatasetMismatch, InvalidCursor,
                                 InvalidTemporalQuery, NotFound,
                                 OwnershipRadarError,
                                 UnsupportedCursorVersion, _cursor_encode,
                                 _qsig)

T0 = "2024-01-01T00:00:00+00:00"


def _cur(*key):
    return base64.urlsafe_b64encode(
        json.dumps(list(key)).encode()).decode()


class _ErrFetcher:
    """Fetcher stub: every get() fails like a network outage."""
    def __init__(self):
        self.calls = []

    def get(self, url, note=""):
        self.calls.append(url)
        return ({"status": "ERROR", "error": "boom",
                 "retrieved_at": T0, "run_id": "r"}, b"")


def _build():
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "fixture.sqlite")
    cx = store.init_db(path)
    cx.execute("INSERT INTO universe_version VALUES(?,?,?,?,?)",
               ("fixture-v1", "{}", "2024-01-01", "x" * 64, "test"))
    cx.execute("""INSERT INTO universe_issuer VALUES
                  ('fixture-v1','A39000013','A39000013','BANCO SAN',
                   '[]','NIF','OFFICIAL')""")
    cx.execute("INSERT INTO issuer_alias VALUES('SAN','A39000013',"
               "'TICKER','fixture')")

    def notice(nk, surf, issuer, filing):
        cx.execute("""INSERT INTO notice(notice_key,source_surface,
                      source_registration_number,issuer_id,filing_date)
                      VALUES(?,?,?,?,?)""",
                   (nk, surf, nk.split(":")[1], issuer, filing))
        cx.execute("""INSERT INTO notice_observation(run_id,notice_key,
                      observed_at,present_in_source)
                      VALUES('r',?,?,1)""", (nk, T0))

    # --- significant holdings: notice_key order deliberately
    # differs from threshold_date order; ps:5 has NULL date ---
    for nk, thr in (("ps:1", "2024-05-01"), ("ps:2", "2024-03-01"),
                    ("ps:3", "2024-04-01"), ("ps:4", "2024-05-01"),
                    ("ps:5", None)):
        notice(nk, "ps", "A39000013", "2024-05-02")
        cx.execute("""INSERT INTO ps_notice_semantic(notice_key,
                      semantic_parser_version,parse_status,
                      threshold_date) VALUES(?, 'pspdf-t','PARSED',?)""",
                   (nk, thr))
    # expected: 05-01: ps:4,ps:1 -> 04-01: ps:3 -> 03-01: ps:2
    #           -> NULL: ps:5

    # --- treasury positions: interleaved notification_date; p4 NULL
    for nk, nd in (("ac:p1", "2024-01-15"), ("ac:p2", "2024-03-15"),
                   ("ac:p3", "2024-02-15"), ("ac:p4", None)):
        notice(nk, "ac", "A39000013", "2024-03-20")
        cx.execute("""INSERT INTO ac_notice_semantic(notice_key,
                      semantic_parser_version,parse_status,
                      notification_date,final_position_json)
                      VALUES(?,'acpdf-t','PARSED',?,'{"pct":"1"}')""",
                   (nk, nd))
    # expected: p2 -> p3 -> p1 -> p4

    # --- treasury operations: 3 rows share (operation_date, nk)
    for nk in ("ac:o1", "ac:o2", "ac:o3"):
        notice(nk, "ac", "A39000013", "2024-03-20")
        cx.execute("""INSERT INTO ac_notice_semantic(notice_key,
                      semantic_parser_version,parse_status)
                      VALUES(?,'acpdf-t','PARSED')""", (nk,))
    for i in range(3):
        cx.execute("""INSERT INTO ac_operation(notice_key,row_index,
                      operation_date,operation_flag_normalized)
                      VALUES('ac:o1',?,'2024-02-10','ACQUISITION')""",
                   (i,))
    cx.execute("""INSERT INTO ac_operation(notice_key,row_index,
                  operation_date,operation_flag_normalized)
                  VALUES('ac:o2',0,'2024-01-10','DISPOSAL')""")
    cx.execute("""INSERT INTO ac_operation(notice_key,row_index,
                  operation_date,operation_flag_normalized)
                  VALUES('ac:o3',0,NULL,'ACQUISITION')""")
    # expected: o1 r0,r1,r2 -> o2 r0 -> o3 r0

    # --- insider transactions: tied filing_date + NULL filing ---
    for nk, fd in (("nod:1", "2024-01-15"), ("nod:2", "2024-01-15"),
                   ("nod:3", None)):
        notice(nk, "nod", "A39000013", fd)
        cx.execute("""INSERT INTO transaction_event(event_id,notice_key,
                      source_order,transaction_date)
                      VALUES(?,?,0,'2024-01-10')""",
                   (nk + ":00", nk))
    # expected: nod:2:00 -> nod:1:00 -> nod:3:00

    # --- ledger events: ties + NULL effective_date boundary ---
    for eid, ed in (("ev:1", "2024-01-01"), ("ev:2", None),
                    ("ev:3", "2024-03-01"), ("ev:4", "2024-01-01"),
                    ("ev:5", None)):
        cx.execute("""INSERT INTO ledger_event(event_id,event_type,
                      event_basis,issuer_id,effective_date,
                      first_observed_at)
                      VALUES(?,'T','SOURCE_DECLARED','A39000013',?,?)
                      """, (eid, ed, T0))
    # expected: ev:3 -> ev:4 -> ev:1 -> ev:5 -> ev:2

    # --- issuer known to the ledger but absent from the universe ---
    notice("nod:z1", "nod", "Z99999999", "2024-01-01")
    cx.commit()
    cx.close()
    return path


class PaginationTest(unittest.TestCase):
    """A keyset traversal must yield exactly the unpaginated set —
    no skips, no duplicates — across every page size."""

    @classmethod
    def setUpClass(cls):
        cls.db = _build()
        cls.r = OwnershipRadar.open(cls.db)

    def _walk(self, method, limit, **kw):
        seen, cursor = [], None
        for _ in range(100):
            res = getattr(self.r, method)(limit=limit, cursor=cursor,
                                          **kw)
            seen += list(res.items)
            if not res.has_more:
                return seen
            self.assertTrue(res.next_cursor)
            cursor = res.next_cursor
        self.fail("pagination did not terminate")

    def test_significant_holdings_full_traversal(self):
        got = [i.notice_key for i in
               self._walk("significant_holdings", 2)]
        self.assertEqual(got, ["ps:4", "ps:1", "ps:3", "ps:2", "ps:5"])

    def test_significant_holdings_page1(self):
        got = [i.notice_key for i in
               self._walk("significant_holdings", 1)]
        self.assertEqual(got, ["ps:4", "ps:1", "ps:3", "ps:2", "ps:5"])

    def test_treasury_stock_positions_full_traversal(self):
        got = [i.notice_key for i in
               self._walk("treasury_stock_positions", 1)]
        self.assertEqual(got, ["ac:p2", "ac:p3", "ac:p1", "ac:p4"])

    def test_treasury_operations_tied_key(self):
        got = [(i.notice_key, i.row_index) for i in
               self._walk("treasury_operations", 1)]
        self.assertEqual(got, [("ac:o1", 0), ("ac:o1", 1), ("ac:o1", 2),
                               ("ac:o2", 0), ("ac:o3", 0)])

    def test_treasury_operations_limit2(self):
        got = [(i.notice_key, i.row_index) for i in
               self._walk("treasury_operations", 2)]
        self.assertEqual(got, [("ac:o1", 0), ("ac:o1", 1), ("ac:o1", 2),
                               ("ac:o2", 0), ("ac:o3", 0)])

    def test_insider_transactions_null_filing(self):
        got = [i.event_id for i in
               self._walk("insider_transactions", 1)]
        self.assertEqual(got, ["nod:2:00", "nod:1:00", "nod:3:00"])

    def test_events_null_boundary(self):
        got = [i.event_id for i in self._walk("events", 4)]
        self.assertEqual(got, ["ev:3", "ev:4", "ev:1", "ev:5", "ev:2"])

    def test_traversal_matches_unpaginated(self):
        for m in ("significant_holdings", "treasury_stock_positions",
                  "treasury_operations", "insider_transactions",
                  "events", "notices"):
            all_items = list(getattr(self.r, m)(limit=200).items)
            for size in (1, 2, 3, 7):
                paged = self._walk(m, size)
                keys = lambda xs: [getattr(i, "notice_key",
                                           getattr(i, "event_id", i))
                                   for i in xs]
                self.assertEqual(keys(paged), keys(all_items), m)


class CursorContractTest(unittest.TestCase):
    """Malformed cursors must raise public errors — never IndexError,
    TypeError or raw codec/JSON exceptions. Query cursors are
    versioned envelopes bound to query signature + dataset version;
    legacy alpha.1 cursors are deliberately invalidated."""

    @classmethod
    def setUpClass(cls):
        cls.db = _build()
        cls.r = OwnershipRadar.open(cls.db)

    BAD = ("AAAA", "W10=", "WzFd", "bm90IGpzb24=", "", "!!!",
           "e30=",                       # {}  — wrong shape
           )

    def test_bad_cursors_raise_public_error(self):
        for m in ("notices", "events", "insider_transactions",
                  "significant_holdings", "treasury_stock_positions",
                  "treasury_operations"):
            for c in self.BAD:
                with self.assertRaises(InvalidCursor,
                                       msg="%s cursor=%r" % (m, c)):
                    getattr(self.r, m)(cursor=c)

    def test_legacy_alpha1_cursor_rejected(self):
        # 0.1.0a1 query cursors were bare base64 JSON lists — no
        # version, no binding, and for several methods the embedded
        # key did not match the ordering (rows could be skipped).
        # They must fail closed, never continue silently.
        for legacy in (_cur("ps:4"), _cur("2024-01-01", "ev:1"),
                       _cur("2024-02-10", "ac:o1", 1)):
            for m in ("notices", "events", "insider_transactions",
                      "significant_holdings",
                      "treasury_stock_positions", "treasury_operations"):
                with self.assertRaises(InvalidCursor,
                                       msg="%s legacy=%r" % (m, legacy)):
                    getattr(self.r, m)(cursor=legacy)

    def test_wrong_key_shape_inside_envelope(self):
        dv = self.r._dataset_version()
        qs = _qsig("events", None, None, None, None)
        with self.assertRaises(InvalidCursor):
            self.r.events(cursor=_cursor_encode(["only-one"], qs, dv))
        with self.assertRaises(InvalidCursor):
            self.r.events(cursor=_cursor_encode([1, "ev:1"], qs, dv))

    def test_wrong_version_rejected(self):
        cur = self.r.notices(limit=2).next_cursor
        if cur is None:      # not enough notices in fixture — craft one
            cur = _cursor_encode(["nod:1"], _qsig(
                "notices", None, None, None), self.r._dataset_version())
        ver, raw = cur.split(".", 1)
        with self.assertRaises(UnsupportedCursorVersion):
            self.r.notices(cursor="q9." + raw)
        # a feed cursor is not a query cursor and vice versa
        with self.assertRaises(UnsupportedCursorVersion):
            self.r.notices(cursor="v1." + raw)

    def test_cursor_bound_to_method(self):
        res = self.r.significant_holdings(limit=2)
        self.assertTrue(res.next_cursor)
        with self.assertRaises(CursorDatasetMismatch):
            self.r.treasury_operations(cursor=res.next_cursor)
        with self.assertRaises(CursorDatasetMismatch):
            self.r.notices(cursor=res.next_cursor)

    def test_cursor_bound_to_issuer(self):
        res = self.r.significant_holdings(issuer="SAN", limit=2)
        self.assertTrue(res.next_cursor)
        with self.assertRaises(CursorDatasetMismatch):
            self.r.significant_holdings(issuer="Z99999999",
                                        cursor=res.next_cursor)

    def test_cursor_bound_to_filters(self):
        res = self.r.significant_holdings(issuer="SAN", limit=2)
        for kw in ({"include_cancelled": True},
                   {"effective_at": date(2024, 4, 1)}):
            with self.assertRaises(CursorDatasetMismatch):
                self.r.significant_holdings(issuer="SAN",
                                            cursor=res.next_cursor,
                                            **kw)

    def test_cursor_bound_to_dataset(self):
        other = _build()          # same data, but…
        cx = store.connect(other)  # …different dataset_version
        cx.execute("UPDATE universe_version SET universe_version="
                   "'other-v1'")
        cx.commit()
        cx.close()
        r2 = OwnershipRadar.open(other)
        res = self.r.events(limit=2)
        self.assertTrue(res.next_cursor)
        with self.assertRaises(CursorDatasetMismatch):
            r2.events(cursor=res.next_cursor)

    def test_same_query_same_cursor(self):
        a = self.r.significant_holdings(issuer="SAN", limit=2)
        b = self.r.significant_holdings(issuer="A39000013", limit=2)
        self.assertEqual(a.next_cursor, b.next_cursor)

    def test_limit_validation(self):
        for bad in (0, -1, "10", None, 1.5):
            for m in ("notices", "events", "insider_transactions",
                      "significant_holdings",
                      "treasury_stock_positions", "treasury_operations"):
                with self.assertRaises(InvalidTemporalQuery,
                                       msg="%s limit=%r" % (m, bad)):
                    getattr(self.r, m)(limit=bad)
            with self.assertRaises(InvalidTemporalQuery):
                self.r.feed(limit=bad)

    def test_feed_bad_cursor(self):
        for c in self.BAD:
            with self.assertRaises(InvalidCursor, msg="cursor=%r" % c):
                self.r.feed(cursor=c)
        with self.assertRaises(InvalidCursor):
            self.r.feed(cursor="v9.xxx")      # wrong version
        # well-formed envelope, malformed key list
        q = self.r._feed_qsig(None, None, False)
        payload = base64.urlsafe_b64encode(json.dumps(
            {"k": [1], "w": None, "q": q, "dv": None}).encode()).decode()
        with self.assertRaises(InvalidCursor):
            self.r.feed(cursor="v1." + payload)

    def test_cli_feed_table(self):
        # FeedResult has no history_mode — table format must not
        # crash on it (default output used to raise AttributeError).
        buf = io.StringIO()
        with redirect_stdout(buf):
            public_cli.main(["feed", "--db", self.db, "--limit", "2"])
        self.assertIn("count=", buf.getvalue())


class IssuerResolutionTest(unittest.TestCase):
    """issuer= accepts Issuer objects or any identifier string
    resolved exactly like company() — consistently across methods."""

    @classmethod
    def setUpClass(cls):
        cls.db = _build()
        cls.r = OwnershipRadar.open(cls.db)

    def test_alias_resolves_everywhere(self):
        self.assertEqual(
            self.r.insider_transactions(issuer="SAN").count, 3)
        self.assertEqual(
            self.r.significant_holdings(issuer="SAN").count, 5)
        self.assertEqual(
            self.r.treasury_operations(issuer="SAN").count, 5)
        self.assertEqual(self.r.events(issuer="SAN").count, 5)
        self.assertTrue(self.r.notices(issuer="SAN").count > 0)

    def test_issuer_object(self):
        i = self.r.company("SAN")
        self.assertEqual(
            self.r.insider_transactions(issuer=i).count, 3)

    def test_notice_only_issuer_id(self):
        # Z99999999 is not in the universe but owns a notice
        res = self.r.notices(issuer="Z99999999")
        self.assertEqual([n.notice_key for n in res.items],
                         ["nod:z1"])

    def test_unknown_identifier_raises(self):
        with self.assertRaises(NotFound):
            self.r.notices(issuer="NOPE")
        with self.assertRaises(NotFound):
            self.r.feed(issuer="NOPE")


class OpenContractTest(unittest.TestCase):
    def test_missing_db_is_public_error(self):
        with self.assertRaises(OwnershipRadarError):
            OwnershipRadar.open(os.path.join(
                tempfile.mkdtemp(), "does-not-exist.sqlite"))

    def test_path_with_spaces(self):
        tmp = tempfile.mkdtemp()
        d = os.path.join(tmp, "dir with spaces")
        os.makedirs(d)
        p = os.path.join(d, "db.sqlite")
        store.init_db(p).close()
        r = OwnershipRadar.open(p)
        self.assertEqual(r.dataset_info().schema_version, "1")

    def test_init_db_bare_filename(self):
        tmp = tempfile.mkdtemp()
        cwd = os.getcwd()
        try:
            os.chdir(tmp)
            cx = store.init_db("bare.sqlite")
            cx.close()
            self.assertTrue(os.path.isfile("bare.sqlite"))
        finally:
            os.chdir(cwd)


class IngestionContractTest(unittest.TestCase):
    def test_start_run_named_columns(self):
        cx = store.init_db(
            os.path.join(tempfile.mkdtemp(), "x.sqlite"))
        rid = ingest.start_run(cx, "BACKFILL", "ALL", "v1")
        row = cx.execute("SELECT run_type,scope,universe_version FROM "
                         "crawl_run WHERE run_id=?", (rid,)).fetchone()
        self.assertEqual(row, ("BACKFILL", "ALL", "v1"))

    def test_scan_retry_respects_issuer_scope(self):
        """Regression: retry_statuses must not bypass issuer_ids —
        the old unparenthesized OR re-fetched every errored doc in
        the dataset regardless of scope."""
        cx = store.init_db(
            os.path.join(tempfile.mkdtemp(), "x.sqlite"))
        for nk, iid, tok in (("nod:a", "A39000013", "TOKA"),
                             ("nod:b", "Z99999999", "TOKB")):
            cx.execute("""INSERT INTO notice(notice_key,source_surface,
                          source_registration_number,issuer_id,
                          filing_date,doc_token)
                          VALUES(?,?,?,?,'2024-01-01',?)""",
                       (nk, "nod", nk, iid, tok))
            cx.execute("""INSERT INTO notice_doc(notice_key,doc_status)
                          VALUES(?,'EXTRACTION_ERROR')""", (nk,))
        cx.commit()
        fx = _ErrFetcher()
        pipeline.scan_docs(cx, fx, "r", issuer_ids=["A39000013"],
                           retry_statuses=("EXTRACTION_ERROR",))
        self.assertEqual(len(fx.calls), 1)
        self.assertIn("TOKA", fx.calls[0])

    def test_fetch_error_is_retryable_not_not_pdf(self):
        """Regression: a transient fetch failure must record
        EXTRACTION_ERROR (retryable), never a permanent content
        verdict like NOT_PDF."""
        cx = store.init_db(
            os.path.join(tempfile.mkdtemp(), "x.sqlite"))
        cx.execute("""INSERT INTO notice(notice_key,source_surface,
                      source_registration_number,issuer_id,filing_date,
                      doc_token)
                      VALUES('nod:x','nod','x','A1','2024-01-01','TK')""")
        cx.commit()
        fx = _ErrFetcher()
        pipeline.scan_docs(cx, fx, "r")
        st = cx.execute("SELECT doc_status FROM notice_doc WHERE "
                        "notice_key='nod:x'").fetchone()[0]
        self.assertEqual(st, "EXTRACTION_ERROR")

    def test_report_is_read_only(self):
        """Regression: `ingest report`/`invariants` must not mutate
        the dataset — previously they persisted the shipped universe
        seed into whatever DB was being inspected."""
        import sqlite3
        path = _build()
        before = sqlite3.connect(
            "file:%s?mode=ro" % path.replace(os.sep, "/"),
            uri=True).execute(
            "SELECT COUNT(*) FROM universe_issuer").fetchone()[0]
        os.environ["RADAR_PROD_DB"] = path
        try:
            from ownership_radar.__main__ import _ingest
            with redirect_stdout(io.StringIO()):
                _ingest(["report"])
        finally:
            del os.environ["RADAR_PROD_DB"]
        after = sqlite3.connect(
            "file:%s?mode=ro" % path.replace(os.sep, "/"),
            uri=True).execute(
            "SELECT COUNT(*) FROM universe_issuer").fetchone()[0]
        self.assertEqual(before, after)

    def test_report_missing_db_errors(self):
        os.environ["RADAR_PROD_DB"] = os.path.join(
            tempfile.mkdtemp(), "absent.sqlite")
        try:
            from ownership_radar.__main__ import _ingest
            with self.assertRaises(SystemExit) as cm:
                _ingest(["report"])
            self.assertEqual(cm.exception.code, 1)
            self.assertFalse(os.path.exists(
                os.environ["RADAR_PROD_DB"]))
        finally:
            del os.environ["RADAR_PROD_DB"]


if __name__ == "__main__":
    unittest.main()
