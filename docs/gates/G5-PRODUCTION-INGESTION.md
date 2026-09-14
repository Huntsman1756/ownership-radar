# G5 — Production Ingestion & Universe Scale-out — Gate Contract (frozen)

Status: **FROZEN before implementation.** Results are appended, never
used to relax the contract.

G5 proves the acquisition → parse → ledger chain works on the defined
issuer universe (`docs/gates/G5-UNIVERSE.md`), not just on curated
corpora. NOT a public API.

## Fixed design decisions

- **Universe**: AEAT ITF-2026 list (see G5-UNIVERSE.md). `issuer_id` =
  NIF. Tickers are aliases only.
- **Surfaces**: `nod` (global date-window enumeration proven in G5
  recon: `directivos-resultado?fechad&fechah` without nif returns all
  issuers), `ps`, `ac`, `nod_legacy` (enumerate only — pre-2018 docs
  are outside supported semantics).
- **Doc fetch policy**: PDFs are fetched for notices with
  `filing_date >= 2015-12-28` (Circular 8/2015 start) plus all `nod`
  notices (post-2018 by construction). Older notices get
  `doc_status=NOT_FETCHED_LEGACY_ERA` — enumerated, honestly out of
  semantic scope, never claimed parsed.
- **Classification taxonomy** (fail-closed):
  `PARSED | UNSUPPORTED_TEMPLATE | UNSUPPORTED_LEGACY_TEMPLATE |
  UNSUPPORTED_NO_TEXT_LAYER | NO_DOCUMENT_AVAILABLE |
  NOT_FETCHED_LEGACY_ERA | EXTRACTION_ERROR | NOT_PDF`.
  Legacy era is pre-2015-12-28 for ps/ac; nod_legacy docs are
  UNSUPPORTED_LEGACY by supported-scope definition.
- **Run types**: `BACKFILL | INCREMENTAL | RECONCILIATION` recorded on
  `crawl_run.run_type` with `scope` + `universe_version`.
- **Checkpointing**: per `(run_id, scope_key)`; resume skips completed
  scopes; never page-number-only state.
- **Raw storage**: content-addressable `raw_blob` keyed by sha256;
  repeated bytes → new observation, same blob.
- **Disappearance**: `mark_disappearances` is scoped to issuers
  enumerated in the run (G1's global variant would false-positive on
  partial-scope runs).
- **Cancellation split (G5 pre-publication note)**: a notice_relation
  `A ANNULS B` is preserved regardless of whether B was ever observed.
  The ledger keeps emitting `NOTICE_CANCELLED` only when B was
  observed (G4 semantics frozen); the *relation* itself is the
  `CANCELLATION_RELATION_OBSERVED` evidence and is always retained.
  `CANCELLED_NOTICE_RAW_OBSERVED` = the subset where B has a notice
  row. Public API must expose both counts.

## Scout (Stage A) — frozen selection

Deterministic pick from universe v1: `i % 7` over the NIF-sorted
seed ∪ the 5 already-known corpus issuers (overlap check + required
coverage) → **12 issuers**, frozen before any document parse:

```text
idx  issuer_id   name                                   sector profile
  0  A01004324   VIDRALA                                industrial, mid-cap
  7  A08663619   CAIXABANK                              financial, IBEX (corpus)
 14  A28013811   SACYR                                  construction/concessions
 21  A28157360   BANKINTER                              financial, IBEX
 28  A39000013   BANCO SANTANDER                        financial, IBEX (corpus)
 35  A58389123   GRIFOLS                                pharma, dual-class ISINs
 42  A78304516   MELIA HOTELS                           hotels
 49  A85130821   GRENERGY RENOVABLES                    renewables, small-cap
 56  A87586483   AEDAS HOMES                            real estate, recent listing
     A48265169   BBVA                                   financial, IBEX (corpus)
     A78374725   REPSOL                                 energy, IBEX (corpus)
     A28015865   TELEFONICA                             telecom, IBEX (corpus)
```

Scope per issuer: `nod`, `ps_ac`, `nod_legacy` enumeration (full
listing history); documents fetched only where `pipeline.doc_scope`
says supported-era (ps/ac ≥ 2015-12-28, nod always, nod_legacy
never). Failure taxonomy: `PARSED`, `PARSED_WITH_UNMAPPED_VALUES`,
`UNSUPPORTED_TEMPLATE`, `UNSUPPORTED_LEGACY_TEMPLATE`,
`UNSUPPORTED_NO_TEXT_LAYER`, `NO_DOCUMENT_AVAILABLE`, `NOT_PDF`,
`EXTRACTION_ERROR`, `NOT_FETCHED_LEGACY_ERA`. No issuer will be
swapped after seeing its results.

## Scout findings (recorded during Stage A)

1. **CNMV NIF form inconsistency (transport)**: `ps_ac_ini.aspx?nif=`
   resolves an entity by NIF, but the content section silently
   depends on the hyphenated/unhyphenated form *per entity*:
   `A39000013` returns SAN content, `A-28013811` is the only form
   returning SACYR content (unhyphenated resolves the name but shows
   an empty hub). Deterministic zero-content → alternate-form retry
   implemented in `cnmv._alt_nif`; the URL actually used is in every
   observation's `source_url_observed`. Not fuzzy matching — same
   official identifier, two wire representations.

2. **Annulment letters on the `ps` surface**: 3 documents
   (`ps:2024075651` BKT, `ps:2024113958` GRF, `ps:2026069676` MEL)
   are free-form *letters* asking CNMV to annul a previous filing —
   not Modelo 1/2 forms. Correctly classified
   `UNSUPPORTED_TEMPLATE` (fail-closed). They are cancellation
   evidence worth a dedicated extractor in a later phase; for G5
   they stay explicitly unsupported, never silently parsed.

3. **Multi-page annex control chains (parser bug, fixed)**:
   `ps:2026086234` (GRF, Goldman Sachs filing) repeats the
   section-8 column header per annex page → several `_chain_rows`
   segments with colliding `row_index` → `UNIQUE constraint` on
   `ps_control_chain_row`. Fixed by offsetting `row_index` across
   ANNEX segments (`chain_path_index` stays per-table). Objective
   regression fix; G3 tests unchanged and passing.

4. **Scanned holder uploads**: 5 `ps` docs with no text layer
   (BKT/BBVA/GRF/GRE) — expected class
   `UNSUPPORTED_NO_TEXT_LAYER`, not an error.

## Gates

Scout: G5-S01..S07 (selection frozen, issuer identity exact, no new
transport assumptions, unknown templates fail-closed, supported
templates parse exact, ledger materialization exact, no cross-issuer
contamination).

Universe: G5-01..G5-20 (reproducible universe, full enumeration,
registration-identity stability, content-addressable raw,
append-only observations, exact issuer binding, unknown templates
accounted, extraction failures accounted, idempotent incremental,
reconciliation detects changes, backfill vs live distinct,
non-destructive disappearance, cancellation relations preserved,
semantic rebuild without network, identical ledger rebuild,
AS_KNOWN_AT at scale, checkpoint resume exact, stable second-run set,
production invariants, clean-clone tests).

Verdicts: `PASS` / `FAIL` / `INCONCLUSIVE` only.

## Kill criteria

K1 fuzzy issuer matching needed → FAIL.
K2 frequent new templates that can't fail-close → FAIL.
K3 incremental demonstrably loses notices → FAIL.
K4 reconciliation requires deleting/overwriting history → FAIL.
K5 derived dataset not rebuildable offline → FAIL.
K6 ledger non-deterministic at scale → FAIL.
K7 universe not reproducibly definable → FAIL.
