"""Internal crawl orchestration — `python -m ownership_radar crawl`
runs one SAN/BBVA observation pass into `data/radar.sqlite`.

This is the G1-era entry point used to produce the local listing
database that the corpus tooling (`scripts/fetch_*_corpus.py`) reads.
Production ingestion lives in `ingest.py` / `poller.py` (typed runs,
checkpoints, failure isolation).

A run is an append-only observation pass over the bounded issuer
universe. Output: data/raw/<run_id>/ (immutable captures), data/runs/,
data/radar.sqlite.
"""
import json
import os
from datetime import datetime, timezone

from . import PARSER_VERSION
from . import cnmv, store
from .crawler import Fetcher

# dataset paths are cwd-relative — a checkout convention, not
# package-relative (site-packages must never be a data dir)
DATA_DIR = os.environ.get("RADAR_DATA_DIR", "data")
DB_PATH = os.path.join(DATA_DIR, "radar.sqlite")
RAW_DIR = os.path.join(DATA_DIR, "raw")
RUNS_DIR = os.path.join(DATA_DIR, "runs")

ISSUERS = {
    "SAN": {"nif": "A39000013", "name": "BANCO SANTANDER, S.A."},
    "BBVA": {"nif": "A48265169", "name": "BANCO BILBAO VIZCAYA ARGENTARIA, S.A."},
}


def run(issuers=None):
    issuers = ISSUERS if issuers is None else issuers
    os.makedirs(RUNS_DIR, exist_ok=True)
    cx = store.init_db(DB_PATH)
    run_id = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
    t0 = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    cx.execute("""INSERT INTO crawl_run(run_id,started_at,completed_at,
                  source,parser_version,status,stats_json)
                  VALUES(?,?,?,?,?,?,NULL)""",
               (run_id, t0, None, "cnmv.es", PARSER_VERSION, "RUNNING"))
    cx.commit()
    fx = Fetcher(run_id, RAW_DIR)
    stats = {}
    try:
        fx.get(f"{cnmv.BASE}/portal/Consultas/BusquedaUltimosDias",
               note="ultimos_dias")
        for ik, issuer in issuers.items():
            cnmv.collect_issuer_identity(fx, cx, ik, issuer, run_id)
            stats[f"{ik}_nod"] = cnmv.collect_nod(fx, cx, ik, issuer, run_id, store)
            stats[f"{ik}_nod_legacy"] = cnmv.collect_nod_legacy(fx, cx, ik, issuer, run_id, store)
            stats[f"{ik}_ps_ac"] = cnmv.collect_ps_ac(fx, cx, ik, issuer, run_id, store)
            cx.commit()
        cx.execute("""UPDATE notice SET notice_status='ANULLED'
            WHERE notice_key IN (SELECT annulled_key FROM notice_relation
                                 WHERE relation_type='ANNULS')""")
        cx.execute("""UPDATE notice SET notice_status='RECTIFIED'
            WHERE notice_key IN (SELECT annulled_key FROM notice_relation
                                 WHERE relation_type='RECTIFIES')
              AND notice_status NOT IN ('ANULLED')""")
        stats["disappearances_marked"] = store.mark_disappearances(cx, run_id)
        stats["requests"] = fx.n
        t1 = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        cx.execute("UPDATE crawl_run SET completed_at=?,status=?,stats_json=? WHERE run_id=?",
                   (t1, "OK", json.dumps(stats), run_id))
        cx.commit()
        with open(os.path.join(RUNS_DIR, run_id + ".json"), "w",
                  encoding="utf-8") as f:
            json.dump({"run_id": run_id, "started_at": t0, "completed_at": t1,
                       "parser_version": PARSER_VERSION, "stats": stats,
                       "fetches": fx.log}, f, ensure_ascii=False, indent=1)
        print(json.dumps({"run_id": run_id, "stats": stats}, indent=1))
    except Exception as e:
        cx.execute("UPDATE crawl_run SET status=? WHERE run_id=?",
                   ("ERROR:" + repr(e), run_id))
        cx.commit()
        raise
    return run_id


if __name__ == "__main__":
    run()
