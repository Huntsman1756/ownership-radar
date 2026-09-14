"""G4 ledger — source facts, derived events, bitemporal queries.

Layers (contract: docs/gates/G4-LEDGER-SEMANTICS.md):

    notice_observation  (G1, immutable, knowledge time)
      -> source_fact    SOURCE_DECLARED content, deterministic identity
      -> ledger_event   SOURCE_DECLARED or DETERMINISTIC_DERIVATION
      -> projections    derived views, never source truth

Two time axes are never mixed: effective_date (economic/regulatory)
vs first_observed_at (knowledge). AS_KNOWN_AT never retro-projects;
CURRENT_KNOWLEDGE_RECONSTRUCTED uses everything known today.

Derived tables are append-modelled: materialize() rebuilds them
wholesale from the semantic layer + notice_relation + the rule
registry. Identical inputs produce byte-identical digests.
"""
import hashlib
import json

DERIVATION_VERSION = "g4-ledger-0.1.0"

SOURCE_DECLARED = "SOURCE_DECLARED"
DETERMINISTIC_DERIVATION = "DETERMINISTIC_DERIVATION"

NO_OBSERVATION_HISTORY = "NO_OBSERVATION_HISTORY"
RELATION_GRAPH_ERROR = "RELATION_GRAPH_ERROR"

# Derivation registry — every derived event names its rule.
RULES = [
    {"rule_id": "NOTICE_FILED/v1", "rule_version": "1",
     "event_type": "NOTICE_FILED", "event_basis": SOURCE_DECLARED,
     "description": "one filing event per observed notice",
     "legal_basis": None},
    {"rule_id": "NOTICE_CANCELLED_FROM_ANNULS/v1", "rule_version": "1",
     "event_type": "NOTICE_CANCELLED", "event_basis": SOURCE_DECLARED,
     "description": "ANNULS relation -> cancellation of the annulled "
                    "notice", "legal_basis": None},
    {"rule_id": "NOD_TXN_TO_INSIDER_EVENT/v1", "rule_version": "1",
     "event_type": "INSIDER_*", "event_basis": DETERMINISTIC_DERIVATION,
     "description": "transaction_nature_normalized BUY/SELL -> "
                    "INSIDER_ACQUISITION/INSIDER_DISPOSAL, else "
                    "INSIDER_TRANSACTION_OTHER",
     "legal_basis": "MAR Art.19 / EU 2016/523"},
    {"rule_id": "PS_DISCLOSURE_TO_POSITION_EVENT/v1",
     "rule_version": "1",
     "event_type": "SIGNIFICANT_HOLDING_POSITION_DISCLOSED",
     "event_basis": DETERMINISTIC_DERIVATION,
     "description": "one position-disclosure event per parsed PS "
                    "notice; never a trade",
     "legal_basis": "LMV Art.23 / Circ. 8/2015, 2/2022"},
    {"rule_id": "AC_OPERATION_TO_TREASURY_EVENT/v1",
     "rule_version": "1",
     "event_type": "TREASURY_OPERATION_REPORTED",
     "event_basis": DETERMINISTIC_DERIVATION,
     "description": "one event per declared section-4 operation row",
     "legal_basis": "LMV / Circ. 8/2015 Mod.4, 2/2022 Mod.2"},
    {"rule_id": "AC_POSITION_TO_TREASURY_EVENT/v1",
     "rule_version": "1",
     "event_type": "TREASURY_STOCK_POSITION_DISCLOSED",
     "event_basis": DETERMINISTIC_DERIVATION,
     "description": "one event per declared section-5 resulting "
                    "position", "legal_basis": "Circ. 8/2015, 2/2022"},
]

NATURE_TO_EVENT = {"BUY": "INSIDER_ACQUISITION",
                   "SELL": "INSIDER_DISPOSAL"}

PARSED_STATUSES = ("PARSED", "PARSED_WITH_UNMAPPED_VALUES")


def _canon(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      default=str)


def _sha(obj):
    return hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()


def _first_observed(cx, notice_key):
    r = cx.execute("""SELECT MIN(observed_at) FROM notice_observation
                      WHERE notice_key=? AND present_in_source=1""",
                   (notice_key,)).fetchone()
    return r[0] if r and r[0] else \
        cx.execute("""SELECT MIN(observed_at) FROM notice_observation
                      WHERE notice_key=?""", (notice_key,)).fetchone()[0]


