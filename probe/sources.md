# Sources discovered — CNMV

All endpoints under `https://www.cnmv.es`. Transport is HTTPS GET returning
HTML (ASP.NET WebForms). No JSON/XML API was found on the paths probed:
`api.cnmv.es` and `internet.cnmv.es` both 302-redirect to
`http://www.cnmv.es/wap/index.wml` (legacy WAP page). Deep links to some
aspx pages outside the navigation flow return `Error?errorcode=CVFE`.

## Per-family surfaces

### `nod` — Notificaciones de operaciones de directivos (post-01/05/2018)

- List: `GET /portal/consultas/directivos-resultado?nif={NIF}&page={N}`
- Bounded windows: `&fechad=DD/MM/YYYY&fechah=DD/MM/YYYY` — accepted
  server-side, verified live (SAN 2024 -> 4 pages / 32 notices).
- Pagination: `page=N`, `Página X de Y` marker, 10 notices/page,
  newest-first. **Not** insertion-stable — hence windowed traversal +
  dedup by registration number.
- Per-notice fields in the block: filing date, issuer, `Declarante:`,
  `Motivo de la notificación:`, `Número de registro:`, and when applicable
  `Notificación que rectifica a nº de registro:` / `rectificada por nº`.
- Document: `https://www.cnmv.es/webservices/verdocumento/ver?e={token}` —
  token is a **deterministic, durable, per-document identifier**
  (byte-identical across 3 runs / ~9h, and yesterday's tokens still serve
  PDFs today). No session required.

### `nod_legacy` — Directivos pre-01/05/2018 (RD 1362/2007 models)

- Entry: `GET .../derechosvoto/notificacionesanterioresdirectivos?nif={NIF}`
  -> grid of persons (directivos "distintos de consejeros") each linking to
  `otrasnotificacionesdirectivos.aspx?qS={GUID}` — per-person full history.
- `qS` tokens are **ephemeral session-scoped navigation tokens** (fresh per
  crawl); only used to reach pages, never as identity.
- Pre-2018 consejeros are NOT here — they appear on the `ps` surface
  (Circular 8/2015 "Modelo 2 – Notificación de consejeros"), confirmed by
  document fingerprints.
- Some pre-2010 PDFs are scanned images without a text layer
  (e.g. reg 2011144527 — `pdftotext` yields empty output).

### `ps` / `ac` — Participaciones significativas y autocartera

- Hub: `GET .../derechosvoto/ps_ac_ini.aspx?nif={NIF}` (also exposes
  "Sociedades cotizadas donde participa" and "Pactos parasociales" — the
  latter out of G0 scope).
- `Notificaciones-Participaciones` -> current positions grid ->
  per-holder history `NotificacionesAnteriores.aspx?qS={GUID}`:
  columns `Total % acciones (A)`, `Total % Inst. financieros (B)`,
  `Total A+B`, `Información adicional`, `Número de Registro`,
  `F.Registro Entrada CNMV`. History grids are single-page (36 rows seen
  in one grid, no pager) — enumeration is per-holder, not global.
- `personasotrasnotificaciones` link lists ex-holders / other persons
  (this is where pre-2020-03-02 consejero PS notices live).
- `Autocartera` -> `NotificacionesAnterioresAC` -> issuer's own history.
- Rows may carry `NotificacionesAnuladas.aspx?qS={GUID}` links ->
  annulment page stating literally:
  "Notificación con nº de registro de entrada {X} anula la siguiente
  notificación: {Y} de {DD/MM/YYYY}" (plural form "anula la/s siguiente/es
  notificación/es" also seen). One empty annulment page was observed
  (`ps:2025054066`, BBVA) — see results.md anomaly.
- 33 PS notices (all filing_date < 2008, all via OTRAS_NOTIFICACIONES)
  carry a registration number but **no linked document** — paper-era
  filings, not digitized. Registration numbers pre-2007 are 9-digit
  (`199950136`), 10-digit afterwards — same sequence, longer prefix.

### Incorporations — last 5 days

- `GET /portal/Consultas/BusquedaUltimosDias` — per day -> registry ->
  issuer list with per-section counts, e.g.
  "Participaciones significativas y Autocartera (6)". **Does not list
  registration numbers** and does not cover the NOD/directivos registry
  — usable as an incorporation signal at issuer level only.

### Related surfaces documented but out of scope

- OIR: `GET /portal/otra-informacion-relevante/resultado-oir.aspx?nif=&fechaDesde=&fechaHasta=`
  works without session. Entries show an OIR-internal "Número de registro:
  651"-style per-issuer sequence, but detail links expose the shared
  10-digit sequence (`detalleifialdia.aspx?nReg=2020025905`). Result pages
  appear truncated (8 items in a 22-month window) — pagination mechanism
  not fully characterized; not needed for G0.
- Legacy "hechos relevantes": `/portal/hr/busquedahr.aspx?division=3`
  ("hasta 08/02/2020").
- Issuer identity: `datosgenerales.aspx?nif=` gives NIF + LEI
  (SAN LEI 5493006QMFDDMYWIAM13; BBVA K8MS7FD7N5Z2WQ51AZ71).

## Depth observed

| family      | SAN                  | BBVA                 |
|-------------|----------------------|----------------------|
| nod         | 2018-07-02 → 2026-09-08 (320) | 2018-09-21 → 2026-08-25 (258) |
| nod_legacy  | 2007-08-14 → 2018-04-17 (312) | 2008-04-09 → 2018-04-20 (177) |
| ps          | 1999-09-28 → 2026-06-09 (1077)| 2000-10-16 → 2026-05-02 (751) |
| ac          | 2008-02-25 → 2026-09-07 (130) | 2008-01-15 → 2026-07-01 (164) |

## Registration number space

Single shared year-prefixed sequence ("registro de entrada", e.g.
`2026120682`) used across nod/ps/ac (and OIR detail `nReg`). Zero
cross-family collisions in the corpus, but `notice_key` keeps the family
prefix defensively.

## Template generations (document fingerprints — see evidence/templates/)

| era / surface          | fingerprint |
|------------------------|-------------|
| nod_legacy 2007–2018   | "MODELO III — NOTIFICACIÓN DE LOS DIRECTIVOS (DISTINTOS DE LOS CONSEJEROS)..." (monolingual, RD 1362/2007) |
| nod 2018→today         | bilingual "STANDARD FORM ... PDMR / persons closely associated" (MAR model) — identical generation across 2019/2021/2025 samples |
| ps pre-07/08/2022      | Circular 8/2015: "Modelo 1" (non-consejeros) + "Modelo 2 – Notificación de consejeros" |
| ps post-07/08/2022     | Circular 2/2022 "Modelo 1 — NOTIFICACIÓN DE PARTICIPACIONES SIGNIFICATIVAS" (adds loyalty double-voting clauses) |
| ac pre-07/08/2022      | "Formulario Modelo 4" (own shares) |
| ac post-07/08/2022     | "Formulario Modelo 2" (own shares) |

Regime is therefore derivable from `filing_date` + `source_family` +
document template fingerprint — not from URL/hostname.
