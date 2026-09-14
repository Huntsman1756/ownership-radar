"""Coverage reporting + production invariants + dataset manifest.

Coverage is reported with explicit denominators per layer:
acquisition (enumerated) -> document (token present) -> template
support -> semantic parse -> ledger. A single "%" without denominators
is not a coverage figure.
"""
import hashlib
import json
import os
from collections import Counter, defaultdict

from . import ledger, store

DOC_ERA = "2015-12-28"


def coverage_matrix(cx, universe_version=None):
    """issuer x family x status counts with explicit denominators."""
    q = """SELECT n.issuer_id, n.source_surface,
                  COUNT(*) total,
                  SUM(CASE WHEN n.doc_token IS NOT NULL THEN 1 ELSE 0 END) with_doc,
                  SUM(CASE WHEN n.filing_date >= ? THEN 1 ELSE 0 END) supported_era,
                  MIN(n.filing_date), MAX(n.filing_date)
           FROM notice n GROUP BY n.issuer_id, n.source_surface
           ORDER BY n.issuer_id, n.source_surface"""
    rows = cx.execute(q, (DOC_ERA,)).fetchall()
    doc_stats = {r[0]: r[1] for r in cx.execute(
        "SELECT notice_key, doc_status FROM notice_doc")}
    matrix = {}
    for ik, surf, total, with_doc, era, fmin, fmax in rows:
        e = matrix.setdefault(ik, {})
        e[surf] = {"enumerated": total, "with_doc_token": with_doc,
                   "supported_era": era if surf in ("ps", "ac") else total,
                   "filing_range": [fmin, fmax]}
    for ik, surf, total, *_ in rows:
        ks = [r[0] for r in cx.execute(
            "SELECT notice_key FROM notice WHERE issuer_id=? AND "
            "source_surface=?", (ik, surf))]
        c = Counter(doc_stats.get(k, "UNPROCESSED") for k in ks)
        matrix[ik][surf]["doc_status"] = dict(c)
    return matrix


def global_metrics(cx, universe_issuers=None):
    iss_attempted = {r[0] for r in cx.execute(
        "SELECT DISTINCT issuer_id FROM notice")}
    notices = cx.execute("SELECT COUNT(*) FROM notice").fetchone()[0]
    docs = Counter(r[0] for r in cx.execute(
        "SELECT doc_status FROM notice_doc"))
    templates = Counter((r[0] or "NULL") for r in cx.execute(
        "SELECT regulatory_template FROM notice"))
    facts = cx.execute("SELECT COUNT(*) FROM source_fact").fetchone()[0]
    events = cx.execute("SELECT COUNT(*) FROM ledger_event").fetchone()[0]
    obs = cx.execute("SELECT COUNT(*) FROM notice_observation").fetchone()[0]
    blobs = cx.execute("SELECT COUNT(*),COALESCE(SUM(raw_bytes),0) "
                       "FROM raw_blob").fetchone()
    rels = cx.execute("SELECT COUNT(*) FROM notice_relation").fetchone()[0]
    # §22: an observed `A ANNULS B` relation is official evidence on
    # its own; whether B's own raw was captured is a separate fact.
    cro = cx.execute("SELECT COUNT(*) FROM notice_relation WHERE "
                     "relation_type='ANNULS'").fetchone()[0]
    cnro = cx.execute("""SELECT COUNT(*) FROM notice_relation r
                         JOIN notice n ON n.notice_key=r.annulled_key
                         WHERE r.relation_type='ANNULS'""").fetchone()[0]
    fails = cx.execute("SELECT COUNT(*) FROM failed_item").fetchone()[0]
    disc = cx.execute("SELECT COUNT(*) FROM discovered_issuer").fetchone()[0]
    return {
        "issuers_attempted": len(iss_attempted),
        "issuers_universe": len(universe_issuers or {}),
        "notices_enumerated": notices,
        "observations": obs,
        "raw_blobs": blobs[0], "raw_bytes": blobs[1],
        "doc_status": dict(docs),
        "templates": dict(templates),
        "source_facts": facts, "ledger_events": events,
        "relations": rels,
        "cancellation_relations_observed": cro,
        "cancelled_notice_raw_observed": cnro,
        "failed_items": fails,
        "discovered_issuers": disc,
    }


