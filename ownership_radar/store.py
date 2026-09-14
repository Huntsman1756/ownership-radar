"""Storage layer — canonical projection + append-only observations.

Invariants enforced here:
  * notice_key = (source_surface, source_registration_number)
  * notice_observation is INSERT-only — history is never rewritten
  * the canonical notice projection is UPSERTed and may be corrected by
    later observations; the audit trail lives in notice_observation
  * disappearances are recorded as present_in_source=0 observations with
    status SOURCE_DISAPPEARANCE_OBSERVED — never auto-promoted

Dimensions kept independent (G0 design finding):
  source_surface      where CNMV exposed it (nod | nod_legacy | ps | ac)
  notice_type         semantic kind (PDMR_TRANSACTION | DIRECTOR_NOTIFICATION
                      | SIGNIFICANT_HOLDING | TREASURY_STOCK | UNCLASSIFIED)
  regulatory_template document model generation (NULL until fingerprinted)
"""
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS crawl_run(
 run_id TEXT PRIMARY KEY, started_at TEXT, completed_at TEXT,
 source TEXT, parser_version TEXT, status TEXT, stats_json TEXT);
CREATE TABLE IF NOT EXISTS issuer(
 issuer_id TEXT PRIMARY KEY, nif TEXT, lei TEXT, name_raw TEXT,
 capital_raw TEXT, observed_run_id TEXT);
CREATE TABLE IF NOT EXISTS notice(
 notice_key TEXT PRIMARY KEY,
 source_surface TEXT NOT NULL,
 source_registration_number TEXT NOT NULL,
 notice_type TEXT NOT NULL DEFAULT 'UNCLASSIFIED',
 notice_type_basis TEXT NOT NULL DEFAULT 'NONE',
 regulatory_template TEXT,
 issuer_id TEXT, regime TEXT, filing_date TEXT, notice_status TEXT,
 identity_status TEXT, doc_token TEXT, declarant_name_raw TEXT,
 declarant_role TEXT, declarant_scope_issuer_id TEXT,
 pct_a TEXT, pct_b TEXT, pct_total TEXT, extra_json TEXT,
 first_seen_run TEXT, last_seen_run TEXT);
CREATE TABLE IF NOT EXISTS notice_observation(
 obs_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, notice_key TEXT,
 observed_at TEXT, raw_sha256 TEXT, normalized_sha256 TEXT,
 source_url_observed TEXT, source_url_canonical TEXT,
 status_observed TEXT, present_in_source INTEGER);
CREATE TABLE IF NOT EXISTS notice_relation(
 annulling_key TEXT, annulled_key TEXT, relation_type TEXT,
 evidence_url TEXT, observed_run_id TEXT, evidence_sha256 TEXT,
 PRIMARY KEY(annulling_key, annulled_key, relation_type));
CREATE TABLE IF NOT EXISTS event(
 notice_key TEXT, event_index INTEGER, event_date TEXT,
 declarant_name_raw TEXT, declarant_role TEXT, declarant_scope_issuer_id TEXT,
 shares TEXT, percentage_before TEXT, percentage_after TEXT, price TEXT,
 instrument TEXT, evidence TEXT,
 PRIMARY KEY(notice_key, event_index));
CREATE TABLE IF NOT EXISTS run_seen(
 run_id TEXT, notice_key TEXT, PRIMARY KEY(run_id, notice_key));
