"""G3-B treasury-stock parser — CNMV own-shares forms.

Templates: CIRC_8_2015_MODEL_4 and CIRC_2_2022_MODEL_2 (the Circular
2/2022 renumbering; structure observed identical). Three semantic
layers are kept strictly separate:

  section 4  operation FLOW (each row = one acquisition/transmission)
  section 5  resulting STOCK (final position in shares/voting rights)
  section 2  declared regulatory trigger (2.2 = 1% acquisitions flag)

The 1% trigger is a DECLARED checkbox — it is never recomputed and
disposals are never netted against acquisitions.
"""
import hashlib
import re

from . import g3pdf as g

SEMANTIC_PARSER_VERSION = "acpdf-0.1.0"


def _sub_header_anchors(lines, s, e, labels):
    """x0 anchors of every sub-header cell inside [s, e) containing
    one of the labels. The CNMV grid renders Directas/Indirectas/
    Precio on stacked visual lines and data cell x0 drifts a few
    points from its column anchor, so callers snap each value to
    the NEAREST anchor — interval banding misclassifies cells."""
    xs = []
    for j in range(s, min(e, s + 60)):
        hits = [c for c in lines[j]
                if any(lab in g._n(c["t"]).upper() for lab in labels)]
        if hits:
            xs += [c["x0"] for c in hits]
        elif xs:
            break
    return sorted(set(round(x, 1) for x in xs))


def _nearest(x, anchors, tol=42.0):
    best, bd = None, tol
    for i, a in enumerate(anchors):
        d = abs(x - a)
        if d < bd:
            best, bd = i, d
    return best


_OP_KEYS = ("shares_direct", "price_direct", "shares_indirect",
            "price_indirect", "vr_direct", "vr_indirect",
            "pct_direct", "pct_indirect")
_FP_KEYS = ("shares_direct", "shares_indirect", "vr_direct",
            "vr_indirect", "vr_total", "pct_direct", "pct_indirect",
            "pct_total")


