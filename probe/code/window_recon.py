#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Independent reconciliation: bounded-interval NOD queries vs full traversal.

Fetches directivos-resultado?nif=&fechad=&fechah= for disjoint yearly windows
covering the whole post-2018 NOD range, saves raw under evidence/windowed/,
and compares the union of registration numbers with the traversal set in
probe.sqlite. Windows are disjoint -> the union must equal the full set;
the mechanism is insertion-safe because windows are content-addressed by
registration number, not page offset.
"""
import http.cookiejar
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe as P

OUT = os.path.join(P.PROBE_ROOT, "evidence", "windowed")
os.makedirs(OUT, exist_ok=True)

def fetch(op, url, tag):
    body = op.open(url, timeout=120).read()
    fn = os.path.join(OUT, tag + ".html")
    open(fn, "wb").write(body)
    meta = {"requested_url": url, "final_url": op.open if False else None,
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "raw_sha256": P.sha256b(body), "raw_file": f"evidence/windowed/{tag}.html"}
    open(fn + ".meta.json", "w").write(json.dumps(meta, indent=1))
    time.sleep(P.DELAY_S)
    return body.decode("utf-8", "replace")

def window_regs(op, nif, d, h, issuer, tag):
    regs = set()
    page, total = 0, None
    while True:
        url = (f"{P.BASE}/portal/consultas/directivos-resultado?nif={nif}"
               f"&fechad={d}&fechah={h}" + (f"&page={page}" if page else ""))
        t = fetch(op, url, f"{issuer}_{d.replace('/','')}_{h.replace('/','')}_p{page}")
        if total is None:
            m = re.search(r"Página \d+ de (\d+)", t)
            total = int(m.group(1)) if m else 1
        for b in re.findall(r'repListaPrincipal_ctl\d+_elementoPrimerNivel.*?</li>\s*</ul>',
                            t, re.S):
            m = re.search(r'registro:\s*(\d+)', b)
            if m:
                regs.add(m.group(1))
        page += 1
        if page >= total:
            break
    return regs

def main():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", P.UA)]
    cx = P.db()
    # disjoint windows: 2018-05-01..2020-03-01 (overlap window of interest),
    # then calendar years to today
    windows = [("01/05/2018", "01/03/2020"), ("02/03/2020", "31/12/2020"),
               ("01/01/2021", "31/12/2021"), ("01/01/2022", "31/12/2022"),
               ("01/01/2023", "31/12/2023"), ("01/01/2024", "31/12/2024"),
               ("01/01/2025", "31/12/2025"), ("01/01/2026", "14/09/2026")]
    result = {}
    for ik, issuer in P.ISSUERS.items():
        nif = issuer["nif"]
        union = set()
        per_window = {}
        for d, h in windows:
            r = window_regs(op, nif, d, h, ik, "nod")
            per_window[f"{d}-{h}"] = len(r)
            union |= r
        trav = {row[0] for row in cx.execute(
            "SELECT source_registration_number FROM notice "
            "WHERE source_family='nod' AND issuer_id=?", (ik,))}
        result[ik] = {
            "windows": per_window,
            "windowed_union": len(union),
            "traversal": len(trav),
            "only_in_windowed": sorted(union - trav),
            "only_in_traversal": sorted(trav - union),
        }
        print(ik, json.dumps(result[ik], indent=1))
    open(os.path.join(OUT, "recon_result.json"), "w").write(
        json.dumps(result, indent=1, ensure_ascii=False))

if __name__ == "__main__":
    main()
