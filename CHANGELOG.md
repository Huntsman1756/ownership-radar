# Changelog

All notable changes to this project. Format follows
[Keep a Changelog](https://keepachangelog.com/) loosely. Python package
versions use PEP 440 (for example `0.1.0a2`) and Git release tags use
the corresponding prerelease form (`v0.1.0-alpha.2`).

## [Unreleased]

### Changed

- Public-repository hardening: standard MIT license text for SPDX/GitHub
  detection, normalized line-ending policy, editor defaults, weekly
  Dependabot updates, CodeQL scanning, least-privilege/concurrent CI,
  package validation with `twine check`, SHA-pinned GitHub Actions,
  and explicit `CODEOWNERS` review ownership.
- Public docs refreshed to the current `v0.1.0-alpha.2` release and the
  actual installation paths; PyPI is not advertised until it is
  published.
- Security/conduct reporting language no longer implies that sensitive
  reports filed in public issues are confidential.

## [0.1.0-alpha.2] — 2026-09-17

### Fixed

- **Pagination (data loss while paging)**: `significant_holdings`,
  `treasury_stock_positions` and `treasury_operations` emitted
  cursors that did not match their declared ordering — rows were
  silently skipped when a page boundary landed mid-tie
  (`treasury_operations` dropped operation rows sharing
  `(operation_date, notice_key)`; the holdings/positions methods
  dropped rows with a different sort field). Cursors now carry the
  full composite key.
- **Cursor robustness**: malformed, truncated or wrong-shape cursors
  now raise `InvalidTemporalQuery`/`InvalidCursor` consistently —
  previously some inputs escaped as `IndexError` or silently
  returned empty results. `limit` is validated (`>=1`); `limit=0`
  could previously loop a feed consumer forever.
- **`issuer=` consistency**: all query methods resolve identifier
  strings exactly like `company()` (previously only `feed()` did;
  other methods treated strings as literal issuer_ids, so
  `issuer="SAN"` returned nothing).
- **`OwnershipRadar.open`**: missing/unopenable datasets now raise
  `OwnershipRadarError` instead of a raw `sqlite3.OperationalError`;
  paths with spaces/`%` are handled via proper file-URI encoding.
- **Ingestion**: `scan_docs(retry_statuses=...)` no longer bypasses
  the `issuer_ids`/`filing_since`/`surfaces` scope (unparenthesized
  `OR`); a transient fetch failure records `EXTRACTION_ERROR`
  (retryable) instead of the permanent verdict `NOT_PDF`;
  `ingest.start_run` / `cli.run` use named-column inserts compatible
  with the migrated `crawl_run` schema.
- **Crawler**: no longer sleeps after the final retry; response
  bodies are capped at 256 MB.
- `store.init_db("name.sqlite")` works with bare filenames.
- `python -m ownership_radar ingest report|invariants` exits with an
  error instead of silently creating an empty database when the
  dataset path does not exist, and no longer writes the universe
  seed into the dataset being inspected (read commands are now
  read-only).
- `ingest`/`crawl` data directories are cwd-relative (`data/...`,
  overridable via `RADAR_PROD_DIR`/`RADAR_DATA_DIR`) instead of
  resolving inside site-packages when running from an installed
  package.
- `scripts/build_universe.py` writes the seed path the loader
  actually reads; `scripts/parse_g2_corpus.py` reads the manifest
  as UTF-8 (was crashing on Windows code pages).
- `ownership-radar feed` no longer crashes in the default table
  format (`FeedResult` has no `history_mode`).

### Changed

- **Query cursors are now versioned and bound.** `QueryResult`
  cursors are `q2.<…>` envelopes carrying the full composite key, a
  signature of the issuing query (method + resolved issuer +
  filters) and the dataset version. Cross-method, cross-filter or
  cross-dataset reuse raises `CursorDatasetMismatch`; malformed or
  legacy cursors raise `InvalidCursor`/`UnsupportedCursorVersion`.
  **Query cursors produced by `0.1.0a1` are intentionally
  invalidated** — their pagination keys were incorrect and could
  skip records. Feed cursors (`v1.`) and `feed_item_id` (`v1:`)
  are unchanged.
- `universe/itf2026-v1.json` moved to `ownership_radar/seeds/` and
  is now shipped inside the wheel — `ingest` works from an
  installed package, not only from a checkout.
- `python -m ownership_radar crawl` runs the internal G1 crawl
  explicitly (previously unreachable dead code).
- Packaging metadata: authors, keywords, classifiers, project URLs,
  `[dev]` extra (`pytest`, pinned `ruff`, `build`).
- CI now runs `ruff check` (pyflakes correctness rules) on every
  Python version.

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
