#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ownership Radar ES - G0 Acquisition Probe (disposable).

Purpose: verify whether CNMV public sources support a bitemporal,
reproducible ownership ledger. Captures raw evidence first, normalizes
second. No fuzzy matching, no inference of identity beyond what the
source states explicitly.

Python 3.11+, stdlib only.
"""
import hashlib
import html as htmlmod
import http.cookiejar
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

PARSER_VERSION = "0.1.1-g0"
BASE = "https://www.cnmv.es"
UA = "OwnershipRadarES-G0-Probe/0.1 (technical viability probe; low frequency; caching enabled)"
DELAY_S = 0.9
MAX_RETRIES = 3
BACKOFF_S = 5.0

PROBE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(PROBE_ROOT, "raw")
RUNS_DIR = os.path.join(PROBE_ROOT, "runs")
NORM_DIR = os.path.join(PROBE_ROOT, "normalized")
DB_PATH = os.path.join(PROBE_ROOT, "probe.sqlite")

ISSUERS = {
    "SAN": {"nif": "A39000013", "name": "BANCO SANTANDER, S.A."},
    "BBVA": {"nif": "A48265169", "name": "BANCO BILBAO VIZCAYA ARGENTARIA, S.A."},
}

# ---------------------------------------------------------------- raw capture

_seq = 0

def sha256b(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

class Fetcher:
    def __init__(self, run_id):
        self.run_id = run_id
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self.op.addheaders = [("User-Agent", UA)]
        self.outdir = os.path.join(RAW_DIR, run_id)
        os.makedirs(self.outdir, exist_ok=True)
        self.n = 0
        self.log = []

    def get(self, url, binary=False, note=""):
        """GET with raw capture. Returns dict meta+body."""
        global _seq
        self.n += 1
        _seq += 1
        seq = _seq
        last_err = None
        for attempt in range(MAX_RETRIES):
            try:
                req = urllib.request.Request(url)
                t0 = datetime.now(timezone.utc)
                resp = self.op.open(req, timeout=120)
                body = resp.read()
                meta = {
                    "seq": seq,
                    "run_id": self.run_id,
                    "requested_url": url,
                    "final_url": resp.geturl(),
                    "status": resp.status,
                    "retrieved_at": t0.isoformat(timespec="milliseconds"),
                    "content_type": resp.headers.get("Content-Type"),
                    "headers": {k: v for k, v in resp.headers.items()},
                    "raw_sha256": sha256b(body),
                    "raw_bytes": len(body),
                    "note": note,
                    "attempt": attempt + 1,
                }
                ext = ".pdf" if "pdf" in (meta["content_type"] or "") else ".html"
                fn = f"{seq:05d}{ext}"
                with open(os.path.join(self.outdir, fn), "wb") as f:
                    f.write(body)
                meta["raw_file"] = f"raw/{self.run_id}/{fn}"
                with open(os.path.join(self.outdir, fn + ".meta.json"), "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=1)
                self.log.append(meta)
                time.sleep(DELAY_S)
                return meta, body
            except Exception as e:  # noqa
                last_err = repr(e)
                time.sleep(BACKOFF_S * (attempt + 1))
        meta = {"seq": seq, "run_id": self.run_id, "requested_url": url,
                "status": "ERROR", "error": last_err,
                "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "note": note}
        self.log.append(meta)
        return meta, b""

# ---------------------------------------------------------------- db

SCHEMA = """
CREATE TABLE IF NOT EXISTS crawl_run(
 run_id TEXT PRIMARY KEY, started_at TEXT, completed_at TEXT,
 source TEXT, parser_version TEXT, status TEXT, stats_json TEXT);
CREATE TABLE IF NOT EXISTS issuer(
 issuer_id TEXT PRIMARY KEY, nif TEXT, lei TEXT, name_raw TEXT,
 capital_raw TEXT, observed_run_id TEXT);