def _notice_meta(cx):
    return {r[0]: {"issuer_id": r[1], "filing_date": r[2],
                   "source_surface": r[3], "notice_type": r[4]}
            for r in cx.execute(
                "SELECT notice_key,issuer_id,filing_date,"
                "source_surface,notice_type FROM notice")}


# ------------------------------------------------------------------ facts

def _fact(notice_key, fact_type, payload, effective_date,
          filing_date, parser, parser_version, raw_sha256,
          observed_at):
    psha = _sha(payload)
    return {"notice_key": notice_key, "fact_type": fact_type,
            "payload": payload, "payload_sha256": psha,
            "effective_date": effective_date, "filing_date": filing_date,
            "semantic_parser": parser,
            "semantic_parser_version": parser_version,
            "raw_sha256": raw_sha256, "first_observed_at": observed_at}


def build_source_facts(cx):
    """Semantic tables -> source_fact rows (SOURCE_DECLARED only —
    no derived/QA values inside payloads)."""
    meta = _notice_meta(cx)
    facts = []

    # -- NOD: one fact per transaction_event (execution lines inside)
    nod_sem = {r[0]: r for r in cx.execute(
        "SELECT notice_key,semantic_parser_version,notification_kind,"
        "amendment_text_raw,notifying_party_name_raw,"
        "notifying_party_kind,closely_associated,"
        "related_pdmr_name_raw,related_pdmr_position_raw,"
        "issuer_name_document,issuer_lei_document,doc_sha256,"
        "parse_status FROM nod_notice_semantic")}
    tevs = cx.execute(
        "SELECT event_id,notice_key,instrument_code_raw,"
        "instrument_type_raw,transaction_nature_raw,"
        "transaction_nature_normalized,transaction_date_raw,"
        "transaction_date,venue_raw,venue_code_raw,"
        "outside_trading_venue,declared_aggregate_volume,"
        "declared_aggregate_price,declared_price_currency,"
        "computed_volume,computed_vwap,aggregate_qa "
        "FROM transaction_event").fetchall()
    execs = {}
    for eid, li, praw, p, ccy, vraw, v in cx.execute(
            "SELECT event_id,line_index,price_raw,price,"
            "price_currency,volume_raw,volume FROM execution_line "
            "ORDER BY event_id,line_index"):
        execs.setdefault(eid, []).append(
            {"line_index": li, "price_raw": praw, "price": p,
             "currency": ccy, "volume_raw": vraw, "volume": v})
    for (eid, nk, icode, itype, nraw,nnorm, dtr, dt, vraw, vcode,
         outv, dvol, dprice, dccy, cvol, cvwap, qa) in tevs:
        sem = nod_sem.get(nk)
        if not sem or sem[12] not in PARSED_STATUSES:
            continue
        m = meta.get(nk, {})
        payload = {
            "notice": {"notification_kind": sem[2],
                       "amendment_text_raw": sem[3],
                       "notifying_party_name_raw": sem[4],
                       "notifying_party_kind": sem[5],
                       "closely_associated": sem[6],
                       "related_pdmr_name_raw": sem[7],
                       "related_pdmr_position_raw": sem[8],
                       "issuer_name_document": sem[9],
                       "issuer_lei_document": sem[10]},
            "transaction": {
                "instrument_code_raw": icode,
                "instrument_type_raw": itype,
                "transaction_nature_raw": nraw,
                "transaction_nature_normalized": nnorm,
                "transaction_date_raw": dtr, "transaction_date": dt,
                "venue_raw": vraw, "venue_code_raw": vcode,
                "outside_trading_venue": outv,
                "declared_aggregate_volume": dvol,
                "declared_aggregate_price": dprice,
                "declared_price_currency": dccy,
                "execution_lines": execs.get(eid, [])},
            # QA stays OUT of the source payload — it is derived.
        }
        facts.append(_fact(
            nk, "NOD_TRANSACTION_EVENT", payload,
            effective_date=dt or m.get("filing_date"),
            filing_date=m.get("filing_date"),
            parser="nodpdf", parser_version=sem[1],
            raw_sha256=sem[11],
            observed_at=_first_observed(cx, nk)))

    # -- PS: one disclosure fact per parsed notice
    cols = [c[1] for c in cx.execute(
        "PRAGMA table_info(ps_notice_semantic)")]
    for r in cx.execute(
            "SELECT * FROM ps_notice_semantic").fetchall():
        d = dict(zip(cols, r))
        if d["parse_status"] not in PARSED_STATUSES:
            continue
        nk = d["notice_key"]
        m = meta.get(nk, {})
        payload = {
            "issuer_name_document": d["issuer_name_document"],
            "registry_stamp_raw": d["registry_stamp_raw"],
            "obliged_subject_name_raw": d["obliged_subject_name_raw"],
            "obliged_subject_residence_raw":
                d["obliged_subject_residence_raw"],
            "reasons": {k: d[k] for k in (
                "reason_voting_rights",
                "reason_voting_rights_regulated", "reason_instruments",
                "reason_instruments_regulated",
                "reason_issuer_voting_rights_change", "reason_other",
                "reason_other_text_raw", "concerted_agreement")},
            "shareholders_raw": d["shareholders_raw"],
            "threshold_date_raw": d["threshold_date_raw"],
            "threshold_date": d["threshold_date"],
            "percentage_semantics": d["percentage_semantics"],
            "position_current": json.loads(d["position_current_json"])
            if d["position_current_json"] else None,
            "position_previous": json.loads(d["position_previous_json"])
            if d["position_previous_json"] else None,
            "issuer_total_voting_rights_raw":
                d["issuer_total_voting_rights_raw"],
            "subject_control_flag": d["subject_control_flag"],
            "proxy_voting_rights_raw": d["proxy_voting_rights_raw"],
            "proxy_pct_raw": d["proxy_pct_raw"],
            "annulment": json.loads(d["annulment_json"])
            if d["annulment_json"] else None,
            "loyalty_section_present": d["loyalty_section_present"],
            "row_counts": {
                "shares": cx.execute(
                    "SELECT COUNT(*) FROM ps_shares_row "
                    "WHERE notice_key=?", (nk,)).fetchone()[0],
                "instruments": cx.execute(
                    "SELECT COUNT(*) FROM ps_instrument_row "
                    "WHERE notice_key=?", (nk,)).fetchone()[0],
                "chain": cx.execute(
                    "SELECT COUNT(*) FROM ps_control_chain_row "
                    "WHERE notice_key=?", (nk,)).fetchone()[0],
                "loyalty": cx.execute(
                    "SELECT COUNT(*) FROM ps_loyalty_row "
                    "WHERE notice_key=?", (nk,)).fetchone()[0]},
            "regulatory_template": d["regulatory_template"],
        }
        facts.append(_fact(
            nk, "SIGNIFICANT_HOLDING_DISCLOSURE", payload,
            effective_date=d["threshold_date"] or m.get("filing_date"),
            filing_date=m.get("filing_date"),
            parser="pspdf", parser_version=d["semantic_parser_version"],
            raw_sha256=d["doc_sha256"],
            observed_at=_first_observed(cx, nk)))

    # -- AC: one fact per declared operation + one per final position
    ac_sem = {r[0]: r for r in cx.execute(
        "SELECT notice_key,semantic_parser_version,notification_date,"
        "notification_date_raw,final_position_json,doc_sha256,"
        "parse_status,issuer_name_document,issuer_nif_raw,"
        "issuer_voting_rights_raw,reason_first_admission,"
        "reason_acquisitions_1pct,reason_voting_rights_update,"
        "total_acquisitions_json,total_transmissions_json,"
        "regulatory_template FROM ac_notice_semantic")}
    ops = cx.execute(
        "SELECT notice_key,operation_date_raw,operation_date,"
        "operation_flag_raw,operation_flag_normalized,isin,"
        "shares_direct_raw,shares_direct,price_direct_raw,"
        "price_direct,shares_indirect_raw,shares_indirect,"
        "price_indirect_raw,price_indirect,vr_direct_raw,vr_direct,"
        "vr_indirect_raw,vr_indirect,pct_direct_raw,pct_direct,"
        "pct_indirect_raw,pct_indirect,raw_json "
        "FROM ac_operation").fetchall()
    for (nk, odr, od, fraw, fnorm, isin, sdr, sd, pdr, pd, sir, si,
         pir, pi, vdrr, vd, virr, vi, pcdr, pcd, pcir, pci,
         raw) in ops:
        sem = ac_sem.get(nk)
        if not sem or sem[6] not in PARSED_STATUSES:
            continue
        m = meta.get(nk, {})
        payload = {
            "issuer_name_document": sem[7], "issuer_nif_raw": sem[8],
            "operation_date_raw": odr, "operation_date": od,
            "operation_flag_raw": fraw,
            "operation_flag_normalized": fnorm,
            "isin": isin,
            "shares_direct_raw": sdr, "shares_direct": sd,
            "price_direct_raw": pdr, "price_direct": pd,
            "shares_indirect_raw": sir, "shares_indirect": si,
            "price_indirect_raw": pir, "price_indirect": pi,
            "vr_direct_raw": vdrr, "vr_direct": vd,
            "vr_indirect_raw": virr, "vr_indirect": vi,
            "pct_direct_raw": pcdr, "pct_direct": pcd,
            "pct_indirect_raw": pcir, "pct_indirect": pci,
            "regulatory_template": sem[15]}
        facts.append(_fact(
            nk, "TREASURY_OPERATION", payload,
            effective_date=od or m.get("filing_date"),
            filing_date=m.get("filing_date"),
            parser="acpdf", parser_version=sem[1],
            raw_sha256=sem[5], observed_at=_first_observed(cx, nk)))
    for nk, sem in ac_sem.items():
        if sem[6] not in PARSED_STATUSES or not sem[4]:
            continue
        m = meta.get(nk, {})
        payload = {
            "issuer_name_document": sem[7], "issuer_nif_raw": sem[8],
            "issuer_voting_rights_raw": sem[9],
            "notification_date_raw": sem[3], "notification_date": sem[2],
            "reason_first_admission": sem[10],
            "reason_acquisitions_1pct": sem[11],
            "reason_voting_rights_update": sem[12],
            "total_acquisitions": json.loads(sem[13])
            if sem[13] else None,
            "total_transmissions": json.loads(sem[14])
            if sem[14] else None,
            "final_position": json.loads(sem[4]),
            "regulatory_template": sem[15]}
        facts.append(_fact(
            nk, "TREASURY_RESULTING_POSITION", payload,
            effective_date=sem[2] or m.get("filing_date"),
            filing_date=m.get("filing_date"),
            parser="acpdf", parser_version=sem[1],
            raw_sha256=sem[5], observed_at=_first_observed(cx, nk)))
    return facts


