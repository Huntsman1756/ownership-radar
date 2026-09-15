# FEED — Incremental daily feed (G6-C)

The feed exposes **new information observed by Ownership Radar ES**,
ordered on the observation axis. It never means "events whose
economic date is today".

```text
observed_at     when Ownership Radar learned the information
filing_date     when the notice was filed at CNMV
effective_date  the economic/regulatory date the fact declares
```

These three axes are always kept distinct:

```text
transaction_date = 2024-03-10   (effective_date)
filing_date      = 2024-03-13
observed_at      = 2026-09-15   (backfill) → RECONSTRUCTED_HISTORICAL
```

A backfilled item discovered today is **not** a 2026 event.

## Python API

```python
from ownership_radar import OwnershipRadar

radar = OwnershipRadar.open("ownership-radar.sqlite")

res = radar.feed(limit=100)                    # live feed (default)
res = radar.feed(include_backfill=True)        # + reconstructed items
res = radar.feed(issuer="SAN")                 # issuer filter
res = radar.feed(item_type="NOTICE_OBSERVED")  # type filter

cur = res.next_cursor                          # opaque, versioned
res = radar.feed(cursor=cur, limit=100)        # next page

cur = radar.feed_cursor_latest()               # "from now"
res = radar.feed(cursor=cur)
```

`cursor=None` is frozen contract: **the beginning of the selected
feed**. New subscriptions should use `feed_cursor_latest()`.

## FeedItem

```text
feed_item_id        v1:<sha256> — stable, deterministic
feed_item_type      see taxonomy below
observed_at         first qualifying observation instant
run_id / run_type   BACKFILL | INCREMENTAL | RECONCILIATION
history_class       OBSERVED_CURRENT | RECONSTRUCTED_HISTORICAL
issuer_id           NIF-based issuer identity
notice_key          canonical notice key
event_id            ledger event (semantic items only)
annulling_notice_key / annulled_notice_key / relation_type
effective_date      declared economic date (never = observed_at)
filing_date         CNMV filing date
event_basis         SOURCE_DECLARED | DETERMINISTIC_DERIVATION
annulment_status    for relation items: NONE|RESOLVED|AMBIGUOUS|CYCLE
summary             minimal typed payload
```

`FeedItem.provenance()` resolves to the full chain (source URL,
raw_sha256, parser, derivation rule).

## FeedResult

```text
status            OK
items             tuple[FeedItem]
count / has_more
next_cursor       opaque v1 cursor (None on last page)
watermark         snapshot bound of this traversal
dataset_version   dataset generation the cursor is bound to
schema_version    "1"
```

## Item types

```text
NOTICE_OBSERVED                         the notice first observed
INSIDER_TRANSACTION_OBSERVED            NOD transaction fact
SIGNIFICANT_HOLDING_DISCLOSURE_OBSERVED PS disclosure fact
TREASURY_OPERATION_OBSERVED             AC operation flow
TREASURY_STOCK_POSITION_OBSERVED        AC resulting position
CANCELLATION_RELATION_OBSERVED          A ANNULS B first observed
NOTICE_DISAPPEARANCE_OBSERVED           disappearance streak start
```

One notice legitimately yields `NOTICE_OBSERVED` + N semantic items —
this is declared, not duplication. The same information re-observed
(re-poll, identical reconciliation, re-materialization) yields
**nothing**: the unit is the *first qualifying observation*.

## history_class

```text
BACKFILL                          → RECONSTRUCTED_HISTORICAL
INCREMENTAL / RECONCILIATION      → OBSERVED_CURRENT
```

`OBSERVED_CURRENT` means "newly observed via a live run" — it does
**not** assert `effective_date ≈ observed_at`.

## Backfill exclusion

Default `include_backfill=False` filters `run_type='BACKFILL'`.
Backfilled facts exist in the dataset and appear when explicitly
requested — they are never silently mixed into the live feed.

## Cancellation items

`CANCELLATION_RELATION_OBSERVED` emits when `A ANNULS B` is first
observed, even when B has no notice row (relation-only evidence).
`summary` carries `annulment_status`, `annulling_notices` and
`cancelled_notice_raw_observed`. Ambiguous targets keep
`AMBIGUOUS` with all candidates — never resolved arbitrarily.

## Disappearance items

Emitted only from explicit `SOURCE_DISAPPEARANCE_OBSERVED`
observations, at the start of each disappearance streak. Re-observed
absence produces nothing. `summary.cancellation_evidence_present`
states whether any ANNULS evidence exists — a disappearance is never
converted into a cancellation without explicit relation evidence.

## Reconciliation noise

A reconciliation observing identical state produces **zero** feed
items even though it appends `notice_observation` rows internally.
`new observation row ≠ new public information`.

## Delivery contract

**Replayable + idempotent — not "exactly once".** Re-reading a cursor
range returns the same logical items with the same `feed_item_id`;
consumers deduplicate on it. See ADR-G6-FEED-IDENTITY and
ADR-G6-FEED-CURSOR.
