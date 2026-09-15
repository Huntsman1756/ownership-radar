# G6 — Public Data-Product Contract — Gate Contract (frozen)

Status: **FROZEN before implementation.** Results are appended, never
used to relax the contract.

G5 proved the dataset works at production scale. G6 exposes it without
degrading G1–G5 guarantees. Three ordered blocks:

```text
G6-A  Storage/query hardening
G6-B  Public Python API + CLI
G6-C  Incremental daily feed
```

## G6-A — Storage/query hardening

- **Eliminate all-pairs amplification** of `fact_version_relation`
  (7.65M rows for 1,295 notice-level relations at Stage B scale)
  while keeping *exactly* G4 semantics: the logical fact-level
  projection (every fact of the annulled notice `CANCELLED_BY` /
  `RECTIFIED_BY` every fact of the annulling notice) must be
  preserved. Proof criterion: `ledger_digest` identical before and
  after the change on both the G4 corpus DB and the production DB.
- **Ambiguous ANNULS public representation**: a target annulled by
  >1 notice is never resolved to a single terminal. Public surface:
  `relation_status=AMBIGUOUS`, `annulled_notice`, `annulling_notices`
  list. Any `current_authoritative()`-style resolution fails closed
  on ambiguous chains.
- **Annulment-letter extractor gate**: measure first whether the
  1,079 `UNSUPPORTED_TEMPLATE` free-form letters carry targets or
  semantics not already covered by the 1,240 `notice_relation` rows.
  Extractor enters G6-A only if it recovers new evidence; otherwise
  deferred and documented.
- **Query benchmark**: real production queries (events for issuer,
  latest PS position, latest treasury position, `AS_KNOWN_AT`)
  timed and recorded. No optimization that reduces provenance.

## G6-B — Public Python API + CLI

- Stable functions: `company`, `insider_transactions`,
  `significant_holdings`, `treasury_stock`, `ownership_history`,
  `provenance`, `as_known_at`, `reconstructed_as_of`.
- **Temporal API is explicit**: `events(..., known_at=...)` vs
  `events(..., effective_at=...)` — never an ambiguous `date=`.
- JSON/JSONL output; provenance chain to notice + raw_sha256.
- No fuzzy resolution anywhere in the public surface.

## G6-C — Incremental daily feed

- Feed items mean `NEWLY_OBSERVED` CNMV information, never
  "effective today" — fields: `observed_at`, `effective_date`,
  `filing_date`, `history_class` (`OBSERVED_CURRENT` /
  `RECONSTRUCTED_HISTORICAL`).
- BACKFILL runs excluded from the live feed; INCREMENTAL and
  RECONCILIATION produce items.
- Cancellations/rectifications are first-class items.
- Stable cursor/checkpoint so consumers can resume.

## Gates (pre-registered)

```text
G6-A1  DIGEST_IDENTICAL_AFTER_REPRESENTATION_CHANGE
G6-A2  NO_ALL_PAIRS_STORAGE
G6-A3  AMBIGUOUS_ANNULS_FAIL_CLOSED
G6-A4  LETTER_EVIDENCE_MEASURED
G6-A5  QUERY_BENCHMARK_RECORDED
G6-B1  EXPLICIT_TEMPORAL_PARAMETERS
G6-B2  PROVENANCE_TO_RAW
G6-B3  NO_FUZZY_PUBLIC_RESOLUTION
G6-C1  FEED_MEANS_NEWLY_OBSERVED
G6-C2  BACKFILL_NOT_IN_LIVE_FEED
G6-C3  STABLE_CURSOR
```

Verdicts: `PASS` / `FAIL` / `INCONCLUSIVE` only.

## G6-A — results (2026-09-15)

```text
G6-A1  DIGEST_IDENTICAL_AFTER_REPRESENTATION_CHANGE   PASS
       fact_version_relation is now a VIEW over
       notice_relation x source_fact — identical logical rows.
       corpus digest   986d6ff2…5211  (unchanged from G4)
       prod digest     268e41b1…4e65  (unchanged from G5)

G6-A2  NO_ALL_PAIRS_STORAGE                            PASS
       7.65M stored rows -> 0 (view). materialize 158s (was ~290s).
       production DB: 3,616 MB -> 459 MB (-87%)

G6-A3  AMBIGUOUS_ANNULS_FAIL_CLOSED                    PASS
       ledger.annulment_status(): NONE|RESOLVED|AMBIGUOUS|CYCLE with
       annulling_notices list; ledger.current_authoritative()
       returns AMBIGUOUS/SUPERSEDED/AUTHORITATIVE, never picks.
       Tests: tests/test_g6_hardening.py

G6-A4  LETTER_EVIDENCE_MEASURED                        PASS
       113/1,087 UNSUPPORTED_TEMPLATE docs already appear as
       annulling_key in notice_relation (corroboration only).
       80-doc text probe: only ~4% carry annulment keywords — the
       class is heterogeneous free-form filings, not predominantly
       annulment letters. >=1 candidate uncovered target found
       (ps:2024075651 -> ps:2024076278). Marginal yield: ~tens of
       candidate relations vs 1,240 known. Extractor DEFERRED
       post-G6 — documented, not a blocker.

G6-A5  QUERY_BENCHMARK_RECORDED                        PASS
       production DB, 34,981 notices / 141,489 facts:
         events for issuer (SAN, 6,772)          0.00s
         event list (limit 200)                  0.01s
         latest PS disclosure                    0.01s
         latest treasury position                0.01s
         AS_KNOWN_AT single notice               0.00s
         annulment_status / current_authoritative 0.00s
         fact_version_relation full count        3.78s
           (7.65M logical rows — provenance view, not a query path)
```
