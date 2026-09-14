"""Production ingestion — checkpointed, failure-isolated runs.

Run types: BACKFILL (first universe pass), RECONCILIATION (periodic
re-enumeration), INCREMENTAL (poller-driven, see poller.py).

Every run records run_type + scope + universe_version on crawl_run.
Checkpoints live per (run_id, scope_key); a crashed run resumes by
skipping DONE scopes — never by page numbers or process memory.
Failures are isolated into failed_item and the run continues.
"""
import json
import os
import sqlite3
from datetime import datetime, timezone

from . import cnmv, pipeline, store
from .crawler import Fetcher

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROD_DIR = os.path.join(REPO_ROOT, "data", "production")
DB_PATH = os.path.join(PROD_DIR, "ownership-radar.sqlite")
RAW_DIR = os.path.join(PROD_DIR, "raw")
BLOB_DIR = os.path.join(PROD_DIR, "blobs")

RUN_TYPES = ("BACKFILL", "INCREMENTAL", "RECONCILIATION")

FAMILIES = {"nod": cnmv.collect_nod,
            "nod_legacy": cnmv.collect_nod_legacy,
            "ps_ac": cnmv.collect_ps_ac}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def start_run(cx, run_type, scope, universe_version=None,
              run_id=None):
    assert run_type in RUN_TYPES
    run_id = run_id or datetime.now(timezone.utc).strftime(
        run_type.lower() + "-%Y%m%dT%H%M%SZ")
    cx.execute("INSERT INTO crawl_run VALUES(?,?,?,?,?,?,?,?,?,?)",
               (run_id, _now(), None, "cnmv.es", None, "RUNNING",
                None, run_type, scope, universe_version))
    cx.commit()
    return run_id


def finish_run(cx, run_id, stats, ok=True):
    cx.execute("""UPDATE crawl_run SET completed_at=?,status=?,
                  stats_json=? WHERE run_id=?""",
               (_now(), "OK" if ok else "ERROR",
                json.dumps(stats, ensure_ascii=False), run_id))
    cx.commit()


def checkpoint(cx, run_id, scope_key, status, cursor=None):
    cx.execute("""INSERT OR REPLACE INTO crawl_checkpoint
                  VALUES(?,?,?,?,?)""",
               (run_id, scope_key, status,
                json.dumps(cursor) if cursor is not None else None,
                _now()))
    cx.commit()


def done_scopes(cx, run_id):
    return {r[0] for r in cx.execute(
        "SELECT scope_key FROM crawl_checkpoint WHERE run_id=? AND "
        "status='DONE'", (run_id,))}


def fail(cx, run_id, scope_key, issuer_id, family, notice_key, stage,
         error, retryable):
    cx.execute("""INSERT INTO failed_item VALUES(?,?,?,?,?,?,?,?,?,?)""",
               (run_id, scope_key, issuer_id, family, notice_key,
                stage, type(error).__name__[:80],
                1 if retryable else 0, repr(error)[:400], _now()))


def register_blobs(cx, fx):
    for meta in fx.log:
        if meta.get("raw_sha256"):
            cx.execute("""INSERT OR IGNORE INTO raw_blob
                          VALUES(?,?,?,?,?,?)""",
                       (meta["raw_sha256"], meta.get("raw_file"),
                        meta.get("raw_bytes"), meta.get("content_type"),
                        meta.get("run_id"), meta.get("retrieved_at")))


def enumerate_issuer(fx, cx, issuer_id, issuer, run_id, families):
    """One issuer, per-family failure isolation."""
    stats = {}
    for fam in families:
        try:
            stats[fam] = FAMILIES[fam](fx, cx, issuer_id, issuer,
                                       run_id, store)
        except Exception as e:  # noqa
            stats[fam] = "ERROR"
            fail(cx, run_id, issuer_id, issuer_id, fam, None,
                 "enumerate", e, retryable=True)
    cx.commit()
    return stats


def enumerate_universe(cx, fx, issuers, run_id,
                       families=("nod", "ps_ac", "nod_legacy")):
    """Checkpointed enumeration over the issuer universe."""
    done = done_scopes(cx, run_id)
    stats = {}
    for ik in sorted(issuers):
        scope = f"enum:{ik}"
        if scope in done:
            stats[ik] = "SKIPPED_DONE"
            continue
        istats = enumerate_issuer(
            fx, cx, ik, {"nif": issuers[ik]["nif"],
                         "name": issuers[ik]["name"]},
            run_id, families)
        stats[ik] = istats
        checkpoint(cx, run_id, scope, "DONE",
                   {"families": list(istats)})
    return stats


