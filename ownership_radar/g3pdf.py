"""G3 shared PDF grid extraction + template fingerprinting.

Shared by pspdf (G3-A significant holdings) and acpdf (G3-B treasury
stock). Position-aware variant of the G2 extractor: cells keep their
x coordinates so direct/indirect columns can be identified from the
header band they fall under (empty columns emit no cell — cell ORDER
alone is not a reliable column indicator).

Pages -> lines -> cells: cell = {"x0": float, "x1": float, "t": str}.
"""
import unicodedata
from decimal import Decimal
import io
import re

X_GAP = 3.0
Y_TOL = 1.0

PARSED = "PARSED"
PARSED_UNMAPPED = "PARSED_WITH_UNMAPPED_VALUES"
UNSUPPORTED_TEMPLATE = "UNSUPPORTED_TEMPLATE"
UNSUPPORTED_LEGACY = "UNSUPPORTED_LEGACY_TEMPLATE"
UNSUPPORTED_NO_TEXT = "UNSUPPORTED_NO_TEXT_LAYER"
MALFORMED = "MALFORMED_SOURCE"
EXTRACTION_ERROR = "EXTRACTION_ERROR"

T_MODEL_1_C8 = "CIRC_8_2015_MODEL_1"
T_MODEL_1_C2 = "CIRC_2_2022_MODEL_1"
T_MODEL_2_DIR = "CIRC_8_2015_MODEL_2_DIRECTOR"
T_MODEL_4 = "CIRC_8_2015_MODEL_4"
T_MODEL_2_AC = "CIRC_2_2022_MODEL_2"

_DATE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_INT = re.compile(r"^\d{1,3}(?:\.\d{3})+$|^\d+$")
_PCT = re.compile(r"^\d+,\d+$")


def _n(t):
    return unicodedata.normalize("NFKC", t or "").replace("\xa0", " ")


def dec(s):
    """CNMV decimal literal -> exact Decimal (None if unparseable)."""
    if s is None:
        return None
    t = s.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return Decimal(t)
    except Exception:
        return None


def dec_int(s):
    """CNMV thousands-separated integer -> int (None if unparseable)."""
    if s is None:
        return None
    t = s.replace(" ", "").replace(".", "")
    return int(t) if t.isdigit() else None


def norm_date(s):
    m = _DATE.match(s or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def extract_cells(pdf_bytes):
    """PDF bytes -> list[page] of list[line] of positioned cells."""
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
            cx0 = 0.0
            for c in cs:
                if px is not None and c.x0 - px > X_GAP:
                    cells.append({"x0": cx0, "x1": px, "t": cur})
                    cur = ""
                if not cur:
                    cx0 = c.x0
                cur += c.get_text()
                px = c.x1
            cells.append({"x0": cx0, "x1": px, "t": cur})
            lines.append([c for c in cells if c["t"].strip()])
        pages.append(lines)
    return pages


def flat_text(pages):
    return " ".join(_n(c["t"]) for p in pages for l in p for c in l)


def fingerprint(pages):
    """Content-anchor template identification (contract:
    docs/gates/G3-SIGNIFICANT-HOLDINGS-TREASURY.md)."""
    flat = [c["t"].strip() for p in pages for l in p for c in l
            if c["t"].strip()]
    if not flat:
        return UNSUPPORTED_NO_TEXT
    j = " ".join(_n(t) for t in flat).upper()
    bil = "STANDARD FORM" in j
    ps = "PARTICIPACIONES" in j and "SIGNIFICATIVAS" in j and bil
    if ps:
        return T_MODEL_1_C2 if ("LEALTAD" in j or "LOYALTY" in j) \
            else T_MODEL_1_C8
    if "CONSEJEROS" in j and "MODELO" in j:
        return T_MODEL_2_DIR if bil else UNSUPPORTED_LEGACY
    if "ACCIONES PROPIAS" in j or "OWN SHARES" in j:
        if not bil:
            return UNSUPPORTED_LEGACY
        if "MODELO 4" in j or "FORM #4" in j:
            return T_MODEL_4
        if "MODELO 2" in j or "FORM #2" in j:
            return T_MODEL_2_AC
        return UNSUPPORTED_TEMPLATE
    if not bil and "MODELO" in j:
        return UNSUPPORTED_LEGACY
    return UNSUPPORTED_TEMPLATE


# ---------------------------------------------------------------- helpers

def find_line(lines, *needles, start=0):
    """First line index whose joined NFKC-folded text contains a
    needle (needles matched on UPPERCASE-folded text)."""
    for i in range(start, len(lines)):
        t = _n(" ".join(c["t"] for c in lines[i])).upper()
        if any(n in t for n in needles):
            return i
    return -1


def all_lines(pages):
    return [l for p in pages for l in p]


def cells_after(lines, i, stop_needles=(), max_lines=40):
    """Non-label value lines following anchor i, up to a stop needle."""
    out = []
    for j in range(i + 1, min(len(lines), i + max_lines)):
        t = _n(" ".join(c["t"] for c in lines[j])).upper()
        if any(n in t for n in stop_needles):
            break
        out.append((j, lines[j]))
    return out


def checkbox(line_text):
    """'[ √ ]'/'[x]' -> True; '[ ]' -> False; absent -> None."""
    t = _n(line_text)
    m = re.search(r"\[\s*([^\]]*?)\s*\]", t)
    if not m:
        return None
    return bool(m.group(1).strip())


def column_bands(header_cells, labels):
    """Return [(label, x_start, x_end)] bands from header x positions.

    labels: ordered list of substrings identifying each column header
    cell. Band i covers [x_i, x_{i+1}); last band extends to +inf.
    """
    ups = [_n(c["t"]).upper() for c in header_cells]
    xs = []
    for lab in labels:
        hit = [c["x0"] for c, u in zip(header_cells, ups) if lab in u]
        if not hit:
            return None
        xs.append(min(hit))
    if xs != sorted(xs):
        return None
    bands = [(labels[i], xs[i],
              xs[i + 1] if i + 1 < len(xs) else float("inf"))
             for i in range(len(xs))]
    return bands


def assign_column(x0, bands):
    for lab, a, b in bands:
        if a <= x0 < b:
            return lab
    return None
