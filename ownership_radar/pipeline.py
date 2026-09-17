"""Document pipeline — raw PDF bytes -> semantic parse -> persist.

Classification taxonomy (fail-closed, never silently dropped):

    PARSED                        fingerprint matched, parse ok
    PARSED_WITH_UNMAPPED_VALUES   parsed, some cells unmapped
    UNSUPPORTED_TEMPLATE          text layer ok, fingerprint unknown
    UNSUPPORTED_LEGACY_TEMPLATE   pre-supported-era model
    UNSUPPORTED_NO_TEXT_LAYER     no extractable text (scan)
    NO_DOCUMENT_AVAILABLE         listing carries no doc token
    NOT_PDF                       token resolved to non-PDF bytes
    EXTRACTION_ERROR              pdfminer/parser raised
    NOT_FETCHED_LEGACY_ERA        outside supported era, not fetched

ps surface caveat (G0/G3): it mixes SIGNIFICANT_HOLDING and
DIRECTOR_HOLDING (Circular 8/2015 Modelo 2). pspdf fingerprints the
document; a Modelo-2 director form is UNSUPPORTED for the G3
significant-holdings parser, not an error.
"""
import logging
from datetime import datetime, timezone

from . import acpdf, nodpdf, pspdf, store

NO_DOC = "NO_DOCUMENT_AVAILABLE"
NOT_PDF = "NOT_PDF"
NOT_FETCHED = "NOT_FETCHED_LEGACY_ERA"
ERR = "EXTRACTION_ERROR"

# supported-era start: Circular 8/2015 models enter 28/12/2015
SUPPORTED_ERA_PS_AC = "2015-12-28"

PARSERS = {"nod": nodpdf, "ps": pspdf, "ac": acpdf}


def doc_scope(notice):
    """Should this notice's document be fetched for semantics?"""
    surf = notice["source_surface"]
    if surf == "nod":
        return True
    if surf in ("ps", "ac"):
        fd = notice.get("filing_date")
        return bool(fd) and fd >= SUPPORTED_ERA_PS_AC
    return False  # nod_legacy and anything unknown


def _persist(cx, surface, notice_key, p, corpus_split=None):
    if surface == "nod":
        store.store_semantic(cx, notice_key, p, corpus_split)
    elif surface == "ps":
        store.store_ps_semantic(cx, notice_key, p, corpus_split)
    elif surface == "ac":
        store.store_ac_semantic(cx, notice_key, p, corpus_split)


def process_doc(cx, notice_key, surface, body, run_id,
                raw_sha256=None, corpus_split=None):
    """Parse PDF bytes for one notice; persist semantics; update
    notice_doc + notice.regulatory_template. Returns doc_status."""
    parser = PARSERS[surface]
    try:
        p = parser.parse_pdf(body)
    except Exception as e:  # noqa
        logging.getLogger(__name__).warning(
            "parse error %s: %r", notice_key, e)
        p = {"parse_status": ERR,
             "semantic_parser_version": parser.SEMANTIC_PARSER_VERSION,
             "parse_notes": repr(e)[:400]}
    status = p.get("parse_status") or ERR
    if status not in (ERR,):
        try:
            _persist(cx, surface, notice_key, p, corpus_split)
        except Exception as e:  # noqa
            logging.getLogger(__name__).warning(
                "persist error %s: %r", notice_key, e)
            status = ERR
            p["parse_notes"] = repr(e)[:400]
    cx.execute("""INSERT OR REPLACE INTO notice_doc VALUES(?,?,?,?,?,?,?)""",
               (notice_key, status, raw_sha256,
                datetime.now(timezone.utc)
                .isoformat(timespec="milliseconds"), run_id, status,
                p.get("semantic_parser_version")))
    return status


