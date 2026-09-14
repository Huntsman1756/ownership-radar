"""CNMV surface collectors (ported from the G0 probe).

Surfaces:
  nod        /portal/consultas/directivos-resultado (post-01/05/2018 PDMR)
  nod_legacy /portal/consultas/derechosvoto/notificacionesanterioresdirectivos
             (pre-2018 directivos "distintos de consejeros")
  ps         ps_ac_ini hub -> per-holder NotificacionesAnteriores grids
             (mixes SIGNIFICANT_HOLDING and, pre-2020-03-02,
             DIRECTOR_HOLDING — semantic typing deferred to G2+)
  ac         ps_ac_ini hub -> NotificacionesAnterioresAC (treasury stock)

qS={guid} navigation tokens are ephemeral and session-scoped; they are
never stored as identity. Documents live behind deterministic
verdocumento tokens (durable, per-document — G0-proven).
"""
import html as htmlmod
import re

BASE = "https://www.cnmv.es"

# ------------------------------------------------------------------ parsing

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


# ------------------------------------------------------------------ collectors

def collect_nod(fx, cx, issuer_key, issuer, run_id, store):
    """directivos-resultado?nif=&page=N ; also supports fechad/fechah
    windowing (used by the reconciliation tooling)."""
    nif = issuer["nif"]
    base_url = f"{BASE}/portal/consultas/directivos-resultado?nif={nif}"
    page, total_pages, n_notices = 0, None, 0
    while True:
        url = base_url + (f"&page={page}" if page else "")
        meta, body = fx.get(url, note=f"nod list {issuer_key} page={page}")
        h = body.decode("utf-8", "replace")
        if total_pages is None:
            m = re.search(r"Página \d+ de (\d+)", h)
            total_pages = int(m.group(1)) if m else 1
        blocks = re.findall(
            r'repListaPrincipal_ctl\d+_elementoPrimerNivel.*?</li>\s*</ul>',
            h, re.S) or re.split(r'elementoPrimerNivel', h)[1:]
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
                "source_surface": "nod",
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
            store.upsert_notice(cx, n, run_id)
            n_notices += 1
            if rect:
                store.add_relation(cx, "nod:" + reg.group(1), "nod:" + rect.group(1),
                                   "RECTIFIES", meta.get("requested_url"), run_id,
                                   meta.get("raw_sha256"))
            if rectd:
                store.add_relation(cx, "nod:" + rectd.group(1), "nod:" + reg.group(1),
                                   "RECTIFIES", meta.get("requested_url"), run_id,
                                   meta.get("raw_sha256"))
        page += 1
        if page >= total_pages:
            break
    return n_notices


def collect_nod_legacy(fx, cx, issuer_key, issuer, run_id, store):
    """Pre-2018 per-person grid -> otrasnotificacionesdirectivos history."""
    nif = issuer["nif"]
    url = f"{BASE}/portal/consultas/derechosvoto/notificacionesanterioresdirectivos?nif={nif}"
    meta, body = fx.get(url, note=f"nod_legacy grid {issuer_key}")
    h = body.decode("utf-8", "replace")
    n_notices = 0
    for r in table_rows(h, 'id="ctl00_ContentPrincipal_grid"'):
        cells = cell_texts(r)
        hist = re.search(r"otrasnotificacionesdirectivos\.aspx\?qS=\{[^}]*\}", r)
        reg = reg_from_row(r)
        name = cells[0] if cells else None
        role = cells[1] if len(cells) > 1 else None
        if reg:
            n = {"source_surface": "nod_legacy",
                 "source_registration_number": reg,
                 "issuer_id": issuer_key,
                 "filing_date": parse_date(cells[2]) if len(cells) > 2 else None,
                 "declarant_name_raw": name, "declarant_role": role,
                 "doc_token": (re.search(r'verdocumento/ver\?e=([^"&\']+)', r).group(1)
                               if re.search(r'verdocumento/ver\?e=', r) else None),
                 "notice_status": "ACTIVE",
                 "raw_sha256": meta.get("raw_sha256"),
                 "source_url_observed": meta.get("requested_url"),
                 "source_url_canonical": meta.get("final_url")}
            store.upsert_notice(cx, n, run_id)
            n_notices += 1
        if hist:
            hurl = BASE + "/portal/consultas/derechosvoto/" + hist.group(0)
            m2, b2 = fx.get(hurl, note=f"nod_legacy hist {issuer_key} {name}")
            h2 = b2.decode("utf-8", "replace")
            rows2 = table_rows(h2, "ctl00_ContentPrincipal_grid") or \
                re.findall(r"<tr[^>]*>(.*?)</tr>", h2, re.S)
            for r2 in rows2:
                cells2 = cell_texts(r2)
                reg2 = reg_from_row(r2)
                if not reg2:
                    continue
                fecha2 = next((d for d in (parse_date(c) for c in cells2) if d), None)
                n = {"source_surface": "nod_legacy",
                     "source_registration_number": reg2,
                     "issuer_id": issuer_key, "filing_date": fecha2,
                     "declarant_name_raw": name, "declarant_role": role,
                     "doc_token": (re.search(r'verdocumento/ver\?e=([^"&\']+)', r2).group(1)
                                   if re.search(r'verdocumento/ver\?e=', r2) else None),
                     "notice_status": "ACTIVE",
                     "raw_sha256": m2.get("raw_sha256"),
                     "source_url_observed": m2.get("requested_url"),
                     "source_url_canonical": m2.get("final_url")}
                store.upsert_notice(cx, n, run_id)
                n_notices += 1
    return n_notices


