# G3 — Significant Holdings + Treasury Stock — Gate Contract (frozen)

Status: **FROZEN before parser development.** This file is the
pre-registered contract; results are appended, never used to relax it.

G3 is split into two semantically independent subphases:

- **G3-A — Significant Holdings** (`source_surface = ps`)
- **G3-B — Treasury Stock** (`source_surface = ac`)

The global G3 verdict is `PASS` only if G3-A **and** G3-B are `PASS`.

## Regulatory scope (fixed)

| family | template | fingerprint name |
|---|---|---|
| ps | Circular 8/2015 — Modelo 1 (major holdings) | `CIRC_8_2015_MODEL_1` |
| ps | Circular 2/2022 — Modelo 1 (major holdings) | `CIRC_2_2022_MODEL_1` |
| ps | Circular 8/2015 — Modelo 2 (directors) — *recognized, out of scope* | `CIRC_8_2015_MODEL_2_DIRECTOR` |
| ac | Circular 8/2015 — Modelo 4 (own shares) | `CIRC_8_2015_MODEL_4` |
| ac | Circular 2/2022 — Modelo 2 (own shares) | `CIRC_2_2022_MODEL_2` |

Legal boundary: `legal_effective_date(Circular 2/2022) = 2022-08-07`.
`legal_effective_date(Circular 8/2015) = 2015-12-28`. Dates are corpus-
reporting metadata only — a template is never identified by filing
date, URL, hostname or `source_surface`.

Out of scope: pre-Circular-8/2015 parsers (Circular 2/2007 and earlier),
OCR, LLM, fuzzy matching, entity resolution, OIR reconciliation, event
taxonomy / ledger layer (deferred to G4+).

## Fingerprint contract (content anchors only)

The CNMV bilingual form title is `Formulario Modelo N` +
`Standard Form #N` plus a subtitle. The subtitle disambiguates
colliding numbers (Modelo 2 exists both as directors, 8/2015, and as
treasury, 2/2022). Matching is case-insensitive on the NFKC-folded
text layer; the bilingual layout interleaves ES/EN cell text, so
anchors are whole words that must all be *present*, never contiguous
phrases.

Observed generation discriminators (from corpus characterization):

- PS major-holdings family: `PARTICIPACIONES` + `SIGNIFICATIVAS` +
  bilingual marker `STANDARD FORM`.
  - with `LEALTAD`/`LOYALTY` (section 11) → `CIRC_2_2022_MODEL_1`;
  - without → `CIRC_8_2015_MODEL_1`. The pre-2020-03-02 subtitle
    `que no tengan la condición de consejeros` is *optional* evidence:
    post-2020-03-02 Circular-8/2015 filings dropped it once director
    notifications moved to the NOD surface — its absence does NOT
    make the doc Circular 2/2022.
- `CIRC_8_2015_MODEL_2_DIRECTOR`: `CONSEJEROS` + `MODELO` +
  bilingual marker (title `Formulario Modelo 2` + `Notification form
  for directors`).
- `CIRC_8_2015_MODEL_4`: `ACCIONES PROPIAS` + `MODELO 4`/`FORM #4` +
  bilingual marker.
- `CIRC_2_2022_MODEL_2`: `ACCIONES PROPIAS` + `MODELO 2`/`FORM #2` +
  bilingual marker.
- Monolingual CNMV ownership forms (`MODELO I`/`II`/`…` titles or
  `ACCIONES PROPIAS` without `STANDARD FORM`) →
  `UNSUPPORTED_LEGACY_TEMPLATE` — pre-Circular-8/2015 filings persist
  well into the C8 window (e.g. a monolingual MODELO I filed
  2018-03-19), so *filing date is never a template discriminator*.
- No text layer → `UNSUPPORTED_NO_TEXT_LAYER`.
- Anything else → `UNSUPPORTED_TEMPLATE`.

