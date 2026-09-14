"""G2 NOD/MAR PDF parser — EU 2016/523 form as rendered by CNMV.

Two layers:
  extract_lines(pdf_bytes)  pdfminer LTChar -> pages -> lines -> cells
  parse_lines(pages)        deterministic structure parser (no PDF dep)

The second layer is pure text, so unit tests feed synthetic fixtures
without shipping real CNMV documents.

CNMV renders section 4 as a wide grid (not the stacked EU layout):
each physical row is one price/volume pair (execution_line); the
maximal run of rows sharing (instrument code, instrument nature,
transaction nature, date, venue) is one repetition block
(transaction_event); the following "Total Agregado" row is the
declared aggregate — never an execution line.
"""
import hashlib
import io
import re
import unicodedata
from decimal import Decimal


def _n(t):
    """NFKC fold for matching only — raw fields keep the literal text
    (the CNMV form uses fi/fl ligatures and non-breaking spaces)."""
    return unicodedata.normalize("NFKC", t or "").replace("\xa0", " ")

SEMANTIC_PARSER_VERSION = "nodpdf-0.1.0"
TEMPLATE_PDMR = "EU_2016_523_PDMR_CNMV"

X_GAP = 3.0            # cell-separation threshold, PDF points
Y_TOL = 1.0            # line-clustering tolerance, PDF points

_DATE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_NUM = re.compile(r"^-?\d{1,3}(?:[. ]\d{3})*,\d+$|^-?\d+,\d+$")
_CHECKED = re.compile(r"\[\s*[^\]\s]\s*\]")

PARSED = "PARSED"
PARSED_UNMAPPED = "PARSED_WITH_UNMAPPED_VALUES"
UNSUPPORTED_TEMPLATE = "UNSUPPORTED_TEMPLATE"
UNSUPPORTED_NO_TEXT = "UNSUPPORTED_NO_TEXT_LAYER"
MALFORMED = "MALFORMED_SOURCE"
EXTRACTION_ERROR = "EXTRACTION_ERROR"

# deterministic lexical rules only — anything else stays NULL/UNKNOWN
NATURE_MAP = {"Compra": "BUY", "Venta": "SELL"}
_LEGAL_SUFFIX = re.compile(
    r"\b(S\.?\s?A\.?|S\.?\s?L\.?|L\.?\s?P\.?|LTD|LLC|B\.?\s?V\.?|GMBH|SARL|N\.?\s?V\.?|PLC|INC)\b",
    re.I)


def dec(s):
    """CNMV decimal literal -> exact Decimal (None if unparseable)."""
    if s is None:
        return None
    t = s.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return Decimal(t)
    except Exception:
        return None


# ---------------------------------------------------------------- extraction

def extract_lines(pdf_bytes):
    """PDF bytes -> list[page] of list[line] of list[cell] strings."""
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTChar
    pages = []
    for page in extract_pages(io.BytesIO(pdf_bytes)):
        chars = []

        def walk(o):
            for c in o:
                if isinstance(c, LTChar):
                    chars.append(c)
                elif hasattr(c, "__iter__"):
                    try:
                        walk(c)
                    except TypeError:
                        pass
        walk(page)
        rows = {}
        for c in chars:
            for y in rows:
                if abs(c.y0 - y) <= Y_TOL:
                    rows[y].append(c)
                    break
            else:
                rows[c.y0] = [c]
        lines = []
        for y in sorted(rows, reverse=True):
            cs = sorted(rows[y], key=lambda c: c.x0)
            cells, cur, px = [], "", None
            for c in cs:
                if px is not None and c.x0 - px > X_GAP:
                    cells.append(cur)
                    cur = ""
                cur += c.get_text()
                px = c.x1
            cells.append(cur)
            lines.append([c.strip() for c in cells if c.strip()])
        pages.append(lines)
    return pages


def _flat(pages):
    return [cell for page in pages for line in page for cell in line]


def fingerprint(pages):
    flat = _flat(pages)
    if not flat:
        return UNSUPPORTED_NO_TEXT
    joined = _n(" ".join(flat))
    anchors = ("MODELO DE NOTIFICACIÓN" in joined and
               "STANDARD FORM FOR NOTIFICATION" in joined and
               "Total Agregado" in joined and
               all(lbl in joined for lbl in
                   ("4.a)", "4.b)", "4.c)", "4.d)", "4.e)",
                    "4.f)", "4.g)", "4.h)")))
    return TEMPLATE_PDMR if anchors else UNSUPPORTED_TEMPLATE


# ---------------------------------------------------------------- structure

def _next_value(lines, i):
    """First non-empty cell of the next non-empty line after i."""
    for j in range(i + 1, len(lines)):
        if lines[j]:
            return lines[j][0], j
    return None, i


