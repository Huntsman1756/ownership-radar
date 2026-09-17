"""G3-A significant-holdings parser — CNMV Modelo 1 forms.

Templates: CIRC_8_2015_MODEL_1 and CIRC_2_2022_MODEL_1 (the latter adds
section 11 loyalty-vote fields). Both render as bilingual grids; cell
x-position determines direct/indirect column identity.

A significant-holding notice is a POSITION DISCLOSURE: this module
never emits transactions/trades. Percentages carry the regulatory
generation (`percentage_semantics`) because Circular 2/2022 changed
the meaning of "% voting rights" (loyalty double votes included when
applicable).

Two layers, mirroring nodpdf: parse_lines(pages) works on the
extract_cells() structure; parse_pdf(pdf_bytes) is the full pipeline.
"""
import hashlib
import re
from decimal import Decimal

from . import g3pdf as g

SEMANTIC_PARSER_VERSION = "pspdf-0.1.0"

SEM_PRE = "PRE_C2_2022_VOTING_RIGHTS"
SEM_POST = "C2_2022_INCLUDING_LOYALTY"


def _first_numeric(lines, i, limit=6, extra=None):
    """First line after i whose every cell looks numeric. `extra` is an
    optional regex for additional accepted cell values (e.g. 'N.A.')."""
    for j in range(i + 1, min(len(lines), i + limit)):
        if lines[j] and all(
                g._PCT.match(c["t"].strip()) or g._INT.match(c["t"].strip())
                or (extra and re.fullmatch(extra, c["t"].strip()))
                for c in lines[j]):
            return lines[j], j
    return None, i


def _value_after(lines, i, stop=(), limit=4):
    for j in range(i + 1, min(len(lines), i + limit)):
        t = g._n(" ".join(c["t"] for c in lines[j]))
        if any(s in t.upper() for s in stop):
            return None, j
        if lines[j]:
            return lines[j], j
    return None, i


def _num_cells(line):
    return [c for c in line
            if g._PCT.match(c["t"].strip()) or g._INT.match(c["t"].strip())
            or g._DATE.match(c["t"].strip())]


def _pct_or_int(c):
    t = c["t"].strip()
    if g._PCT.match(t):
        return {"raw": t, "dec": str(g.dec(t))}
    if g._INT.match(t):
        return {"raw": t, "int": g.dec_int(t)}
    return None


