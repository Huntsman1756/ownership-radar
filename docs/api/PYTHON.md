# Public Python API — Ownership Radar ES

Stable contract: only names exported by `ownership_radar/__init__.py`.
Internals (`store`, `ledger`, `pipeline`, `cnmv`, `ingest`, `poller`,
`coverage`, `universe`) may change without notice.

```python
from ownership_radar import OwnershipRadar

radar = OwnershipRadar.open("ownership-radar.sqlite")   # read-only
issuer = radar.company("SAN")
```

The connection is SQLite read-only (`mode=ro` + `query_only`). The API
performs **zero network requests** — ingestion is a separate admin
surface.

## Resolution

`radar.company(identifier)` resolves **exactly** one of:
`issuer_id`/NIF, LEI, ISIN, or a registered ticker alias.
Ticker is an alias, never identity.

```text
exact match       -> Issuer
no match          -> NotFound
>1 distinct hits  -> AmbiguousIdentifier
```

## Public surface

```text
OwnershipRadar.open(path)
radar.company(ident)                    -> Issuer
radar.notice(notice_key)                -> Notice | NotFound
radar.notices(issuer=, surface=, known_at=, limit=, cursor=)
radar.events(issuer=, known_at=, effective_at=, basis=, limit=, cursor=)
radar.insider_transactions(issuer=, known_at=, effective_at=,
                           include_cancelled=, limit=, cursor=)
radar.recent_insider_transactions(...)  (all issuers)
radar.significant_holdings(issuer=, ...)
radar.treasury_stock_positions(issuer=, ...)
radar.treasury_operations(issuer=, ...)
radar.annulment_status(notice_key)      -> AnnulmentStatus
radar.current_authoritative(notice_key) -> AuthoritativeResult
radar.require_authoritative(notice_key) -> AuthoritativeResult
                                         | AmbiguousAnnulment
radar.dataset_info()                    -> DatasetInfo
radar.coverage()                        -> explicit denominators
radar.feed(cursor=, limit=, issuer=, item_type=,
           include_backfill=)           -> FeedResult
radar.feed_cursor_latest()              -> opaque "from now" cursor
```

`Issuer` mirrors the per-issuer query methods
(`issuer.insider_transactions()`, `issuer.significant_holdings()`,
`issuer.treasury_stock_positions()`, `issuer.treasury_operations()`,
`issuer.notices()`, `issuer.events()`).

Everywhere `issuer=` is accepted it takes an `Issuer` or any
identifier string resolved by the same exact rules as `company()`
— consistently across `notices`, `events`, `insider_transactions`,
`significant_holdings`, `treasury_stock_positions`,
`treasury_operations` and `feed`. A string that matches no universe
entry but is already an `issuer_id` in the dataset is accepted
verbatim; anything else raises `NotFound`.

## Domain objects

All frozen dataclasses; read-only.

- `InsiderTransaction` — declared NOD transactions (MAR/PDMR).
  No "current insider holdings" is ever computed.
- `SignificantHoldingDisclosure` — position disclosures, **never**
  trades. No BUY/SELL labels derived from percentage deltas.
- `TreasuryOperation` — section-4 operation **flow**.
- `TreasuryStockPosition` — section-5 resulting **stock**.
  Flow and stock are separate object types and separate queries.
- `LedgerEvent` — `event_basis` is always `SOURCE_DECLARED` or
  `DETERMINISTIC_DERIVATION` (filter: `basis=`).
- `Notice` — registry identity, surface, template, doc/parse status,
  `annulment_status()`, `current_authoritative()`,
  `require_authoritative()`, `provenance()`.
- `QueryResult` — `status`, `history_mode`, `known_at`,
  `effective_at`, `items`, `count`, `has_more`, `next_cursor`,
  `dataset_version`.
- `FeedItem` — one newly-observed unit: `feed_item_id` (stable
  `v1:<sha256>`), `feed_item_type`, `observed_at`, `run_type`,
  `history_class`, `effective_date`, `filing_date`, `event_basis`,
  `annulment_status`, `summary`, `provenance()`.
- `FeedResult` — `items`, `count`, `has_more`, `next_cursor`,
  `watermark`, `dataset_version`. The feed is replayable +
  idempotent, not exactly-once — see `FEED.md`.

## Temporal semantics

Two explicit axes — there is no `date=` anywhere:

- `known_at=` — knowledge time: only observations
  `first_observed_at <= known_at` are visible (AS_KNOWN_AT).
  Earlier than the first observation: empty result with
  `status == NO_OBSERVATION_HISTORY`. Never retro-projected.
- `effective_at=` — economic time: `effective_date <= effective_at`,
  evaluated with the knowledge the query allows.

Defaults: `known_at` = latest knowledge, `effective_at` = unbounded
("everything currently known"). See `TEMPORAL-QUERIES.md`.

## Annulment contract

`annulment_status()` returns `NONE | RESOLVED | AMBIGUOUS | CYCLE`
plus `annulling_notices` and `terminal`. AMBIGUOUS lists every
candidate and is never resolved to one. `require_authoritative()`
raises `AmbiguousAnnulment` on AMBIGUOUS/CYCLE;
`current_authoritative()` returns the status object instead.

`AnnulmentStatus` also carries the evidence split:
`cancellation_relation_observed` (an observed `A ANNULS B` relation
exists) vs `cancelled_notice_raw_observed` (B itself was observed).
They are never collapsed into `cancelled=True`.

## Pagination

`limit` + opaque `cursor` (keyset on the declared ordering).
Ordering is declared per method — never SQLite row order.
`QueryResult.next_cursor` is stable and deterministic for the same
query parameters. `limit` must be a positive integer.

Query cursors are versioned envelopes (`q2.<…>`) bound to the
issuing query — method, resolved issuer, and every filter — and to
the dataset version. A cursor reused against a different method,
filters or dataset raises `CursorDatasetMismatch`; a wrong-version
cursor raises `UnsupportedCursorVersion`; anything malformed raises
`InvalidCursor`. Bare unversioned cursors produced by `0.1.0a1` are
deliberately rejected (`InvalidCursor`) — their keys were computed
against the wrong ordering and could skip records. Feed cursors
(`v1.<…>`) are a separate, unchanged contract — see `FEED.md`.

`OwnershipRadar.open(path)` raises `OwnershipRadarError` if the
dataset file cannot be opened (missing path, unreadable file).

## Types

Money/percentages/volumes: `Decimal` (never float).
Dates: `datetime.date`. Observed instants: timezone-aware `datetime`
(UTC). JSON (CLI): decimals serialize as strings, dates as ISO-8601 —
lossless.

## Errors

`OwnershipRadarError` base + `NotFound`, `AmbiguousIdentifier`,
`InvalidTemporalQuery`, `UnsupportedQuery`, `AmbiguousAnnulment`,
`DataIntegrityError`, `InvalidCursor`, `UnsupportedCursorVersion`,
`CursorDatasetMismatch`. No raw sqlite3 exceptions escape the
contract.

## Scope honesty

`radar.dataset_info()` reports `universe_version` (currently
`itf2026-v1`, 60 issuers — ITF-scope, not "all Spanish issuers"),
parser/derivation versions, counts and the ledger digest.
`radar.coverage()` exposes acquisition / document / template-support /
semantic-parse / ledger denominators separately.
