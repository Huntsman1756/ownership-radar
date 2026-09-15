# ADR-G6-FEED-IDENTITY — stable feed item identity

Status: accepted (G6-C)

## Decision

```text
feed_item_id = "v1:" + sha256("feed/v1|" + item_key)[:32]
```

where `item_key` is the canonical per-type identity derived in
`store.FEED_SQL`:

```text
NOTICE_OBSERVED                         NOTICE:<notice_key>
INSIDER_TRANSACTION_OBSERVED            FACT:<fact_id>
SIGNIFICANT_HOLDING_DISCLOSURE_OBSERVED FACT:<fact_id>
TREASURY_OPERATION_OBSERVED             FACT:<fact_id>
TREASURY_STOCK_POSITION_OBSERVED        FACT:<fact_id>
CANCELLATION_RELATION_OBSERVED          REL:<annulled>|<annulling>|ANNULS
NOTICE_DISAPPEARANCE_OBSERVED           DIS:<notice_key>|<streak_start_observed_at>
```

(`fact_id` is the G4 deterministic fact identity; `DIS` includes the
streak-start timestamp because a notice may disappear, reappear and
disappear again — each streak is new information.)

## Properties

- Deterministic across processes, replays and rebuilds.
- Independent of SQLite `rowid`, insertion order, page position,
  filesystem paths and wall-clock.
- Changing only `observed_at` cannot change the ID of FACT/NOTICE/REL
  items — identity is the *semantic thing observed*, anchored at its
  first qualifying observation.
- A distinct amendment/rectification notice is a distinct identity,
  hence a distinct item.

## Ordering key

```text
(observed_at ASC, item_key ASC)
```

`observed_at` is the first qualifying observation instant —
sufficient for tie-safe keyset pagination because `item_key` is
unique per `(feed_item_type, item_key)` primary key.

## Delivery contract

Replayable + idempotent. **No exactly-once claim**: a consumer that
replays a window receives the same items with the same IDs and
deduplicates on `feed_item_id`.
