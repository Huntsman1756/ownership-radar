# Results — G0 Acquisition Probe

Issuers: Banco Santander (SAN, NIF A39000013, LEI 5493006QMFDDMYWIAM13),
BBVA (NIF A48265169, LEI K8MS7FD7N5Z2WQ51AZ71). Third issuer: not needed.

Corpus after 3 runs: 3189 notices (nod 578, nod_legacy 489, ps 1828,
ac 294), 9567 append-only observations, 52 explicit relations,
2 issuer identities.

## 1. Transport & identity (PROVEN)

- No structured API found (`api.cnmv.es`, `internet.cnmv.es` -> WAP
  redirect). Real transport = ASP.NET HTML GET surfaces + a document
  service (`/webservices/verdocumento/ver?e=`).
- 3189/3189 notices carry an official "Número de registro (de entrada)"
  — a shared year-prefixed sequence across families. `identity_status`
  = OFFICIAL_REGISTRY_NUMBER for 100% of the corpus; the
  PROVISIONAL_CONTENT_HASH fallback exists but was never exercised.
- Notice identity recrawl-stable: identical sets across 3 runs; document
  tokens byte-identical across runs and still resolve ~30h later.
- Ephemeral navigation tokens (`qS={guid}`) are session-scoped —
  documented, never used as identity.

## 2. Determinism evidence (PROVEN)

| check | result |
|-------|--------|
| run1 vs run2 vs run3 notice sets | identical (0/0 divergence, 3189 each) |
| doc_token per notice across runs | identical (spot + full table) |
| normalized_sha256 per notice | identical across runs **after v0.1.1 fix** — v0.1.0 wrongly included the observed URL (ephemeral `qS` tokens) in the content hash; caught and corrected during the probe (see §8 note in gates.md / parser changelog below) |
| NOD windowed union vs traversal | identical (320 SAN / 258 BBVA, 0 divergence) |
| disappearance observations | 0 (nothing vanished between runs) |

## 3. Independent reconciliation (PARTIAL — per family)

- `nod`: **fully reconciled** — 8 disjoint date windows
  (`fechad`/`fechah`, covering 2018-05-01 → 2026-09-14) union to exactly
  the traversal set for both issuers (`evidence/windowed/`,
  `evidence/windowed/recon_result.json`).
- `ps`, `ac`, `nod_legacy`: enumeration is **deterministic and
  run-stable** but no independent per-notice enumeration surface exists
  to reconcile against. The últimos-5-días page reconciles only at
  issuer level (counts per registry, no reg numbers) and does not cover
  `nod`. Completeness for these families is **UNKNOWN by design** — the
  ledger must expose coverage bounds, never claim completeness.

## 4. Amendment / cancellation case study (PROVEN — explicit, no inference)

Real chains, all expressed verbatim by CNMV:

```
ac:2021035057 (SAN, 2021-03-18, ACTIVE)
  └─ anula ─> ac:2021034475 (2021-03-17, ANULLED)
       └─ anula ─> ac:2020135157 (2020-12-21, ANULLED)

ac:2020120323 -> ac:2020034159 -> ac:2020033836   (SAN autocartera)
ps:2025137723 -> ps:2025137603 -> ps:2025136379   (SAN PS)
nod:2026120682 -rectifica-> nod:2026113065        (SAN NOD, both listed)
```

Evidence example (`raw/run-20260914T035225Z/00137.html`,
sha256 a0d8bbb3a34fc577…): "Notificación con nº de registro de entrada
2021035057 anula la siguiente notificación: 2021034475 de 17/03/2021".

Two distinct mechanics observed:

- **NOD rectification**: both notices stay listed; the newer carries
  "rectifica a nº de registro X" (and the older "rectificada por nº Y").
- **PS/AC annulment**: annulment is expressed on a dedicated
  `NotificacionesAnuladas` page linked from the annulling row;
  **31 of 48 annulled notices are absent from the history listings** —
  annulment removes entries from the current-state view (they remain
  provable only via the explicit relation captured at crawl time).
  This is precisely why `notice_observation` must be append-only and why
  A ⊆ B cannot be assumed.

Anomaly: `ps:2025054066` (BBVA, BNP PARIBAS) has an `anuladas` link whose
page renders **empty** (`raw/run-20260914T035225Z/00205.html`) — relation
cannot be extracted; recorded as one EMPTY_ANNULMENT_PAGE anomaly, not
resolved by guessing.

## 5. Regime findings (PROVEN/OBSERVED per item)

