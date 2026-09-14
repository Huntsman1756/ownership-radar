#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G0 reconciliation helpers.

A) Traversal evidence: dump per-family/page stats from probe.sqlite.
B) Independent reconciliation: bounded-interval NOD query vs full traversal;
   compare set of registration numbers.
C) Run-to-run diff between two runs.
"""
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request
import http.cookiejar

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe as P

DB = P.DB_PATH
BASE = P.BASE
UA = P.UA


def nod_window(nif, d, h, out_html_dir):
    """Bounded-interval NOD query: returns set of reg numbers."""
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", UA)]
    regs, toks, blocks_all = set(), [], []
    page = 0
    total = None
    while True:
        url = (f"{BASE}/portal/consultas/directivos-resultado?nif={nif}"
               f"&fechad={d}&fechah={h}" + (f"&page={page}" if page else ""))
        body = op.open(url, timeout=120).read()
        if out_html_dir:
            fn = os.path.join(out_html_dir,
                              f"nodwin_{nif}_{d.replace('/','')}_{h.replace('/','')}_p{page}.html")
            open(fn, "wb").write(body)
        t = body.decode("utf-8", "replace")
        if total is None:
            m = re.search(r"Página \d+ de (\d+)", t)
            total = int(m.group(1)) if m else 1
        for b in re.findall(r'repListaPrincipal_ctl\d+_elementoPrimerNivel.*?</li>\s*</ul>',
                            t, re.S):
            m = re.search(r'Número de registro:\s*(\d+)', b)
            if m:
                regs.add(m.group(1))
        page += 1
        if page >= total:
            break
        time.sleep(P.DELAY_S)
    return regs


def run_diff(cx, ra, rb):
    qa = {r[0] for r in cx.execute("SELECT notice_key FROM run_seen WHERE run_id=?", (ra,))}
    qb = {r[0] for r in cx.execute("SELECT notice_key FROM run_seen WHERE run_id=?", (rb,))}
    return {"only_in_a": sorted(qa - qb), "only_in_b": sorted(qb - qa),
            "common": len(qa & qb), "count_a": len(qa), "count_b": len(qb)}


def traversal_stats(cx, run_id):
    out = {}
    for fam in ("nod", "nod_legacy", "ps", "ac"):
        rows = cx.execute(
            "SELECT issuer_id, COUNT(*), MIN(filing_date), MAX(filing_date) "
            "FROM notice WHERE source_family=? AND first_seen_run=? "
            "GROUP BY issuer_id", (fam, run_id)).fetchall()
        out[fam] = [{"issuer": r[0], "count": r[1],
                     "min_filing": r[2], "max_filing": r[3]} for r in rows]
    rels = cx.execute("SELECT relation_type, COUNT(*) FROM notice_relation "
                      "WHERE observed_run_id=? GROUP BY relation_type",
                      (run_id,)).fetchall()
    out["relations"] = dict(rels)
    return out


if __name__ == "__main__":
    cx = P.db()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "stats":
        run = sys.argv[2]
        print(json.dumps(traversal_stats(cx, run), indent=1, ensure_ascii=False))
    elif cmd == "diff":
        print(json.dumps(run_diff(cx, sys.argv[2], sys.argv[3]), indent=1))
    elif cmd == "window":
        nif, d, h = sys.argv[2], sys.argv[3], sys.argv[4]
        outdir = sys.argv[5] if len(sys.argv) > 5 else None
        regs = nod_window(nif, d, h, outdir)
        print(json.dumps(sorted(regs), indent=1))