def assign_fact_ids(facts):
    """Deterministic identity: sort by content, index only exact
    duplicate payloads inside a notice. No rowid/order dependence."""
    groups = {}
    for f in facts:
        groups.setdefault((f["notice_key"], f["fact_type"]),
                          []).append(f)
    for key, fs in groups.items():
        fs.sort(key=lambda f: f["payload_sha256"])
        seen = {}
        for f in fs:
            i = seen.get(f["payload_sha256"], 0)
            seen[f["payload_sha256"]] = i + 1
            f["fact_index"] = i
            f["fact_id"] = _sha({"notice_key": f["notice_key"],
                                 "fact_type": f["fact_type"],
                                 "payload_sha256": f["payload_sha256"],
                                 "dup_index": i})
    return facts


# ------------------------------------------------------------------ events

def _event(event_type, basis, issuer_id, effective_date, filing_date,
           source_notice_key, source_fact_id, rule_id, payload,
           observed_at):
    psha = _sha(payload)
    identity = {"source": source_fact_id or source_notice_key,
                "event_type": event_type, "rule_id": rule_id,
                "derivation_version": DERIVATION_VERSION,
                "payload_sha256": psha}
    return {"event_id": _sha(identity), "event_type": event_type,
            "event_basis": basis, "issuer_id": issuer_id,
            "effective_date": effective_date,
            "filing_date": filing_date,
            "source_notice_key": source_notice_key,
            "source_fact_id": source_fact_id, "rule_id": rule_id,
            "derivation_version": DERIVATION_VERSION,
            "payload_json": _canon(payload), "payload_sha256": psha,
            "first_observed_at": observed_at}