| boundary | finding |
|----------|---------|
| pre-2018 | `nod_legacy` surface: directivos (non-consejeros), MODELO III docs, max filing SAN 2018-04-17 / BBVA 2018-04-20 |
| 01/05/2018 cut | clean application boundary: `nod` min filing SAN 2018-07-02 / BBVA 2018-09-21; zero overlap, zero same-date collisions between apps |
| 01/05/2018→01/03/2020 window | 113 `nod` notices exist (SAN 65, BBVA 48) and are served by the current app with the **same bilingual MAR template** as post-2020 filings — no duplicate/omission observed between the two query apps for these issuers |
| consejeros pre-02/03/2020 | report via `ps` surface (Circular 8/2015 "Modelo 2 – Notificación de consejeros"; e.g. ps:2019021574 SAN, J.A. Álvarez, 2019-02-18) — reachable through `personasotrasnotificaciones` |
| 07/08/2022 (Circ. 2/2022) | template transition proven in documents: ac Modelo 4 → Modelo 2; ps Circ.8/2015 Modelo 1/2 → Circ.2/2022 Modelo 1. First observed post-regime filings: ac 2022-08-14, ps 2022-08-26 (legal effective 07/08/2022 — `legal_effective_date` ≠ `observed_template_transition`, as expected) |
| percentage semantics | post-2022 Modelo 1 adds "votos adicionales atribuidos por acciones de lealtad" (loyalty double voting) absent from the 2019 model → `percentage_semantics` field required; listing columns (%A, %B, A+B) are position totals |

## 6. Declarant identity (conservative)

- `global identities created = 0`, `fuzzy merges performed = 0`.
- Noise metrics (nod+nod_legacy): SAN 123 raw names → 101 normalized
  buckets, 20 buckets with >1 raw variant (accents `GARCIA/GARCÍA`,
  case, spacing `BOSTOCK , NATHAN`, typos `Saénz`); BBVA 60 → 58, 1
  multi-variant bucket.
- Convention differs by surface: `nod` uses "NAME SURNAMES",
  `ps`/`nod_legacy` use "SURNAMES, NAME" — same person appears under
  both ("BELEN ROMANA GARCIA" vs "ROMANA GARCIA, BELEN"). Stored raw
  only, scoped `declarant_scope_issuer_id`.
- Corporate holders carry their own variants
  ("MUTUA MADRILEÑA AUTOMOVILISTA" vs "..., S.S.P.F.") — kept distinct.

## 7. Bitemporality stance

- All data captured is `RECONSTRUCTED_HISTORY` — reconstructed from the
  state observable at crawl time. True `OBSERVED_HISTORY` starts with
  our runs (5 identical observations so far).
- We never claim what CNMV showed at date X < first_observation; the
  source itself removes annulled notices from listings.

## 8. Design finding — source_surface ≠ notice_type ≠ regulatory_template

The single most consequential architecture finding of G0: the topology
of CNMV's historical query applications does **not** align with the
semantic event taxonomy. Concretely:

- `nod_legacy` (pre-2018 surface) contains only directivos "distintos de
  consejeros" — consejeros' holdings were reported through the **PS
  surface** under Circular 8/2015 "Modelo 2 – Notificación de
  consejeros" (proven by document fingerprint, e.g.
  `ps:2019021574` SAN, 2019-02-18).
- The `ps` surface therefore mixes SIGNIFICANT_HOLDING and
  DIRECTOR_HOLDING notice types before 02/03/2020.
- The same regulatory template family appears under different surfaces
  across time, and the same surface serves different templates across
  regimes.

Consequence for the schema — three independent dimensions, never
collapsed:

```
source_surface       nod | nod_legacy | ps_ac | ...
notice_type          PDMR_TRANSACTION | DIRECTOR_HOLDING |
                     SIGNIFICANT_HOLDING | TREASURY_STOCK | ...
regulatory_template  RD1362_2007_MODELO_III | CIRC_8_2015_MODEL_1 |
                     CIRC_8_2015_MODEL_2 | CIRC_8_2015_MODEL_4 |
                     MAR_PDMR | CIRC_2_2022_MODEL_1 | CIRC_2_2022_MODEL_2 | ...
```

`regime` is derived from filing_date + template fingerprint + surface
evidence — never from hostname/URL/family alone.

## 9. Known unknowns (nothing hidden)

1. Completeness of `ps`/`ac`/`nod_legacy` enumeration cannot be
   independently proven — a subject whose entire history is outside the
   current/ex-holder grids would be invisible to us. Mitigation:
   periodic re-enumeration + disappearance observations.
2. 33 pre-2008 PS notices have registration numbers but no retrievable
   document (paper era).
3. Some pre-2010 legacy PDFs are scans without text layer — future
   event-level extraction for that slice needs OCR or manual handling
   (out of scope: no LLM/OCR assumed).
4. Whether OIR/hechos-relevantes contain economic duplicates of
   2018–2020 NOD filings was not fully resolved (OIR surface works via
   GET but result truncation observed; OIR is outside the G0 ledger).
5. `event` rows are listing-level stubs (index 0). The NOD form's
   section 4 explicitly repeats per instrument/operation/date/venue —
   a notice is 1..N events; full event extraction requires PDF parsing
   (not attempted beyond template fingerprinting).
6. One empty annulment page (§4) — mechanism unexplained.
7. `doc_token` semantics: durable per-document identifier proven
   empirically, but its encoding/expiry rules are opaque; future system
   should re-resolve tokens from listings rather than treat them as
   permanent URLs.
8. CNMV deregistration of ex-listed issuers' PS notices (10-year rule)
   not observable with SAN/BBVA — recorded as a designed-for risk only.
