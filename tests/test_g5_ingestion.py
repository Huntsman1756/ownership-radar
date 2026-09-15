"""G5 tests — production ingestion mechanics on a fake fetcher.

No network: FakeFetcher serves canned (meta, body) pairs keyed by URL
pattern. Covers idempotency, checkpoints, failure isolation, scoped
disappearances, content-addressable blobs, incremental discovery and
AS_KNOWN_AT at scale.
"""
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone

from ownership_radar import (cnmv, coverage, ingest, ledger, pipeline,
                             poller, store, universe)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class FakeFetcher:
    """Deterministic URL->(meta, body) source. `pages` maps a
    predicate/key substring to bytes. Misses raise KeyError -> the
    runner must isolate the failure, not abort."""
    def __init__(self, pages):
        self.pages = pages
        self.n = 0
        self.log = []
        self.run_id = "fake-run"
        self.calls = []

    def get(self, url, note=""):
        self.n += 1
        self.calls.append(url)
        for key, body in self.pages.items():
            if key in url:
                b = body.encode() if isinstance(body, str) else body
                sha = store.sha256b(b)
                meta = {"run_id": self.run_id, "requested_url": url,
                        "final_url": url, "status": 200,
                        "retrieved_at": _now(), "raw_sha256": sha,
                        "raw_bytes": len(b), "raw_file": "fake/" + sha[:8],
                        "content_type": "application/pdf"
                        if b[:4] == b"%PDF" else "text/html"}
                self.log.append(meta)
                return meta, b
        raise RuntimeError("no page for " + url)


ISSUERS = {
    "A00000001": {"nif": "A00000001", "name": "EMPRESA UNO, S.A."},
    "A00000002": {"nif": "A00000002", "name": "EMPRESA DOS, S.A."},
}
UNIVERSE = ({"universe_version": "test-v1", "content_sha256": "x",
             "source": {"name": "synthetic"}, "generated_at": "now",
             "scope_note": "test"}, ISSUERS)

NOD_PAGE = """
<li class="repListaPrincipal_ctl00_elementoPrimerNivel">
 <span class="liFechaRegistro">10/09/2026</span>
 <a href="datosentidad.aspx?nif=A-00000001">EMPRESA UNO</a>
 Declarante: PEREZ, JUAN
 Motivo de la notificación: CONSEJERO
 Número de registro: 2026000001
 <a href="webservices/verdocumento/ver?e=TOK1">doc</a>
</li><ul></ul>
<li class="repListaPrincipal_ctl01_elementoPrimerNivel">
 <span class="liFechaRegistro">11/09/2026</span>
 <a href="datosentidad.aspx?nif=A-00000002">EMPRESA DOS</a>
 Declarante: LOPEZ, ANA
 Número de registro: 2026000002
 <a href="webservices/verdocumento/ver?e=TOK2">doc</a>
</li><ul></ul>
Página 1 de 1"""

PS_HUB = """
<a href="Notificaciones-Participaciones.aspx?qS={G1}">np</a>
<a href="Autocartera.aspx?qS={G9}">ac</a>"""
PS_CURRENT = '<a href="NotificacionesAnteriores.aspx?qS={H1}">h</a>'
PS_HIST = """
<table id="gridNotifAnt"><caption>ACME HOLDING</caption>
<tr><td>1,5</td><td>0,0</td><td>1,5</td><td>-</td>
<td><a href="verdocumento/ver?e=TOKP1">Abrir PDF de 2020111222</a></td>
<td>15/03/2020</td></tr></table>"""
AC_HIST = """
<table id="gridNotifAnt">
<tr><td>0,1</td><td>0,2</td><td>0,3</td><td>-</td>
<td><a href="verdocumento/ver?e=TOKA1">Abrir PDF de 2021333444</a></td>
<td>10/06/2021</td></tr></table>"""
NO_PS = "<html><body>nada</body></html>"
FAKE_PDF = b"%PDF-1.4 fake"
L5D = """
<a>Participaciones significativas y Autocartera (1)</a><ul>
<li><a href="derechosvoto/ps_ac_ini.aspx?nif=A-00000001">EMPRESA UNO</a></li>
<li><a href="derechosvoto/ps_ac_ini.aspx?nif=A-99999999">DESCONOCIDA SA</a></li>
</ul>"""