`CIRC_8_2015_MODEL_2_DIRECTOR` documents are fingerprinted but the
G3-A semantic parser does not run on them: status
`UNSUPPORTED_TEMPLATE` (recognized, outside the registered scope).

## Core semantic invariants (pre-registered)

### G3-A — a significant-holding notice is a disclosure, not a trade

```
notice → significant_holding_disclosure → position/components
```

- Never invent BUY/SELL transactions from percentage differences.
- The declared reason (§2 checkboxes) is preserved as flags + raw;
  `Otros motivos` free text preserved verbatim.
- §5 threshold date is a declared source value.
- §6 position: shares %, financial-instruments %, total %, issuer
  total voting rights; previous-notification position kept separate.
- §7.A: share components keep direct/indirect columns distinct
  (column identity comes from cell x-position under the column
  header — never from cell order alone when a column is empty).
- §7.B.1 / §7.B.2: each instrument row is its own entity with type,
  expiration, exercise period, settlement (7.B.2), voting rights and
  %. Instruments are never collapsed into shares.
- §8 control chain: preserved as ordered rows (name + % voting + %
  instruments + total), including the "not controlled" checkbox and
  the free-text chain description.
- §3 concerted-action checkbox preserved; §4 shareholder/holder list
  preserved verbatim.
- §9 proxy voting rights preserved when present.
- In-form annulment block (`Anulación de notificaciones
  anteriormente remitidas`) is captured as declared evidence — it
  never writes `notice_relation` by itself.
- §11 (2/2022 only): loyalty voting fields kept as their own
  structure (11.A additional rights direct/indirect, 11.B pending
  loyalty shares by month). Empty §11 → all loyalty fields NULL with
  `loyalty_section_present=TRUE, populated=FALSE`. Loyalty fields can
  never be populated on a `CIRC_8_2015_MODEL_1` parse.
- `percentage_semantics`: `PRE_C2_2022_VOTING_RIGHTS` for
  `CIRC_8_2015_MODEL_1`; `C2_2022_INCLUDING_LOYALTY` for
  `CIRC_2_2022_MODEL_1`. Carried on every percentage-bearing row set.
- Declared aggregate (§6) vs computed component sum: QA only —
  `DECLARED_COMPUTED_MATCH|MISMATCH|NOT_COMPUTABLE` at the declared
  value's own rounding granularity. Declared is never overwritten.

### G3-B — three separate semantic layers

```
operations during period  ≠  resulting position  ≠  regulatory trigger
```

- §2 reason checkboxes preserved; **2.2 is the declared 1 %
  acquisition trigger** — stored as a flag, not recomputed.
- §4: one row per operation: date, A/T raw flag, ISIN, direct shares +
  price, indirect shares + price, direct/indirect voting rights,
  % direct/indirect. Rows with empty share/price cells (loan-type
  operations) are preserved with NULLs, not dropped.
- `Total Adquisición` / `Total Transmisión` rows stored as declared
  totals; computed sums kept as QA, never replacing declared.
- §5 final position: direct/indirect shares, voting rights (direct,
  indirect, total), % (direct, indirect, total) — the *stock*, never
  merged with the §4 *flow*.
- §6 indirect position: 6.1 controlled undertakings rows
  (name + %), 6.2 interposed persons, 6.3 other circumstances, total
  indirect %. §7 chain detail preserved as raw text (it is a
  free-text narrative in both generations).
- Trigger QA (`acquisition_flow_qa`): computed acquisition sums are
  compared against declared totals only; **disposals are never
  subtracted** in any trigger-related derivation.

### Shared

- `Decimal` only; raw literal + normalized value both stored; comma
  decimals and dot thousands separators are the CNMV convention.
- Parse statuses: `PARSED`, `PARSED_WITH_UNMAPPED_VALUES`,
  `UNSUPPORTED_TEMPLATE`, `UNSUPPORTED_LEGACY_TEMPLATE`,
  `UNSUPPORTED_NO_TEXT_LAYER`, `MALFORMED_SOURCE`, `EXTRACTION_ERROR`.