def collect_ps_ac(fx, cx, issuer_key, issuer, run_id, store):
    """ps_ac_ini hub -> current positions + per-holder histories + AC."""
    nif = issuer["nif"]
    hub = f"{BASE}/portal/consultas/derechosvoto/ps_ac_ini.aspx?nif={nif}"
    meta, body = fx.get(hub, note=f"ps hub {issuer_key}")
    h = body.decode("utf-8", "replace")
    n_notices = 0

    np_links = qs_links(h, "Notificaciones-Participaciones")
    if not np_links:
        return 0
    meta_np, b_np = fx.get(BASE + "/portal/consultas/derechosvoto/" + np_links[0],
                           note=f"ps current {issuer_key}")
    hnp = b_np.decode("utf-8", "replace")

    history_links = [(l, "CURRENT_HOLDER")
                     for l in qs_links(hnp, "NotificacionesAnteriores")]
    pon_links = qs_links(hnp, "personasotrasnotificaciones")

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
            n = {"source_surface": "ps",
                 "source_registration_number": reg,
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
            store.upsert_notice(cx, n, run_id)
            n_notices += 1
            for al in re.findall(r"NotificacionesAnuladas\.aspx\?qS=\{[^}]*\}", r):
                collect_anuladas(fx, cx, BASE + "/portal/consultas/derechosvoto/" +
                                 al.replace("{", "%7B").replace("}", "%7D"),
                                 "ps", reg, run_id, store)

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
                n = {"source_surface": "ac",
                     "source_registration_number": reg,
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
                store.upsert_notice(cx, n, run_id)
                n_notices += 1
                for al in re.findall(r"NotificacionesAnuladas\.aspx\?qS=\{[^}]*\}", r):
                    collect_anuladas(fx, cx, BASE + "/portal/consultas/derechosvoto/" +
                                     al.replace("{", "%7B").replace("}", "%7D"),
                                     "ac", reg, run_id, store)
    return n_notices


def collect_anuladas(fx, cx, url, surf, annulling_reg, run_id, store):
    """NotificacionesAnuladas page: explicit 'X anula Y' relation.
    One empty page was observed in G0 (ps:2025054066) — absence of the
    'anula' statement yields no relation, never a guessed one."""
    meta, body = fx.get(url, note=f"anuladas {annulling_reg}")
    h = body.decode("utf-8", "replace")
    t = clean(re.sub(r"<[^>]+>", " ", h))
    m = re.search(r"registro de entrada\s*(\d{9,10})\s*anula", t)
    annulled = re.findall(r"(\d{9,10})\s*de\s*(\d{2}/\d{2}/\d{4})", t)
    if m:
        for areg, adate in annulled:
            store.add_relation(cx, surf + ":" + m.group(1), surf + ":" + areg,
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
