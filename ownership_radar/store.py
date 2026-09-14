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
  notice_type         semantic kind (PDMR_NOTIFICATION | DIRECTOR_NOTIFICATION
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
-- G2 semantic layer (nodpdf). Decimals stored as exact TEXT plus the
-- raw literal; aggregate QA never rewrites the declared CNMV value.
CREATE TABLE IF NOT EXISTS nod_notice_semantic(
 notice_key TEXT PRIMARY KEY,
 semantic_parser_version TEXT, regulatory_template TEXT,
 parse_status TEXT, parse_notes TEXT,
 notification_kind TEXT, amendment_text_raw TEXT,
 notifying_party_name_raw TEXT, notifying_party_kind TEXT,
 position_status_raw TEXT, closely_associated TEXT,
 related_pdmr_name_raw TEXT, related_pdmr_position_raw TEXT,
 issuer_name_document TEXT, issuer_lei_document TEXT,
 additional_info_raw TEXT,
 doc_sha256 TEXT, pdf_engine TEXT, corpus_split TEXT, parsed_at TEXT);
CREATE TABLE IF NOT EXISTS transaction_event(
 event_id TEXT PRIMARY KEY,          -- notice_key:NN (doc order only)
 notice_key TEXT NOT NULL, source_order INTEGER NOT NULL,
 instrument_code_raw TEXT, instrument_type_raw TEXT,
 transaction_nature_raw TEXT, transaction_nature_normalized TEXT,
 share_option_program_linked TEXT,
 transaction_date_raw TEXT, transaction_date TEXT,
 venue_raw TEXT, venue_code_raw TEXT, outside_trading_venue TEXT,
 declared_aggregate_volume TEXT, declared_aggregate_price TEXT,
 declared_price_currency TEXT, declared_quantity_currency TEXT,
 computed_volume TEXT, computed_vwap TEXT, aggregate_qa TEXT);
CREATE TABLE IF NOT EXISTS execution_line(
 event_id TEXT NOT NULL, line_index INTEGER NOT NULL,
 price_raw TEXT, price TEXT, price_currency TEXT,
 volume_raw TEXT, volume TEXT, quantity_currency TEXT,
 PRIMARY KEY(event_id, line_index));
-- G3-A semantic layer (pspdf). A PS notice is a position disclosure,
-- NOT a trade: the tables below model declared position components and
-- must never be read as BUY/SELL events. Decimals are exact TEXT plus
-- raw literal; declared aggregates are never overwritten by computed QA.
CREATE TABLE IF NOT EXISTS ps_notice_semantic(
 notice_key TEXT PRIMARY KEY,
 semantic_parser_version TEXT, regulatory_template TEXT,
 parse_status TEXT, parse_notes TEXT,
 issuer_name_document TEXT, registry_stamp_raw TEXT,
 obliged_subject_name_raw TEXT, obliged_subject_residence_raw TEXT,
 reason_voting_rights INTEGER, reason_voting_rights_regulated INTEGER,
 reason_instruments INTEGER, reason_instruments_regulated INTEGER,
 reason_issuer_voting_rights_change INTEGER, reason_other INTEGER,
 reason_other_text_raw TEXT, concerted_agreement INTEGER,
 shareholders_raw TEXT,
 threshold_date_raw TEXT, threshold_date TEXT,
 percentage_semantics TEXT,
 position_current_json TEXT, position_previous_json TEXT,
 issuer_total_voting_rights_raw TEXT, issuer_total_voting_rights TEXT,
 shares_subtotal_json TEXT, instruments_a_subtotal_json TEXT,
 instruments_b_subtotal_json TEXT,
 subject_control_flag TEXT, chain_info_text_raw TEXT,
 proxy_voting_rights_raw TEXT, proxy_pct_raw TEXT,
 proxy_meeting_date_raw TEXT,
 additional_info_raw TEXT, annulment_json TEXT,
 loyalty_section_present INTEGER,
 loyalty_11a_json TEXT, loyalty_11a_rows_json TEXT,
 loyalty_11b_rows_json TEXT,
 signature_raw TEXT, aggregate_qa TEXT,
 doc_sha256 TEXT, pdf_engine TEXT, corpus_split TEXT, parsed_at TEXT);
CREATE TABLE IF NOT EXISTS ps_shares_row(
 notice_key TEXT NOT NULL, row_index INTEGER NOT NULL,
 isin TEXT, vr_direct_raw TEXT, vr_direct TEXT,
 vr_indirect_raw TEXT, vr_indirect TEXT,
 pct_direct_raw TEXT, pct_direct TEXT,
 pct_indirect_raw TEXT, pct_indirect TEXT, raw_json TEXT,
 PRIMARY KEY(notice_key, row_index));
CREATE TABLE IF NOT EXISTS ps_instrument_row(
 notice_key TEXT NOT NULL, section TEXT NOT NULL, row_index INTEGER NOT NULL,
 instrument_type_raw TEXT, expiration_raw TEXT, expiration_date TEXT,
 exercise_period_raw TEXT, settlement_raw TEXT,
 voting_rights_raw TEXT, voting_rights TEXT,
 pct_raw TEXT, pct TEXT, raw_json TEXT,
 PRIMARY KEY(notice_key, section, row_index));
CREATE TABLE IF NOT EXISTS ps_control_chain_row(
 notice_key TEXT NOT NULL, source TEXT NOT NULL,
 chain_path_index INTEGER NOT NULL, row_index INTEGER NOT NULL,
 entity_name_raw TEXT,
 pct_voting_rights_raw TEXT, pct_instruments_raw TEXT,
 pct_total_raw TEXT,
 PRIMARY KEY(notice_key, source, chain_path_index, row_index));
CREATE TABLE IF NOT EXISTS ps_loyalty_row(
 notice_key TEXT NOT NULL, section TEXT NOT NULL, row_index INTEGER NOT NULL,
 attribution_date_raw TEXT, attribution_date TEXT, raw_json TEXT,
 PRIMARY KEY(notice_key, section, row_index));
-- G3-B semantic layer (acpdf). section-4 rows are the operation FLOW;
-- the section-5 final position is the resulting STOCK; the section-2
-- 1% checkbox is the declared regulatory TRIGGER. Three layers, kept
-- separate: disposals are never netted against cumulative acquisitions.
CREATE TABLE IF NOT EXISTS ac_notice_semantic(
 notice_key TEXT PRIMARY KEY,
 semantic_parser_version TEXT, regulatory_template TEXT,
 parse_status TEXT, parse_notes TEXT,
 registry_stamp_raw TEXT, issuer_nif_raw TEXT,
 issuer_name_document TEXT,
 issuer_voting_rights_raw TEXT, issuer_voting_rights TEXT,
 reason_first_admission INTEGER, reason_acquisitions_1pct INTEGER,
 reason_voting_rights_update INTEGER,
 notification_date_raw TEXT, notification_date TEXT,
 total_acquisitions_json TEXT, total_transmissions_json TEXT,
 operations_flow_qa_json TEXT, final_position_json TEXT,
 indirect_controlled_checked INTEGER,
 indirect_controlled_pct_raw TEXT, total_indirect_pct_raw TEXT,
 indirect_controlled_empty INTEGER, indirect_interposed_empty INTEGER,
 indirect_other_empty INTEGER,
 chain_detail_raw TEXT, additional_info_raw TEXT, signature_raw TEXT,
 doc_sha256 TEXT, pdf_engine TEXT, corpus_split TEXT, parsed_at TEXT);
CREATE TABLE IF NOT EXISTS ac_operation(
 notice_key TEXT NOT NULL, row_index INTEGER NOT NULL,
 operation_date_raw TEXT, operation_date TEXT,
 operation_flag_raw TEXT, operation_flag_normalized TEXT, isin TEXT,
 shares_direct_raw TEXT, shares_direct TEXT,
 price_direct_raw TEXT, price_direct TEXT,
 shares_indirect_raw TEXT, shares_indirect TEXT,
 price_indirect_raw TEXT, price_indirect TEXT,
 vr_direct_raw TEXT, vr_direct TEXT, vr_indirect_raw TEXT, vr_indirect TEXT,
 pct_direct_raw TEXT, pct_direct TEXT,
 pct_indirect_raw TEXT, pct_indirect TEXT, raw_json TEXT,
 PRIMARY KEY(notice_key, row_index));
CREATE TABLE IF NOT EXISTS ac_indirect_row(
 notice_key TEXT NOT NULL, section TEXT NOT NULL, row_index INTEGER NOT NULL,
 name_raw TEXT, pct_raw TEXT,
 PRIMARY KEY(notice_key, section, row_index));
-- G4 ledger layer (ledger.py). source_fact rows are SOURCE_DECLARED
-- content with deterministic identity; ledger_event rows are built by
-- versioned derivation rules and are fully rebuildable from facts +
-- relations + the rule registry. derived_at is intentionally absent:
-- no wallclock may contaminate deterministic digests.
CREATE TABLE IF NOT EXISTS source_fact(
 fact_id TEXT PRIMARY KEY,
 notice_key TEXT NOT NULL, fact_type TEXT NOT NULL,
 fact_index INTEGER NOT NULL,
 effective_date TEXT, filing_date TEXT,
 semantic_parser TEXT, semantic_parser_version TEXT,
 source_payload_json TEXT, source_payload_sha256 TEXT,
 raw_sha256 TEXT, first_observed_at TEXT);
CREATE TABLE IF NOT EXISTS fact_version_relation(
 from_fact_id TEXT NOT NULL, to_fact_id TEXT NOT NULL,
 relation_type TEXT NOT NULL, basis TEXT NOT NULL,
 annulling_notice_key TEXT, observed_at TEXT,
 PRIMARY KEY(from_fact_id, to_fact_id, relation_type));
CREATE TABLE IF NOT EXISTS derivation_rule(
 rule_id TEXT PRIMARY KEY, rule_version TEXT NOT NULL,
 event_type TEXT NOT NULL, description TEXT,
 legal_basis TEXT, effective_from TEXT, effective_to TEXT);
CREATE TABLE IF NOT EXISTS ledger_event(
 event_id TEXT PRIMARY KEY,
 event_type TEXT NOT NULL, event_basis TEXT NOT NULL,
 issuer_id TEXT,
 effective_date TEXT, filing_date TEXT,
 source_notice_key TEXT, source_fact_id TEXT,
 rule_id TEXT, derivation_version TEXT,
 payload_json TEXT, payload_sha256 TEXT,
 first_observed_at TEXT);
"""

# Conservative surface-level defaults only. The ps surface deliberately
# stays UNCLASSIFIED: before 2020-03-02 it mixes DIRECTOR_HOLDING
# (Circular 8/2015 Modelo 2) and SIGNIFICANT_HOLDING — a surface label
# must never be promoted to a semantic type without evidence.
SURFACE_TYPE_DEFAULT = {
    "nod":        ("PDMR_NOTIFICATION", "SURFACE_DEFAULT"),
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
    # forward-only column migrations for existing databases
    cols = {r[1] for r in cx.execute(
        "PRAGMA table_info(nod_notice_semantic)")}
    if "pdf_engine" not in cols:
        cx.execute("ALTER TABLE nod_notice_semantic "
                   "ADD COLUMN pdf_engine TEXT")
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


def store_semantic(cx, notice_key, p, corpus_split=None):
    """Persist one nodpdf parse result. Idempotent per notice_key —
    events/lines are replaced wholesale by the same parser version."""
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    cx.execute("""INSERT OR REPLACE INTO nod_notice_semantic(
        notice_key,semantic_parser_version,regulatory_template,
        parse_status,parse_notes,notification_kind,amendment_text_raw,
        notifying_party_name_raw,notifying_party_kind,
        position_status_raw,closely_associated,related_pdmr_name_raw,
        related_pdmr_position_raw,issuer_name_document,
        issuer_lei_document,additional_info_raw,doc_sha256,pdf_engine,
        corpus_split,parsed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (notice_key, p.get("semantic_parser_version"),
         p.get("regulatory_template"), p.get("parse_status"),
         json.dumps(p.get("unmapped") or [], ensure_ascii=False) or None,
         p.get("notification_kind"), p.get("amendment_text_raw"),
         p.get("notifying_party_name_raw"), p.get("notifying_party_kind"),
         p.get("position_status_raw"), p.get("closely_associated"),
         p.get("related_pdmr_name_raw"), p.get("related_pdmr_position_raw"),
         p.get("issuer_name_document"), p.get("issuer_lei_document"),
         p.get("additional_info_raw"), p.get("doc_sha256"),
         p.get("pdf_engine"), corpus_split, now))
    if p.get("regulatory_template") and \
            p["regulatory_template"].startswith("EU_"):
        cx.execute("UPDATE notice SET regulatory_template=? WHERE notice_key=?",
                   (p["regulatory_template"], notice_key))
    cx.execute("""DELETE FROM execution_line WHERE event_id IN
                  (SELECT event_id FROM transaction_event
                   WHERE notice_key=?)""", (notice_key,))
    cx.execute("DELETE FROM transaction_event WHERE notice_key=?",
               (notice_key,))
    for ev in p.get("events") or []:
        eid = f"{notice_key}:{ev['source_order']:02d}"
        ccy = {e.get("currency") for e in ev["executions"]}
        ccy = ccy.pop() if len(ccy) == 1 else None
        cx.execute("""INSERT INTO transaction_event VALUES(
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (eid, notice_key, ev["source_order"],
             ev.get("instrument_code_raw"), ev.get("instrument_type_raw"),
             ev.get("transaction_nature_raw"),
             ev.get("transaction_nature_normalized"),
             ev.get("share_option_program_linked"),
             ev.get("transaction_date_raw"), ev.get("transaction_date"),
             ev.get("venue_raw"), ev.get("venue_code_raw"),
             ev.get("outside_trading_venue"),
             ev.get("declared_aggregate_volume"),
             ev.get("declared_aggregate_price"),
             ccy, None,
             ev.get("computed_volume"), ev.get("computed_vwap"),
             ev.get("aggregate_qa")))
        for i, e in enumerate(ev["executions"]):
            cx.execute("INSERT INTO execution_line VALUES(?,?,?,?,?,?,?,?)",
                       (eid, i, e.get("price_raw"),
                        str(e["price"]) if e.get("price") is not None else None,
                        e.get("currency"), e.get("volume_raw"),
                        str(e["volume"]) if e.get("volume") is not None
                        else None, None))


def _js(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True) \
        if v is not None else None


def _b(v):
    return None if v is None else (1 if v else 0)


def store_ps_semantic(cx, notice_key, p, corpus_split=None):
    """Persist one pspdf parse result (G3-A). Idempotent per
    notice_key: child rows are replaced wholesale per parse."""
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    cx.execute("""INSERT OR REPLACE INTO ps_notice_semantic(
        notice_key,semantic_parser_version,regulatory_template,
        parse_status,parse_notes,issuer_name_document,registry_stamp_raw,
        obliged_subject_name_raw,obliged_subject_residence_raw,
        reason_voting_rights,reason_voting_rights_regulated,
        reason_instruments,reason_instruments_regulated,
        reason_issuer_voting_rights_change,reason_other,
        reason_other_text_raw,concerted_agreement,shareholders_raw,
        threshold_date_raw,threshold_date,percentage_semantics,
        position_current_json,position_previous_json,
        issuer_total_voting_rights_raw,issuer_total_voting_rights,
        shares_subtotal_json,instruments_a_subtotal_json,
        instruments_b_subtotal_json,subject_control_flag,
        chain_info_text_raw,proxy_voting_rights_raw,proxy_pct_raw,
        proxy_meeting_date_raw,additional_info_raw,annulment_json,
        loyalty_section_present,loyalty_11a_json,loyalty_11a_rows_json,
        loyalty_11b_rows_json,signature_raw,aggregate_qa,
        doc_sha256,pdf_engine,corpus_split,parsed_at)
        VALUES(""" + ",".join(["?"] * 45) + """)""",
        (notice_key, p.get("semantic_parser_version"),
         p.get("regulatory_template"), p.get("parse_status"),
         _js(p.get("unmapped") or []), p.get("issuer_name_document"),
         p.get("registry_stamp_raw"), p.get("obliged_subject_name_raw"),
         p.get("obliged_subject_residence_raw"),
         _b(p.get("reason_voting_rights")),
         _b(p.get("reason_voting_rights_regulated")),
         _b(p.get("reason_instruments")),
         _b(p.get("reason_instruments_regulated")),
         _b(p.get("reason_issuer_voting_rights_change")),
         _b(p.get("reason_other")), p.get("reason_other_text_raw"),
         _b(p.get("concerted_agreement")), p.get("shareholders_raw"),
         p.get("threshold_date_raw"), p.get("threshold_date"),
         p.get("percentage_semantics"),
         _js(p.get("position_current")), _js(p.get("position_previous")),
         p.get("issuer_total_voting_rights_raw"),
         (str(p["issuer_total_voting_rights"])
          if p.get("issuer_total_voting_rights") is not None else None),
         _js(p.get("shares_subtotal")),
         _js(p.get("instruments_a_subtotal")),
         _js(p.get("instruments_b_subtotal")),
         p.get("subject_control_flag"), p.get("chain_info_text_raw"),
         p.get("proxy_voting_rights_raw"), p.get("proxy_pct_raw"),
         p.get("proxy_meeting_date_raw"), p.get("additional_info_raw"),
         _js(p.get("annulment")),
         _b(p.get("loyalty_section_present")),
         _js(p.get("loyalty_11a")), _js(p.get("loyalty_11a_rows")),
         _js(p.get("loyalty_11b_rows")), p.get("signature_raw"),
         p.get("aggregate_qa"), p.get("doc_sha256"),
         p.get("pdf_engine"), corpus_split, now))
    if p.get("regulatory_template"):
        cx.execute("UPDATE notice SET regulatory_template=? "
                   "WHERE notice_key=?",
                   (p["regulatory_template"], notice_key))
    for tbl in ("ps_shares_row", "ps_instrument_row",
                "ps_control_chain_row", "ps_loyalty_row"):
        cx.execute(f"DELETE FROM {tbl} WHERE notice_key=?", (notice_key,))
    for r in p.get("shares_rows") or []:
        cx.execute("INSERT INTO ps_shares_row VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                   (notice_key, r["row_index"], r.get("isin"),
                    r.get("vr_direct_raw"),
                    _txt(r.get("vr_direct")),
                    r.get("vr_indirect_raw"), _txt(r.get("vr_indirect")),
                    r.get("pct_direct_raw"), _txt(r.get("pct_direct")),
                    r.get("pct_indirect_raw"), _txt(r.get("pct_indirect")),
                    _js(r.get("raw_cells"))))
    for sec, rows in (("7.B.1", p.get("instruments_a_rows") or []),
                      ("7.B.2", p.get("instruments_b_rows") or [])):
        for r in rows:
            cx.execute("""INSERT INTO ps_instrument_row VALUES
                          (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (notice_key, sec, r["row_index"],
                        r.get("instrument_type_raw"), r.get("expiration_raw"),
                        r.get("expiration_date"), r.get("exercise_period_raw"),
                        r.get("settlement_raw"), r.get("voting_rights_raw"),
                        _txt(r.get("voting_rights")), r.get("pct_raw"),
                        _txt(r.get("pct")), _js(r.get("raw_cells"))))
    for r in p.get("chain_rows") or []:
        cx.execute("INSERT INTO ps_control_chain_row VALUES(?,?,?,?,?,?,?,?)",
                   (notice_key, r["source"], r["chain_path_index"],
                    r["row_index"], r.get("entity_name_raw"),
                    r.get("pct_voting_rights_raw"),
                    r.get("pct_instruments_raw"), r.get("pct_total_raw")))
    for sec, rows in (("11.A", p.get("loyalty_11a_rows") or []),
                      ("11.B", p.get("loyalty_11b_rows") or [])):
        for r in rows:
            cx.execute("INSERT INTO ps_loyalty_row VALUES(?,?,?,?,?,?)",
                       (notice_key, sec, r["row_index"],
                        r.get("attribution_date_raw"),
                        r.get("attribution_date"), _js(r.get("raw_cells"))))


def _txt(v):
    return None if v is None else str(v)


def store_ac_semantic(cx, notice_key, p, corpus_split=None):
    """Persist one acpdf parse result (G3-B). Flow rows (section 4),
    declared totals, resulting stock (section 5) and the declared 1%
    trigger are stored as distinct layers."""
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    cx.execute("""INSERT OR REPLACE INTO ac_notice_semantic(
        notice_key,semantic_parser_version,regulatory_template,
        parse_status,parse_notes,registry_stamp_raw,issuer_nif_raw,
        issuer_name_document,issuer_voting_rights_raw,
        issuer_voting_rights,reason_first_admission,
        reason_acquisitions_1pct,reason_voting_rights_update,
        notification_date_raw,notification_date,
        total_acquisitions_json,total_transmissions_json,
        operations_flow_qa_json,final_position_json,
        indirect_controlled_checked,indirect_controlled_pct_raw,
        total_indirect_pct_raw,indirect_controlled_empty,
        indirect_interposed_empty,indirect_other_empty,
        chain_detail_raw,additional_info_raw,signature_raw,
        doc_sha256,pdf_engine,corpus_split,parsed_at)
        VALUES(""" + ",".join(["?"] * 32) + """)""",
        (notice_key, p.get("semantic_parser_version"),
         p.get("regulatory_template"), p.get("parse_status"),
         _js(p.get("unmapped") or []), p.get("registry_stamp_raw"),
         p.get("issuer_nif_raw"), p.get("issuer_name_document"),
         p.get("issuer_voting_rights_raw"),
         _txt(p.get("issuer_voting_rights")),
         _b(p.get("reason_first_admission")),
         _b(p.get("reason_acquisitions_1pct")),
         _b(p.get("reason_voting_rights_update")),
         p.get("notification_date_raw"), p.get("notification_date"),
         _js(p.get("total_acquisitions")),
         _js(p.get("total_transmissions")),
         _js(p.get("operations_flow_qa")), _js(p.get("final_position")),
         _b(p.get("indirect_controlled_checked")),
         p.get("indirect_controlled_pct_raw"),
         p.get("total_indirect_pct_raw"),
         _b(p.get("indirect_controlled_empty")),
         _b(p.get("indirect_interposed_empty")),
         _b(p.get("indirect_other_empty")),
         p.get("chain_detail_raw"), p.get("additional_info_raw"),
         p.get("signature_raw"), p.get("doc_sha256"),
         p.get("pdf_engine"), corpus_split, now))
    if p.get("regulatory_template"):
        cx.execute("UPDATE notice SET regulatory_template=? "
                   "WHERE notice_key=?",
                   (p["regulatory_template"], notice_key))
    cx.execute("DELETE FROM ac_operation WHERE notice_key=?",
               (notice_key,))
    cx.execute("DELETE FROM ac_indirect_row WHERE notice_key=?",
               (notice_key,))
    for o in p.get("operations") or []:
        cx.execute("""INSERT INTO ac_operation VALUES(
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (notice_key, o["row_index"], o.get("operation_date_raw"),
             o.get("operation_date"), o.get("operation_flag_raw"),
             o.get("operation_flag_normalized"), o.get("isin"),
             o.get("shares_direct_raw"), _txt(o.get("shares_direct")),
             o.get("price_direct_raw"), _txt(o.get("price_direct")),
             o.get("shares_indirect_raw"), _txt(o.get("shares_indirect")),
             o.get("price_indirect_raw"), _txt(o.get("price_indirect")),
             o.get("vr_direct_raw"), _txt(o.get("vr_direct")),
             o.get("vr_indirect_raw"), _txt(o.get("vr_indirect")),
             o.get("pct_direct_raw"), _txt(o.get("pct_direct")),
             o.get("pct_indirect_raw"), _txt(o.get("pct_indirect")),
             _js(o.get("raw_cells"))))
    for sec, rows in (("6.1", p.get("indirect_controlled") or []),
                      ("6.2", p.get("indirect_interposed") or []),
                      ("6.3", p.get("indirect_other") or [])):
        for i, r in enumerate(rows):
            cx.execute("INSERT INTO ac_indirect_row VALUES(?,?,?,?,?)",
                       (notice_key, sec, i, r.get("name_raw"),
                        r.get("pct_raw")))


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