def parse_lines(pages):
    out = {
        "semantic_parser_version": SEMANTIC_PARSER_VERSION,
        "regulatory_template": g.fingerprint(pages),
        "parse_status": None, "unmapped": [],
        "registry_stamp_raw": None,
        "issuer_name_document": None,
        "reason_voting_rights": None,
        "reason_voting_rights_regulated": None,
        "reason_instruments": None,
        "reason_instruments_regulated": None,
        "reason_issuer_voting_rights_change": None,
        "reason_other": None,
        "reason_other_text_raw": None,
        "concerted_agreement": None,
        "obliged_subject_name_raw": None,
        "obliged_subject_residence_raw": None,
        "shareholders_raw": None,
        "threshold_date_raw": None, "threshold_date": None,
        "percentage_semantics": None,
        "position_current": None, "position_previous": None,
        "issuer_total_voting_rights_raw": None,
        "issuer_total_voting_rights": None,
        "shares_rows": [], "shares_subtotal": None,
        "instruments_a_rows": [], "instruments_a_subtotal": None,
        "instruments_b_rows": [], "instruments_b_subtotal": None,
        "subject_control_flag": None,
        "chain_info_text_raw": None,
        "chain_rows": [],
        "proxy_voting_rights_raw": None, "proxy_pct_raw": None,
        "proxy_meeting_date_raw": None,
        "additional_info_raw": None,
        "annulment": None,
        "loyalty_section_present": None,
        "loyalty_11a": None, "loyalty_11a_rows": [],
        "loyalty_11b_rows": [],
        "signature_raw": None,
        "post_signature_raw": None,
        "aggregate_qa": None,
    }
    tpl = out["regulatory_template"]
    if tpl in (g.UNSUPPORTED_NO_TEXT, g.UNSUPPORTED_TEMPLATE,
               g.UNSUPPORTED_LEGACY, g.T_MODEL_2_DIR, g.T_MODEL_4,
               g.T_MODEL_2_AC):
        out["parse_status"] = (g.UNSUPPORTED_NO_TEXT
                               if tpl == g.UNSUPPORTED_NO_TEXT
                               else g.UNSUPPORTED_LEGACY
                               if tpl == g.UNSUPPORTED_LEGACY
                               else g.UNSUPPORTED_TEMPLATE)
        return out
    out["percentage_semantics"] = \
        SEM_POST if tpl == g.T_MODEL_1_C2 else SEM_PRE
    out["loyalty_section_present"] = tpl == g.T_MODEL_1_C2

    lines = g.all_lines(pages)

    i = g.find_line(lines, "REGISTRO DE ENTRADA N")
    if i >= 0:
        out["registry_stamp_raw"] = g._n(
            " ".join(c["t"] for c in lines[i])).strip()

    i = g.find_line(lines, "IDENTIFICACIÓN DEL EMISOR")
    if i >= 0:
        v, _ = _value_after(lines, i,
                            stop=("MOTIVO DE LA NOTIFICACIÓN",))
        if v:
            out["issuer_name_document"] = g._n(
                " ".join(c["t"] for c in v)).strip()
    else:
        out["unmapped"].append("issuer_anchor")

    # -- section 2: reason checkboxes -------------------------------------
    # Unchecked boxes may render as a lone "[ ]" cell on an adjacent
    # visual line; look one line up/down when the label line has none.
    def cb_of(i):
        t = g._n(" ".join(c["t"] for c in lines[i])).upper()
        cb = g.checkbox(t)
        if cb is not None:
            return cb
        for j in (i - 1, i + 1):
            if 0 <= j < len(lines) and lines[j]:
                cs = [c["t"].strip() for c in lines[j]]
                if len(cs) == 1 and re.fullmatch(r"\[\s*[^\]]*\]", cs[0]):
                    return g.checkbox(cs[0])
        return None

    last_reason = None
    for li, l in enumerate(lines):
        t = g._n(" ".join(c["t"] for c in l)).upper()
        cb = cb_of(li)
        if cb is None:
            continue
        if "ADQUISICIÓN O TRANSMISIÓN DE DERECHOS DE VOTO" in t:
            out["reason_voting_rights"] = cb
            last_reason = "vr"
        elif "ADQUISICIÓN O TRANSMISIÓN DE INSTRUMENTOS" in t:
            out["reason_instruments"] = cb
            last_reason = "fi"
        elif "OPERACIÓN REALIZADA EN UN MERCADO REGULADO" in t:
            if last_reason == "vr":
                out["reason_voting_rights_regulated"] = cb
            elif last_reason == "fi":
                out["reason_instruments_regulated"] = cb
        elif "MODIFICACIÓN EN EL NÚMERO DE DERECHOS DE VOTO" in t:
            out["reason_issuer_voting_rights_change"] = cb
        elif "OTROS MOTIVOS" in t:
            out["reason_other"] = cb
            last_reason = "other"
        elif "EJERCICIO CONCERTADO" in t:
            out["concerted_agreement"] = cb

    i = g.find_line(lines, "OTROS MOTIVOS")
    if i >= 0 and out["reason_other"]:
        # free text may sit on the label line itself or the next line;
        # skip footnote markers and checkbox-only lines
        cand = []
        for j in range(i, min(len(lines), i + 4)):
            cs = [c["t"].strip() for c in lines[j]
                  if c["t"].strip() and
                  not re.fullmatch(r"\[\s*[^\]]*\]", c["t"].strip()) and
                  not re.fullmatch(r"\d{1,2}", c["t"].strip())]
            if j == i:
                tail = [c for c in cs if "OTROS" not in
                        g._n(c).upper() and "OTHER" not in
                        g._n(c).upper() and
                        "MOTIVOS" not in g._n(c).upper()]
                cand += tail
            else:
                cand += cs
            if cand:
                break
        txt = g._n(" ".join(cand)).strip()
        if txt and "IDENTIFICACIÓN" not in txt.upper():
            out["reason_other_text_raw"] = txt

    # -- section 3: obliged subject ---------------------------------------
    i = g.find_line(lines, "APELLIDOS Y NOMBRE O DENOMINACIÓN")
    if i >= 0:
        v, _ = _value_after(lines, i, stop=("CIUDAD Y PAÍS",))
        if v:
            out["obliged_subject_name_raw"] = g._n(
                " ".join(c["t"] for c in v)).strip()
    i = g.find_line(lines, "CIUDAD Y PAÍS DEL DOMICILIO")
    if i >= 0:
        v, _ = _value_after(lines, i,
                            stop=("CONCERTADO", "4. IDENTIFICACIÓN",
                                  "IDENTIFICACIÓN DEL ACCIONISTA"))
        if v and "CONCERTADO" not in g._n(
                " ".join(c["t"] for c in v)).upper():
            out["obliged_subject_residence_raw"] = g._n(
                " ".join(c["t"] for c in v)).strip()

    # -- section 4: shareholder(s)/holder(s) -------------------------------
    i = g.find_line(lines, "SI ES DISTINTO DEL INDICADO EN EL",
                    "IF DIFFERENT FROM 3")
    if i >= 0:
        stop = g.find_line(lines, "FECHA EN LA QUE SE CRUZÓ",
                           "THRESHOLD WAS CROSSED", start=i + 1)
        seg = []
        for l in lines[i + 1:stop if stop > i else i + 6]:
            if not l:
                continue
            lt = g._n(" ".join(c["t"] for c in l)).upper()
            if any(k in lt for k in
                   ("APARTADO 3", "4 BIS", "FULL NAME OF SHARE",
                    "ANEXO", "ANNEX", "FORMULARIO MODELO",
                    "STANDARD FORM")):
                continue
            cs = [c["t"].strip() for c in l
                  if c["t"].strip() and
                  not re.fullmatch(r"\d{1,2}", c["t"].strip()) and
                  not re.fullmatch(r"\d+ / \d+", c["t"].strip()) and
                  c["t"].strip() != "..."]
            if cs:
                seg.append(" ".join(cs))
        txt = g._n(" ".join(seg)).strip()
        txt = re.sub(r"^(Apellidos|Full name).*?:", "", txt,
                     flags=re.I | re.S).strip()
        out["shareholders_raw"] = txt or None

    # -- section 5: threshold date -----------------------------------------
    i = g.find_line(lines, "FECHA EN LA QUE SE CRUZÓ",
                    "THRESHOLD WAS CROSSED")
    if i >= 0:
        for j in range(i + 1, min(len(lines), i + 4)):
            d = [c["t"].strip() for c in lines[j]
                 if g._DATE.match(c["t"].strip())]
            if d:
                out["threshold_date_raw"] = d[0]
                out["threshold_date"] = g.norm_date(d[0])
                break
        if out["threshold_date_raw"] is None:
            out["unmapped"].append("threshold_date")
    else:
        out["unmapped"].append("threshold_anchor")

    # -- section 6: total position -----------------------------------------
    i = g.find_line(lines, "SITUACIÓN RESULTANTE",
                    "RESULTING POSITION")
    if i >= 0:
        row, _ = _first_numeric(lines, i)
        if row:
            vals = [c["t"].strip() for c in row]
            out["position_current"] = {
                "pct_shares_raw": vals[0] if len(vals) > 0 else None,
                "pct_instruments_raw": vals[1] if len(vals) > 1 else None,
                "pct_total_raw": vals[2] if len(vals) > 2 else None,
                "issuer_total_vr_raw": vals[3] if len(vals) > 3 else None,
                "pct_shares": str(g.dec(vals[0])) if len(vals) > 0 else None,
                "pct_instruments": str(g.dec(vals[1]))
                if len(vals) > 1 else None,
                "pct_total": str(g.dec(vals[2])) if len(vals) > 2 else None,
                "issuer_total_vr": g.dec_int(vals[3])
                if len(vals) > 3 else None,
            }
            out["issuer_total_voting_rights_raw"] = \
                out["position_current"]["issuer_total_vr_raw"]
            out["issuer_total_voting_rights"] = \
                out["position_current"]["issuer_total_vr"]
        else:
            out["unmapped"].append("position_current")
    else:
        out["unmapped"].append("position_anchor")

    # the label wraps over several visual lines; anchor on the first
    # fragment and confirm "PREVIA" appears just after
    i = -1
    for j, l in enumerate(lines):
        t = g._n(" ".join(c["t"] for c in l)).upper()
        if t.startswith("POSICIÓN DE LA"):
            nxt = " ".join(g._n(" ".join(c["t"] for c in lines[k]))
                           for k in range(j, min(len(lines), j + 4)))
            if "PREVIA" in nxt.upper():
                i = j
                break
    if i >= 0:
        row, _ = _first_numeric(lines, i, limit=14,
                                extra=r"N\.A\.|-|\.\.\.")
        if row:
            vals = [c["t"].strip() for c in row]
            out["position_previous"] = {
                "pct_shares_raw": vals[0] if len(vals) > 0 else None,
                "pct_instruments_raw": vals[1] if len(vals) > 1 else None,
                "pct_total_raw": vals[2] if len(vals) > 2 else None,
                "pct_shares": str(g.dec(vals[0]))
                if len(vals) > 0 and g.dec(vals[0]) is not None else None,
                "pct_instruments": str(g.dec(vals[1]))
                if len(vals) > 1 and g.dec(vals[1]) is not None else None,
                "pct_total": str(g.dec(vals[2]))
                if len(vals) > 2 and g.dec(vals[2]) is not None else None,
            }

    # -- section 7.A: shares ------------------------------------------------
    s7a = g.find_line(lines, "7.A. DERECHOS DE VOTO ATRIBUIDOS",
                      "VOTING RIGHTS ATTACHED TO SHARES")
    e7a = g.find_line(lines, "SUBTOTAL 7.A", start=s7a + 1) \
        if s7a >= 0 else -1
    if s7a >= 0 and e7a > s7a:
        hdr_i = None
        for j in range(s7a, e7a):
            t = " ".join(c["t"] for c in lines[j])
            if "Directo" in g._n(t) and "Indirecto" in g._n(t):
                hdr_i = j
        bands = None
        if hdr_i is not None:
            # header carries Directo/Indirecto twice (counts, then %);
            # take the four cells left-to-right as band starts
            xs = [c["x0"] for c in lines[hdr_i]
                  if "DIRECTO" in g._n(c["t"]).upper() or
                  "INDIRECTO" in g._n(c["t"]).upper()]
            xs = sorted(xs)[:4]
            if len(xs) == 4:
                bands = [("D", xs[0], xs[1]), ("I", xs[1], xs[2]),
                         ("DP", xs[2], xs[3]), ("IP", xs[3],
                                                float("inf"))]
        consumed = set()
        for j in range(s7a + 1, e7a):
            if j in consumed:
                continue
            l = lines[j]
            if not l:
                continue
            t = g._n(" ".join(c["t"] for c in l))
            if "Directo" in t or "Indirecto" in t or "..." in t or \
                    "Clase o tipo" in t or "Class or type" in t or \
                    "Número de" in t or "Number of" in t or \
                    "derechos de voto" in t.lower():
                continue
            isin = next((c["t"].strip() for c in l
                         if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9,10}",
                                         c["t"].strip())), None)
            nums = _num_cells(l)
            # an ISIN-only line is the first visual line of a wrapped
            # row: merge the following numeric-only line into it
            if isin is not None and not nums:
                for k in range(j + 1, min(e7a, j + 4)):
                    nxt = lines[k]
                    if nxt and all(
                            g._PCT.match(c["t"].strip()) or
                            g._INT.match(c["t"].strip())
                            for c in nxt):
                        l = l + nxt
                        nums = _num_cells(l)
                        consumed.add(k)
                        break
            # footnote reference markers are single tiny numeric cells
            if isin is None and (len(nums) < 2 or len(l) < 2):
                continue
            row = {"row_index": len(out["shares_rows"]),
                   "isin": isin,
                   "vr_direct_raw": None, "vr_indirect_raw": None,
                   "pct_direct_raw": None, "pct_indirect_raw": None,
                   "vr_direct": None, "vr_indirect": None,
                   "pct_direct": None, "pct_indirect": None,
                   "raw_cells": [c["t"].strip() for c in l]}
            if bands and nums:
                for c in nums:
                    col = g.assign_column(c["x0"], bands)
                    v = c["t"].strip()
                    if col == "D" and g._INT.match(v) and \
                            row["vr_direct_raw"] is None:
                        row["vr_direct_raw"] = v
                        row["vr_direct"] = g.dec_int(v)
                    elif col == "I" and g._INT.match(v) and \
                            row["vr_indirect_raw"] is None:
                        row["vr_indirect_raw"] = v
                        row["vr_indirect"] = g.dec_int(v)
                    elif col == "DP" and g._PCT.match(v):
                        row["pct_direct_raw"] = v
                        row["pct_direct"] = str(g.dec(v))
                    elif col == "IP" and g._PCT.match(v):
                        row["pct_indirect_raw"] = v
                        row["pct_indirect"] = str(g.dec(v))
            out["shares_rows"].append(row)
        if e7a > 0:
            l = lines[e7a]
            vals = [c["t"].strip() for c in _num_cells(l)]
            out["shares_subtotal"] = {
                "vr_raw": vals[0] if vals else None,
                "pct_raw": vals[1] if len(vals) > 1 else None,
                "vr": g.dec_int(vals[0]) if vals else None,
                "pct": str(g.dec(vals[1])) if len(vals) > 1 else None,
            }

    # -- section 7.B instruments -------------------------------------------
    def instr_rows(start_anchor, end_anchor, has_settlement):
        rows = []
        subtotal = None
        s = g.find_line(lines, *start_anchor)
        e = g.find_line(lines, *end_anchor, start=s + 1) if s >= 0 else -1
        if s < 0:
            return rows, subtotal, -1, -1
        # a logical row may wrap across visual lines: the type label,
        # dates and values can land on separate lines. Accumulate cells
        # until the row carries a percentage cell, then close it.
        pend = []        # cells of the open logical row
        pend_text = []   # bare text lines before the row's first cells
        for j in range(s + 1, e if e > s else s + 60):
            l = lines[j]
            if not l:
                continue
            t = g._n(" ".join(c["t"] for c in l))
            if any(k in t for k in
                   ("Tipo de instrumento", "Type of financial",
                    "Fecha última", "Expiration", "Período de",
                    "Exercise", "Liquidación", "settlement",
                    "Número de", "Number of", "% derechos",
                    "% of voting", "...")):
                continue
            nums = _num_cells(l)
            dts = [c for c in l if g._DATE.match(c["t"].strip())]
            if not nums and not dts:
                # pure text: type continuation (wrapped label)
                txts = " ".join(c["t"].strip() for c in l).strip()
                if txts and l[0]["x0"] < 250 and not any(
                        k in t for k in ("SUBTOTAL", "7.B.", "8. ",
                                         "Standard form",
                                         "Formulario Modelo")):
                    if pend:
                        pend += l
                    elif re.fullmatch(r"\d+", txts):
                        continue
                    else:
                        pend_text.append(txts)
                continue
            pend += l
            if not any(g._PCT.match(c["t"].strip()) for c in pend):
                continue  # row still open (values not reached yet)
            cells = pend
            pend = []
            row = {"row_index": len(rows), "raw_cells":
                   [c["t"].strip() for c in cells],
                   "instrument_type_raw": None,
                   "expiration_raw": None, "exercise_period_raw": None,
                   "settlement_raw": None,
                   "voting_rights_raw": None, "voting_rights": None,
                   "pct_raw": None, "pct": None}
            skip = {"N/A", "FÍSICA", "EFECTIVO", "PHYSICAL", "CASH",
                    "AMBAS", "AT ANY TIME", "-", "–"}
            texts = [c["t"].strip() for c in cells
                     if not (g._PCT.match(c["t"].strip()) or
                             g._INT.match(c["t"].strip()) or
                             g._DATE.match(c["t"].strip()))
                     and g._n(c["t"]).strip().upper() not in skip]
            type_txt = " ".join(pend_text + texts).strip()
            pend_text = []
            row["instrument_type_raw"] = type_txt or None
            pcts = [c for c in cells if g._PCT.match(c["t"].strip())]
            ints = [c for c in cells if g._INT.match(c["t"].strip())]
            dts = [c for c in cells if g._DATE.match(c["t"].strip())]
            if pcts:
                row["pct_raw"] = pcts[-1]["t"].strip()
                row["pct"] = str(g.dec(row["pct_raw"]))
            if ints:
                row["voting_rights_raw"] = ints[-1]["t"].strip()
                row["voting_rights"] = g.dec_int(ints[-1]["t"].strip())
            if dts:
                row["expiration_raw"] = dts[0]["t"].strip()
                row["expiration_date"] = g.norm_date(dts[0]["t"].strip())
                if len(dts) > 1 or any(
                        c["t"].strip() == "-" for c in cells):
                    row["exercise_period_raw"] = " ".join(
                        c["t"].strip() for c in cells
                        if g._DATE.match(c["t"].strip()) or
                        c["t"].strip() in ("-", "at any time"))
            else:
                na = [c["t"].strip() for c in cells
                      if c["t"].strip().upper() == "N/A"]
                if na:
                    row["expiration_raw"] = na[0]
            if has_settlement:
                setl = [c["t"].strip() for c in cells
                        if c["t"].strip() in ("Física", "Efectivo",
                                              "Physical", "Cash",
                                              "Ambas")]
                row["settlement_raw"] = setl[0] if setl else None
            rows.append(row)
        pend = []
        pend_text = []
        if e > s:
            vals = [c["t"].strip() for c in _num_cells(lines[e])]
            subtotal = {
                "voting_rights_raw": vals[0] if vals else None,
                "pct_raw": vals[1] if len(vals) > 1 else None,
                "voting_rights": g.dec_int(vals[0]) if vals else None,
                "pct": str(g.dec(vals[1])) if len(vals) > 1 else None}
        return rows, subtotal, s, e

    out["instruments_a_rows"], out["instruments_a_subtotal"], sa, ea = \
        instr_rows(("7.B.1. INSTRUMENTOS", "13(1)(A)"),
                   ("SUBTOTAL 7.B.1", "7.B.2."), False)
    out["instruments_b_rows"], out["instruments_b_subtotal"], sb, eb = \
        instr_rows(("7.B.2. INSTRUMENTOS", "13(1)(B)"),
                   ("SUBTOTAL 7.B.2", "8. INFORMACIÓN"), True)

    # -- section 8: control chain -------------------------------------------
    s8 = g.find_line(lines, "INFORMACIÓN SOBRE EL SUJETO OBLIGADO",
                     "INFORMATION IN RELATION TO THE PERSON")
    e8 = g.find_line(lines, "9. DERECHOS DE VOTO", "VOTING RIGHTS "
                     "RECEIVED", start=s8 + 1) if s8 >= 0 else -1
    if s8 >= 0:
        seg8 = lines[s8:e8 if e8 > s8 else len(lines)]
        for l in seg8:
            t = g._n(" ".join(c["t"] for c in l)).upper()
            cb = g.checkbox(t)
            if cb is None:
                continue
            if "NO ESTÁ CONTROLADO" in t and cb:
                out["subject_control_flag"] = "NOT_CONTROLLED"
            elif "CADENA DE CONTROL" in t and cb:
                out["subject_control_flag"] = "CHAIN_DETAIL"
        i = g.find_line(seg8, "INFORMACIÓN SOBRE LA CADENA DE CONTROL",
                        "INFORMATION IN RELATION TO THE FULL CHAIN")
        if i >= 0:
            j = i + 1
            parts = []
            while j < len(seg8):
                t = g._n(" ".join(c["t"] for c in seg8[j]))
                if "Apellidos y nombre" in t or "Full name" in t:
                    break
                parts.append(t.strip())
                j += 1
            out["chain_info_text_raw"] = " ".join(
                p for p in parts if p).strip() or None
        # inline chain table (when present directly in section 8)
        hi = g.find_line(seg8, "APELLIDOS Y NOMBRE O DENOMINACIÓN",
                         "FULL NAME OR COMPANY NAME")
        if hi >= 0:
            out["chain_rows"] += _chain_rows(
                seg8[hi + 1:], source="SECTION_8")

    # -- annex chain tables ---------------------------------------------------
    # The chain table can appear inline in section 8 and/or in an
    # annex (headed "Annex"/"Anexo"/"Annexure" or unheaded). Detect
    # every occurrence of the chain-table column header anywhere in
    # the document and parse the rows after it.
    if s8 >= 0:
        for j, l in enumerate(lines):
            if j <= (e8 if e8 > s8 else s8):
                continue
            t = g._n(" ".join(c["t"] for c in l)).upper()
            if "APELLIDOS Y NOMBRE O DENOMINACIÓN" in t or \
                    "FULL NAME OR COMPANY NAME" in t:
                # multi-page annex tables repeat the column header on
                # each page -> several segments; row_index must stay
                # unique per notice (chain_path_index stays per-table)
                new = _chain_rows(lines[j + 1:], source="ANNEX")
                base = len(out["chain_rows"])
                for r in new:
                    r["row_index"] += base
                out["chain_rows"] += new

    # -- section 9: proxy ----------------------------------------------------
    s9 = g.find_line(lines, "DERECHOS DE VOTO RECIBIDOS EN "
                     "REPRESENTACIÓN", "VOTING RIGHTS RECEIVED")
    if s9 >= 0:
        row, _ = _first_numeric(lines, s9)
        if row:
            vals = [c["t"].strip() for c in row]
            out["proxy_voting_rights_raw"] = vals[0] if vals else None
            out["proxy_pct_raw"] = vals[1] if len(vals) > 1 else None
            dts = [c["t"].strip() for c in row
                   if g._DATE.match(c["t"].strip())]
            if dts:
                out["proxy_meeting_date_raw"] = dts[0]

    # -- section 10 + in-form annulment block --------------------------------
    s10 = g.find_line(lines, "10. INFORMACIÓN ADICIONAL",
                      "ADDITIONAL INFORMATION")
    san = g.find_line(lines, "ANULACIÓN DE NOTIFICACIONES",
                      "ANNULMENT OF NOTIFICATIONS")
    if s10 >= 0:
        stop = san if san > s10 else \
            g.find_line(lines, "LUGAR Y FECHA", start=s10 + 1)
        seg = [" ".join(c["t"] for c in l)
               for l in lines[s10 + 1:stop if stop > s10 else len(lines)]
               if l]
        out["additional_info_raw"] = g._n(
            " ".join(seg)).strip() or None
    if san >= 0:
        send = g.find_line(lines, "LUGAR Y FECHA", "PLACE AND DATE",
                           "11. INFORMACIÓN", start=san + 1)
        seg = lines[san + 1:send if send > san else len(lines)]
        reg = dts = None
        reasons = []
        mode = None
        for l in seg:
            t = g._n(" ".join(c["t"] for c in l)).strip()
            tu = t.upper()
            if "NÚMERO DE REGISTRO" in tu or "ENTRY REGISTRATION" in tu:
                mode = "reg"
                continue
            if "FECHA DE REGISTRO" in tu or "ENTRY REGISTRATION DATE" in tu:
                mode = "date"
                continue
            if "MOTIVOS DE LA ANULACIÓN" in tu or "REASONS FOR" in tu:
                mode = "why"
                continue
            if not t:
                continue
            if g._DATE.match(t):
                dts = dts or t
            elif re.fullmatch(r"\d{9,10}", t):
                reg = reg or t
            elif mode == "why":
                reasons.append(t)
            elif mode is None and (reg or dts):
                reasons.append(t)
        if reg or dts or reasons:
            out["annulment"] = {
                "annulled_registry_raw": reg, "annulled_date_raw": dts,
                "annulment_reasons_raw": " ".join(reasons) or None}

    # -- section 11: loyalty (CIRC_2_2022 only) -------------------------------
    s11 = g.find_line(lines, "VOTO DOBLE POR LEALTAD",
                      "DOUBLE VOTE DUE TO LOYALTY")
    if s11 >= 0 and tpl == g.T_MODEL_1_C2:
        s11a = g.find_line(lines, "11.A", start=s11)
        sub = g.find_line(lines, "SUBTOTAL 11.A", start=s11)
        out["loyalty_11a_rows"] = []
        if s11a > 0 and sub > s11a:
            for j in range(s11a + 1, sub):
                l = lines[j]
                nums = _num_cells(l)
                dts = [c for c in l if g._DATE.match(c["t"].strip())]
                if len(nums) >= 2 and dts:
                    out["loyalty_11a_rows"].append({
                        "row_index": len(out["loyalty_11a_rows"]),
                        "raw_cells": [c["t"].strip() for c in l]})
        if sub > s11:
            vals = [c for c in _num_cells(lines[sub])]
            out["loyalty_11a"] = {
                "direct_vr_raw": vals[0]["t"].strip() if len(vals) > 0
                else None,
                "indirect_vr_raw": vals[1]["t"].strip() if len(vals) > 1
                else None,
                "direct_additional_raw": vals[2]["t"].strip()
                if len(vals) > 2 else None,
                "indirect_additional_raw": vals[3]["t"].strip()
                if len(vals) > 3 else None,
                "direct_pct_raw": vals[4]["t"].strip() if len(vals) > 4
                else None,
                "indirect_pct_raw": vals[5]["t"].strip() if len(vals) > 5
                else None}
        s11b = g.find_line(lines, "11.B", "REGISTRO ESPECIAL",
                           "SPECIAL REGISTER", start=s11)
        e11b = g.find_line(lines, "SUBTOTAL 11.B", "LUGAR Y FECHA",
                           start=s11b + 1) if s11b > 0 else -1
        if s11b > 0:
            for j in range(s11b + 1, e11b if e11b > s11b else
                           len(lines)):
                l = lines[j]
                if not l:
                    continue
                # a data row opens with the attribution date cell;
                # lone footnote markers are not rows
                if not g._DATE.match(l[0]["t"].strip()):
                    continue
                nums = _num_cells(l)
                if len(nums) >= 2:
                    out["loyalty_11b_rows"].append({
                        "row_index": len(out["loyalty_11b_rows"]),
                        "attribution_date_raw": l[0]["t"].strip(),
                        "attribution_date": g.norm_date(l[0]["t"].strip()),
                        "raw_cells": [c["t"].strip() for c in l]})
    elif s11 >= 0:
        out["unmapped"].append("loyalty_section_unexpected_template")

    # -- signature / post-signature annex ------------------------------------
    i = g.find_line(lines, "LUGAR Y FECHA DE LA NOTIFICACIÓN",
                    "PLACE AND DATE OF THE NOTIFICATION")
    if i >= 0:
        v, j = _value_after(lines, i)
        if v:
            out["signature_raw"] = g._n(
                " ".join(c["t"] for c in v)).strip()
            rest = [" ".join(c["t"] for c in l)
                    for l in lines[j + 1:] if l]
            rest = [r for r in rest
                    if "Standard form" not in r and
                    not re.fullmatch(r"Formulario Modelo \d", g._n(r)) and
                    not re.fullmatch(r"\d+ / \d+", g._n(r))]
            out["post_signature_raw"] = g._n(
                " ".join(rest)).strip() or None

    # -- aggregate QA (declared never overwritten) -----------------------------
    pc = out["position_current"]
    if pc and pc.get("pct_shares") and pc.get("pct_instruments") \
            and pc.get("pct_total"):
        comp = g.dec(pc["pct_shares"]) + g.dec(pc["pct_instruments"])
        decl = g.dec(pc["pct_total"])
        gran = Decimal(1).scaleb(-decl.as_tuple().exponent) / 2
        out["aggregate_qa"] = "DECLARED_COMPUTED_MATCH" \
            if abs(comp - decl) <= gran else "DECLARED_COMPUTED_MISMATCH"
    elif pc:
        out["aggregate_qa"] = "NOT_COMPUTABLE"

    out["parse_status"] = g.PARSED_UNMAPPED if out["unmapped"] else g.PARSED
    return out


