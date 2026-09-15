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

## Stage B + incremental — results (2026-09-15)

Runs (all `OK`): `scout-a-2026`, `scout-a-sacyr-fix`,
`stage-b-2026` (BACKFILL, 10h03m, 24,503 requests),
`incremental-20260914T225326Z` (INCREMENTAL, 10-day NOD window),
`recon-scout-2026` + `recon-legacy-fix` (RECONCILIATION).

```text
notices enumerated            34,981   (ac 2,066 · nod 8,617 ·
                                        nod_legacy 2,149 · ps 22,149)
observations                  69,074   (append-only, incl. 1,419
                                        historical false-positive
                                        disappearances — kept, latest=0)
raw blobs                     29,829 unique sha256 / 4.66 GB
notice_doc rows               34,981   (no gap; nod_legacy classified
                                        NOT_FETCHED_LEGACY_ERA)
failed_items                  0
discovered_issuers            6        (non-universe NIFs from global
                                        NOD window — candidates only)
```

Document status (every notice has a row):

```text
PARSED                        15,670
PARSED_WITH_UNMAPPED_VALUES      534
UNSUPPORTED_NO_TEXT_LAYER      1,943   (scanned holder uploads)
UNSUPPORTED_TEMPLATE           1,087   (1,079 ps + 8 ac; dominated by
                                        free-form annulment letters —
                                        scout finding 2, fail-closed)
UNSUPPORTED_LEGACY_TEMPLATE    1,690
NOT_FETCHED_LEGACY_ERA        14,056
NOT_PDF                            1   (nod:2023020749 — CNMV returns
                                        empty body for this token;
                                        retried, still empty →
                                        permanent source anomaly)
EXTRACTION_ERROR                   0   (both retried from local blobs
                                        → PARSED; offline reparse
                                        works, §32)
```

Ledger materialized (production DB, 3.6 GB):

```text
source_fact    141,489   (TREASURY_OPERATION 123,251 ·
                          NOD_TRANSACTION_EVENT 10,829 ·
                          SIGNIFICANT_HOLDING_DISCLOSURE 6,479 ·
                          TREASURY_RESULTING_POSITION 930)
ledger_event   158,083   (SOURCE_DECLARED 16,594 · derived 141,489)
relations        1,295   (ANNULS 1,240 · RECTIFIES 55)
  cancellation_relations_observed  1,240
  cancelled_notice_raw_observed      362   (§22 split surfaced)
digest        268e41b1e603701e5f5efe4341d6e7c29944418461fe6a980fcdd75da8934e65
              identical across repeated materialize() — G5-15
```

### Scale findings beyond the scout

5. **Surface-scoped disappearance (bug, fixed)**: `recon-scout-2026`
   enumerated `nod`/`ps_ac` only; `mark_disappearances` was
   issuer-scoped but not surface-scoped → 1,419 `nod_legacy` notices
   falsely marked `SOURCE_DISAPPEARANCE_OBSERVED`. Fixed by scoping
   disappearances to the surfaces actually enumerated
   (`FAMILY_SURFACES` in `ingest.py`); regression test added. The
   1,419 historical observations remain append-only evidence; a
   corrective `recon-legacy-fix` re-enumerated `nod_legacy` →
   latest-state disappearances: **0**.

6. **Multiple annulling notices (real CNMV ambiguity)**: 3 `ps`
   targets (`ps:2015140636`, `ps:2014053922`, `ps:2018020031`) are
   annulled by two distinct notices each (batch-annulment pattern).
   `resolve_annulment_chains` fails closed (`multiple_annulling_
   notices`) — relations preserved, no winner picked. Reported as
   `graph_anomalies`/`ambiguous_annulment_targets`, not corruption.

7. **fact_version_relation all-pairs amplification**: G4's
   fact-level `CANCELLED_BY`/`RECTIFIED_BY` expansion is all-pairs
   between the two notices' facts. On large treasury annexes this
   produced 7.65M rows — semantically frozen G4 behaviour, honest
   but heavy. Notice-level `notice_relation` remains the primary
   evidence; flag for a G6 revisit (relation-at-notice-level may
   suffice publicly).