def _find_anchor(lines, *needles, start=0):
    for i in range(start, len(lines)):
        t = _n(" ".join(lines[i]))
        if any(n in t for n in needles):
            return i
    return -1


def _is_data_row(cells):
    return (len(cells) == 8 and _DATE.match(cells[3]) is not None and
            _NUM.match(cells[5]) is not None)


def parse_lines(pages):
    """pages (lines of cells) -> normalized notice parse dict."""
    out = {"semantic_parser_version": SEMANTIC_PARSER_VERSION,
           "regulatory_template": fingerprint(pages),
           "parse_status": None, "unmapped": [],
           "notification_kind": None, "amendment_text_raw": None,
           "notifying_party_name_raw": None, "notifying_party_kind": None,
           "position_status_raw": None, "closely_associated": "UNKNOWN",
           "related_pdmr_name_raw": None, "related_pdmr_position_raw": None,
           "issuer_name_document": None, "issuer_lei_document": None,
           "additional_info_raw": None, "events": []}
    if out["regulatory_template"] in (UNSUPPORTED_NO_TEXT,
                                      UNSUPPORTED_TEMPLATE):
        out["parse_status"] = out["regulatory_template"]
        return out

    lines = [l for page in pages for l in page]

    # -- section 1: notifying party -------------------------------------
    i = _find_anchor(lines, "Nombre y apellidos", "Name and surname")
    if i >= 0:
        v, _ = _next_value(lines, i)
        out["notifying_party_name_raw"] = v
    else:
        out["unmapped"].append("party_name_anchor")

    # -- section 2: checkboxes / position / kind --------------------------
    pdmr = ca = None
    for l in lines:
        t = _n(" ".join(l))
        if "Persona con responsabilidad" in t or \
           "Person discharging managerial" in t:
            pdmr = bool(_CHECKED.search(t))
        if "Persona estrechamente vinculada" in t or \
           "Person closely associated" in t:
            ca = bool(_CHECKED.search(t))
    if ca and not pdmr:
        out["closely_associated"] = "TRUE"
    elif pdmr and not ca:
        out["closely_associated"] = "FALSE"
    else:
        out["unmapped"].append("checkbox_state")

    name = out["notifying_party_name_raw"] or ""
    if pdmr and not ca:
        out["notifying_party_kind"] = "NATURAL_PERSON"   # PDMR is always natural
    elif _LEGAL_SUFFIX.search(name):
        out["notifying_party_kind"] = "LEGAL_PERSON"
    elif name:
        out["notifying_party_kind"] = "UNKNOWN"

    i = _find_anchor(lines, "Cargo - posición", "Job title")
    if i >= 0:
        v, j = _next_value(lines, i)
        # job title may wrap; take lines until the next labeled field
        extra = []
        k = j + 1
        while k < len(lines) and _find_anchor(
                [lines[k]], "Notificación inicial",
                "Initial Noti") < 0:
            extra.append(" ".join(lines[k]))
            k += 1
        out["position_status_raw"] = " ".join([v or ""] + extra).strip() or None

    i = _find_anchor(lines, "Notificación inicial", "Initial Noti")
    if i >= 0:
        v, j = _next_value(lines, i)
        vn = _n(v)
        if "Modificaci" in vn:
            out["notification_kind"] = "AMENDMENT"
            # explanation text = anything between the kind value and
            # the section-3 anchor (the EU form asks to describe the
            # corrected error); absent -> NULL, never the value itself
            s3 = _find_anchor(lines, "DATOS DEL EMISOR",
                              "DETAILS OF THE ISSUER", start=j + 1)
            stop = s3 if s3 > j else len(lines)
            rest = " ".join(" ".join(l) for l in lines[j + 1:stop] if l)
            out["amendment_text_raw"] = rest.strip() or None
        elif "Inicial" in vn:
            out["notification_kind"] = "INITIAL"
        else:
            out["notification_kind"] = "UNKNOWN"
            out["unmapped"].append("notification_kind")
    else:
        out["notification_kind"] = "UNKNOWN"
        out["unmapped"].append("kind_anchor")

    # -- section 3: issuer ------------------------------------------------
    i = _find_anchor(lines, "a) Identificación", "Identiﬁcación")
    if i >= 0:
        v, _ = _next_value(lines, i)
        out["issuer_name_document"] = v
    i = _find_anchor(lines, "b) LEI", "LEI:")
    if i >= 0:
        v, _ = _next_value(lines, i)
        out["issuer_lei_document"] = v

    # -- section 4: transaction grid --------------------------------------
    s4 = _find_anchor(lines, "DATOS DE LA OPERACIÓN", "DETAILS OF THE")
    send = _find_anchor(lines, "Otra información", "Additional information")
    grid = lines[s4 + 1:send if send > s4 else len(lines)] if s4 >= 0 else []
    if s4 < 0:
        out["unmapped"].append("section4_anchor")
    if send > s4:
        extra = [" ".join(l) for l in lines[send + 1:] if l]
        out["additional_info_raw"] = "\n".join(extra).strip() or None

    cur = None
    pending_agg = None
    for l in grid:
        if _is_data_row(l):
            key = (l[0], l[1], l[2], l[3], l[4])
            if cur is None or cur["_key"] != key:
                cur = {"_key": key, "source_order": len(out["events"]),
                       "instrument_code_raw": l[0],
                       "instrument_type_raw": l[1],
                       "transaction_nature_raw": l[2],
                       "transaction_date_raw": l[3],
                       "venue_raw": l[4],
                       "executions": [], "aggregate": None}
                out["events"].append(cur)
            cur["executions"].append(
                {"volume_raw": l[5], "price_raw": l[6],
                 "currency_raw": l[7]})
        elif any("Total Agregado" in c for c in l):
            pending_agg = True
        elif pending_agg and all(_NUM.match(c) for c in l) and \
                1 <= len(l) <= 2:
            if cur is not None:
                cur["aggregate"] = {"volume_raw": l[0],
                                    "price_raw": l[1] if len(l) > 1 else None}
            pending_agg = False
        elif any(re.search(r"4\.[a-h]\)", c) for c in l) or \
                any("..." in c for c in l):
            continue  # grid header labels
        elif _DATE.match(l[0] if l else "") is None and l and \
                cur is None and not pending_agg:
            pass  # column header text rows
    for ev in out["events"]:
        del ev["_key"]

    if not out["events"] and s4 >= 0:
        out["unmapped"].append("no_data_rows")

    for ev in out["events"]:
        normalize_event(ev)
    out["parse_status"] = PARSED_UNMAPPED if out["unmapped"] else PARSED
    return out


