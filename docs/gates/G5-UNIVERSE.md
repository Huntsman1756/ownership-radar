# G5 — Universe definition (frozen)

## What "covered issuers" means — universe v1

**Source**: AEAT — *"Relación de sociedades españolas cuyas acciones,
a fecha 1 de diciembre de 2025, tienen un valor de capitalización
bursátil superior a 1.000 millones de euros"* (Impuesto sobre
Transacciones Financieras, RD 366/2021, ejercicio 2026).

URL: `https://www3.agenciatributaria.gob.es/static_files/Sede/Tema/
Declaraciones_informativas/I_Transacciones_Financieras/
RELACION_SOCIEDADES_EJERCICIO_2026.pdf`

**Included**: every NIF in that list (one row per NIF-ISIN pair;
dual-class issuers collapse to one NIF). Official NIF + legal name +
share ISIN per entry.

**Explicitly excluded (documented coverage bound, not hidden)**:

- listed companies with market cap ≤ €1bn on 1/12/2025 (the ITF
  threshold): the universe is "ITF-scope issuers", a strict subset of
  all Spanish listed companies;
- BME Growth / MAB issuers not in the ITF list;
- delisted / historical-only issuers;
- non-share issuers, funds, SICAVs, debt-only issuers;
- issuers appearing only via NOD-window discovery: they are recorded
  in `discovered_issuer` as *candidates*, not auto-promoted into the
  universe.

## Why this source

- Official Spanish source (AEAT), annual, stable URL per ejercicio.
- Carries NIF + ISIN — the exact identifier priority G5 requires
  (no ticker-as-identity).
- Deterministically reproducible: seed file carries
  `content_sha256` of the parsed entry list; regenerating from the
  same PDF produces the same entries.

## Identity policy

- `issuer_id` = NIF (e.g. `A39000013`). Official, stable, no fuzzy.
- `issuer_alias` holds market tickers (SAN, BBVA, ...) as
  `alias_type=TICKER`, source-annotated; aliases are conveniences,
  never identity.
- `identity_quality = OFFICIAL_IDENTIFIER` for all seed entries.

## Universe versioning

```text
universe_version = "itf2026-v1"
source           = the AEAT URL above
generated_at     = seed build time
content_sha256   = sha256 of canonical entry list
```

Every production `crawl_run` records the `universe_version` it ran
against. A new universe = new version, new seed file; never in-place
edits.