- Field absent in source (`NULL` + section/field marked absent) is
  never conflated with extraction failure (`unmapped` note +
  `PARSED_WITH_UNMAPPED_VALUES`).
- Annulled/cancelled notices keep their semantic rows; `notice_relation`
  (G1) links them — semantics are never deleted.
- `semantic_parser_version` independent per family:
  `pspdf-0.1.0`, `acpdf-0.1.0`; `pdf_engine` recorded per parse.
- Canonical semantic digest depends on content + parser/engine
  versions only — never on URL, path or run timestamp.

## Corpus — deterministic selection (frozen rules)

### DEV (from `data/radar.sqlite`, issuers SAN + BBVA)

Buckets by `filing_date`: `LEGACY` = < 2015-12-28, `C8` =
[2015-12-28, 2022-08-06], `C2` = ≥ 2022-08-07.

- **G3-A**: the `ps` surface mixes significant-holding disclosures
  with pre-2020-03-02 director notifications. Listing metadata
  (`extra_json.list_origin`, captured at collection time) splits the
  population deterministically: `CURRENT_HOLDER` = per-holder history
  grids; `OTRAS_NOTIFICACIONES` = the "otras notificaciones" grid,
  which mixes directors with some significant holders. Inside OTRAS,
  `declarant_name_raw` contains a comma for natural persons
  ("SURNAME, NAME") and typically none for institutions — a lexical
  selection heuristic only (no semantic inference; over-inclusion is
  harmless). Selection per issuer:
  - bucket C8: **all** `CURRENT_HOLDER` notices, **all** OTRAS
    notices whose `declarant_name_raw` contains no comma, plus
    comma-bearing OTRAS index ≡ 0 (mod 40);
  - bucket C2: index ≡ 0 (mod 5) over the whole bucket;
  - bucket LEGACY: indices {0, n−1};
  - plus every `ps:*` member of `notice_relation` (either side);
  - plus the 4 `ps_*` PDFs already in `probe/evidence/templates/`.
- **G3-B**: within each issuer × bucket C8, index ≡ 0 (mod 8); bucket
  C2 index ≡ 0 (mod 6); LEGACY indices {0, n−1}; every `ac:*` member
  of `notice_relation`; plus the 2 `ac_*` template samples.

Rows are ordered by `(filing_date, source_registration_number)`
inside each bucket; NULL dates sort first.

### HOLDOUT (issuers never equal to SAN/BBVA; untouched until eval)

Candidate list, fixed order (same as G2): `CABK A08663619`,
`TEF A28015865`, `ITX A15022502`, `IBE A95758389`, `REP A78374725`.

For each family independently, `collect_ps_ac` is run into
`corpus/corpus.sqlite` in candidate order; the first **2** issuers
whose listing yields ≥ 4 in-scope notices in **each** bucket (C8 and
C2) for that family are selected. If fewer than 2 issuers satisfy a
bucket minimum, the first 2 issuers by total in-scope count are used
and the deficit is recorded as `NOT_OBSERVED` coverage.

Per selected issuer × family: within each bucket (C8, C2), split the
population into strata — `S1` = `list_origin=CURRENT_HOLDER`,
`S2` = OTRAS with no comma in `declarant_name_raw`, `S3` = the rest —
and select indices `{0, n−1}` per stratum × bucket (deduplicated).
For `ac` all notices fall in S3. Plus up to 2 most recent
`ps:`/`ac:` relation members (either side) for that issuer; plus
LEGACY index 0 (one negative case per issuer).

Holdout is evaluated once against the frozen rules. A holdout failure
is reported verbatim, never converted into DEV.

### SPECIAL_CASE_LOYALTY

Before freezing results, all fetched `CIRC_2_2022_MODEL_1` DEV docs
are scanned for populated §11 fields. Any found form a separately
documented `SPECIAL_CASE_LOYALTY` set — never retro-added to HOLDOUT.
If none: `LOYALTY_VALUES = NOT_OBSERVED` and loyalty gates can at most
assert structural support.