def _chain_rows(seg, source):
    """Chain table rows: name cell + optional % cells. A new path
    starts when the entity repeats the first entry of the current
    path (root repeats). `chain_path_index` is a derived grouping."""
    rows, cur_root, path = [], None, -1
    for l in seg:
        if not l:
            continue
        name = l[0]["t"].strip()
        t = g._n(" ".join(c["t"] for c in l))
        if any(k in t for k in ("Apellidos y nombre", "% derechos",
                                "paraíso", "supera el", "Total (",
                                "9. DERECHOS", "10. INFORMACIÓN",
                                "11. INFORMACIÓN",
                                "Standard form", "Formulario Modelo",
                                "LUGAR Y FECHA", "Lugar y fecha")):
            if "9. DERECHOS" in t or "10. INFORMACIÓN" in t or \
                    "11. INFORMACIÓN" in t or "Lugar y fecha" in t or \
                    "LUGAR Y FECHA" in t:
                break
            continue
        # chain entity names live in the left column; fragments of
        # wrapped header cells land far right and are not rows
        if not name or l[0]["x0"] > 150 or \
                re.fullmatch(r"\d+ / \d+", name) or \
                re.fullmatch(r"\d+", name):
            continue
        # header cells split across visual lines are not entities
        if name.upper().startswith((
                "FULL NAME", "COMPANY NAME", "OF THE CONTROLLED",
                "APELLIDOS", "NOMBRE", "DENOMINACIÓN", "%",
                "CONTROLLED UNDERTAKING", "ENTIDAD")):
            continue
        nums = [c["t"].strip() for c in l[1:]
                if g._PCT.match(c["t"].strip())]
        if cur_root is None:
            cur_root = name
        if name == cur_root and rows and rows[-1]["source"] == source:
            path += 1
        elif not rows or rows[-1]["source"] != source:
            path += 1
        rows.append({"source": source,
                     "row_index": len(rows),
                     "chain_path_index": path,
                     "entity_name_raw": name,
                     "pct_voting_rights_raw": nums[0] if nums else None,
                     "pct_instruments_raw": nums[1] if len(nums) > 1
                     else None,
                     "pct_total_raw": nums[2] if len(nums) > 2 else None})
    return rows


def parse_pdf(pdf_bytes):
    try:
        pages = g.extract_cells(pdf_bytes)
    except Exception as e:
        return {"semantic_parser_version": SEMANTIC_PARSER_VERSION,
                "parse_status": g.EXTRACTION_ERROR,
                "error": repr(e)}
    out = parse_lines(pages)
    import pdfminer
    out["pdf_engine"] = f"pdfminer.six=={pdfminer.__version__}"
    out["doc_sha256"] = hashlib.sha256(pdf_bytes).hexdigest()
    return out