def build_events(cx, facts):
    meta = _notice_meta(cx)
    events = []
    for f in facts:
        nk = f["notice_key"]
        m = meta.get(nk, {})
        issuer = m.get("issuer_id")
        p = f["payload"]
        if f["fact_type"] == "NOD_TRANSACTION_EVENT":
            nn = p["transaction"]["transaction_nature_normalized"]
            et = NATURE_TO_EVENT.get(nn, "INSIDER_TRANSACTION_OTHER")
            events.append(_event(
                et, DETERMINISTIC_DERIVATION, issuer,
                f["effective_date"], f["filing_date"], nk,
                f["fact_id"], "NOD_TXN_TO_INSIDER_EVENT/v1",
                {"person": p["notice"]["notifying_party_name_raw"],
                 "person_kind": p["notice"]["notifying_party_kind"],
                 "related_pdmr": p["notice"]["related_pdmr_name_raw"],
                 "instrument": p["transaction"],
                 "notification_kind": p["notice"]["notification_kind"]},
                f["first_observed_at"]))
        elif f["fact_type"] == "SIGNIFICANT_HOLDING_DISCLOSURE":
            events.append(_event(
                "SIGNIFICANT_HOLDING_POSITION_DISCLOSED",
                DETERMINISTIC_DERIVATION, issuer,
                f["effective_date"], f["filing_date"], nk,
                f["fact_id"], "PS_DISCLOSURE_TO_POSITION_EVENT/v1",
                {"subject": p["obliged_subject_name_raw"],
                 "threshold_date": p["threshold_date"],
                 "position_current": p["position_current"],
                 "position_previous": p["position_previous"],
                 "percentage_semantics": p["percentage_semantics"],
                 "reasons": p["reasons"],
                 "row_counts": p["row_counts"]},
                f["first_observed_at"]))
        elif f["fact_type"] == "TREASURY_OPERATION":
            events.append(_event(
                "TREASURY_OPERATION_REPORTED",
                DETERMINISTIC_DERIVATION, issuer,
                f["effective_date"], f["filing_date"], nk,
                f["fact_id"], "AC_OPERATION_TO_TREASURY_EVENT/v1",
                {"operation_flag_raw": p["operation_flag_raw"],
                 "operation_flag_normalized":
                     p["operation_flag_normalized"],
                 "isin": p["isin"],
                 "shares_direct": p["shares_direct"],
                 "shares_indirect": p["shares_indirect"],
                 "price_direct": p["price_direct"],
                 "price_indirect": p["price_indirect"]},
                f["first_observed_at"]))
        elif f["fact_type"] == "TREASURY_RESULTING_POSITION":
            events.append(_event(
                "TREASURY_STOCK_POSITION_DISCLOSED",
                DETERMINISTIC_DERIVATION, issuer,
                f["effective_date"], f["filing_date"], nk,
                f["fact_id"], "AC_POSITION_TO_TREASURY_EVENT/v1",
                {"final_position": p["final_position"],
                 "notification_date": p["notification_date"],
                 "reason_acquisitions_1pct":
                     p["reason_acquisitions_1pct"]},
                f["first_observed_at"]))
    # notice-level events
    by_notice = {}
    for f in facts:
        by_notice.setdefault(f["notice_key"], f)
    for nk, f in sorted(by_notice.items()):
        m = meta.get(nk, {})
        events.append(_event(
            "NOTICE_FILED", SOURCE_DECLARED, m.get("issuer_id"),
            m.get("filing_date"), m.get("filing_date"), nk,
            None, "NOTICE_FILED/v1",
            {"notice_key": nk, "notice_type": m.get("notice_type"),
             "source_surface": m.get("source_surface")},
            _first_observed(cx, nk)))
    for annulling, annulled, rtype in cx.execute(
            "SELECT annulling_key,annulled_key,relation_type "
            "FROM notice_relation"):
        # the ANNULS relation is evidence by itself — a cancellation
        # event is emitted for every observed annulled notice, parsed
        # or not
        if annulled not in meta:
            continue
        m = meta.get(annulling, {})
        events.append(_event(
            "NOTICE_CANCELLED", SOURCE_DECLARED,
            meta.get(annulled, {}).get("issuer_id"),
            m.get("filing_date"), m.get("filing_date"), annulled,
            None, "NOTICE_CANCELLED_FROM_ANNULS/v1",
            {"annulled_notice_key": annulled,
             "annulling_notice_key": annulling,
             "relation_type": rtype},
            _first_observed(cx, annulling)))
    return events