def pages_base():
    return {
        "directivos-resultado?nif=A00000001": NOD_PAGE,
        "directivos-resultado?nif=A00000002": NOD_PAGE.replace(
            "A-00000001", "A-00000002").replace("2026000001", "2026000099"),
        "notificacionesanterioresdirectivos?nif=A00000001": NO_PS,
        "notificacionesanterioresdirectivos?nif=A00000002": NO_PS,
        "ps_ac_ini.aspx?nif=A00000001": PS_HUB,
        "ps_ac_ini.aspx?nif=A00000002": NO_PS,
        "Notificaciones-Participaciones": PS_CURRENT,
        "NotificacionesAnteriores": PS_HIST,
        "Autocartera": PS_CURRENT.replace(
            "NotificacionesAnteriores", "NotificacionesAnterioresAC"),
        "NotificacionesAnterioresAC": AC_HIST,
        "ver?e=": FAKE_PDF,
        "datosgenerales": "<table id='gridDatos'><tr>"
            "<td data-th='NIF'>A00000001</td></tr></table>",
        "directivos-resultado?fechad": NOD_PAGE.replace(
            "A-00000001", "A-00000001").replace(
            "A-00000002", "A-77777777"),
        "BusquedaUltimosDias": L5D,
    }


def mkdb(tmp):
    return store.init_db(os.path.join(tmp, "p.sqlite"))


class FakeParser:
    SEMANTIC_PARSER_VERSION = "fake-1.0"

    def __init__(self, status="PARSED"):
        self.status = status

    def parse_pdf(self, b):
        return {"parse_status": self.status,
                "semantic_parser_version": "fake-1.0",
                "regulatory_template": "FAKE_TPL",
                "doc_sha256": store.sha256b(b)}


