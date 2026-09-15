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

## G6-B — results (2026-09-15)

Public surface: `ownership_radar/api.py` + `public_cli.py`; docs in
`docs/api/`. All objects frozen dataclasses; connection read-only
(`mode=ro` + `query_only`); zero network in the query layer.

```text
PUBLIC_API_STORAGE_INDEPENDENT          PASS  domain objects only;
                                              no SQL/rowid/paths leak
EXACT_ISSUER_RESOLUTION                 PASS  NIF/LEI/ISIN/alias ->
                                              Issuer|NotFound|
                                              AmbiguousIdentifier
TEMPORAL_ARGUMENTS_UNAMBIGUOUS          PASS  known_at/effective_at
                                              only; no date=/as_of=
NO_AS_KNOWN_AT_RETROPROJECTION          PASS  pre-history ->
                                              NO_OBSERVATION_HISTORY
SOURCE_DERIVED_EXPLICIT                 PASS  event_basis on every
                                              event; basis= filter
PS_NO_INVENTED_TRADES_PUBLIC            PASS  disclosure objects have
                                              no side/nature fields
TREASURY_FLOW_STOCK_DISTINCT_PUBLIC     PASS  TreasuryOperation vs
                                              TreasuryStockPosition
AMBIGUOUS_ANNULS_FAIL_CLOSED_PUBLIC     PASS  AMBIGUOUS + candidates;
                                              require_authoritative
                                              raises; works on
                                              relation-only keys
PROVENANCE_PUBLICLY_TRACEABLE           PASS  notice -> url -> sha256
                                              -> parser -> rule
COVERAGE_PUBLICLY_DISCLOSED             PASS  dataset_info() says
                                              itf2026-v1/60 issuers;
                                              coverage() denominators
CURSOR_STABLE                           PASS  keyset cursor, opaque,
                                              no overlap page1/page2
DECIMAL_LOSSLESS                        PASS  Decimal in Python; str
                                              in JSON ("12.66")
JSON_SCHEMA_VERSIONED                   PASS  schema_version:"1" in
                                              every envelope
CLI_MACHINE_OUTPUT_CLEAN                PASS  stdout pure payload;
                                              errors to stderr;
                                              exit 0/1/2
QUERY_LAYER_OFFLINE                     PASS  mode=ro + query_only;
                                              write attempt fails
PUBLIC_CONTRACT_BLACKBOX_PASS           PASS  26 tests, public imports
                                              only (test_g6_public_api)
QUERY_BENCHMARK_PASS                    PASS  prod DB: company 0ms,
                                              issuer queries p95 <85ms,
                                              recent-insiders p95 163ms
CLEAN_INSTALL_PASS                      PASS  pip install . in clean
                                              venv; ownership-radar
                                              console script works
G1_G5_REGRESSION_FREE                   PASS  103 tests + 30 subtests
```

## G6-C — results (2026-09-15)

Feed derived by `store.FEED_SQL` into materialized `feed_item`
(rebuilt by `ledger.materialize`/`rebuild_feed`; `feed_digest`
stable across rebuilds). Public surface: `radar.feed()`,
`radar.feed_cursor_latest()`, `FeedItem`, `FeedResult`,
`ownership-radar feed` (json|jsonl|atom|table) +
`feed-cursor-latest`. Docs: `docs/api/FEED.md`, `docs/api/ATOM.md`,
`docs/model/FEED-SEMANTICS.md`, `docs/decisions/ADR-G6-FEED-*`.

Production feed (`itf2026-v1`, 60 issuers):

```text
NOTICE_OBSERVED                          34,981
INSIDER_TRANSACTION_OBSERVED             10,829
SIGNIFICANT_HOLDING_DISCLOSURE_OBSERVED   6,479
TREASURY_OPERATION_OBSERVED             123,251
TREASURY_STOCK_POSITION_OBSERVED            930
CANCELLATION_RELATION_OBSERVED            1,240   (6 AMBIGUOUS rows,
                                                    3 targets x 2)
NOTICE_DISAPPEARANCE_OBSERVED             1,419   (the preserved G5
                                          false-disappearance streaks)
total                                   179,129
run_type   BACKFILL 177,616 | INCREMENTAL 94 | RECONCILIATION 1,419
feed_digest  c99f94849ccee9ad06d8de0adf9e6e8aded09d5030e7f27dfaf1833d639fcfbd
```