def materialize(cx):
    """Rebuild the derived ledger from semantic tables + relations.
    Idempotent: identical inputs -> identical digest."""
    cx.execute("DELETE FROM fact_version_relation")
    cx.execute("DELETE FROM ledger_event")
    cx.execute("DELETE FROM source_fact")
    cx.execute("DELETE FROM derivation_rule")
    for r in RULES:
        cx.execute(
            "INSERT INTO derivation_rule VALUES(?,?,?,?,?,?,?)",
            (r["rule_id"], r["rule_version"], r["event_type"],
             r["description"], r["legal_basis"], None, None))
    facts = assign_fact_ids(build_source_facts(cx))
    for f in facts:
        cx.execute(
            "INSERT INTO source_fact VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (f["fact_id"], f["notice_key"], f["fact_type"],
             f["fact_index"], f["effective_date"], f["filing_date"],
             f["semantic_parser"], f["semantic_parser_version"],
             _canon(f["payload"]), f["payload_sha256"],
             f["raw_sha256"], f["first_observed_at"]))
    by_notice = {}
    for f in facts:
        by_notice.setdefault(f["notice_key"], []).append(f)
    for annulling, annulled, rtype in cx.execute(
            "SELECT annulling_key,annulled_key,relation_type "
            "FROM notice_relation"):
        rel = {"ANNULS": "CANCELLED_BY",
               "RECTIFIES": "RECTIFIED_BY"}.get(rtype)
        if not rel or annulled not in by_notice or \
                annulling not in by_notice:
            continue
        obs = _first_observed(cx, annulling)
        for fa in by_notice[annulled]:
            for fb in by_notice[annulling]:
                cx.execute(
                    "INSERT OR IGNORE INTO fact_version_relation "
                    "VALUES(?,?,?,?,?,?)",
                    (fa["fact_id"], fb["fact_id"], rel,
                     "NOTICE_RELATION:" + rtype, annulling, obs))
    for e in build_events(cx, facts):
        cx.execute(
            "INSERT INTO ledger_event VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (e["event_id"], e["event_type"], e["event_basis"],
             e["issuer_id"], e["effective_date"], e["filing_date"],
             e["source_notice_key"], e["source_fact_id"], e["rule_id"],
             e["derivation_version"], e["payload_json"],
             e["payload_sha256"], e["first_observed_at"]))
    cx.commit()
    return {"facts": len(facts),
            "digest": ledger_digest(cx)}


