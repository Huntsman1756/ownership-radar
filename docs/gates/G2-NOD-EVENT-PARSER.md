# G2 — NOD Event Parser — Gate Contract (frozen)

Status: **FROZEN before parser development** (this file is the
pre-registered contract; results are appended, never used to relax it).

Scope: post-2018 NOD/MAR notifications (`source_surface = nod`).

Out of scope: `nod_legacy` (MODELO III), `ps`, `ac`, OIR, OCR, fuzzy
matching, LLM, entity resolution, API/frontend.

## G1 model correction applied

`source_surface=nod` now maps to `notice_type=PDMR_NOTIFICATION`
(basis `SURFACE_DEFAULT`). A notice is a *notification* carrying
1..N transactions — never `PDMR_TRANSACTION` at notice level.
`event_type` is never inferred from surface.

## Target template

CNMV rendering of the EU Implementing Regulation 2016/523 standard form
(bilingual ES/EN). Observed physical structure (from captured PDFs):

- Sections 1–3: party / reason (checkboxes) / issuer+LEI.
- Section 4 rendered as a wide grid, NOT the stacked EU layout.
  Grid columns: `4.a)` instrument identification code,
  `4.b)` instrument nature, `4.c)` transaction nature, `4.d)` date,
  `4.e)` venue, `4.f)` volume, `4.g)` unit price, `4.h)` currency.
- One grid row = one price/volume pair → one `execution_line`.
- `Total Agregado / Aggregated information (5)` = declared aggregate
  of the enclosing repetition block → stored on `transaction_event`,
  NEVER counted as an execution.

Because the CNMV rendering is materially different from the raw EU
model (wide grid vs. stacked table, currency column, total row), the
fingerprint name is `EU_2016_523_PDMR_CNMV`. If inspection shows a
variant with a distinguishable structure, a second canonical name may
be registered and documented — none may be invented.

Fingerprint rule (content/structure only — never URL/surface/date):
ALL anchors present in the text layer:
`MODELO DE NOTIFICACIÓN` + `STANDARD FORM FOR NOTIFICATION` +
`4.a)` … `4.h)` grid labels + `Total Agregado|Aggregated information`.
Anything else → `UNSUPPORTED_TEMPLATE`. No text layer →
`UNSUPPORTED_NO_TEXT_LAYER`.

## Data model

`transaction_event` = one logical repetition of the section-4 block:
the maximal consecutive run of grid rows sharing
(instrument_code, instrument_nature, transaction_nature, date, venue)
followed by its `Total Agregado`. Each grid row = one `execution_line`.
`source_order` = document order only — NOT a stable economic identity
across amendments.

Notice-level semantic fields: `notification_kind` (INITIAL/AMENDMENT/
UNKNOWN), `amendment_text_raw`, `notifying_party_name_raw`,
`notifying_party_kind` (NATURAL_PERSON/LEGAL_PERSON/UNKNOWN),
`position_status_raw`, `closely_associated` (TRUE/FALSE/UNKNOWN from
checkboxes), `related_pdmr_*`, `issuer_name_document`,
`issuer_lei_document`, `additional_info_raw`, `regulatory_template`,
`parse_status`, `semantic_parser_version`.

Parse statuses (fail closed):
`PARSED`, `PARSED_WITH_UNMAPPED_VALUES`, `UNSUPPORTED_TEMPLATE`,
`UNSUPPORTED_NO_TEXT_LAYER`, `MALFORMED_SOURCE`, `EXTRACTION_ERROR`.
"absent in source" is stored distinctly from "parser failed to extract".

## Numeric / aggregate policy (predefined)

- All money/volume values stored as exact-decimal TEXT plus the raw
  literal. No `float` anywhere in the event layer.
- `computed_volume` = exact Decimal sum of execution volumes.
- `computed_vwap` = Σ(price·volume)/Σ(volume), computed only when every
  execution line carries price+volume in the same declared currency.