8. **Scale performance note**: with no index on
   `notice_observation(notice_key)` the first materialize did not
   complete in reasonable time (per-fact `MIN(observed_at)` scans).
   Added covering indexes (`ix_obs_notice` et al.) — forward-only
   migration, semantics unchanged; materialize ≈ 200–290 s.

9. **Incremental poll**: 16 new notices (filed during backfill),
   8 issuers re-enumerated from last-5-days hints, 5 new discovered
   NIFs, 0 duplicates. Second-run set stable: scout keys ⊂ stage-b
   keys, no missing, no dupes.

## Gates

Scout: G5-S01..S07 — all PASS (selection frozen pre-parse; NIF exact;
only the deterministic NIF-form retry added, §1; unknowns fail-closed;
supported templates parse; ledger exact; no cross-issuer rows).

Universe gates:

```text
G5-01 UNIVERSE_DEFINITION_REPRODUCIBLE     PASS  itf2026-v1 + sha256
G5-02 FULL_ENUMERATION_COMPLETES           PASS  60/60, 0 failed_items
G5-03 REGISTRATION_IDENTITY_STABLE         PASS  34,981 unique keys
G5-04 RAW_CONTENT_ADDRESSABLE              PASS  29,829 blobs dedup
G5-05 SOURCE_OBSERVATIONS_APPEND_ONLY      PASS  69,074, never deleted
G5-06 ISSUER_BINDING_EXACT                 PASS  NIF-only; no fuzzy
G5-07 UNKNOWN_TEMPLATE_ACCOUNTED           PASS  1,087 classified
G5-08 EXTRACTION_FAILURES_ACCOUNTED        PASS  2→0 after offline retry
G5-09 INCREMENTAL_DISCOVERY_IDEMPOTENT     PASS  dedupe by notice_key
G5-10 PERIODIC_RECONCILIATION_DETECTS      PASS  scoped by family
G5-11 BACKFILL_VS_LIVE_DISTINCT            PASS  run_type recorded
G5-12 DISAPPEARANCE_NON_DESTRUCTIVE        PASS  observe-only, scoped
G5-13 CANCELLATION_RELATIONS_PRESERVED     PASS  1,240 + 3 ambiguous
G5-14 SEMANTIC_REBUILD_WITHOUT_NETWORK     PASS  blob→parse retries OK
G5-15 LEDGER_REBUILD_IDENTICAL             PASS  digest 268e41b1…
G5-16 AS_KNOWN_AT_NO_RETROPROJECTION       PASS  real ACTIVE→CANCELLED
G5-17 CHECKPOINT_RESUME_EXACT              PASS  (run resumed across
                                                sessions during Stage B)
G5-18 SECOND_RUN_SET_STABLE                PASS  scout ⊂ stage-b, 0 gap
G5-19 PRODUCTION_INVARIANTS_PASS           PASS  0 violations; 3
                                                ambiguous ANNULS accounted
G5-20 CLEAN_CLONE_TESTS_PASS               PASS  72 + 30 subtests
```

## Kill criteria

K1–K7: none triggered. No fuzzy matching anywhere; all unknowns
fail-closed; incremental lost nothing; history never rewritten;
offline rebuild proven; digest deterministic; universe reproducible.

## Verdict

```text
G5 PASS
```

Recommendation: `PROCEED TO G6 PUBLIC PYTHON API / CLI / DAILY FEED`.
Known follow-ups for G6 scope decisions: fact_version_relation
amplification (finding 7), dedicated extractor for free-form
annulment letters (1,079 docs), 3 ambiguous ANNULS targets.

## Kill criteria (contract, pre-registered)

K1 fuzzy issuer matching needed → FAIL.
K2 frequent new templates that can't fail-close → FAIL.
K3 incremental demonstrably loses notices → FAIL.
K4 reconciliation requires deleting/overwriting history → FAIL.
K5 derived dataset not rebuildable offline → FAIL.
K6 ledger non-deterministic at scale → FAIL.
K7 universe not reproducibly definable → FAIL.