def ledger_digest(cx):
    """Deterministic digest over the whole derived ledger."""
    rows = [("F",) + tuple(r) for r in cx.execute(
        "SELECT * FROM source_fact ORDER BY fact_id")]
    rows += [("R",) + tuple(r) for r in cx.execute(
        "SELECT * FROM fact_version_relation ORDER BY from_fact_id,"
        "to_fact_id")]
    rows += [("E",) + tuple(r) for r in cx.execute(
        "SELECT * FROM ledger_event ORDER BY event_id")]
    return hashlib.sha256(_canon(rows).encode()).hexdigest()


# ----------------------------------------------------------------- queries

def resolve_annulment_chains(cx):
    """annulled -> terminal annulling notice. Returns (terminal map,
    errors). Multi-target or cyclic graphs are errors, never silently
    resolved."""
    edges = {}
    for annulling, annulled in cx.execute(
            "SELECT annulling_key,annulled_key FROM notice_relation "
            "WHERE relation_type='ANNULS'"):
        edges.setdefault(annulled, set()).add(annulling)
    terminal, errors = {}, []
    for start, targets in edges.items():
        if len(targets) > 1:
            errors.append({"notice_key": start,
                           "error": RELATION_GRAPH_ERROR,
                           "detail": "multiple_annulling_notices"})
            continue
        path, cur, seen = [start], start, {start}
        while cur in edges:
            nxt = edges[cur]
            if len(nxt) > 1:
                errors.append({"notice_key": start,
                               "error": RELATION_GRAPH_ERROR,
                               "detail": "multiple_annulling_notices"})
                break
            cur = next(iter(nxt))
            if cur in seen:
                errors.append({"notice_key": start,
                               "error": RELATION_GRAPH_ERROR,
                               "detail": "cycle:" + ">".join(path)})
                break
            seen.add(cur)
            path.append(cur)
        else:
            terminal[start] = cur
    return terminal, errors