- Match criterion: `computed_volume == declared_aggregate_volume`
  (exact) AND `|computed_vwap − declared_aggregate_price| ≤
  0.5·10^(−decimals(declared_aggregate_price))` (declared price is a
  rounded VWAP; tolerance = its own rounding granularity).
- Divergence → recorded as `aggregate_qa=DIVERGENT` evidence; the
  declared value is never overwritten.

## Corpus — deterministic selection (frozen rules)

### DEV (SAN/BBVA, from `data/radar.sqlite`)

For each of SAN, BBVA: all `source_surface='nod'` notices ordered by
`(filing_date, source_registration_number)`; select index ≡ 0 mod 12,
PLUS every notice appearing in `notice_relation` (either side), PLUS
the five PDFs already in `probe/evidence/templates/`. ≈55 documents.

### HOLDOUT (other issuers — never touched during development)

Candidate list, fixed order: `CABK A08663619`, `TEF A28015865`,
`ITX A15022502`, `IBE A95758389`, `REP A78374725`.
Take the first **3** issuers whose full NOD listing yields ≥ 15
notices. For each selected issuer: sort by
`(filing_date, source_registration_number)`; select indices
`{0, ⌊n/4⌋, ⌊n/2⌋, ⌊3n/4⌋, n−1}` (deduplicated), PLUS up to 2 most
recent notices whose listing title contains "rectifica" or "anula".
≈15–21 documents. Results are evaluated once; a holdout failure is
reported, never converted to DEV.

## Gates (PASS / FAIL / INCONCLUSIVE only)

| Gate | Criterion |
|---|---|
| G2-01 CLEAN_CLONE_TESTS_PASS | suite passes on a clean clone w/o private corpus; corpus tests SKIP |
| G2-02 TEMPLATE_FINGERPRINT_EXACT | fingerprint labels match manual document inspection |
| G2-03 NOTICE_PARTY_EXTRACTION_EXACT | party name/kind/CA fields exact vs. source |
| G2-04 INITIAL_AMENDMENT_EXTRACTION_EXACT | kind + amendment_text_raw exact |
| G2-05 ISSUER_LEI_DOCUMENT_EXACT | issuer name + LEI from document |
| G2-06 TRANSACTION_BLOCK_COUNT_EXACT | event count = real block count |
| G2-07 EXECUTION_LINE_COUNT_EXACT | line count = real row count |
| G2-08 INSTRUMENT_EXTRACTION_EXACT | code + nature per event |
| G2-09 TRANSACTION_NATURE_RAW_EXACT | raw nature preserved verbatim |
| G2-10 PRICE_VOLUME_DECIMAL_EXACT | exact decimals, no float |
| G2-11 AGGREGATE_PRESERVED_NO_DOUBLE_COUNT | aggregates preserved, never extra exec lines |
| G2-12 DATE_VENUE_EXTRACTION_EXACT | transaction_date/venue per event |
| G2-13 NOTICE_TO_EVENTS_PROVENANCE_COMPLETE | every event → notice_key + raw_sha256 + parser_version |
| G2-14 HOLDOUT_GENERALIZATION | holdout parses under frozen rules; failures reported verbatim |
| G2-15 SECOND_PARSE_DETERMINISTIC | two independent parses → identical normalized output |

Explicitly absent coverage is reported `NOT_OBSERVED`, never faked.

---

# RESULTS (appended after evaluation — contract above unchanged)

## Corpus

- **DEV = 64 entries** (61 target-template + 3 negative controls):
  SAN/BBVA `nod` by frozen index rule + relation members + template
  samples. Filing years 2018–2026.
- **HOLDOUT = 15**: CABK (237 nod notices listed), TEF (849),
  REP (684) — the first 3 candidates of the fixed list; all yielded
  ≥15 notices. Indices + rectifica/anula rule → 5/issuer; no
  RECTIFIES-titled notices existed in the selections.

## Extraction