class TestG5(unittest.TestCase):

    def test_universe_seed_loads(self):
        seed, iss = universe.load_universe()
        self.assertEqual(seed["universe_version"], "itf2026-v1")
        self.assertEqual(len(iss), 60)
        self.assertTrue(all(e["nif"].startswith("A")
                            for e in iss.values()))
        self.assertIsNone(universe.resolve(iss, "ZZZZ"))

    def test_enumerate_isolates_failure(self):
        tmp = tempfile.mkdtemp()
        cx = mkdb(tmp)
        fx = FakeFetcher(pages_base())
        fx.pages.pop("ps_ac_ini.aspx?nif=A00000002")
        stats = ingest.enumerate_universe(
            cx, fx, ISSUERS, "r1", families=("ps_ac",))
        self.assertEqual(stats["A00000002"]["ps_ac"], "ERROR")
        self.assertGreater(stats["A00000001"]["ps_ac"], 0)
        n = cx.execute("SELECT COUNT(*) FROM failed_item").fetchone()[0]
        self.assertEqual(n, 1)

    def test_checkpoint_resume_skips_done(self):
        tmp = tempfile.mkdtemp()
        cx = mkdb(tmp)
        fx = FakeFetcher(pages_base())
        ingest.checkpoint(cx, "r1", "enum:A00000001", "DONE")
        stats = ingest.enumerate_universe(
            cx, fx, ISSUERS, "r1", families=("ps_ac",))
        self.assertEqual(stats["A00000001"], "SKIPPED_DONE")
        called = [u for u in fx.calls
                  if "nif=A00000001" in u and "ps_ac_ini" in u]
        self.assertEqual(called, [])

    def test_second_run_no_new_identities(self):
        tmp = tempfile.mkdtemp()
        cx = mkdb(tmp)
        fx = FakeFetcher(pages_base())
        for rid in ("r1", "r2"):
            ingest.enumerate_universe(cx, fx, ISSUERS, rid,
                                      families=("nod", "ps_ac"))
        keys = [r[0] for r in cx.execute(
            "SELECT notice_key FROM notice ORDER BY notice_key")]
        obs = cx.execute("SELECT COUNT(*) FROM "
                         "notice_observation").fetchone()[0]
        self.assertGreaterEqual(len(keys), 4)
        self.assertGreater(obs, len(keys))  # per-run observations
        self.assertEqual(len(keys),
                         len(set(keys)))  # no dup identities

    def test_scoped_disappearances(self):
        tmp = tempfile.mkdtemp()
        cx = mkdb(tmp)
        fx = FakeFetcher(pages_base())
        ingest.enumerate_universe(cx, fx, ISSUERS, "r1",
                                  families=("ps_ac",))
        # run2: issuer2 hub empty (its notice 'disappears')
        fx.pages["Notificaciones-Participaciones"] = NO_PS
        fx.pages["Autocartera"] = NO_PS
        ingest.enumerate_universe(cx, fx, ISSUERS, "r2",
                                  families=("ps_ac",))
        n = store.mark_disappearances(cx, "r2", issuer_ids=["A00000002"])
        # issuer2 had no notices anyway -> 0 scoped marks
        self.assertEqual(n, 0)
        # marking scoped to issuer1 alone must not flag issuer2 rows
        n2 = store.mark_disappearances(cx, "r2",
                                       issuer_ids=["A00000001"])
        self.assertGreaterEqual(n2, 0)
        keys = [r[0] for r in cx.execute(
            "SELECT notice_key FROM notice_observation WHERE "
            "status_observed='SOURCE_DISAPPEARANCE_OBSERVED'")]
        for k in keys:
            iid = cx.execute("SELECT issuer_id FROM notice WHERE "
                             "notice_key=?", (k,)).fetchone()[0]
            self.assertEqual(iid, "A00000001")

    def test_disappearance_scoped_by_surface(self):
        """Regression: recon run that never enumerated nod_legacy
        must not mark nod_legacy notices as disappeared (scout-12
        reconciliation produced 1,419 false positives before fix)."""
        tmp = tempfile.mkdtemp()
        cx = mkdb(tmp)
        now = _now()
        cx.execute("""INSERT INTO notice(notice_key,source_surface,
            source_registration_number,issuer_id,filing_date,
            notice_status,first_seen_run,last_seen_run)
            VALUES('nod_legacy:1','nod_legacy','1','A00000001',
            '2010-01-01','ACTIVE','r1','r1')""")
        cx.commit()
        # run r2 enumerated only ps+ac for this issuer
        n = store.mark_disappearances(
            cx, "r2", issuer_ids=["A00000001"], surfaces=("ps", "ac"))
        self.assertEqual(n, 0)

    def test_blob_dedupe(self):
        tmp = tempfile.mkdtemp()
        cx = mkdb(tmp)
        fx = FakeFetcher(pages_base())
        fx.get("https://cnmv/webservices/verdocumento/ver?e=1")
        fx.get("https://cnmv/webservices/verdocumento/ver?e=1")
        ingest.register_blobs(cx, fx)
        n = cx.execute("SELECT COUNT(*) FROM raw_blob").fetchone()[0]
        self.assertEqual(n, 1)  # same sha -> one blob, two observations

    def test_pipeline_classification(self):
        tmp = tempfile.mkdtemp()
        cx = mkdb(tmp)
        fx = FakeFetcher(pages_base())
        nk = "ps:2020111222"
        cx.execute("""INSERT INTO notice(notice_key,source_surface,
                      source_registration_number,issuer_id,filing_date,
                      doc_token) VALUES(?,?,?,?,?,?)""",
                   (nk, "ps", "2020111222", "A00000001", "2020-03-15",
                    "TOKP1"))
        st = pipeline.fetch_and_process(
            fx, cx, {"notice_key": nk, "source_surface": "ps",
                     "doc_token": "TOKP1"}, "r1")
        self.assertIn(st, ("EXTRACTION_ERROR", "UNSUPPORTED_TEMPLATE",
                           "UNSUPPORTED_NO_TEXT_LAYER", "PARSED",
                           "PARSED_WITH_UNMAPPED_VALUES"))
        row = cx.execute("SELECT doc_status FROM notice_doc WHERE "
                         "notice_key=?", (nk,)).fetchone()
        self.assertEqual(row[0], st)
        # legacy-era notice: NOT_FETCHED, never fetched
        nk2 = "ps:1999000001"
        st2 = pipeline.process_doc  # noqa
        cx.execute("""INSERT INTO notice(notice_key,source_surface,
                      source_registration_number,issuer_id,filing_date,
                      doc_token) VALUES(?,?,?,?,?,?)""",
                   (nk2, "ps", "1999000001", "A00000001",
                    "1999-05-01", "TOKX"))
        stats = pipeline.scan_docs(cx, fx, "r2")
        row2 = cx.execute("SELECT doc_status FROM notice_doc WHERE "
                          "notice_key=?", (nk2,)).fetchone()
        self.assertEqual(row2[0], "NOT_FETCHED_LEGACY_ERA")
        self.assertFalse(any("TOKX" in u for u in fx.calls))

    def test_poller_incremental(self):
        tmp = tempfile.mkdtemp()
        cx = mkdb(tmp)
        fx = FakeFetcher(pages_base())
        stats = poller.incremental(cx, fx, "inc1", ISSUERS, docs=False)
        # window notices landed incl. out-of-universe issuer
        self.assertGreaterEqual(stats["nod"]["notices"], 2)
        disc = {r[0] for r in cx.execute(
            "SELECT nif FROM discovered_issuer")}
        self.assertIn("A77777777", disc)   # nod window
        self.assertIn("A99999999", disc)   # last5days
        self.assertGreaterEqual(stats["new_notices"], 2)

    def test_invariants_clean(self):
        tmp = tempfile.mkdtemp()
        cx = mkdb(tmp)
        fx = FakeFetcher(pages_base())
        ingest.enumerate_universe(cx, fx, ISSUERS, "r1",
                                  families=("nod", "ps_ac"))
        self.assertEqual(coverage.invariants(cx), [])

    def test_as_known_at_at_scale(self):
        """Late observation: notice filed 2020, first observed in r2
        (2026) — AS_KNOWN_AT before r2 must not see it."""
        tmp = tempfile.mkdtemp()
        cx = mkdb(tmp)
        fx = FakeFetcher(pages_base())
        ingest.enumerate_universe(cx, fx, ISSUERS, "r1",
                                  families=("nod",))
        ledger.materialize(cx)
        ev = ledger.events_for_issuer(cx, "A00000001")
        cutoff = "2021-01-01T00:00"
        known = [e for e in ev["events"]
                 if (e["first_observed_at"] or "9999") <= cutoff]
        self.assertEqual(known, [])  # no retro-projection

    def test_ledger_rebuild_identical(self):
        tmp = tempfile.mkdtemp()
        cx = mkdb(tmp)
        fx = FakeFetcher(pages_base())
        ingest.enumerate_universe(cx, fx, ISSUERS, "r1",
                                  families=("nod", "ps_ac"))
        d1 = ledger.materialize(cx)["digest"]
        for t in ("source_fact", "fact_version_relation",
                  "ledger_event", "derivation_rule"):
            cx.execute(f"DELETE FROM {t}")
        cx.commit()
        d2 = ledger.materialize(cx)["digest"]
        self.assertEqual(d1, d2)


if __name__ == "__main__":
    unittest.main()