def parse_lines(pages):
    out = {
        "semantic_parser_version": SEMANTIC_PARSER_VERSION,
        "regulatory_template": g.fingerprint(pages),
        "parse_status": None, "unmapped": [],
        "registry_stamp_raw": None,
        "issuer_nif_raw": None,
        "issuer_name_document": None,
        "issuer_voting_rights_raw": None, "issuer_voting_rights": None,
        "reason_first_admission": None,
        "reason_acquisitions_1pct": None,
        "reason_voting_rights_update": None,
        "notification_date_raw": None, "notification_date": None,
        "operations": [],
        "total_acquisitions": None, "total_transmissions": None,
        "operations_flow_qa": None,
        "final_position": None,
        "indirect_controlled": [], "indirect_controlled_pct_raw": None,
        "indirect_controlled_checked": None,
        "indirect_interposed": [], "indirect_other": [],
        "indirect_controlled_empty": None,
        "indirect_interposed_empty": None, "indirect_other_empty": None,
        "total_indirect_pct_raw": None,
        "chain_detail_raw": None,
        "additional_info_raw": None,
        "signature_raw": None,
    }
    t = out["regulatory_template"]
    if t in (g.UNSUPPORTED_NO_TEXT, g.UNSUPPORTED_TEMPLATE,
             g.UNSUPPORTED_LEGACY, g.T_MODEL_1_C8, g.T_MODEL_1_C2,
             g.T_MODEL_2_DIR):
        out["parse_status"] = (g.UNSUPPORTED_NO_TEXT
                               if t == g.UNSUPPORTED_NO_TEXT
                               else g.UNSUPPORTED_LEGACY
                               if t == g.UNSUPPORTED_LEGACY
                               else g.UNSUPPORTED_TEMPLATE)
        return out

    lines = g.all_lines(pages)

    i = g.find_line(lines, "REGISTRO DE ENTRADA N")
    if i >= 0:
        out["registry_stamp_raw"] = g._n(
            " ".join(c["t"] for c in lines[i])).strip()

    # -- section 1: issuer ---------------------------------------------------
    i = g.find_line(lines, "NIF | TAX ID", "NIF")
    if i >= 0:
        for l in lines[i:i + 3]:
            for c in l:
                tt = c["t"].strip()
                if re.fullmatch(r"[A-Z]?\d{7,8}[A-Z]?", tt):
                    out["issuer_nif_raw"] = tt
    i = g.find_line(lines, "DENOMINACIÓN SOCIAL", "COMPANY NAME")
    if i >= 0:
        for j in range(i + 1, min(len(lines), i + 3)):
            if lines[j]:
                out["issuer_name_document"] = g._n(
                    " ".join(c["t"] for c in lines[j])).strip()
                break
    i = g.find_line(lines, "DERECHOS DE VOTO", "VOTING RIGHTS")
    if i >= 0:
        # the value cell renders on the visual line ABOVE the label;
        # only the multi-group integer (thousands separators) counts
        for j in range(max(0, i - 2), min(len(lines), i + 4)):
            hit = [c["t"].strip() for c in lines[j]
                   if re.fullmatch(r"\d{1,3}(?:\.\d{3}){2,}",
                                   c["t"].strip())]
            if hit:
                out["issuer_voting_rights_raw"] = hit[0]
                out["issuer_voting_rights"] = g.dec_int(hit[0])
                break

    # -- section 2: reasons ----------------------------------------------------
    # unchecked boxes may render as a lone "[ ]" cell on the adjacent
    # visual line — look one line up/down when the label has none
    def cb_of(i):
        t = g._n(" ".join(c["t"] for c in lines[i])).upper()
        cb = g.checkbox(t)
        if cb is not None:
            return cb
        for j in (i - 1, i + 1):
            if 0 <= j < len(lines) and lines[j]:
                cs = [c["t"].strip() for c in lines[j]]
                if len(cs) == 1 and \
                        re.fullmatch(r"\[\s*[^\]]*\]", cs[0]):
                    return g.checkbox(cs[0])
        return None

    for li, l in enumerate(lines):
        t = g._n(" ".join(c["t"] for c in l)).upper()
        cb = cb_of(li)
        if cb is None:
            continue
        if "PRIMERA ADMISIÓN" in t or "FIRST ADMISSION" in t:
            out["reason_first_admission"] = cb
        elif "UMBRAL DEL 1%" in t or "THRESHOLD OF 1%" in t:
            out["reason_acquisitions_1pct"] = cb
        elif "ACTUALIZACIÓN SOBREVENIDA" in t or "UPDATING AS A RESULT" in t:
            out["reason_voting_rights_update"] = cb

    # -- section 3: notification date ------------------------------------------
    i = g.find_line(lines, "FECHA QUE MOTIVA LA NOTIFICACIÓN",
                    "DATE GIVING RISE")
    if i >= 0:
        for j in range(i + 1, min(len(lines), i + 4)):
            d = [c["t"].strip() for c in lines[j]
                 if g._DATE.match(c["t"].strip())]
            if d:
                out["notification_date_raw"] = d[0]
                out["notification_date"] = g.norm_date(d[0])
                break
        if out["notification_date_raw"] is None:
            out["unmapped"].append("notification_date")

    # -- section 4: operations ---------------------------------------------------
    s4 = g.find_line(lines, "DETALLE DE LAS OPERACIONES",
                     "DETAIL OF THE TRANSACTIONS")
    e4 = g.find_line(lines, "5. POSESIÓN FINAL", "FINAL POSITION",
                     start=s4 + 1) if s4 >= 0 else -1
    if s4 < 0:
        out["unmapped"].append("section4_anchor")
    else:
        anchors = _sub_header_anchors(
            lines, s4, e4,
            ("DIRECTAS", "INDIRECTAS", "DIRECTOS", "INDIRECTOS",
             "PRECIO", "PRICE"))
        # 8 column anchors in _OP_KEYS order
        for l in lines[s4 + 1:e4 if e4 > s4 else len(lines)]:
            if not l:
                continue
            tt = g._n(" ".join(c["t"] for c in l))
            tu = tt.upper()
            if "TOTAL ADQUISICIÓN" in tu or "TOTAL ACQUISITIONS" in tu:
                out["total_acquisitions"] = _total_row(l, anchors)
                continue
            if "TOTAL TRANSMISIÓN" in tu or "TOTAL TRANSMISSIONS" in tu:
                out["total_transmissions"] = _total_row(l, anchors)
                continue
            if not any(g._DATE.match(c["t"].strip()) for c in l):
                continue
            dcell = next(c for c in l if g._DATE.match(c["t"].strip()))
            at = next((c["t"].strip() for c in l
                       if c["t"].strip() in ("A", "T")), None)
            isin = next((c["t"].strip() for c in l
                         if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9,10}",
                                         c["t"].strip())), None)
            nums = [c for c in l
                    if g._PCT.match(c["t"].strip()) or
                    g._INT.match(c["t"].strip())]
            op = {"row_index": len(out["operations"]),
                  "operation_date_raw": dcell["t"].strip(),
                  "operation_date": g.norm_date(dcell["t"].strip()),
                  "operation_flag_raw": at,
                  "operation_flag_normalized":
                      {"A": "ACQUISITION", "T": "DISPOSAL"}.get(at),
                  "isin": isin,
                  "shares_direct_raw": None, "price_direct_raw": None,
                  "shares_indirect_raw": None, "price_indirect_raw": None,
                  "vr_direct_raw": None, "vr_indirect_raw": None,
                  "pct_direct_raw": None, "pct_indirect_raw": None,
                  "shares_direct": None, "price_direct": None,
                  "shares_indirect": None, "price_indirect": None,
                  "vr_direct": None, "vr_indirect": None,
                  "pct_direct": None, "pct_indirect": None,
                  "raw_cells": [c["t"].strip() for c in l]}
            if anchors and len(anchors) == 8:
                for c in nums:
                    bi = _nearest(c["x0"], anchors)
                    if bi is None:
                        continue
                    k = _OP_KEYS[bi]
                    if op[k + "_raw"] is not None:
                        # second value snapped to one column: keep
                        # both in raw_cells only, flag unmapped
                        out["unmapped"].append(
                            f"op{op['row_index']}_{k}_duplicate")
                        continue
                    op[k + "_raw"] = c["t"].strip()
                    op[k] = (str(g.dec(c["t"].strip()))
                             if k.startswith(("price", "pct"))
                             else g.dec_int(c["t"].strip()))
            else:
                out["unmapped"].append("op_column_anchors")
            out["operations"].append(op)
        if not out["operations"]:
            out["unmapped"].append("no_operation_rows")

    # flow QA: declared totals vs computed sums (never netted)
    if out["total_acquisitions"] or out["total_transmissions"]:
        qa = {}
        for kind, decl in (("acquisitions", out["total_acquisitions"]),
                           ("transmissions", out["total_transmissions"])):
            flag = "ACQUISITION" if kind == "acquisitions" else "DISPOSAL"
            ops = [o for o in out["operations"]
                   if o["operation_flag_normalized"] == flag]
            sd = sum(o["shares_direct"] or 0 for o in ops)
            si = sum(o["shares_indirect"] or 0 for o in ops)
            vd = sum(o["vr_direct"] or 0 for o in ops)
            vi = sum(o["vr_indirect"] or 0 for o in ops)
            if decl:
                # declared totals sit under the voting-rights columns;
                # a column absent in source compares as zero
                dd = g.dec_int(decl["vr_direct_raw"] or "0")
                di = g.dec_int(decl["vr_indirect_raw"] or "0")
                st = "MATCH" if (dd == vd and di == vi) \
                    else "DIVERGENT"
                qa[kind] = {
                    "computed_shares_direct": str(sd),
                    "computed_shares_indirect": str(si),
                    "computed_vr_direct": str(vd),
                    "computed_vr_indirect": str(vi),
                    "declared_vr_direct_raw": decl["vr_direct_raw"],
                    "declared_vr_indirect_raw": decl["vr_indirect_raw"],
                    "status": st}
        out["operations_flow_qa"] = qa

    # -- section 5: final position ---------------------------------------------
    s5 = e4
    e5 = g.find_line(lines, "6. IDENTIFICACIÓN", "IDENTITY AND DETAILS",
                     start=s5 + 1) if s5 >= 0 else -1
    if s5 >= 0:
        anchors5 = _sub_header_anchors(
            lines, s5, e5, ("DIRECTAS", "INDIRECTAS", "DIRECTOS",
                            "INDIRECTOS", "TOTAL"))
        for l in lines[s5 + 1:e5 if e5 > s5 else len(lines)]:
            if not l:
                continue
            tt = g._n(" ".join(c["t"] for c in l))
            if "TOTAL" in tt.upper() and not any(
                    re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9,10}", c["t"].strip())
                    for c in l):
                nums = [c["t"].strip() for c in l
                        if g._PCT.match(c["t"].strip()) or
                        g._INT.match(c["t"].strip())]
                if nums and out["final_position"] is not None:
                    out["final_position"]["total_row_raw"] = nums
                continue
            isin = next((c["t"].strip() for c in l
                         if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9,10}",
                                         c["t"].strip())), None)
            if not isin:
                continue
            fp = {"isin": isin, "raw_cells": [c["t"].strip() for c in l]}
            if anchors5 and len(anchors5) == 8:
                for c in l[1:]:
                    v = c["t"].strip()
                    if not (g._PCT.match(v) or g._INT.match(v)):
                        continue
                    bi = _nearest(c["x0"], anchors5)
                    if bi is None:
                        continue
                    k = _FP_KEYS[bi]
                    if k + "_raw" in fp:
                        continue
                    fp[k + "_raw"] = v
                    fp[k] = (str(g.dec(v)) if k.startswith("pct")
                             else g.dec_int(v))
            else:
                nums = [c["t"].strip() for c in l[1:]
                        if g._PCT.match(c["t"].strip()) or
                        g._INT.match(c["t"].strip())]
                for k, v in zip(_FP_KEYS, nums):
                    fp[k + "_raw"] = v
                    fp[k] = (str(g.dec(v)) if k.startswith("pct")
                             else g.dec_int(v))
            out["final_position"] = fp

    # -- section 6: indirect position --------------------------------------------
    s6 = e5
    e6 = g.find_line(lines, "7. DETALLE DE LA CADENA",
                     "DETAILS OF THE CHAIN", start=s6 + 1) \
        if s6 >= 0 else -1
    if s6 >= 0:
        cur = None
        pending = []
        last_key = None
        for l in lines[s6:e6 if e6 > s6 else len(lines)]:
            tt = g._n(" ".join(c["t"] for c in l))
            tu = tt.upper()
            cb = g.checkbox(tt)
            if "6.1" in tu or "SOCIEDADES CONTROLADAS" in tu or \
                    "COMPANIES CONTROLLED" in tu:
                cur = "controlled"
                if cb:
                    out["indirect_controlled_checked"] = True
                pc = [c["t"].strip() for c in l if g._PCT.match(
                    c["t"].strip())]
                if pc:
                    out["indirect_controlled_pct_raw"] = pc[-1]
                continue
            if "6.2" in tu or "PERSONAS INTERPUESTAS" in tu or \
                    "PERSON ACTING" in tu:
                cur = "interposed"
                continue
            if "6.3" in tu or "OTRAS CIRCUNSTANCIAS" in tu or \
                    "OTHER DIFFERENT" in tu:
                cur = "other"
                continue
            if "TOTAL PARTICIPACION INDIRECTA" in tu or \
                    "TOTAL INDIRECT HOLDING" in tu:
                pc = [c["t"].strip() for c in l if g._PCT.match(
                    c["t"].strip())]
                if pc:
                    out["total_indirect_pct_raw"] = pc[-1]
                cur = None
                continue
            if cur is None or not l:
                continue
            if any(k in tu for k in ("DENOMINACIÓN SOCIAL",
                                     "COMPANY NAME",
                                     "APELLIDOS Y NOMBRE",
                                     "FULL NAME")):
                continue
            name = l[0]["t"].strip()
            if not name or re.fullmatch(r"\[\s*[^\]]*\]", name):
                continue
            if "NO HAY DATOS" in tu:
                out["indirect_" + cur + "_empty"] = True
                continue
            key = {"controlled": "indirect_controlled",
                   "interposed": "indirect_interposed",
                   "other": "indirect_other"}[cur]
            last_key = key
            pc = [c["t"].strip() for c in l
                  if g._PCT.match(c["t"].strip())]
            # long entity names wrap across lines; pct cells may land
            # on their own line between the fragments
            if (g._PCT.match(name) or g._INT.match(name)) and \
                    len(pc) == 1 and name == pc[0]:
                if pending:
                    out[key].append({"name_raw": " ".join(pending),
                                     "pct_raw": name})
                    pending = []
                elif out[key]:
                    out[key][-1]["pct_raw"] = \
                        out[key][-1]["pct_raw"] or name
                continue
            if pc:
                if pending:
                    name = " ".join(pending) + " " + name
                    pending = []
                out[key].append({"name_raw": name,
                                 "pct_raw": pc[0]})
            else:
                pending.append(name)
        # trailing pct-less lines continue the last entity's name
        if pending and last_key and out[last_key]:
            out[last_key][-1]["name_raw"] += " " + " ".join(pending)

    # -- section 7 + 8 -----------------------------------------------------------
    s7 = e6
    e7 = g.find_line(lines, "8. INFORMACIÓN ADICIONAL",
                     "ADDITIONAL INFORMATION", start=s7 + 1) \
        if s7 >= 0 else -1
    if s7 >= 0 and e7 > s7:
        seg = [" ".join(c["t"] for c in l)
               for l in lines[s7 + 1:e7] if l]
        out["chain_detail_raw"] = g._n(" ".join(seg)).strip() or None
    s8 = e7
    e8 = g.find_line(lines, "LUGAR Y FECHA", "PLACE AND DATE",
                     start=s8 + 1) if s8 >= 0 else -1
    if s8 >= 0:
        seg = [" ".join(c["t"] for c in l)
               for l in lines[s8 + 1:e8 if e8 > s8 else len(lines)] if l]
        out["additional_info_raw"] = g._n(" ".join(seg)).strip() or None
    i = g.find_line(lines, "LUGAR Y FECHA DE LA NOTIFICACIÓN",
                    "PLACE AND DATE OF THE NOTIFICATION")
    if i >= 0:
        for j in range(i + 1, min(len(lines), i + 3)):
            if lines[j]:
                out["signature_raw"] = g._n(
                    " ".join(c["t"] for c in lines[j])).strip()
                break

    out["parse_status"] = g.PARSED_UNMAPPED if out["unmapped"] else g.PARSED
    return out