## Gates

### Common

| Gate | Criterion |
|---|---|
| G3-C01 BASELINE_G2_UNCHANGED | G2 tests + G2 semantic digests byte-identical before/after G3 |
| G3-C02 CLEAN_CLONE_TESTS_PASS | fresh clone + venv: suite passes; corpus tests SKIP explicitly |
| G3-C03 TEMPLATE_FINGERPRINT_EXACT | fingerprints match manual doc inspection on all corpus files |
| G3-C04 RAW_TO_SEMANTIC_PROVENANCE_COMPLETE | every semantic row → notice_key + doc_sha256 + parser version |
| G3-C05 ABSENT_VS_EXTRACTION_FAILURE_DISTINCT | no silent NULL for present-but-failed fields anywhere in corpus |
| G3-C06 SECOND_PARSE_DETERMINISTIC | two independent parses → identical digests |

### G3-A — Significant Holdings

| Gate | Criterion |
|---|---|
| G3-A01 MODEL_I_PARSE_EXACT | all DEV CIRC_8_2015_MODEL_1 docs reach PARSED/PARSED_WITH_UNMAPPED_VALUES with correct fields |
| G3-A02 MODEL_1_PARSE_EXACT | same for CIRC_2_2022_MODEL_1 |
| G3-A03 OBLIGED_SUBJECT_EXACT | §3 name + residence + §4 holders verbatim vs oracle |
| G3-A04 NOTIFICATION_REASON_EXACT | §2 checkbox flags + `Otros` text exact |
| G3-A05 THRESHOLD_DATE_EXACT | §5 date exact |
| G3-A06 TOTAL_POSITION_EXACT | §6 current+previous rows, all four values + issuer total |
| G3-A07 SHARES_COMPONENT_EXACT | §7.A rows: ISIN, direct/indirect counts and %, column identity |
| G3-A08 FINANCIAL_INSTRUMENT_ROWS_EXACT | §7.B.1+7.B.2 row counts + all fields |
| G3-A09 DIRECT_INDIRECT_SEMANTICS_PRESERVED | empty-column cells never shift a value into the wrong direct/indirect slot |
| G3-A10 CONTROL_CHAIN_PRESERVED | §8 rows + checkbox + annex rows preserved in order |
| G3-A11 PREVIOUS_POSITION_PRESERVED | §6 previous-notification row distinct from current |
| G3-A12 AGGREGATE_QA_NO_SILENT_REWRITE | declared §6 never overwritten; QA status recorded |
| G3-A13 PRE_POST_2022_PERCENTAGE_SEMANTICS_EXPLICIT | `percentage_semantics` carries the correct regulatory generation per row set |
| G3-A14 NO_INVENTED_TRANSACTION | zero transaction/trade objects emitted by the PS parser |
| G3-A15 HOLDOUT_GENERALIZATION | holdout parses under frozen rules vs independent oracle |
| G3-A16 LOYALTY_SECTION_STRUCTURAL | §11 parsed structurally on C2 docs; populated values only if observed |

### G3-B — Treasury Stock