CREATE TABLE IF NOT EXISTS notice(
 notice_key TEXT PRIMARY KEY, source_family TEXT,
 source_registration_number TEXT, issuer_id TEXT, regime TEXT,
 filing_date TEXT, notice_status TEXT, identity_status TEXT,
 doc_token TEXT, declarant_name_raw TEXT, declarant_role TEXT,
 pct_a TEXT, pct_b TEXT, pct_total TEXT, extra_json TEXT,
 first_seen_run TEXT, last_seen_run TEXT);
CREATE TABLE IF NOT EXISTS notice_observation(
 obs_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, notice_key TEXT,
 observed_at TEXT, raw_sha256 TEXT, normalized_sha256 TEXT,
 source_url_observed TEXT, source_url_canonical TEXT,
 status_observed TEXT, present_in_source INTEGER);
CREATE TABLE IF NOT EXISTS event(
 notice_key TEXT, event_index INTEGER, event_date TEXT,
 declarant_name_raw TEXT, declarant_role TEXT, declarant_scope_issuer_id TEXT,
 shares TEXT, percentage_before TEXT, percentage_after TEXT, price TEXT,
 instrument TEXT, evidence TEXT,
 PRIMARY KEY(notice_key, event_index));
CREATE TABLE IF NOT EXISTS notice_relation(
 annulling_key TEXT, annulled_key TEXT, relation_type TEXT,
 evidence_url TEXT, observed_run_id TEXT, evidence_sha256 TEXT,
 PRIMARY KEY(annulling_key, annulled_key, relation_type));
CREATE TABLE IF NOT EXISTS run_seen(
 run_id TEXT, notice_key TEXT, PRIMARY KEY(run_id, notice_key));