def status_as_known_at(cx, notice_key, known_at):
    """ACTIVE/CANCELLED/NOT_OBSERVED using only observations <= T."""
    obs = cx.execute(
        "SELECT observed_at,status_observed FROM notice_observation "
        "WHERE notice_key=? AND observed_at<=? ORDER BY observed_at",
        (notice_key, known_at)).fetchall()
    if not obs:
        return "NOT_OBSERVED"
    annullers = cx.execute(
        "SELECT annulling_key FROM notice_relation "
        "WHERE annulled_key=? AND relation_type='ANNULS'",
        (notice_key,)).fetchall()
    for (a,) in annullers:
        fo = _first_observed(cx, a)
        if fo and fo <= known_at:
            return "CANCELLED"
    return obs[-1][1] or "ACTIVE"


def _earliest_observation(cx):
    r = cx.execute("SELECT MIN(observed_at) FROM notice_observation")
    return r.fetchone()[0]


def events_for_issuer(cx, issuer_id, mode="CURRENT_KNOWLEDGE_"
                      "RECONSTRUCTED", effective_at=None,
                      known_at=None):
    """mode=CURRENT_KNOWLEDGE_RECONSTRUCTED: everything known today,
    filtered by effective_at.
    mode=AS_KNOWN_AT: only events whose source was observed by
    known_at. If known_at precedes the first observation ->
    NO_OBSERVATION_HISTORY."""
    if mode == "AS_KNOWN_AT":
        if not known_at:
            raise ValueError("AS_KNOWN_AT requires known_at")
        first = _earliest_observation(cx)
        if first and known_at < first:
            return {"status": NO_OBSERVATION_HISTORY, "events": []}
    q = ("SELECT event_id,event_type,event_basis,effective_date,"
         "filing_date,source_notice_key,source_fact_id,rule_id,"
         "payload_json,first_observed_at FROM ledger_event "
         "WHERE issuer_id=?")
    args = [issuer_id]
    if effective_at:
        q += " AND effective_date<=?"
        args.append(effective_at)
    if mode == "AS_KNOWN_AT":
        q += " AND first_observed_at<=?"
        args.append(known_at)
    q += " ORDER BY effective_date,event_id"
    evs = [{"event_id": r[0], "event_type": r[1],
            "event_basis": r[2], "effective_date": r[3],
            "filing_date": r[4], "source_notice_key": r[5],
            "source_fact_id": r[6], "rule_id": r[7],
            "payload": json.loads(r[8]), "first_observed_at": r[9]}
           for r in cx.execute(q, args)]
    return {"status": "OK", "mode": mode, "issuer_id": issuer_id,
            "events": evs}


def facts_for_issuer(cx, issuer_id, effective_at=None, known_at=None):
    q = ("SELECT f.* FROM source_fact f JOIN notice n ON "
         "f.notice_key=n.notice_key WHERE n.issuer_id=?")
    args = [issuer_id]
    if effective_at:
        q += " AND f.effective_date<=?"
        args.append(effective_at)
    if known_at:
        q += " AND f.first_observed_at<=?"
        args.append(known_at)
    q += " ORDER BY f.effective_date,f.fact_id"
    cols = [c[1] for c in cx.execute("PRAGMA table_info(source_fact)")]
    return [dict(zip(cols, r)) for r in cx.execute(q, args)]


