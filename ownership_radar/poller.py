"""Incremental poller — discovery + re-enumeration, never trust
today alone.

NOD: the surface supports GLOBAL date windows (no nif) — one query
enumerates every issuer's filings in [start,end]. Windows overlap
the last successful window (documented overlap, dedupe by notice_key,
never by URL).

PS/AC: BusquedaUltimosDias is a discovery HINT only (it lists
issuers, not registration numbers — G0). Changed issuers are
re-enumerated through the authoritative per-issuer surfaces and
diffed by notice_key.
"""
import json
from datetime import datetime, timedelta, timezone

from . import cnmv, ingest, pipeline, store
from .crawler import Fetcher

OVERLAP_DAYS = 10  # rolling overlap for the NOD global window;
# dedupe is by notice_key so overlap is harmless — it protects
# against late listings near window edges.


def _d(d):
    return d.strftime("%d/%m/%Y")


def incremental(cx, fx, run_id, issuers, overlap_days=OVERLAP_DAYS,
                docs=True):
    """One incremental pass. Returns stats."""
    universe_nifs = {e["nif"] for e in issuers.values()}
    stats = {"overlap_days": overlap_days}
    before = {r[0] for r in cx.execute("SELECT notice_key FROM notice")}

    # --- NOD global window [last_ok - overlap, today]
    last_ok = cx.execute(
        "SELECT MAX(started_at) FROM crawl_run WHERE status='OK' AND "
        "run_id<>?", (run_id,)).fetchone()[0]
    if last_ok:
        start = datetime.fromisoformat(last_ok) - timedelta(
            days=overlap_days)
    else:
        start = datetime.now(timezone.utc) - timedelta(
            days=overlap_days)
    end = datetime.now(timezone.utc)
    stats["nod_window"] = {"from": _d(start), "to": _d(end)}
    r = cnmv.collect_nod_window(fx, cx, run_id, store, _d(start),
                                _d(end), universe_nifs)
    stats["nod"] = r
    cx.commit()

    # --- PS/AC hint -> re-enumerate touched universe issuers
    hints = cnmv.last5days_ps_ac_issuers(fx, cx, run_id)
    touched = {h["nif"] for h in hints}
    stats["hint_issuers"] = sorted(touched)
    in_universe = touched & universe_nifs
    out_universe = touched - universe_nifs
    for nif in sorted(out_universe):
        cx.execute("INSERT OR IGNORE INTO discovered_issuer "
                   "VALUES(?,?,?,?,?)",
                   (nif, next((h["name_raw"] for h in hints
                               if h["nif"] == nif), None),
                    run_id, datetime.now(timezone.utc)
                    .isoformat(timespec="milliseconds"),
                    "last5days"))
    re_num = {}
    for ik in sorted(in_universe):
        e = issuers[ik]
        try:
            re_num[ik] = cnmv.collect_ps_ac(
                fx, cx, ik, {"nif": e["nif"], "name": e["name"]},
                run_id, store)
        except Exception as ex:  # noqa
            ingest.fail(cx, run_id, "incremental", ik, "ps_ac", None,
                        "enumerate", ex, retryable=True)
            re_num[ik] = "ERROR"
    stats["ps_ac_reenumerated"] = re_num
    cx.commit()

    # --- docs for whatever is new/unprocessed
    if docs:
        stats["docs"] = pipeline.scan_docs(cx, fx, run_id)

    after = {r[0] for r in cx.execute("SELECT notice_key FROM notice")}
    stats["new_notices"] = len(after - before)
    stats["new_notice_keys"] = sorted(after - before)[:200]
    ingest.register_blobs(cx, fx)
    cx.commit()
    return stats


def run(db_path, universe, run_id=None, overlap_days=OVERLAP_DAYS,
        docs=True, raw_root=ingest.RAW_DIR,
        blob_root=ingest.BLOB_DIR):
    issuers = universe[1]
    cx = store.init_db(db_path)
    rid = ingest.start_run(cx, "INCREMENTAL", "poller",
                           universe[0]["universe_version"], run_id)
    fx = Fetcher(rid, raw_root, blob_root=blob_root)
    try:
        stats = incremental(cx, fx, rid, issuers, overlap_days, docs)
        ingest.finish_run(cx, rid, {"stats": stats})
    except Exception as e:  # noqa
        ingest.finish_run(cx, rid, {"error": repr(e)}, ok=False)
        raise
    return rid, stats