| Gate | Criterion |
|---|---|
| G3-B01 MODEL_IV_PARSE_EXACT | all DEV CIRC_8_2015_MODEL_4 docs parse correctly |
| G3-B02 MODEL_2_PARSE_EXACT | same for CIRC_2_2022_MODEL_2 |
| G3-B03 ISSUER_EXACT | §1 NIF + name + declared voting rights |
| G3-B04 OPERATION_COUNT_EXACT | §4 row count = real operation rows |
| G3-B05 ACQUISITION_DISPOSAL_EXACT | A/T flag raw + normalized per row; mixed notices keep both |
| G3-B06 SHARES_EXACT | direct/indirect share counts per operation, incl. empty-cell rows |
| G3-B07 PRICE_DECIMAL_EXACT | prices as exact Decimals + raw; empty price preserved as NULL |
| G3-B08 RESULTING_POSITION_EXACT | §5 shares/rights/% triads exact |
| G3-B09 FLOW_VS_STOCK_DISTINCT | §4 totals and §5 position stored in distinct structures |
| G3-B10 ONE_PERCENT_TRIGGER_NOT_MODELED_AS_NET_CHANGE | trigger = §2.2 declared flag; no derived net-change trigger |
| G3-B11 INDIRECT_POSITION_PRESERVED | §6.1/6.2/6.3 rows + total indirect % |
| G3-B12 CANCELLATION_HISTORY_NON_DESTRUCTIVE | annulled notices keep semantic rows; relations link, never delete |
| G3-B13 HOLDOUT_GENERALIZATION | holdout parses under frozen rules vs independent oracle |

Verdicts allowed: `PASS`, `FAIL`, `INCONCLUSIVE`. Absent structure in
corpus is reported `NOT_OBSERVED` — never faked, never counted as PASS.

## Oracle method (pre-registered)

Holdout oracle: `corpus/oracle/g3_holdout_expected.json`, hand-
annotated from `pdftotext` (Poppler) output — engine independent of
pdfminer. Field-level semantic values only (no x/y positions).
A dedicated test compares parser output vs oracle field by field.

---

## Results (appended after freeze — contract unchanged)

Corpus-wide parse (`corpus/g3_parse_report.json`, `_run2` byte-
identical → G3-C06 PASS):

| split | PARSED | UNSUPPORTED_* | NO_DOC_TOKEN |
|---|---|---|---|
| ps_dev | 44 (25 C8_M1, 19 C2_M1) | 44 no-text, 14 legacy, 5 template | 14 |
| ps_holdout | 12 (6 C8_M1, 6 C2_M1) | 4 no-text, 4 legacy, 3 template | 1 |
| ac_dev | 38 (22 C8_M4, 16 C2_M2) | 17 no-text, 7 legacy | 18 |
| ac_holdout | 10 (1 C8_M4, 9 C2_M2) | 3 no-text, 1 legacy | 0 |

Extraction totals: 5332 PS instrument rows, 2333 chain rows,
56/56 `DECLARED_COMPUTED_MATCH`, 0 unmapped; 4798 AC operations,
96/96 flow-QA `MATCH`, every parsed AC notice mixed A+T.

`NOT_OBSERVED` (declared, never faked): populated §11 loyalty values
(25 C2 docs carry the structure, all empty); concerted-agreement
checkbox checked; `reason_issuer_voting_rights_change` checked;
AC `single-operation`, `acquisition-only` and `disposal-only`
notices — all 48 parsed AC notices are mixed AND multi-operation
(both row types are exercised, but coverage is not generalized to
shapes not observed). In-form annulment block observed ×2 (PS);
`notice_relation` ANNULS links preserved for 15 ps + 30 ac pairs.

Holdout oracle `corpus/oracle/g3_holdout_expected.json` (hand-
annotated from `pdftotext` — Poppler, independent of pdfminer):
**0 field-level mismatches** across all PS + AC holdout notices
(`tests/test_g3_holdout_oracle.py`).

Synthetic invariants: `tests/test_g3_invariants.py` — 15 tests
(position-not-trade, instruments not collapsed, declared never
overwritten, pre/post-2022 semantics, no AC netting, declared-only
trigger, flow ≠ stock, annulment persistence, determinism).

### Gate verdicts

| Gate | Verdict |
|---|---|
| G3-C01..C06 | PASS (G2 suite 27→42 incl. G3 tests, 0 digest diffs) |
| G3-A01..A15 | PASS |
| G3-A16 LOYALTY_SECTION_STRUCTURAL | PASS (structure parsed; populated values NOT_OBSERVED) |
| G3-B01..B13 | PASS |