def fetch_and_process(fx, cx, notice, run_id):
    """Fetch + parse one notice's document through verdocumento."""
    nk = notice["notice_key"]
    token = notice.get("doc_token")
    if not token:
        cx.execute("""INSERT OR REPLACE INTO notice_doc
                      VALUES(?,?,NULL,NULL,NULL,NULL,NULL)""",
                   (nk, NO_DOC))
        return NO_DOC
    meta, body = fx.get(
        "https://www.cnmv.es/webservices/verdocumento/ver?e=" + token,
        note=f"doc {nk}")
    if meta.get("status") == "ERROR" or not body:
        # transient fetch failure — a retryable class, never a
        # content verdict
        cx.execute("""INSERT OR REPLACE INTO notice_doc
                      VALUES(?,?,?,?,?,NULL,NULL)""",
                   (nk, ERR, meta.get("raw_sha256"),
                    meta.get("retrieved_at"), run_id))
        return ERR
    if body[:4] != b"%PDF":
        cx.execute("""INSERT OR REPLACE INTO notice_doc
                      VALUES(?,?,?,?,?,NULL,NULL)""",
                   (nk, NOT_PDF, meta.get("raw_sha256"),
                    meta.get("retrieved_at"), run_id))
        return NOT_PDF
    _register_blob(cx, meta)
    return process_doc(cx, nk, notice["source_surface"], body, run_id,
                       raw_sha256=meta.get("raw_sha256"))


def _register_blob(cx, meta):
    if not meta.get("raw_sha256"):
        return
    cx.execute("""INSERT OR IGNORE INTO raw_blob VALUES(?,?,?,?,?,?)""",
               (meta["raw_sha256"], meta.get("raw_file"),
                meta.get("raw_bytes"), meta.get("content_type"),
                meta.get("run_id"), meta.get("retrieved_at")))


def scan_docs(cx, fx, run_id, issuer_ids=None,
              surfaces=("nod", "ps", "ac", "nod_legacy"),
              limit=None, filing_since=None, retry_statuses=()):
    """Fetch+process pending docs for a scope. Resumable: notices
    already classified in notice_doc are skipped. `filing_since`
    bounds the document window (notices earlier than that stay
    UNPROCESSED — bounded scope is documented, not hidden).
    `retry_statuses` reprocesses transient classes (EXTRACTION_ERROR,
    NOT_PDF) without re-fetching permanently-unsupported classes —
    UNSUPPORTED_*/NO_DOCUMENT_AVAILABLE are deterministic results,
    not failures (§29)."""
    q = """SELECT n.notice_key, n.source_surface, n.doc_token,
                  n.filing_date, n.issuer_id
           FROM notice n
           LEFT JOIN notice_doc d ON d.notice_key = n.notice_key
           WHERE (d.notice_key IS NULL"""
    params = []
    if retry_statuses:
        q += (" OR d.doc_status IN (%s)" %
              ",".join("?" * len(retry_statuses)))
        params += list(retry_statuses)
    q += ")"
    if filing_since:
        q += " AND (n.filing_date IS NULL OR n.filing_date>=?)"
        params.append(filing_since)
    if issuer_ids is not None:
        q += " AND n.issuer_id IN (%s)" % ",".join("?" * len(issuer_ids))
        params += list(issuer_ids)
    if surfaces:
        q += " AND n.source_surface IN (%s)" % ",".join(
            "?" * len(surfaces))
        params += list(surfaces)
    q += " ORDER BY n.issuer_id, n.filing_date, n.notice_key"
    if limit:
        q += f" LIMIT {int(limit)}"
    stats = {"fetched": 0, "skipped_legacy": 0}
    from collections import Counter
    by_status = Counter()
    for row in cx.execute(q, params).fetchall():
        n = {"notice_key": row[0], "source_surface": row[1],
             "doc_token": row[2], "filing_date": row[3],
             "issuer_id": row[4]}
        if not doc_scope(n):
            cx.execute("""INSERT OR REPLACE INTO notice_doc
                          VALUES(?,?,NULL,NULL,NULL,NULL,NULL)""",
                       (n["notice_key"], NOT_FETCHED))
            stats["skipped_legacy"] += 1
            by_status[NOT_FETCHED] += 1
            continue
        st = fetch_and_process(fx, cx, n, run_id)
        stats["fetched"] += 1
        by_status[st] += 1
        if stats["fetched"] % 50 == 0:
            cx.commit()
    cx.commit()
    stats["by_status"] = dict(by_status)
    return stats