def state_for_issuer(cx, issuer_id, known_at=None):
    """Derived projection — never source truth. Latest authoritative
    PS disclosure per obliged subject, latest treasury position, all
    reported insider events."""
    terminal, errors = resolve_annulment_chains(cx)
    annulled = set(terminal)
    if known_at:
        # a cancellation is only known once the annulling notice was
        # observed
        still = set()
        for a in annulled:
            for (ann,) in cx.execute(
                    "SELECT annulling_key FROM notice_relation WHERE "
                    "annulled_key=? AND relation_type='ANNULS'",
                    (a,)):
                fo = _first_observed(cx, ann)
                if fo and fo <= known_at:
                    still.add(a)
        annulled = still
    bound = ""
    args = [issuer_id]
    if known_at:
        bound = " AND f.first_observed_at<=?"
        args.append(known_at)
    ps = {}
    for r in cx.execute(
            "SELECT f.notice_key,f.fact_id,f.effective_date,"
            "f.filing_date,f.source_payload_json FROM source_fact f "
            "JOIN notice n ON f.notice_key=n.notice_key "
            "WHERE n.issuer_id=? AND f.fact_type="
            "'SIGNIFICANT_HOLDING_DISCLOSURE'" + bound,
            args):
        if r[0] in annulled:
            continue
        d = json.loads(r[4])
        subj = d.get("obliged_subject_name_raw")
        key = subj or r[0]
        cur = ps.get(key)
        if cur is None or (r[2] or "", r[1]) > \
                (cur["effective_date"] or "", cur["fact_id"]):
            ps[key] = {"fact_id": r[1], "notice_key": r[0],
                       "subject": subj,
                       "identity_quality": "ISSUER_SCOPED_RAW_NAME"
                       if subj else "UNRESOLVED",
                       "effective_date": r[2], "filing_date": r[3],
                       "position_current": d.get("position_current"),
                       "percentage_semantics":
                           d.get("percentage_semantics")}
    treas = None
    for r in cx.execute(
            "SELECT f.notice_key,f.fact_id,f.effective_date,"
            "f.filing_date,f.source_payload_json FROM source_fact f "
            "JOIN notice n ON f.notice_key=n.notice_key "
            "WHERE n.issuer_id=? AND f.fact_type="
            "'TREASURY_RESULTING_POSITION'" + bound, args):
        if r[0] in annulled:
            continue
        d = json.loads(r[4])
        if treas is None or (r[2] or "", r[1]) > \
                (treas["effective_date"] or "", treas["fact_id"]):
            treas = {"fact_id": r[1], "notice_key": r[0],
                     "effective_date": r[2], "filing_date": r[3],
                     "final_position": d.get("final_position"),
                     "position_source_notice": r[0]}
    nod = events_for_issuer(cx, issuer_id,
                            mode="AS_KNOWN_AT" if known_at else
                            "CURRENT_KNOWLEDGE_RECONSTRUCTED",
                            known_at=known_at)
    insider = [e for e in nod.get("events", [])
               if e["event_type"].startswith("INSIDER_")]
    return {"issuer_id": issuer_id, "known_at": known_at,
            "significant_holdings": sorted(
                ps.values(), key=lambda x: (x["subject"] or "",
                                            x["fact_id"])),
            "treasury_position": treas,
            "reported_insider_events": insider,
            "relation_errors": errors,
            "projection": "DERIVED_NOT_SOURCE_TRUTH"}


def provenance(cx, event_id):
    """event -> fact -> semantic parse -> notice -> observation ->
    raw bytes. Orphans surface as explicit NULLs."""
    e = cx.execute("SELECT * FROM ledger_event WHERE event_id=?",
                   (event_id,)).fetchone()
    if not e:
        return None
    cols = [c[1] for c in cx.execute("PRAGMA table_info(ledger_event)")]
    ev = dict(zip(cols, e))
    out = {"ledger_event": ev, "source_fact": None,
           "semantic_parse": None, "notice": None,
           "observations": []}
    if ev["source_fact_id"]:
        f = cx.execute("SELECT * FROM source_fact WHERE fact_id=?",
                       (ev["source_fact_id"],)).fetchone()
        if f:
            fc = [c[1] for c in cx.execute(
                "PRAGMA table_info(source_fact)")]
            out["source_fact"] = dict(zip(fc, f))
    nk = ev["source_notice_key"]
    n = cx.execute("SELECT * FROM notice WHERE notice_key=?",
                   (nk,)).fetchone()
    if n:
        nc = [c[1] for c in cx.execute("PRAGMA table_info(notice)")]
        out["notice"] = dict(zip(nc, n))
    for t in ("nod_notice_semantic", "ps_notice_semantic",
              "ac_notice_semantic"):
        s = cx.execute(f"SELECT notice_key,semantic_parser_version,"
                       f"regulatory_template,parse_status,doc_sha256 "
                       f"FROM {t} WHERE notice_key=?", (nk,)).fetchone()
        if s:
            out["semantic_parse"] = {
                "table": t, "notice_key": s[0],
                "semantic_parser_version": s[1],
                "regulatory_template": s[2], "parse_status": s[3],
                "doc_sha256": s[4]}
    for r in cx.execute(
            "SELECT observed_at,run_id,raw_sha256,status_observed "
            "FROM notice_observation WHERE notice_key=? "
            "ORDER BY observed_at", (nk,)):
        out["observations"].append(
            {"observed_at": r[0], "run_id": r[1],
             "raw_sha256": r[2], "status_observed": r[3]})
    return out
