"""G6-A storage/query hardening tests.

fact_version_relation as a VIEW must produce the identical logical
row set the stored table produced under G4 (digest is the proof).
Ambiguous ANNULS targets are public as AMBIGUOUS and never resolved
to a single terminal.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

from ownership_radar import ledger, store  # noqa:E402


def _db():
    tmp = tempfile.mkdtemp()
    return store.init_db(os.path.join(tmp, "t.sqlite"))


def _notice(cx, key, surface="ps", obs="2024-01-01T00:00:00+00:00"):
    cx.execute("""INSERT OR IGNORE INTO notice(notice_key,
                  source_surface,source_registration_number,issuer_id)
                  VALUES(?,?,?,?)""",
               (key, surface, key.split(":", 1)[1], "A1"))
    cx.execute("""INSERT INTO notice_observation(run_id,notice_key,
                  observed_at,present_in_source) VALUES('r',?,?,1)""",
               (key, obs))


def _fact(cx, notice_key, idx=0):
    cx.execute("""INSERT INTO source_fact(fact_id,notice_key,fact_type,
                  fact_index,source_payload_sha256,first_observed_at)
                  VALUES(?,?,?,?,?,?)""",
               (f"F:{notice_key}:{idx}", notice_key, "T", idx,
                "x" * 64, "2024-01-01T00:00:00+00:00"))


def _annuls(cx, annulling, annulled):
    cx.execute("""INSERT INTO notice_relation(annulling_key,
                  annulled_key,relation_type) VALUES(?,?,'ANNULS')""",
               (annulling, annulled))


class TestFactVersionRelationView(unittest.TestCase):
    def test_view_matches_all_pairs_semantics(self):
        """The view yields exactly the G4 all-pairs projection."""
        cx = _db()
        for k in ("ps:a", "ps:b"):
            _notice(cx, k)
        _fact(cx, "ps:a", 0)
        _fact(cx, "ps:a", 1)
        _fact(cx, "ps:b", 0)
        _annuls(cx, "ps:b", "ps:a")
        rows = sorted(cx.execute(
            "SELECT from_fact_id,to_fact_id,relation_type,basis,"
            "annulling_notice_key,observed_at "
            "FROM fact_version_relation").fetchall())
        self.assertEqual(len(rows), 2)  # 2 facts of a x 1 fact of b
        for fa, fb, rel, basis, ann, obs in rows:
            self.assertTrue(fa.startswith("F:ps:a:"))
            self.assertEqual(fb, "F:ps:b:0")
            self.assertEqual(rel, "CANCELLED_BY")
            self.assertEqual(basis, "NOTICE_RELATION:ANNULS")
            self.assertEqual(ann, "ps:b")
            self.assertEqual(obs, "2024-01-01T00:00:00+00:00")

    def test_view_rectifies_and_no_fact_pairs(self):
        """RECTIFIES maps to RECTIFIED_BY; relations where a side has
        no facts produce no rows (mirrors the old `not in by_notice`
        skip)."""
        cx = _db()
        for k in ("ps:a", "ps:b", "ps:c"):
            _notice(cx, k)
        _fact(cx, "ps:a")
        _fact(cx, "ps:b")
        cx.execute("""INSERT INTO notice_relation VALUES
                      ('ps:b','ps:a','RECTIFIES',NULL,NULL,NULL)""")
        _annuls(cx, "ps:c", "ps:a")  # ps:c has no facts -> no rows
        rows = cx.execute(
            "SELECT relation_type FROM fact_version_relation").fetchall()
        self.assertEqual([r[0] for r in rows], ["RECTIFIED_BY"])

    def test_not_a_table(self):
        cx = _db()
        kind = cx.execute("SELECT type FROM sqlite_master WHERE name="
                          "'fact_version_relation'").fetchone()[0]
        self.assertEqual(kind, "view")


class TestAmbiguousAnnuls(unittest.TestCase):
    def test_ambiguous_never_resolved(self):
        cx = _db()
        for k in ("ps:t", "ps:x", "ps:y"):
            _notice(cx, k)
        _annuls(cx, "ps:x", "ps:t")
        _annuls(cx, "ps:y", "ps:t")
        st = ledger.annulment_status(cx, "ps:t")
        self.assertEqual(st["relation_status"], "AMBIGUOUS")
        self.assertEqual(st["annulled_notice"], "ps:t")
        self.assertEqual(st["annulling_notices"], ["ps:x", "ps:y"])
        self.assertIsNone(st["terminal"])
        ca = ledger.current_authoritative(cx, "ps:t")
        self.assertEqual(ca["status"], "AMBIGUOUS")
        self.assertIsNone(ca["authoritative"])

    def test_resolved_chain_and_authoritative(self):
        cx = _db()
        for k in ("ps:a", "ps:b", "ps:c"):
            _notice(cx, k)
        _annuls(cx, "ps:b", "ps:a")
        _annuls(cx, "ps:c", "ps:b")
        st = ledger.annulment_status(cx, "ps:a")
        self.assertEqual(st["relation_status"], "RESOLVED")
        self.assertEqual(st["terminal"], "ps:c")
        ca = ledger.current_authoritative(cx, "ps:a")
        self.assertEqual(ca["status"], "SUPERSEDED")
        self.assertEqual(ca["authoritative"], "ps:c")
        ca2 = ledger.current_authoritative(cx, "ps:c")
        self.assertEqual(ca2["status"], "AUTHORITATIVE")


if __name__ == "__main__":
    unittest.main()