def docs_universe(cx, fx, issuers, run_id, per_issuer_checkpoint=True,
                  filing_since=None):
    """Fetch+process supported-era docs, checkpointed per issuer."""
    done = done_scopes(cx, run_id)
    stats = {}
    for ik in sorted(issuers):
        scope = f"docs:{ik}:{filing_since or 'all'}"
        if per_issuer_checkpoint and scope in done:
            stats[ik] = "SKIPPED_DONE"
            continue
        try:
            stats[ik] = pipeline.scan_docs(cx, fx, run_id,
                                           issuer_ids=[ik],
                                           filing_since=filing_since)
        except Exception as e:  # noqa
            stats[ik] = "ERROR"
            fail(cx, run_id, scope, ik, "docs", None, "docs", e,
                 retryable=True)
        checkpoint(cx, run_id, scope, "DONE", stats.get(ik)
                   if isinstance(stats.get(ik), dict) else None)
    return stats


def finalize(cx, fx, run_id, issuer_ids):
    """Post-pass: status propagation, scoped disappearances, blobs."""
    cx.execute("""UPDATE notice SET notice_status='ANULLED'
        WHERE notice_key IN (SELECT annulled_key FROM notice_relation
                             WHERE relation_type='ANNULS')""")
    cx.execute("""UPDATE notice SET notice_status='RECTIFIED'
        WHERE notice_key IN (SELECT annulled_key FROM notice_relation
                             WHERE relation_type='RECTIFIES')
          AND notice_status NOT IN ('ANULLED')""")
    n_disp = store.mark_disappearances(cx, run_id,
                                       issuer_ids=issuer_ids)
    register_blobs(cx, fx)
    cx.commit()
    return {"disappearances_marked": n_disp, "requests": fx.n}


def backfill(db_path, universe, families=("nod", "ps_ac", "nod_legacy"),
             docs=True, run_id=None, issuers=None, filing_since=None,
             raw_root=RAW_DIR, blob_root=BLOB_DIR):
    """First full pass over the universe (or a subset)."""
    issuers = issuers if issuers is not None else universe[1]
    cx = store.init_db(db_path)
    scope = "universe:" + ",".join(sorted(issuers)[:5]) + \
        (f"+{len(issuers)-5}" if len(issuers) > 5 else "")
    run_id = start_run(cx, "BACKFILL", scope, universe[0]
                       ["universe_version"], run_id)
    fx = Fetcher(run_id, raw_root, blob_root=blob_root)
    stats = {"universe_version": universe[0]["universe_version"],
             "issuers": len(issuers), "filing_since": filing_since}
    try:
        stats["enumeration"] = enumerate_universe(cx, fx, issuers,
                                                  run_id, families)
        if docs:
            stats["docs"] = docs_universe(cx, fx, issuers, run_id,
                                          filing_since=filing_since)
        stats.update(finalize(cx, fx, run_id, list(issuers)))
        finish_run(cx, run_id, {"stats": stats})
    except Exception as e:  # noqa
        finish_run(cx, run_id, {"stats": stats, "error": repr(e)},
                   ok=False)
        raise
    return run_id, stats


def reconcile(db_path, universe, families=("nod", "ps_ac"),
              docs=True, run_id=None, issuers=None,
              raw_root=RAW_DIR, blob_root=BLOB_DIR):
    """Periodic re-enumeration: detects new notices, new relations,
    disappearances, late-arriving documents."""
    issuers = issuers if issuers is not None else universe[1]
    cx = store.init_db(db_path)
    scope = "reconcile:" + ",".join(sorted(issuers)[:5]) + \
        (f"+{len(issuers)-5}" if len(issuers) > 5 else "")
    run_id = start_run(cx, "RECONCILIATION", scope, universe[0]
                       ["universe_version"], run_id)
    fx = Fetcher(run_id, raw_root, blob_root=blob_root)
    before = {r[0] for r in cx.execute("SELECT notice_key FROM notice")}
    rel_before = {(r[0], r[1]) for r in cx.execute(
        "SELECT annulling_key,annulled_key FROM notice_relation")}
    stats = {"universe_version": universe[0]["universe_version"],
             "issuers": len(issuers)}
    try:
        stats["enumeration"] = enumerate_universe(cx, fx, issuers,
                                                  run_id, families)
        if docs:
            stats["docs"] = docs_universe(cx, fx, issuers, run_id)
        after = {r[0] for r in cx.execute("SELECT notice_key FROM notice")}
        rel_after = {(r[0], r[1]) for r in cx.execute(
            "SELECT annulling_key,annulled_key FROM notice_relation")}
        stats["new_notices"] = len(after - before)
        stats["new_relations"] = len(rel_after - rel_before)
        stats.update(finalize(cx, fx, run_id, list(issuers)))
        finish_run(cx, run_id, {"stats": stats})
    except Exception as e:  # noqa
        finish_run(cx, run_id, {"stats": stats, "error": repr(e)},
                   ok=False)
        raise
    return run_id, stats