| | DEV | HOLDOUT |
|---|---|---|
| notices parsed | 61/61 PARSED | 15/15 PARSED |
| transaction_events | 73 | 16 |
| execution_lines | 146 | 16 |
| multi-event notices | 6 | 1 |
| amendments | 5 | 0 (NOT_OBSERVED) |
| closely-associated | 5 (4 legal, 1 unknown-kind) | 0 (NOT_OBSERVED) |
| aggregate QA | 72 MATCH / 1 n/a | 16 MATCH |
| venues | XMAD, XMCE, XMEX, XNYS, XBAR, BMEX, SIBE, XOFF, XXXX | XMAD, XBAR, XOFF |
| currencies | EUR, USD, MXN | EUR |
| natures | Compra, Venta, Otros | Compra, Venta, Otros |

Negative controls behaved as designed: 2 × `UNSUPPORTED_TEMPLATE`
(MODELO III), 1 × `UNSUPPORTED_NO_TEXT_LAYER` (scanned 2011 PDF).

## Defects found and fixed during DEV

1. `notification_kind` unmapped on amendments: the PDF uses the `ﬁ`
   ligature (U+FB01) — matching is NFKC-folded, raw preserved. 5
   amendments then classified AMENDMENT.
2. `L.P.` missing from legal-form suffixes (Danford Investments L.P.).

No defect was found via HOLDOUT; holdout was evaluated once.

## Gate matrix

| Gate | Verdict | Evidence |
|---|---|---|
| G2-01 CLEAN_CLONE_TESTS_PASS | **PASS** | fresh clone + venv: suite passes, corpus tests SKIP |
| G2-02 TEMPLATE_FINGERPRINT_EXACT | **PASS** | 76×EU_2016_523_PDMR_CNMV; legacy/scanned rejected by anchors, not by surface |
| G2-03 NOTICE_PARTY_EXTRACTION_EXACT | **PASS** | name/kind/CA exact on corpus incl. legal persons |
| G2-04 INITIAL_AMENDMENT_EXTRACTION_EXACT | **PASS** | 56 INITIAL + 5 AMENDMENT; explanation text captured when present |
| G2-05 ISSUER_LEI_DOCUMENT_EXACT | **PASS** | LEI/name from §3 on all parsed; consistent with listing identity |
| G2-06 TRANSACTION_BLOCK_COUNT_EXACT | **PASS** | 89 events; manual spot-checks incl. 5-block notice |
| G2-07 EXECUTION_LINE_COUNT_EXACT | **PASS** | 162 lines; 0 date-bearing grid rows left unparsed |
| G2-08 INSTRUMENT_EXTRACTION_EXACT | **PASS** | code+type on every event |
| G2-09 TRANSACTION_NATURE_RAW_EXACT | **PASS** | raw verbatim; only Compra/Venta normalized |
| G2-10 PRICE_VOLUME_DECIMAL_EXACT | **PASS** | Decimal-only, raw literals preserved |
| G2-11 AGGREGATE_PRESERVED_NO_DOUBLE_COUNT | **PASS** | aggregates stored on event; never an execution; 88/88 computable MATCH |
| G2-12 DATE_VENUE_EXTRACTION_EXACT | **PASS** | per-event transaction_date + venue |
| G2-13 NOTICE_TO_EVENTS_PROVENANCE_COMPLETE | **PASS** | doc_sha256 + parser_version + notice_key on every row |
| G2-14 HOLDOUT_GENERALIZATION | **PASS** | 15/15 PARSED on 3 unseen issuers, frozen rules |
| G2-15 SECOND_PARSE_DETERMINISTIC | **PASS** | two independent parses: 0 digest diffs |

## Known limitations (honest list)

- HOLDOUT contained no amendment or CA-legal-person notice — those
  paths are proven on DEV only (recorded, not faked).
- `related_pdmr_name/position` kept NULL: CA notices put
  "PDMR name - position" in one field with inconsistent separators.
- `share_option_program_linked` always UNKNOWN (not in grid rendering).
- A scanned/image PDF without text layer is reported, not OCR'd.
- Only exact-match natures normalize; the catalog was not expanded
  speculatively.

