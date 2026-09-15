# Changelog

All notable changes to this project. Format follows
[Keep a Changelog](https://keepachangelog.com/) loosely;
versioning is PEP 440 (`0.1.0a1`) tagged as `v0.1.0-alpha.1`.

## [0.1.0-alpha.1] — 2026-09-15

First public pre-release — production-data alpha / developer preview.

### Added

- **CNMV acquisition**: typed runs (BACKFILL / INCREMENTAL /
  RECONCILIATION), immutable raw captures (content-addressed
  `raw_sha256`), append-only `notice_observation` including
  non-destructive `SOURCE_DISAPPEARANCE_OBSERVED`.
- **NOD/MAR parser**: insider transactions with PDMR /
  closely-associated classification, executions, exact decimals,
  amendments, multi-template + legacy generations.
- **Significant holdings + treasury stock**: PS disclosures
  (positions, thresholds, loyalty-vote semantics) and AC treasury
  operation flows vs resulting stock — kept distinct.
- **Bitemporal ledger**: deterministic `source_fact` / `ledger_event`
  derivation, `SOURCE_DECLARED` vs `DETERMINISTIC_DERIVATION`,
  `AS_KNOWN_AT` vs `CURRENT_KNOWLEDGE_RECONSTRUCTED` queries,
  annulment-chain resolution (fail-closed `AMBIGUOUS`).
- **Production dataset**: universe `itf2026-v1`, 60 issuers —
  34,981 notices, 158,083 ledger events, 179,129 feed items.
- **Public Python API**: `OwnershipRadar` — exact issuer resolution,
  explicit `known_at`/`effective_at`, provenance, `Decimal`
  preservation, keyset pagination, `ambiguity` errors. Read-only +
  zero network.
- **CLI**: `ownership-radar` — table/json/jsonl/atom, clean
  stdout/stderr, exit 0/1/2, `schema_version:"1"`.
- **Incremental feed**: `radar.feed()` / `ownership-radar feed` —
  newly-observed items (notices, semantic facts, ANNULS relations,
  disappearances), stable `feed_item_id`, replayable + idempotent,
  versioned query/dataset-bound cursors, BACKFILL excluded by
  default.
- **Demo dataset**: `scripts/build_demo_dataset.py` — deterministic,
  synthetic, ~330 KB, exercises API/CLI/feed with no CNMV raws.

### Known limitations

- Historical completeness not externally proven for all CNMV
  surfaces; universe is 60 issuers (ITF-scope).
- Legacy/scanned documents may be `UNSUPPORTED_TEMPLATE`.
- Three real ANNULS chains are ambiguous (fail closed).
- No person-level identity resolution; no fuzzy matching.
- Free-text annulment-letter extractor deferred (measured marginal).

### Stability note

`0.1.0a1` is alpha: the public API/CLI/feed contract is tested but
breaking changes may still occur before 1.0 — they will be recorded
here.
