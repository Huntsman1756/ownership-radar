"""Build universe seed from the AEAT ITF issuer list PDF.

Deterministic: same input PDF -> same entries -> same content_sha256.
Writes ownership_radar/seeds/itf2026-v1.json. The PDF itself is NOT
committed (redistribution unknown); its sha256 + URL are recorded in
the seed.

Usage: python scripts/build_universe.py <aeat.pdf>
"""
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SOURCE_URL = ("https://www3.agenciatributaria.gob.es/static_files/Sede/Tema/"
              "Declaraciones_informativas/I_Transacciones_Financieras/"
              "RELACION_SOCIEDADES_EJERCICIO_2026.pdf")
OUT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "ownership_radar", "seeds",
    "itf2026-v1.json")

ROW_RE = re.compile(r"^(\d{4})\s+([A-Z]\d{8})\s*(.*?)\s*$")
ISIN_RE = re.compile(r"^ES[0-9A-Z]{10}$")


def extract_rows(pdf_path):
    """Positioned extraction: each visual row = EJERCICIO | NIF+NAME |
    ISIN | cap | admon. Names may be absent (continuation/dup NIF)."""
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextContainer, LTTextLine
    rows = []
    for page in extract_pages(pdf_path):
        lines = {}
        for el in page:
            if not isinstance(el, LTTextContainer):
                continue
            for ln in el:
                if not isinstance(ln, LTTextLine):
                    continue
                t = ln.get_text().strip()
                if t:
                    lines.setdefault(round(ln.y0, 1), []).append(
                        (round(ln.x0), t))
        pending = []  # name-column fragments on non-row lines belong
        # to the next NIF row below them (wrapped names render above
        # their row in this PDF)
        for y in sorted(lines, reverse=True):
            cells = sorted(lines[y])
            rowtxt = " ".join(c[1] for c in cells)
            m = ROW_RE.match(rowtxt)
            isin = next((c[1] for c in cells if ISIN_RE.match(c[1])),
                        None)
            if m and m.group(1) == "2026" and re.search(
                    r"[A-Z]\d{8}", rowtxt):
                mm = re.search(r"([A-Z]\d{8})\s*(.*)", rowtxt)
                name = mm.group(2)
                if isin:
                    name = name.replace(isin, "")
                name = re.sub(r"\d{1,3}(?:\.\d{3})*,\d{2}", "", name)
                name = re.sub(r"/?\b(AEAT|BIZKAIA|GIPUZKOA|GUIPUZKOA|"
                              r"ARABA|ÁLAVA|ALAVA|NAVARRA|DONOSTIA)\b",
                              "", name)
                name = re.sub(r"\s{2,}", " ",
                              " ".join(pending + [name])).strip() or None
                rows.append({"nif": mm.group(1), "name": name,
                             "isin": isin})
                pending = []
            else:
                # wrapped name fragments are ALL-CAPS company text;
                # page headers/boilerplate excluded
                frag = [t for x, t in cells
                        if 70 <= x < 300 and not ISIN_RE.match(t)
                        and not re.match(r"^\d{4}$", t)
                        and re.search(r"[A-ZÁÉÍÓÚÑ]", t)
                        and t.upper() == t
                        and not re.search(
                            r"IMPUESTO|RELACIÓN DE SOCIEDADES|"
                            r"DENOMINACIÓN|BURSATIL|COMPETENTE|"
                            r"ADMON\.|EJERCICIO|^NIF$", t)]
                pending += frag
    return rows


def main():
    pdf = sys.argv[1]
    pdf_sha = hashlib.sha256(open(pdf, "rb").read()).hexdigest()
    rows = extract_rows(pdf)
    # collapse to one entry per NIF: prefer row carrying a name; keep
    # all ISINs (dual-class issuers list >1)
    by_nif = {}
    for r in rows:
        e = by_nif.setdefault(r["nif"], {"nif": r["nif"], "name": None,
                                         "isins": []})
        if r["name"]:
            e["name"] = r["name"]
        if r["isin"] and r["isin"] not in e["isins"]:
            e["isins"].append(r["isin"])
    entries = [by_nif[k] for k in sorted(by_nif)]
    canon = json.dumps(entries, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"))
    seed = {
        "universe_version": "itf2026-v1",
        "source": {"name": "AEAT ITF RELACION_SOCIEDADES_EJERCICIO_2026",
                   "url": SOURCE_URL, "pdf_sha256": pdf_sha},
        "generated_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds"),
        "content_sha256": hashlib.sha256(canon.encode()).hexdigest(),
        "scope_note": "Spanish listed companies with market cap > 1bn "
                      "EUR on 1/12/2025 (ITF scope). See "
                      "docs/gates/G5-UNIVERSE.md.",
        "issuers": [
            {"issuer_id": e["nif"], "nif": e["nif"], "name": e["name"],
             "isins": e["isins"], "identifier_basis": "NIF",
             "identity_quality": "OFFICIAL_IDENTIFIER"}
            for e in entries],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(seed, f, ensure_ascii=False, indent=1)
    print(len(entries), "issuers;",
          sum(1 for e in entries if not e["name"]), "missing name;",
          seed["content_sha256"][:16])


if __name__ == "__main__":
    main()