"""

def db():
    cx = sqlite3.connect(DB_PATH)
    cx.execute("PRAGMA journal_mode=WAL")
    return cx

def init_db():
    cx = db()
    cx.executescript(SCHEMA)
    cx.commit()
    return cx

# ---------------------------------------------------------------- helpers

def clean(s):
    return htmlmod.unescape(re.sub(r"\s+", " ", s or "")).strip()

def cell_texts(row_html):
    return [clean(re.sub(r"<[^>]+>", " ", c))
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S)]

def table_rows(html, table_id):
    i = html.find(table_id)
    if i < 0:
        return []
    tstart = html.rfind("<table", 0, i)
    depth, j = 0, tstart
    while True:
        m = re.search(r"</?table", html[j:])
        if not m:
            return []
        if html[j + m.start():j + m.start() + 2] == "</":
            depth -= 1
            if depth == 0:
                tend = j + m.end()
                break
        else:
            depth += 1
        j += m.end()
    tbl = html[tstart:tend]
    return re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.S)

def qs_links(html, page):
    return [u.replace("{", "%7B").replace("}", "%7D")
            for u in re.findall(page + r"\.aspx\?qS=\{[^}]*\}", html)]

def reg_from_row(row_html):
    m = re.search(r"registro\s*(\d{9,10})", row_html, re.I)
    if m:
        return m.group(1)
    m = re.search(r"Abrir PDF de\s*(?:[^ ]+\s)*?(\d{9,10})", row_html)
    return m.group(1) if m else None

def parse_date(s):
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None

# ---------------------------------------------------------------- collectors

def collect_nod(fx, cx, issuer_key, issuer, run_id):
    """Current NOD (post-01/05/2018): directivos-resultado?nif=...&page=N"""
    nif = issuer["nif"]
    fam = "nod"
    base_url = f"{BASE}/portal/consultas/directivos-resultado?nif={nif}"
    page = 0
    total_pages = None
    n_notices = 0
    while True:
        url = base_url + (f"&page={page}" if page else "")
        meta, body = fx.get(url, note=f"nod list {issuer_key} page={page}")
        h = body.decode("utf-8", "replace")
        if total_pages is None:
            m = re.search(r"Página \d+ de (\d+)", h)
            total_pages = int(m.group(1)) if m else 1
        # parse blocks
        blocks = re.findall(
            r'repListaPrincipal_ctl\d+_elementoPrimerNivel.*?</li>\s*</ul>', h, re.S)
        if not blocks:  # fallback: split by elemento marker
            blocks = re.split(r'elementoPrimerNivel', h)[1:]
        for b in blocks:
            fecha = re.search(r'liFechaRegistro[^>]*>\s*([0-9/]+)', b)
            emisor = re.search(r'datosentidad\.aspx\?nif=([A-Z0-9-]+)', b)
            dec = re.search(r'Declarante:\s*([^<]+)', b)
            motivo = re.search(r'Motivo de la notificaci[oó]n:\s*([^<]+)', b)
            doc = re.search(r'verdocumento/ver\?e=([^"&\']+)', b)
            reg = re.search(r'Número de registro:\s*(\d+)', b)
            rect = re.search(r'rectifica a nº de registro:\s*(\d+)', b, re.I)
            rectd = re.search(r'rectificada por nº de registro:\s*(\d+)', b, re.I)
            if not reg:
                continue
            n = {
                "source_family": fam,
                "source_registration_number": reg.group(1),
                "issuer_id": issuer_key,
                "issuer_nif_seen": emisor.group(1) if emisor else None,
                "filing_date": parse_date(fecha.group(1)) if fecha else None,
                "declarant_name_raw": clean(dec.group(1)) if dec else None,
                "declarant_role": clean(motivo.group(1)) if motivo else None,
                "doc_token": doc.group(1) if doc else None,
                "notice_status": "RECTIFIES" if rect else ("RECTIFIED" if rectd else "ACTIVE"),
                "raw_sha256": meta.get("raw_sha256"),
                "source_url_observed": meta.get("requested_url"),
                "source_url_canonical": meta.get("final_url"),
            }
            upsert_notice(cx, n, run_id)
            n_notices += 1
            if rect:
                add_relation(cx, fam + ":" + reg.group(1), fam + ":" + rect.group(1),
                             "RECTIFIES", meta.get("requested_url"), run_id,
                             meta.get("raw_sha256"))
            if rectd:
                add_relation(cx, fam + ":" + rectd.group(1), fam + ":" + reg.group(1),
                             "RECTIFIES", meta.get("requested_url"), run_id,
                             meta.get("raw_sha256"))
        page += 1
        if page >= total_pages:
            break
    return n_notices

def collect_nod_legacy(fx, cx, issuer_key, issuer, run_id):
    """Legacy NOD (pre-01/05/2018): notificacionesanterioresdirectivos?nif=
    -> per-director grid -> otrasnotificacionesdirectivos?qS= history."""
    nif = issuer["nif"]
    fam = "nod_legacy"
    url = f"{BASE}/portal/consultas/derechosvoto/notificacionesanterioresdirectivos?nif={nif}"
    meta, body = fx.get(url, note=f"nod_legacy grid {issuer_key}")
    h = body.decode("utf-8", "replace")
    n_notices = 0
    rows = table_rows(h, 'id="ctl00_ContentPrincipal_grid"')
    for r in rows:
        cells = cell_texts(r)
        hist = re.search(r"otrasnotificacionesdirectivos\.aspx\?qS=\{[^}]*\}", r)
        reg = reg_from_row(r)
        name = cells[0] if cells else None
        role = cells[1] if len(cells) > 1 else None
        if reg:
            n = {"source_family": fam, "source_registration_number": reg,
                 "issuer_id": issuer_key, "filing_date": parse_date(cells[2]) if len(cells) > 2 else None,
                 "declarant_name_raw": name, "declarant_role": role,
                 "doc_token": (re.search(r'verdocumento/ver\?e=([^"&\']+)', r) or [None, None])[1]
                 if re.search(r'verdocumento/ver\?e=', r) else None,
                 "notice_status": "ACTIVE",
                 "raw_sha256": meta.get("raw_sha256"),
                 "source_url_observed": meta.get("requested_url"),
                 "source_url_canonical": meta.get("final_url")}
            upsert_notice(cx, n, run_id)
            n_notices += 1
        if hist:
            hurl = BASE + "/portal/consultas/derechosvoto/" + hist.group(0)
            m2, b2 = fx.get(hurl, note=f"nod_legacy hist {issuer_key} {name}")
            h2 = b2.decode("utf-8", "replace")
            rows2 = table_rows(h2, "ctl00_ContentPrincipal_grid")
            if not rows2:
                rows2 = re.findall(r"<tr[^>]*>(.*?)</tr>", h2, re.S)
            for r2 in rows2:
                cells2 = cell_texts(r2)
                reg2 = reg_from_row(r2)
                if not reg2:
                    continue
                fecha2 = None
                for c in cells2:
                    d = parse_date(c)
                    if d:
                        fecha2 = d
                n = {"source_family": fam, "source_registration_number": reg2,
                     "issuer_id": issuer_key, "filing_date": fecha2,
                     "declarant_name_raw": name, "declarant_role": role,
                     "doc_token": (re.search(r'verdocumento/ver\?e=([^"&\']+)', r2).group(1)
                                   if re.search(r'verdocumento/ver\?e=', r2) else None),
                     "notice_status": "ACTIVE",
                     "raw_sha256": m2.get("raw_sha256"),
                     "source_url_observed": m2.get("requested_url"),
                     "source_url_canonical": m2.get("final_url")}
                upsert_notice(cx, n, run_id)
                n_notices += 1
    return n_notices

def collect_ps_ac(fx, cx, issuer_key, issuer, run_id):
    """PS + autocartera via ps_ac_ini hub (ephemeral qS session token)."""
    nif = issuer["nif"]
    fam = "ps"
    hub = f"{BASE}/portal/consultas/derechosvoto/ps_ac_ini.aspx?nif={nif}"
    meta, body = fx.get(hub, note=f"ps hub {issuer_key}")
    h = body.decode("utf-8", "replace")
    n_notices = 0

    np_links = qs_links(h, "Notificaciones-Participaciones")
    if not np_links:
        return 0  # "No hay datos" for issuer
    # current positions + per-holder history links
    meta_np, b_np = fx.get(BASE + "/portal/consultas/derechosvoto/" + np_links[0],
                           note=f"ps current {issuer_key}")
    hnp = b_np.decode("utf-8", "replace")

    history_links = [(l, "CURRENT_HOLDER")
                     for l in qs_links(hnp, "NotificacionesAnteriores")]
    pon_links = qs_links(hnp, "personasotrasnotificaciones")

    # ex-holders / pre-2020-03-02 consejeros
    if pon_links:
        meta_pon, b_pon = fx.get(BASE + "/portal/consultas/derechosvoto/" + pon_links[0],
                               note=f"ps otras {issuer_key}")
        hpon = b_pon.decode("utf-8", "replace")
        for r in table_rows(hpon, "gvOtrasNotificaciones"):
            for l in re.findall(r"NotificacionesAnteriores\.aspx\?qS=\{[^}]*\}", r):
                history_links.append((l, "OTRAS_NOTIFICACIONES"))

    seen_links = set()
    for hl, list_origin in history_links:
        if hl in seen_links:
            continue
        seen_links.add(hl)
        meta_h, b_h = fx.get(BASE + "/portal/consultas/derechosvoto/" + hl,
                             note=f"ps hist {issuer_key} {list_origin}")
        hh = b_h.decode("utf-8", "replace")
        # declarant name lives in the history grid <caption>
        dm = re.search(r'gridNotifAnt"[^>]*>\s*<caption>\s*([^<]+)', hh)
        decl = clean(dm.group(1)) if dm else None
        for r in table_rows(hh, "gridNotifAnt"):
            cells = cell_texts(r)
            reg = reg_from_row(r)
            if not reg:
                continue
            doc = re.search(r'verdocumento/ver\?e=([^"&\']+)', r)
            fecha = None
            for c in reversed(cells):
                d = parse_date(c)
                if d:
                    fecha = d
                    break
            anulada = "anulad" in r.lower() or "NotificacionesAnuladas" in r
            n = {"source_family": fam, "source_registration_number": reg,
                 "issuer_id": issuer_key, "filing_date": fecha,
                 "declarant_name_raw": decl,
                 "declarant_role": "SIGNIFICANT_HOLDER",
                 "list_origin": list_origin,
                 "pct_a": cells[0] if len(cells) > 0 else None,
                 "pct_b": cells[1] if len(cells) > 1 else None,
                 "pct_total": cells[2] if len(cells) > 2 else None,
                 "extra": cells[3] if len(cells) > 3 else None,
                 "doc_token": doc.group(1) if doc else None,
                 "notice_status": "ACTIVE",
                 "raw_sha256": meta_h.get("raw_sha256"),
                 "source_url_observed": meta_h.get("requested_url"),
                 "source_url_canonical": meta_h.get("final_url")}
            upsert_notice(cx, n, run_id)
            n_notices += 1
            for al in re.findall(r"NotificacionesAnuladas\.aspx\?qS=\{[^}]*\}", r):
                collect_anuladas(fx, cx, BASE + "/portal/consultas/derechosvoto/" +
                                 al.replace("{", "%7B").replace("}", "%7D"),
                                 fam, reg, run_id)

    # ---- autocartera
    ac_links = qs_links(h, "Autocartera")
    if ac_links:
        meta_ac, b_ac = fx.get(BASE + "/portal/consultas/derechosvoto/" + ac_links[0],
                               note=f"ac current {issuer_key}")
        hac = b_ac.decode("utf-8", "replace")
        for nac in qs_links(hac, "NotificacionesAnterioresAC"):
            meta_h, b_h = fx.get(BASE + "/portal/consultas/derechosvoto/" + nac,
                                 note=f"ac hist {issuer_key}")
            hh = b_h.decode("utf-8", "replace")
            for r in table_rows(hh, "gridNotifAnt"):
                cells = cell_texts(r)
                reg = reg_from_row(r)
                if not reg:
                    continue
                doc = re.search(r'verdocumento/ver\?e=([^"&\']+)', r)
                fecha = None
                for c in reversed(cells):
                    d = parse_date(c)
                    if d:
                        fecha = d
                        break
                n = {"source_family": "ac", "source_registration_number": reg,
                     "issuer_id": issuer_key, "filing_date": fecha,
                     "declarant_name_raw": issuer["name"],
                     "declarant_role": "ISSUER_TREASURY",
                     "pct_a": cells[0] if len(cells) > 0 else None,
                     "pct_b": cells[1] if len(cells) > 1 else None,
                     "pct_total": cells[2] if len(cells) > 2 else None,
                     "doc_token": doc.group(1) if doc else None,
                     "notice_status": "ACTIVE",
                     "raw_sha256": meta_h.get("raw_sha256"),
                     "source_url_observed": meta_h.get("requested_url"),
                     "source_url_canonical": meta_h.get("final_url")}
                upsert_notice(cx, n, run_id)
                n_notices += 1
                for al in re.findall(r"NotificacionesAnuladas\.aspx\?qS=\{[^}]*\}", r):
                    collect_anuladas(fx, cx, BASE + "/portal/consultas/derechosvoto/" +
                                     al.replace("{", "%7B").replace("}", "%7D"),
                                     "ac", reg, run_id)
    return n_notices

def collect_anuladas(fx, cx, url, fam, annulling_reg, run_id):
    """NotificacionesAnuladas page: explicit 'X anula Y' relation."""
    meta, body = fx.get(url, note=f"anuladas {annulling_reg}")
    h = body.decode("utf-8", "replace")
    t = clean(re.sub(r"<[^>]+>", " ", h))
    m = re.search(r"registro de entrada\s*(\d{9,10})\s*anula", t)
    annulled = re.findall(r"(\d{9,10})\s*de\s*(\d{2}/\d{2}/\d{4})", t)
    if m:
        for areg, adate in annulled:
            add_relation(cx, fam + ":" + m.group(1), fam + ":" + areg,
                         "ANNULS", url, run_id, meta.get("raw_sha256"))

def collect_issuer_identity(fx, cx, issuer_key, issuer, run_id):
    url = f"{BASE}/portal/consultas/ee/datosgenerales.aspx?nif={issuer['nif']}"
    meta, body = fx.get(url, note=f"datosgenerales {issuer_key}")
    h = body.decode("utf-8", "replace")
    rows = table_rows(h, "gridDatos")
    for r in rows:
        cells = re.findall(r'data-th="([^"]+)"[^>]*>(.*?)</td>', r, re.S)
        d = {k: clean(v) for k, v in cells}
        if d.get("NIF"):
            cx.execute("INSERT OR REPLACE INTO issuer VALUES(?,?,?,?,?,?)",
                       (issuer_key, d["NIF"], d.get("LEI"), issuer["name"],
                        d.get("Capital social vigente"), run_id))
            break
    return meta

# ---------------------------------------------------------------- db ops

def upsert_notice(cx, n, run_id):
    key = f"{n['source_family']}:{n['source_registration_number']}"
    regime = regime_of(n["source_family"], n.get("filing_date"))
    # normalized_sha must hash content only; observation context
    # (observed URL incl. ephemeral qS tokens) lives in the observation row.
    norm = json.dumps({k: v for k, v in n.items()
                       if k not in ("raw_sha256", "source_url_observed",
                                    "source_url_canonical")},
                      sort_keys=True, ensure_ascii=False)
    nsha = sha256b(norm.encode())
    cur = cx.execute("SELECT notice_key, first_seen_run FROM notice WHERE notice_key=?",
                     (key,)).fetchone()
    if cur:
        # canonical projection may be corrected by later observations;
        # append-only history lives in notice_observation.
        cx.execute("""UPDATE notice SET last_seen_run=?,
                      filing_date=COALESCE(?,filing_date),
                      doc_token=COALESCE(?,doc_token),
                      declarant_name_raw=COALESCE(?,declarant_name_raw),
                      declarant_role=COALESCE(?,declarant_role),
                      pct_a=COALESCE(?,pct_a), pct_b=COALESCE(?,pct_b),
                      pct_total=COALESCE(?,pct_total),
                      extra_json=COALESCE(?,extra_json)
                      WHERE notice_key=?""",
                   (run_id, n.get("filing_date"), n.get("doc_token"),
                    n.get("declarant_name_raw"), n.get("declarant_role"),
                    n.get("pct_a"), n.get("pct_b"), n.get("pct_total"),
                    json.dumps({"info_adicional": n.get("extra"),
                                "list_origin": n.get("list_origin")},
                               ensure_ascii=False) if (n.get("extra") or n.get("list_origin")) else None,
                    key))
    else:
        cx.execute("""INSERT INTO notice(notice_key,source_family,
                      source_registration_number,issuer_id,regime,filing_date,
                      notice_status,identity_status,doc_token,declarant_name_raw,
                      declarant_role,pct_a,pct_b,pct_total,extra_json,
                      first_seen_run,last_seen_run)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (key, n["source_family"], n["source_registration_number"],
                    n.get("issuer_id"), regime, n.get("filing_date"),
                    n.get("notice_status", "ACTIVE"),
                    "OFFICIAL_REGISTRY_NUMBER" if n["source_registration_number"]
                    else "PROVISIONAL_CONTENT_HASH",
                    n.get("doc_token"), n.get("declarant_name_raw"),
                    n.get("declarant_role"), n.get("pct_a"), n.get("pct_b"),
                    n.get("pct_total"),
                    json.dumps({"info_adicional": n.get("extra"),
                                "list_origin": n.get("list_origin")},
                               ensure_ascii=False),
                    run_id, run_id))
    cx.execute("""INSERT INTO notice_observation(run_id,notice_key,observed_at,
                  raw_sha256,normalized_sha256,source_url_observed,
                  source_url_canonical,status_observed,present_in_source)
                  VALUES(?,?,?,?,?,?,?,?,1)""",
               (run_id, key, datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                n.get("raw_sha256"), nsha, n.get("source_url_observed"),
                n.get("source_url_canonical"), n.get("notice_status", "ACTIVE")))
    cx.execute("INSERT OR IGNORE INTO run_seen VALUES(?,?)", (run_id, key))
    # event stub from listing-level data (index 0)
    cx.execute("""INSERT OR REPLACE INTO event VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
               (key, 0, n.get("filing_date"), n.get("declarant_name_raw"),
                n.get("declarant_role"), n.get("issuer_id"), None,
                None, n.get("pct_total"), None, None,
                "listing"))

def add_relation(cx, a, b, rel, url, run_id, sha):
    cx.execute("""INSERT OR IGNORE INTO notice_relation VALUES(?,?,?,?,?,?)""",
               (a, b, rel, url, run_id, sha))

def regime_of(fam, filing):
    if fam == "nod":
        return "MAR_2018_NOD"
    if fam == "nod_legacy":
        return "PRE_2018_LEGACY"
    if fam in ("ps", "ac") and filing:
        return "CIRC2_2022" if filing >= "2022-08-07" else "RD1362_2007"
    return "UNKNOWN"

# ---------------------------------------------------------------- run

def mark_disappearances(cx, run_id):
    """Notices seen in earlier runs but absent in this run."""
    rows = cx.execute("""SELECT n.notice_key FROM notice n
        WHERE n.last_seen_run<>? AND n.first_seen_run<>?""", (run_id, run_id)).fetchall()
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    for (k,) in rows:
        cx.execute("""INSERT INTO notice_observation(run_id,notice_key,observed_at,
            raw_sha256,normalized_sha256,source_url_observed,source_url_canonical,
            status_observed,present_in_source)
            VALUES(?,?,?,NULL,NULL,NULL,NULL,'SOURCE_DISAPPEARANCE_OBSERVED',0)""",
            (run_id, k, now))

def main():
    init_db()
    cx = db()
    run_id = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
    t0 = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    cx.execute("INSERT INTO crawl_run VALUES(?,?,?,?,?,?,NULL)",
               (run_id, t0, None, "cnmv.es", PARSER_VERSION, "RUNNING"))
    cx.commit()
    fx = Fetcher(run_id)
    stats = {}
    try:
        # last-days incorporations page (reconciliation evidence)
        fx.get(f"{BASE}/portal/Consultas/BusquedaUltimosDias",
               note="ultimos_dias")
        for ik, issuer in ISSUERS.items():
            collect_issuer_identity(fx, cx, ik, issuer, run_id)
            stats[f"{ik}_nod"] = collect_nod(fx, cx, ik, issuer, run_id)
            stats[f"{ik}_nod_legacy"] = collect_nod_legacy(fx, cx, ik, issuer, run_id)
            stats[f"{ik}_ps_ac"] = collect_ps_ac(fx, cx, ik, issuer, run_id)
            cx.commit()
        # mark notices that are explicit annulment/rectification targets
        cx.execute("""UPDATE notice SET notice_status='ANULLED'
            WHERE notice_key IN (SELECT annulled_key FROM notice_relation
                                 WHERE relation_type='ANNULS')""")
        cx.execute("""UPDATE notice SET notice_status='RECTIFIED'
            WHERE notice_key IN (SELECT annulled_key FROM notice_relation
                                 WHERE relation_type='RECTIFIES')
              AND notice_status NOT IN ('ANULLED')""")
        # disappearances vs prior runs
        mark_disappearances(cx, run_id)
        stats["requests"] = fx.n
        t1 = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        cx.execute("UPDATE crawl_run SET completed_at=?,status=?,stats_json=? WHERE run_id=?",
                   (t1, "OK", json.dumps(stats), run_id))
        cx.commit()
        with open(os.path.join(RUNS_DIR, run_id + ".json"), "w", encoding="utf-8") as f:
            json.dump({"run_id": run_id, "started_at": t0, "completed_at": t1,
                       "parser_version": PARSER_VERSION, "stats": stats,
                       "fetches": fx.log}, f, ensure_ascii=False, indent=1)
        print(json.dumps({"run_id": run_id, "stats": stats}, indent=1))
    except Exception as e:
        cx.execute("UPDATE crawl_run SET status=? WHERE run_id=?",
                   ("ERROR:" + repr(e), run_id))
        cx.commit()
        raise

if __name__ == "__main__":
    main()