def _total_row(l, anchors):
    """Declared totals row. Values sit under the voting-rights and
    percentage columns — snap to the same 8 anchors as the data."""
    row = {"vr_direct_raw": None, "vr_indirect_raw": None,
           "pct_direct_raw": None, "pct_indirect_raw": None,
           "raw_cells": [c["t"].strip() for c in l]}
    keep = {"vr_direct": "vr_direct_raw",
            "vr_indirect": "vr_indirect_raw",
            "pct_direct": "pct_direct_raw",
            "pct_indirect": "pct_indirect_raw"}
    for c in l:
        v = c["t"].strip()
        if not (g._PCT.match(v) or g._INT.match(v)):
            continue
        bi = _nearest(c["x0"], anchors) if anchors else None
        k = keep.get(_OP_KEYS[bi]) if bi is not None else None
        if k and row[k] is None:
            row[k] = v
    if row["vr_direct_raw"] is None:
        nums = [c["t"].strip() for c in l
                if g._PCT.match(c["t"].strip()) or
                g._INT.match(c["t"].strip())]
        row["vr_direct_raw"] = nums[0] if len(nums) > 0 else None
        row["vr_indirect_raw"] = nums[1] if len(nums) > 1 else None
        row["pct_direct_raw"] = nums[2] if len(nums) > 2 else None
        row["pct_indirect_raw"] = nums[3] if len(nums) > 3 else None
    return row


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
