"""Fetch the frozen G2 corpus (DEV + HOLDOUT) per docs/gates contract.

DEV:     SAN/BBVA nod notices from data/radar.sqlite
         (index % 12 == 0 by (filing_date, reg) + all notice_relation
         members + the 5 template samples already captured).
HOLDOUT: first 3 issuers of the fixed candidate list whose NOD listing
         yields >= 15 notices; indices {0, n/4, n/2, 3n/4, n-1} plus up
         to 2 most recent RECTIFIES notices.

Output: corpus/dev/, corpus/holdout/ PDFs + corpus/manifest.json.
Holdout issuer listings are stored in corpus/corpus.sqlite.
"""
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ownership_radar import cnmv, store
from ownership_radar.crawler import Fetcher

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "radar.sqlite")
CORPUS_DB = os.path.join(ROOT, "corpus", "corpus.sqlite")
OUT = os.path.join(ROOT, "corpus")
TEMPLATES = os.path.join(ROOT, "probe", "evidence", "templates")

HOLDOUT_CANDIDATES = [
    ("CABK", "A08663619", "CAIXABANK, S.A."),
    ("TEF", "A28015865", "TELEFONICA, S.A."),
    ("ITX", "A15022502", "INDUSTRIA DE DISENO TEXTIL, S.A."),
    ("IBE", "A95758389", "IBERDROLA, S.A."),
    ("REP", "A78374725", "REPSOL, S.A."),
]
MIN_HOLDOUT_NOTICES = 15


def fetch_pdf(fx, token, dest):
    url = f"{cnmv.BASE}/webservices/verdocumento/ver?e={token}"
    meta, body = fx.get(url, note=f"pdf {os.path.basename(dest)}")
    if body[:4] == b"%PDF":
        with open(dest, "wb") as f:
            f.write(body)
        return meta
    return {**meta, "error": "NOT_PDF"}


def dev_selection(cx):
    out = []
    for ik in ("SAN", "BBVA"):
        rows = cx.execute(
            """SELECT source_registration_number, filing_date, doc_token,
                      notice_key FROM notice
               WHERE issuer_id=? AND source_surface='nod'
               ORDER BY filing_date, source_registration_number""",
            (ik,)).fetchall()
        rel = {r[0] for r in cx.execute(
            "SELECT annulling_key FROM notice_relation "
            "UNION SELECT annulled_key FROM notice_relation")}
        for i, (reg, fd, tok, key) in enumerate(rows):
            if i % 12 == 0 or key in rel:
                out.append({"issuer": ik, "reg": reg, "filing_date": fd,
                            "token": tok, "notice_key": key,
                            "why": "relation" if key in rel else "index%12"})
    return out


def holdout_selection(fx, cx):
    chosen = []
    for ik, nif, name in HOLDOUT_CANDIDATES:
        if len(chosen) >= 3:
            break
        n = cnmv.collect_nod(fx, cx, ik, {"nif": nif, "name": name},
                             "corpus-" + ik, store)
        cx.commit()
        if n < MIN_HOLDOUT_NOTICES:
            continue
        rows = cx.execute(
            """SELECT source_registration_number, filing_date, doc_token,
                      notice_key, notice_status FROM notice
               WHERE issuer_id=? AND source_surface='nod'
               ORDER BY filing_date, source_registration_number""",
            (ik,)).fetchall()
        n_rows = len(rows)
        idx = sorted({0, n_rows // 4, n_rows // 2, 3 * n_rows // 4,
                      n_rows - 1})
        sel = [rows[i] for i in idx]
        rect = [r for r in rows if r[4] == "RECTIFIES"][-2:]
        sel += [r for r in rect if r not in sel]
        chosen.append((ik, sel))
    return chosen


def main():
    run_id = "corpus-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fx = Fetcher(run_id, os.path.join(OUT, "raw"))
    manifest = {"run_id": run_id, "generated_at":
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "dev": [], "holdout": []}

    cx = sqlite3.connect(DB)
    os.makedirs(os.path.join(OUT, "dev"), exist_ok=True)
    for e in dev_selection(cx):
        dest = os.path.join(OUT, "dev", f"{e['issuer']}_{e['reg']}.pdf")
        meta = fetch_pdf(fx, e["token"], dest)
        manifest["dev"].append({**e, "file": os.path.relpath(dest, ROOT),
                                "raw_sha256": meta.get("raw_sha256"),
                                "fetched": meta.get("retrieved_at"),
                                "error": meta.get("error")})

    for f in sorted(os.listdir(TEMPLATES)):
        if f.startswith("nod_") and f.endswith(".pdf"):
            legacy = f.startswith("nod_legacy_")
            parts = (f[len("nod_legacy_"):] if legacy else
                     f[len("nod_"):])[:-4].split("_")
            manifest["dev"].append({
                "issuer": parts[0], "reg": parts[1],
                "filing_date": parts[2], "token": None,
                "notice_key": ("nod_legacy:" if legacy else "nod:") + parts[1],
                "why": "template_sample_negative" if legacy
                else "template_sample",
                "file": os.path.relpath(os.path.join(TEMPLATES, f), ROOT)})

    cxc = store.init_db(CORPUS_DB)
    os.makedirs(os.path.join(OUT, "holdout"), exist_ok=True)
    for ik, sel in holdout_selection(fx, cxc):
        for reg, fd, tok, key, st in sel:
            dest = os.path.join(OUT, "holdout", f"{ik}_{reg}.pdf")
            meta = fetch_pdf(fx, tok, dest)
            manifest["holdout"].append({
                "issuer": ik, "reg": reg, "filing_date": fd,
                "notice_key": key, "notice_status": st,
                "why": "rectifies" if st == "RECTIFIES" else "index",
                "file": os.path.relpath(dest, ROOT),
                "raw_sha256": meta.get("raw_sha256"),
                "fetched": meta.get("retrieved_at"),
                "error": meta.get("error")})

    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(json.dumps({"dev": len(manifest["dev"]),
                      "holdout": len(manifest["holdout"]),
                      "errors": sum(1 for e in manifest["dev"] +
                                    manifest["holdout"] if e.get("error"))},
                     indent=1))


if __name__ == "__main__":
    main()