def unknown_templates(cx):
    """UNKNOWN/failed fingerprints grouped for the discovery report."""
    out = defaultdict(list)
    for tbl, nk_col in (("ps_notice_semantic", "notice_key"),
                        ("ac_notice_semantic", "notice_key"),
                        ("nod_notice_semantic", "notice_key")):
        for r in cx.execute(
                f"SELECT {nk_col}, regulatory_template, parse_status, "
                f"doc_sha256 FROM {tbl} WHERE parse_status IN "
                f"('UNSUPPORTED_TEMPLATE','EXTRACTION_ERROR')"):
            out[r[2]].append({"notice_key": r[0],
                              "template": r[1], "doc_sha256": r[2]})
    return dict(out)


def legacy_inventory(cx):
    """Explicit frontier: legacy era / no-doc / no-text, by family+year."""
    rows = cx.execute("""
        SELECT n.source_surface,
               SUBSTR(n.filing_date,1,4) yr,
               d.doc_status, COUNT(*)
        FROM notice n LEFT JOIN notice_doc d
          ON d.notice_key=n.notice_key
        WHERE COALESCE(d.doc_status,'UNPROCESSED') <> 'PARSED'
        GROUP BY n.source_surface, yr, d.doc_status
        ORDER BY n.source_surface, yr""").fetchall()
    inv = defaultdict(lambda: defaultdict(int))
    for surf, yr, st, c in rows:
        inv[surf][(yr or "?") + ":" + (st or "?")] += c
    return {k: dict(v) for k, v in inv.items()}


def invariants(cx):
    """G5-19 production invariants. Returns list of violations."""
    v = []
    q = lambda s: cx.execute(s).fetchone()[0]
    if q("SELECT COUNT(*) FROM (SELECT notice_key FROM notice GROUP BY "
         "notice_key HAVING COUNT(*)>1)"):
        v.append("duplicate notice_key")
    if q("SELECT COUNT(*) FROM source_fact f LEFT JOIN notice n ON "
         "f.notice_key=n.notice_key WHERE n.notice_key IS NULL"):
        v.append("source_fact without notice")
    if q("SELECT COUNT(*) FROM ledger_event e LEFT JOIN source_fact f "
         "ON e.source_fact_id=f.fact_id WHERE e.source_fact_id IS NOT "
         "NULL AND f.fact_id IS NULL"):
        v.append("ledger_event with dangling source_fact_id")
    if q("SELECT COUNT(*) FROM ledger_event WHERE source_fact_id IS "
         "NULL AND event_type NOT IN ('NOTICE_FILED','NOTICE_CANCELLED')"):
        v.append("non-notice event without fact")
    if q("SELECT COUNT(*) FROM notice_observation WHERE run_id IS NULL"):
        v.append("observation without run_id")
    if q("SELECT COUNT(*) FROM raw_blob WHERE raw_sha256 IS NULL OR "
         "raw_sha256=''"):
        v.append("raw reference without sha256")
    if q("SELECT COUNT(*) FROM notice_relation WHERE annulling_key NOT "
         "LIKE '%:%' OR annulled_key NOT LIKE '%:%'"):
        v.append("malformed notice key in relation")
    _t, errors = ledger.resolve_annulment_chains(cx)
    if errors:
        v.append("ANNULS graph errors: %r" % errors[:5])
    return v


def dataset_manifest(cx, universe_meta):
    runs = [dict(zip(("run_id", "run_type", "started_at", "completed_at",
                      "status", "scope"),
                     r)) for r in cx.execute(
        "SELECT run_id,run_type,started_at,completed_at,status,scope "
        "FROM crawl_run ORDER BY started_at")]
    m = {
        "dataset_version": ledger.ledger_digest(cx),
        "universe_version": universe_meta["universe_version"],
        "universe_sha256": universe_meta["content_sha256"],
        "runs": runs,
        "metrics": global_metrics(cx, {}),
        "semantic_parsers": {"nod": "nodpdf-0.1.0", "ps": "pspdf-0.1.0",
                             "ac": "acpdf-0.1.0"},
        "derivation_version": ledger.DERIVATION_VERSION,
        "schema": "g5",
    }
    return m


def report(cx, universe):
    matrix = coverage_matrix(cx)
    return {"metrics": global_metrics(cx, universe[1]),
            "coverage_matrix": matrix,
            "unknown_templates": unknown_templates(cx),
            "legacy_inventory": legacy_inventory(cx),
            "invariant_violations": invariants(cx),
            "manifest": dataset_manifest(cx, universe[0])}
