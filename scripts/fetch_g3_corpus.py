"""Fetch the frozen G3 corpus per docs/gates/G3-SIGNIFICANT-HOLDINGS-TREASURY.md.

DEV:     SAN/BBVA ps+ac notices from data/radar.sqlite under the frozen
         bucket/index rules (LEGACY/C8/C2) + notice_relation members +
         the six probe/evidence/templates samples.
HOLDOUT: first 2 issuers of the fixed candidate list meeting the
         per-family bucket minimums; indices {0, n/2, n-1} per bucket +
         up to 2 recent relation members + LEGACY index 0.

Output: corpus/g3/{ps,ac}_{dev,holdout}/ PDFs +
        corpus/manifests/g3_manifest.json.
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
OUT = os.path.join(ROOT, "corpus", "g3")
TEMPLATES = os.path.join(ROOT, "probe", "evidence", "templates")
MANIFEST = os.path.join(ROOT, "corpus", "manifests", "g3_manifest.json")

HOLDOUT_CANDIDATES = [
    ("CABK", "A08663619", "CAIXABANK, S.A."),
    ("TEF", "A28015865", "TELEFONICA, S.A."),
    ("ITX", "A15022502", "INDUSTRIA DE DISENO TEXTIL, S.A."),
    ("IBE", "A95758389", "IBERDROLA, S.A."),
    ("REP", "A78374725", "REPSOL, S.A."),
]
MIN_PER_BUCKET = 4
B_C8 = ("2015-12-28", "2022-08-06")
B_C2 = ("2022-08-07", "9999-12-31")
B_LEGACY = ("0000-01-01", "2015-12-27")
DEV_MOD = {"ps": {"C8": 20, "C2": 5}, "ac": {"C8": 8, "C2": 6}}


def bucket(fd):
    if fd is None or fd < B_C8[0]:
        return "LEGACY"
    return "C2" if fd >= B_C2[0] else "C8"


def fetch_pdf(fx, token, dest):
    if not token:
        return {"error": "NO_DOC_TOKEN"}
    url = f"{cnmv.BASE}/webservices/verdocumento/ver?e={token}"
    meta, body = fx.get(url, note=f"pdf {os.path.basename(dest)}")
    if body[:4] == b"%PDF":
        with open(dest, "wb") as f:
            f.write(body)
        return meta
    return {**meta, "error": "NOT_PDF"}


def rows_for(cx, ik, surf):
    return cx.execute(
        """SELECT source_registration_number, filing_date, doc_token,
                  notice_key FROM notice
           WHERE issuer_id=? AND source_surface=?
           ORDER BY filing_date, source_registration_number""",
        (ik, surf)).fetchall()


def relation_members(cx, surf, issuer_ids):
    keys = set()
    for r in cx.execute(
            "SELECT annulling_key, annulled_key FROM notice_relation"):
        for k in r:
            if k.startswith(surf + ":"):
                keys.add(k)
    out = []
    for k in sorted(keys):
        row = cx.execute(
            """SELECT source_registration_number, filing_date, doc_token,
                      issuer_id FROM notice WHERE notice_key=?""",
            (k,)).fetchone()
        if row and row[3] in issuer_ids:
            out.append({"issuer": row[3], "reg": row[0], "filing_date": row[1],
                        "token": row[2], "notice_key": k, "why": "relation"})
        elif not row:
            out.append({"issuer": None, "reg": k.split(":", 1)[1],
                        "filing_date": None, "token": None,
                        "notice_key": k, "why": "relation_unlisted"})
    return out


def list_origin(cx, notice_key):
    r = cx.execute("SELECT extra_json FROM notice WHERE notice_key=?",
                   (notice_key,)).fetchone()
    if not r or not r[0]:
        return None
    return json.loads(r[0]).get("list_origin")


def no_comma(cx, notice_key):
    r = cx.execute("SELECT declarant_name_raw FROM notice "
                   "WHERE notice_key=?", (notice_key,)).fetchone()
    return r and r[0] and "," not in r[0]


def dev_selection(cx, surf):
    out = []
    for ik in ("SAN", "BBVA"):
        rows = rows_for(cx, ik, surf)
        by_bucket = {"LEGACY": [], "C8": [], "C2": []}
        for r in rows:
            by_bucket[bucket(r[1])].append(r)
        if surf == "ps":
            comma_otras = []
            for r in by_bucket["C8"]:
                org = list_origin(cx, r[3])
                if org == "CURRENT_HOLDER" or \
                        (org == "OTRAS_NOTIFICACIONES" and
                         no_comma(cx, r[3])):
                    out.append({"issuer": ik, "reg": r[0],
                                "filing_date": r[1], "token": r[2],
                                "notice_key": r[3],
                                "why": f"C8:{org or 'nocomma'}"})
                elif org == "OTRAS_NOTIFICACIONES":
                    comma_otras.append(r)
                else:
                    comma_otras.append(r)
            for i, r in enumerate(comma_otras):
                if i % 40 == 0:
                    out.append({"issuer": ik, "reg": r[0],
                                "filing_date": r[1], "token": r[2],
                                "notice_key": r[3], "why": "C8:otras%40"})
        else:
            for i, r in enumerate(by_bucket["C8"]):
                if i % DEV_MOD[surf]["C8"] == 0:
                    out.append({"issuer": ik, "reg": r[0],
                                "filing_date": r[1], "token": r[2],
                                "notice_key": r[3], "why": "C8:index%8"})
        for i, r in enumerate(by_bucket["C2"]):
            if i % DEV_MOD[surf]["C2"] == 0:
                out.append({"issuer": ik, "reg": r[0], "filing_date": r[1],
                            "token": r[2], "notice_key": r[3],
                            "why": "C2:index"})
        for i in sorted({0, len(by_bucket["LEGACY"]) - 1}):
            r = by_bucket["LEGACY"][i]
            out.append({"issuer": ik, "reg": r[0], "filing_date": r[1],
                        "token": r[2], "notice_key": r[3],
                        "why": "LEGACY:index"})
    out += relation_members(cx, surf, {"SAN", "BBVA"})
    seen, dedup = set(), []
    for e in out:
        if e["notice_key"] not in seen:
            seen.add(e["notice_key"])
            dedup.append(e)
    return dedup


def holdout_selection(fx, cx, surf):
    """First 2 candidates meeting >=MIN_PER_BUCKET in both in-scope
    buckets; else first 2 by total in-scope count."""
    eligible, fallback = [], []
    for ik, nif, name in HOLDOUT_CANDIDATES:
        existing = rows_for(cx, ik, surf)
        if not existing:
            cnmv.collect_ps_ac(fx, cx, ik, {"nif": nif, "name": name},
                               "corpus-" + ik, store)
            cx.commit()
            existing = rows_for(cx, ik, surf)
        by_bucket = {"LEGACY": [], "C8": [], "C2": []}
        for r in existing:
            by_bucket[bucket(r[1])].append(r)
        ok = (len(by_bucket["C8"]) >= MIN_PER_BUCKET and
              len(by_bucket["C2"]) >= MIN_PER_BUCKET)
        entry = (ik, by_bucket)
        (eligible if ok else fallback).append(entry)
    chosen = eligible[:2] if len(eligible) >= 2 else \
        (eligible + sorted(fallback,
                           key=lambda e: -(len(e[1]["C8"]) +
                                          len(e[1]["C2"]))))[:2]
    out = []
    for ik, by_bucket in chosen:
        for b in ("C8", "C2"):
            s1 = [r for r in by_bucket[b]
                  if list_origin(cx, r[3]) == "CURRENT_HOLDER"]
            s2 = [r for r in by_bucket[b]
                  if list_origin(cx, r[3]) == "OTRAS_NOTIFICACIONES"
                  and no_comma(cx, r[3])]
            s3 = [r for r in by_bucket[b] if r not in s1 and r not in s2]
            for tag, pop in (("S1", s1), ("S2", s2), ("S3", s3)):
                n = len(pop)
                for i in sorted({0, n - 1} if n else set()):
                    r = pop[i]
                    out.append({"issuer": ik, "reg": r[0],
                                "filing_date": r[1], "token": r[2],
                                "notice_key": r[3], "why": f"{b}:{tag}"})
        if by_bucket["LEGACY"]:
            r = by_bucket["LEGACY"][0]
            out.append({"issuer": ik, "reg": r[0], "filing_date": r[1],
                        "token": r[2], "notice_key": r[3],
                        "why": "LEGACY:index0"})
        rel = [e for e in relation_members(cx, surf, {ik})
               if e["issuer"] == ik]
        out += rel[-2:]
    seen, dedup = set(), []
    for e in out:
        if e["notice_key"] not in seen:
            seen.add(e["notice_key"])
            dedup.append(e)
    return dedup, [ik for ik, _ in chosen]


def main():
    run_id = "g3corpus-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fx = Fetcher(run_id, os.path.join(OUT, "raw"))
    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    manifest = {"run_id": run_id,
                "generated_at": datetime.now(timezone.utc)
                .isoformat(timespec="seconds"),
                "contract": "docs/gates/G3-SIGNIFICANT-HOLDINGS-TREASURY.md",
                "ps_dev": [], "ps_holdout": [],
                "ac_dev": [], "ac_holdout": [],
                "holdout_issuers": {}}

    cx = sqlite3.connect(DB)
    cxc = store.init_db(CORPUS_DB)

    for surf, split, entries in (("ps", "dev", dev_selection(cx, "ps")),
                                 ("ac", "dev", dev_selection(cx, "ac"))):
        dest_dir = os.path.join(OUT, f"{surf}_{split}")
        os.makedirs(dest_dir, exist_ok=True)
        for e in entries:
            dest = os.path.join(dest_dir, f"{e['issuer']}_{e['reg']}.pdf")
            meta = fetch_pdf(fx, e["token"], dest)
            manifest[f"{surf}_{split}"].append(
                {**e, "file": os.path.relpath(dest, ROOT),
                 "raw_sha256": meta.get("raw_sha256"),
                 "fetched": meta.get("retrieved_at"),
                 "error": meta.get("error")})

    for surf in ("ps", "ac"):
        entries, issuers = holdout_selection(fx, cxc, surf)
        manifest["holdout_issuers"][surf] = issuers
        dest_dir = os.path.join(OUT, f"{surf}_holdout")
        os.makedirs(dest_dir, exist_ok=True)
        for e in entries:
            dest = os.path.join(dest_dir, f"{e['issuer']}_{e['reg']}.pdf")
            meta = fetch_pdf(fx, e["token"], dest)
            manifest[f"{surf}_holdout"].append(
                {**e, "file": os.path.relpath(dest, ROOT),
                 "raw_sha256": meta.get("raw_sha256"),
                 "fetched": meta.get("retrieved_at"),
                 "error": meta.get("error")})

    for f in sorted(os.listdir(TEMPLATES)):
        if (f.startswith("ps_") or f.startswith("ac_")) and \
                f.endswith(".pdf"):
            surf = f.split("_")[0]
            parts = f[:-4].split("_")
            manifest[f"{surf}_dev"].append({
                "issuer": parts[1], "reg": parts[2],
                "filing_date": parts[3], "token": None,
                "notice_key": f"{surf}:{parts[2]}",
                "why": "template_sample",
                "file": os.path.relpath(os.path.join(TEMPLATES, f), ROOT)})

    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    for k in ("ps_dev", "ps_holdout", "ac_dev", "ac_holdout"):
        errs = [e for e in manifest[k] if e.get("error")]
        print(k, len(manifest[k]), "errors:", len(errs))
        for e in errs:
            print("  ", e["reg"], e["error"])


if __name__ == "__main__":
    main()