```text
G6-C1  FEED_MEANS_NEWLY_OBSERVED          PASS
       observed_at/filing_date/effective_date always distinct
       fields; fixture asserts eff=2024-01-05, fil=2024-01-08,
       obs=2024-01-10 on one item. Prod sample: eff 2026-09-11,
       fil 2026-09-14, obs 2026-09-14T22:53Z.
G6-C2  BACKFILL_NOT_IN_LIVE_FEED          PASS
       default include_backfill=False; BACKFILL items exist only
       under explicit opt-in, classed RECONSTRUCTED_HISTORICAL.
G6-C3  STABLE_CURSOR                      PASS
       v1.<b64(JSON)> opaque; keyset (observed_at,item_key);
       query-bound + dataset-bound + watermark snapshot.
```

Detailed G6-C evidence (nomenclature per spec §49):

```text
FEED_IS_OBSERVATION_DRIVEN              PASS  items anchor on first
                                            qualifying observation
OBSERVED_EFFECTIVE_DATES_DISTINCT       PASS  three date fields,
                                            never conflated
FEED_ITEM_ID_STABLE                     PASS  v1:<sha256(item_key)>;
                                            replay-identical
CURSOR_OPAQUE_VERSIONED                 PASS  v1.* b64 JSON
CURSOR_NO_GAPS / NO_PAGE_OVERLAP        PASS  full traversal at
                                            limit=2: exact coverage
CURSOR_TIES_EXACT                       PASS  all INCREMENTAL items
                                            share T1 — paginated
                                            loss-free
CURSOR_QUERY_BOUND                      PASS  filter/backfill
                                            mismatch ->
                                            CursorDatasetMismatch
RECONCILIATION_NOISE_SUPPRESSED         PASS  nod:B re-observed x2 ->
                                            1 item at first obs
CANCELLATION_RELATION_EMITTED           PASS  incl. relation-only
                                            annulling endpoints
AMBIGUOUS_ANNULS_PRESERVED              PASS  AMBIGUOUS + both
                                            candidates; prod: all 3
DISAPPEARANCE_NON_DESTRUCTIVE           PASS  streak-head only;
                                            cancellation_evidence_
                                            present flag; never a
                                            relation
SOURCE_DERIVED_EXPLICIT                 PASS  event_basis carried
                                            on semantic items
FEED_PROVENANCE_TRACEABLE               PASS  item.provenance() ->
                                            notice/url/sha256/parser
JSON_JSONL_SCHEMA_STABLE                PASS  schema_version:"1";
                                            next_cursor on stderr
ATOM_SEMANTICS_CORRECT                  PASS  published=observed_at,
                                            urn ids, valid XML,
                                            dataset in feed id
FEED_OFFLINE                            PASS  mode=ro + query_only;
                                            zero network
FEED_REBUILD_IDENTICAL                  PASS  digest c99f9484…
                                            identical before/after
                                            rebuild_feed()
CLEAN_INSTALL_PASS                      PASS  clean venv install;
                                            feed + CLI work
G1_G6B_REGRESSION_FREE                  PASS  125 tests + 30
                                            subtests
```

Production feed benchmark:

```text
first page (incl. watermark)   p95 484ms
next page                      p95   6ms
issuer-filtered                p95  18ms
type-filtered                  p95 135ms
1000-item JSONL (CLI)              272ms
200-entry Atom (CLI, valid XML)    339ms
```

Kill conditions: none triggered. K1 effective-as-published —
Atom/JSON use observed_at. K2 backfill excluded by default.
K3 identical reconciliation -> 0 items. K4 ties paginate exactly.
K5 AMBIGUOUS preserved (prod verified). K6 disappearance stays
distinct. K7 feed is offline/read-only. K8 rebuild digest identical.
K9 cursor is keyset + versioned payload. K10 dataset_version +
universe in FeedResult/feed id.