# ---------------------------------------------------------------- normalize

def normalize_event(ev):
    """Attach normalized/decimal + QA fields to a raw parsed event."""
    m = _DATE.match(ev.get("transaction_date_raw") or "")
    ev["transaction_date"] = (f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
                              if m else None)
    v = ev.get("venue_raw") or ""
    ev["venue_code_raw"] = v if re.fullmatch(r"[A-Z0-9]{4}", v) else None
    # ISO 10383: XOFF = off-venue; XXXX = no allocated MIC (used for
    # transactions outside any listed venue). Anything else with a MIC
    # is a named trading venue.
    ev["outside_trading_venue"] = ("TRUE" if v in ("XOFF", "XXXX")
                                   else "FALSE" if v else "UNKNOWN")
    ev["transaction_nature_normalized"] = NATURE_MAP.get(
        ev.get("transaction_nature_raw"))
    ev["share_option_program_linked"] = "UNKNOWN"
    for e in ev["executions"]:
        e["volume"] = dec(e["volume_raw"])
        e["price"] = dec(e["price_raw"])
        e["currency"] = e.get("currency_raw") or None
    agg = ev.get("aggregate")
    if agg:
        ev["declared_aggregate_volume"] = agg.get("volume_raw")
        ev["declared_aggregate_price"] = agg.get("price_raw")
    lines = [e for e in ev["executions"]
             if e["volume"] is not None and e["price"] is not None]
    ccy = {e["currency"] for e in lines}
    if lines and len(ccy) == 1:
        cv = sum(e["volume"] for e in lines)
        ev["computed_volume"] = str(cv)
        if cv != 0:
            ev["computed_vwap"] = str(
                sum(e["price"] * e["volume"] for e in lines) / cv)
        if agg:
            dv, dp = dec(agg.get("volume_raw")), dec(agg.get("price_raw"))
            ok_v = dv is not None and dv == cv
            ok_p = True
            if dp is not None and ev.get("computed_vwap") and cv != 0:
                gran = Decimal(1).scaleb(-dp.as_tuple().exponent) / 2
                ok_p = abs(Decimal(ev["computed_vwap"]) - dp) <= gran
            ev["aggregate_qa"] = "MATCH" if (ok_v and ok_p) else "DIVERGENT"
        else:
            ev["aggregate_qa"] = "NO_DECLARED_AGGREGATE"
    else:
        ev["aggregate_qa"] = "NOT_COMPUTABLE"
    return ev


def parse_pdf(pdf_bytes):
    """Full pipeline: bytes -> normalized parse dict (fail-closed)."""
    try:
        pages = extract_lines(pdf_bytes)
    except Exception as e:
        return {"semantic_parser_version": SEMANTIC_PARSER_VERSION,
                "parse_status": EXTRACTION_ERROR,
                "error": repr(e), "events": []}
    out = parse_lines(pages)
    out["doc_sha256"] = hashlib.sha256(pdf_bytes).hexdigest()
    return out