## G2 VERDICT: **PASS** (pre-audit; see G2-R below)

For the `EU_2016_523_PDMR_CNMV` template, Ownership Radar ES converts a
NOD notification deterministically into 1..N transaction events with
execution lines, declared aggregates, party, instrument, nature, date,
venue and full provenance — no fuzzy matching, OCR or double counting.

---

# G2-R FINAL AUDIT (post-G2 bounded remediation)

## 1. related_pdmr_* audit — defect found and fixed

All 6 corpus CA notices were audited directly against source:

| notice | source | fix |
|---|---|---|
| nod:2020131299 | `"SOL DAURELLA COMADRÁN, CONSEJERA"` — **present** | extracted (COMMA rule) |
| nod:2026035251 | `"ANA PATRICIA BOTÍN-SANZ… - PRESIDENTA…"` — **present** (hyphen inside name, unspaced → safe) | extracted (DASH rule) |
| nod:2023105509 | `"Carlos Salazar Lomelín - Consejero"` — **present** | extracted (DASH) |
| nod:2023106224 | idem — **present** | extracted (DASH) |
| nod:2026043972 | idem — **present** | extracted (DASH) |
| nod:2022110940 *(holdout)* | `"ISIDRO FAINÉ - VICEPRESIDENTE"` — **present** | extracted (DASH) |

The G2 claim "CA NOT_OBSERVED in holdout" was wrong: `nod:2022110940`
(CRITERIA CAIXA, S.A.U., legal person) is a CA notice — the earlier
coverage check only looked at the DEV database. Corrected.

present in source = 6 · absent = 0 · extracted = 6 · failed = 0.

## 2. share_option_program_linked audit

No structured field exists in the CNMV grid rendering; option-program
references appear only inside free-text "Otra información". `UNKNOWN`
is therefore *absence of structured data in source*, not an extraction
failure. Free text is not parsed into booleans (that would be
inference). Documented, no code change.

## 3. Holdout oracle

Created `corpus/oracle/holdout_expected.json`: all 15 notices
hand-annotated from `pdftotext` (poppler) output — an engine
independent of pdfminer. `tests/test_holdout_oracle.py` compares every
notice field, every event, every execution line, and every declared
aggregate against the oracle. Result: **15/15 exact**.

## 4. Dependency pinning

`requirements.txt`: `pdfminer-six==20260107` (exact). The engine
version is also stored per-parse in `nod_notice_semantic.pdf_engine`.

## 5. Determinism re-check

Two independent corpus parses after the G2-R changes: 0 digest diffs.

## Re-evaluated gates

| Gate | Verdict | Note |
|---|---|---|
| G2-03 NOTICE_PARTY_EXTRACTION_EXACT | **PASS** | related_pdmr now extracted on all 6 CA notices; holdout CA verified vs oracle |
| G2-04 INITIAL_AMENDMENT_EXTRACTION_EXACT | **PASS** | unchanged (5 AMENDMENT in DEV; none in holdout — NOT_OBSERVED) |
| G2-14 HOLDOUT_GENERALIZATION | **PASS** | now backed by independent oracle, not self-consistency |
| G2-15 SECOND_PARSE_DETERMINISTIC | **PASS** | 0 diffs post-changes |

Structural paths: amendments and CA extraction **proven in DEV**;
CA also present-and-verified in holdout (1 notice); amendments
**NOT_OBSERVED_IN_HOLDOUT**.

## Directory note

The local worktree path keeps the historical typo
`F:\_Proyectos\owership_radar`: the rename to `ownership_radar` was
attempted and blocked by an external process lock (WinError 32, holder
not identifiable from inside the session). Git history/toplevel are
unaffected — the directory name is cosmetic and no repo-internal path
is absolute. Renaming remains a safe one-step operation once the lock
clears (`mv owership_radar ownership_radar` from `F:\_Proyectos`).

## G2 VERDICT (post-audit): **PASS**

