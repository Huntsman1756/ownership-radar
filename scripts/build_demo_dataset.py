"""Build the distributable demo dataset — deterministic.

Creates demo/ownership-radar-demo.sqlite: a small, fully synthetic
dataset exercising the whole public surface (API, CLI, feed). No CNMV
raw documents are redistributed; every raw_sha256 is the hash of a
synthetic placeholder string, and notice contents are invented.

Determinism: all timestamps/ids are literals. Running the script
twice produces an identical logical digest (printed at the end).

Usage:
    python scripts/build_demo_dataset.py [output_path]
"""
import hashlib
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

from ownership_radar import store, ledger  # noqa:E402

TB = "2024-01-10T00:00:00+00:00"   # BACKFILL
T1 = "2024-03-01T00:00:00+00:00"   # INCREMENTAL
T2 = "2024-06-01T00:00:00+00:00"   # RECONCILIATION


def _sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def build(path):
    if os.path.exists(path):
        os.remove(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    cx = store.init_db(path)
    cx.execute("INSERT INTO universe_version VALUES(?,?,?,?,?)",
               ("demo-v1", "{}", "2024-01-01", _sha("demo-v1"),
                "synthetic demo universe"))
    issuers = (("A39000013", "BANCO SANTANDER, S.A.", "ES0113900J37",
                "SAN"),
               ("A48265169", "BANCO BILBAO VIZCAYA ARGENTARIA, S.A.",
                "ES0113211835", "BBVA"))
    for nif, name, isin, tick in issuers:
        cx.execute("INSERT INTO universe_issuer VALUES(?,?,?,?,?,?,?)",
                   ("demo-v1", nif, nif, name,
                    json.dumps([isin]), "NIF", "OFFICIAL"))
        cx.execute("INSERT INTO issuer VALUES(?,?,?,?,?,?)",
                   (nif, nif, "LEI" + nif, name, None, "r"))
        cx.execute("INSERT INTO issuer_alias VALUES(?,?,?,?)",
                   (tick, nif, "TICKER", "demo"))
    for rid, rt, st in (("demo-backfill", "BACKFILL", TB),
                        ("demo-incr", "INCREMENTAL", T1),
                        ("demo-recon", "RECONCILIATION", T2),
                        ("demo-recon2", "RECONCILIATION", T2)):
        cx.execute("INSERT INTO crawl_run(run_id,run_type,started_at,"
                   "status,scope,universe_version) VALUES(?,?,?,?,?,?)",
                   (rid, rt, st, "DONE", "demo", "demo-v1"))

    def notice(nk, surf, filing, issuer="A39000013"):
        cx.execute("""INSERT INTO notice(notice_key,source_surface,
                      source_registration_number,issuer_id,filing_date,
                      regulatory_template,notice_status)
                      VALUES(?,?,?,?,?, 'T1', 'ACTIVE')""",
                   (nk, surf, nk.split(":")[1], issuer, filing))

    def obs(nk, run, at, status=None):
        cx.execute("""INSERT INTO notice_observation(run_id,notice_key,
                      observed_at,present_in_source,status_observed,
                      source_url_canonical,raw_sha256)
                      VALUES(?,?,?,?,?,?,?)""",
                   (run, nk, at, 1 if status is None else 0, status,
                    "https://www.cnmv.es/demo/" + nk,
                    _sha("synthetic-raw:" + nk)))

    # --- SAN NOD: single transaction (backfilled) -----------------
    notice("nod:100", "nod", "2024-01-08")
    obs("nod:100", "demo-backfill", TB)
    cx.execute("""INSERT INTO nod_notice_semantic(notice_key,
                  semantic_parser_version,parse_status,
                  notifying_party_name_raw,notification_kind)
                  VALUES('nod:100','nodpdf-1.0','PARSED',
                  'MARIA GARCIA LOPEZ','INITIAL')""")
    cx.execute("""INSERT INTO transaction_event(event_id,notice_key,
                  source_order,transaction_nature_raw,
                  transaction_nature_normalized,transaction_date,
                  venue_raw,declared_aggregate_price,
                  declared_price_currency)
                  VALUES('nod:100:00','nod:100',0,'Compra','BUY',
                  '2024-01-05','XMAD','12345.67','EUR')""")
    cx.execute("""INSERT INTO execution_line VALUES('nod:100:00',0,
                  '3,45','3.45','EUR','3.571,00','3571','EUR')""")

    # --- SAN NOD: multi-transaction (observed incrementally) ------
    notice("nod:200", "nod", "2024-02-28")
    obs("nod:200", "demo-incr", T1)
    obs("nod:200", "demo-recon", T2)   # identical re-observation
    cx.execute("""INSERT INTO nod_notice_semantic(notice_key,
                  semantic_parser_version,parse_status,
                  notifying_party_name_raw,notification_kind)
                  VALUES('nod:200','nodpdf-1.0','PARSED',
                  'JUAN PEREZ DEMON','AMENDMENT')""")
    for i, (nat, norm, d, p) in enumerate((
            ("Compra", "BUY", "2024-02-25", "500.00"),
            ("Venta", "SELL", "2024-02-26", "750.25"))):
        cx.execute("""INSERT INTO transaction_event(event_id,notice_key,
                      source_order,transaction_nature_raw,
                      transaction_nature_normalized,transaction_date,
                      venue_raw,declared_aggregate_price,
                      declared_price_currency)
                      VALUES(?,?,?,?,?,?,?,?,?)""",
                   (f"nod:200:{i:02d}", "nod:200", i, nat, norm,
                    d, "XMAD", p, "EUR"))

    # --- SAN PS: significant holding disclosure -------------------
    notice("ps:100", "ps", "2024-02-01")
    obs("ps:100", "demo-backfill", TB)
    cx.execute("""INSERT INTO ps_notice_semantic(notice_key,
                  semantic_parser_version,parse_status,
                  obliged_subject_name_raw,threshold_date,
                  position_current_json,position_previous_json,
                  percentage_semantics,reason_voting_rights,
                  regulatory_template)
                  VALUES('ps:100','pspdf-1.0','PARSED','HOLDER DEMO SL',
                  '2024-01-20','{"total_pct": "4.5"}',
                  '{"total_pct": "2.0"}','VOTING_RIGHTS',1,
                  'CIRC_8_2015_MODEL_1')""")
    cx.execute("""INSERT INTO ps_shares_row VALUES('ps:100',0,
                  'ES0113900J37','3000','3000','200','200','4.5','4.5',
                  '2.0','2.0','{}')""")

    # --- SAN AC: treasury ops + resulting position ----------------
    notice("ac:100", "ac", "2024-02-15")
    obs("ac:100", "demo-backfill", TB)
    cx.execute("""INSERT INTO ac_notice_semantic(notice_key,
                  semantic_parser_version,parse_status,
                  notification_date,final_position_json,
                  reason_acquisitions_1pct,regulatory_template)
                  VALUES('ac:100','acpdf-1.0','PARSED','2024-02-10',
                  '{"pct": "1.2"}',1,'CIRC_8_2015_MODEL_4')""")
    for i, (d, fl, sh, pr) in enumerate((
            ("2024-02-05", "ACQUISITION", "500", "3.40"),
            ("2024-02-08", "DISPOSAL", "120", "3.55"))):
        cx.execute("""INSERT INTO ac_operation(notice_key,row_index,
                      operation_date_raw,operation_date,
                      operation_flag_raw,operation_flag_normalized,
                      isin,shares_direct,price_direct,raw_json)
                      VALUES('ac:100',?,?,?,?,?, 'ES0113900J37',?,?,'{}')""",
                   (i, d, d, "C" if fl == "ACQUISITION" else "V",
                    fl, sh, pr))

    # --- annulment chain (relation observed later) ----------------
    notice("ps:old", "ps", "2024-01-05")
    obs("ps:old", "demo-backfill", TB)
    cx.execute("""INSERT INTO ps_notice_semantic(notice_key,
                  semantic_parser_version,parse_status,
                  obliged_subject_name_raw,threshold_date,
                  position_current_json,position_previous_json,
                  percentage_semantics,reason_voting_rights,
                  regulatory_template)
                  VALUES('ps:old','pspdf-1.0','PARSED','OLD HOLDER',
                  '2024-01-04','{"total_pct": "3.0"}',
                  '{}','VOTING_RIGHTS',0,'CIRC_8_2015_MODEL_1')""")
    notice("ps:new", "ps", "2024-05-01")
    obs("ps:new", "demo-recon", T2)
    cx.execute("INSERT INTO notice_relation VALUES('ps:new','ps:old',"
               "'ANNULS',NULL,'demo-recon',NULL)")
    # ambiguous target: two candidate annulling notices
    notice("ps:amb", "ps", "2024-01-06")
    obs("ps:amb", "demo-backfill", TB)
    for k in ("ps:x", "ps:y"):
        notice(k, "ps", "2024-02-22")
        obs(k, "demo-incr", T1)
        cx.execute("INSERT INTO notice_relation VALUES(?,?,?,?,?,?)",
                   (k, "ps:amb", "ANNULS", None, "demo-incr", None))
    # --- BBVA notice (second issuer coverage) ---------------------
    notice("nod:300", "nod", "2024-02-27", "A48265169")
    obs("nod:300", "demo-incr", T1)
    cx.execute("""INSERT INTO nod_notice_semantic(notice_key,
                  semantic_parser_version,parse_status,
                  notifying_party_name_raw,notification_kind)
                  VALUES('nod:300','nodpdf-1.0','PARSED',
                  'ANA MARTIN EJEMPLO','INITIAL')""")
    cx.execute("""INSERT INTO transaction_event(event_id,notice_key,
                  source_order,transaction_nature_raw,
                  transaction_nature_normalized,transaction_date,
                  venue_raw,declared_aggregate_price,
                  declared_price_currency)
                  VALUES('nod:300:00','nod:300',0,'Venta','SELL',
                  '2024-02-24','XMAD','999.99','EUR')""")
    # --- disappearance (reconciliation streak) --------------------
    notice("nod:D", "nod", "2024-01-20")
    obs("nod:D", "demo-incr", T1)
    obs("nod:D", "demo-recon", T2, "SOURCE_DISAPPEARANCE_OBSERVED")
    obs("nod:D", "demo-recon2", T2, "SOURCE_DISAPPEARANCE_OBSERVED")
    # --- document rows (synthetic sha — no raw redistributed) -----
    for nk in ("nod:100", "nod:200", "ps:100", "ac:100", "ps:old",
               "nod:300"):
        cx.execute("""INSERT INTO notice_doc(notice_key,doc_status,
                      raw_sha256,parse_status) VALUES(?,?,?,?)""",
                   (nk, "PARSED", _sha("synthetic-doc:" + nk),
                    "PARSED"))
    cx.commit()
    out = ledger.materialize(cx)
    digest = demo_digest(cx)
    cx.close()
    return {"materialize": out, "demo_digest": digest}


def demo_digest(cx):
    """Logical digest over every table — order-insensitive."""
    h = hashlib.sha256()
    tables = [r[0] for r in cx.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for t in tables:
        cols = [r[1] for r in cx.execute(
            f"PRAGMA table_info({t})")]
        rows = cx.execute(f"SELECT * FROM {t} ORDER BY " +
                          ",".join(f"COALESCE({c},'')" for c in cols)
                          ).fetchall()
        h.update(t.encode())
        for r in rows:
            h.update(repr(r).encode("utf-8"))
    return h.hexdigest()


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        "demo", "ownership-radar-demo.sqlite")
    print(json.dumps(build(out), indent=1))