"""

# Conservative surface-level defaults only. The ps surface deliberately
# stays UNCLASSIFIED: before 2020-03-02 it mixes DIRECTOR_HOLDING
# (Circular 8/2015 Modelo 2) and SIGNIFICANT_HOLDING — a surface label
# must never be promoted to a semantic type without evidence.
SURFACE_TYPE_DEFAULT = {
    "nod":        ("PDMR_TRANSACTION", "SURFACE_DEFAULT"),
    "nod_legacy": ("DIRECTOR_NOTIFICATION", "SURFACE_DEFAULT"),
    "ac":         ("TREASURY_STOCK", "SURFACE_DEFAULT"),
    "ps":         ("UNCLASSIFIED", "NONE"),
}

_CONTENT_EXCLUDED = {"raw_sha256", "source_url_observed",
                     "source_url_canonical"}


def sha256b(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def connect(path):
    cx = sqlite3.connect(path)
    cx.execute("PRAGMA journal_mode=WAL")
    return cx


def init_db(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cx = connect(path)
    cx.executescript(SCHEMA)
    cx.commit()
    return cx


def regime_of(surface, filing):
    if surface == "nod":
        return "MAR_2018_NOD"
    if surface == "nod_legacy":
        return "PRE_2018_LEGACY"
    if surface in ("ps", "ac") and filing:
        return "CIRC2_2022" if filing >= "2022-08-07" else "RD1362_2007_CIRC8_2015"
    return "UNKNOWN"


def upsert_notice(cx, n, run_id):
    key = f"{n['source_surface']}:{n['source_registration_number']}"
    ntype, nbasis = SURFACE_TYPE_DEFAULT.get(n["source_surface"],
                                             ("UNCLASSIFIED", "NONE"))
    regime = regime_of(n["source_surface"], n.get("filing_date"))
    norm = json.dumps({k: v for k, v in n.items() if k not in _CONTENT_EXCLUDED},
                      sort_keys=True, ensure_ascii=False)
    nsha = sha256b(norm.encode())
    cur = cx.execute("SELECT notice_key FROM notice WHERE notice_key=?",
                     (key,)).fetchone()
    if cur:
        cx.execute("""UPDATE notice SET last_seen_run=?,
                      filing_date=COALESCE(?,filing_date),
                      doc_token=COALESCE(?,doc_token),
                      declarant_name_raw=COALESCE(?,declarant_name_raw),
                      declarant_role=COALESCE(?,declarant_role),
                      pct_a=COALESCE(?,pct_a), pct_b=COALESCE(?,pct_b),
                      pct_total=COALESCE(?,pct_total),
                      extra_json=COALESCE(?,extra_json)
                      WHERE notice_key=?""",
                   (run_id, n.get("filing_date"), n.get("doc_token"),
                    n.get("declarant_name_raw"), n.get("declarant_role"),
                    n.get("pct_a"), n.get("pct_b"), n.get("pct_total"),
                    json.dumps({"info_adicional": n.get("extra"),
                                "list_origin": n.get("list_origin")},
                               ensure_ascii=False)
                    if (n.get("extra") or n.get("list_origin")) else None,
                    key))
    else:
        cx.execute("""INSERT INTO notice(notice_key,source_surface,
                      source_registration_number,notice_type,notice_type_basis,
                      regulatory_template,issuer_id,regime,filing_date,
                      notice_status,identity_status,doc_token,
                      declarant_name_raw,declarant_role,
                      declarant_scope_issuer_id,pct_a,pct_b,pct_total,
                      extra_json,first_seen_run,last_seen_run)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (key, n["source_surface"], n["source_registration_number"],
                    ntype, nbasis, n.get("regulatory_template"),
                    n.get("issuer_id"), regime, n.get("filing_date"),
                    n.get("notice_status", "ACTIVE"),
                    "OFFICIAL_REGISTRY_NUMBER" if n["source_registration_number"]
                    else "PROVISIONAL_CONTENT_HASH",
                    n.get("doc_token"), n.get("declarant_name_raw"),
                    n.get("declarant_role"), n.get("issuer_id"),
                    n.get("pct_a"), n.get("pct_b"), n.get("pct_total"),
                    json.dumps({"info_adicional": n.get("extra"),
                                "list_origin": n.get("list_origin")},
                               ensure_ascii=False),
                    run_id, run_id))
    cx.execute("""INSERT INTO notice_observation(run_id,notice_key,observed_at,
                  raw_sha256,normalized_sha256,source_url_observed,
                  source_url_canonical,status_observed,present_in_source)
                  VALUES(?,?,?,?,?,?,?,?,1)""",
               (run_id, key, datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                n.get("raw_sha256"), nsha, n.get("source_url_observed"),
                n.get("source_url_canonical"), n.get("notice_status", "ACTIVE")))
    cx.execute("INSERT OR IGNORE INTO run_seen VALUES(?,?)", (run_id, key))
    cx.execute("""INSERT OR REPLACE INTO event VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
               (key, 0, n.get("filing_date"), n.get("declarant_name_raw"),
                n.get("declarant_role"), n.get("issuer_id"), None,
                None, n.get("pct_total"), None, None, "LISTING_STUB"))


def add_relation(cx, a, b, rel, url, run_id, sha):
    cx.execute("INSERT OR IGNORE INTO notice_relation VALUES(?,?,?,?,?,?)",
               (a, b, rel, url, run_id, sha))


def mark_disappearances(cx, run_id):
    rows = cx.execute("""SELECT n.notice_key FROM notice n
        WHERE n.last_seen_run<>? AND n.first_seen_run<>?""",
        (run_id, run_id)).fetchall()
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    for (k,) in rows:
        cx.execute("""INSERT INTO notice_observation(run_id,notice_key,
            observed_at,raw_sha256,normalized_sha256,source_url_observed,
            source_url_canonical,status_observed,present_in_source)
            VALUES(?,?,?,NULL,NULL,NULL,NULL,'SOURCE_DISAPPEARANCE_OBSERVED',0)""",
            (run_id, k, now))
    return len(rows)
