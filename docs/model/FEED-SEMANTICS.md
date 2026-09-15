# FEED-SEMANTICS — what a feed item means (G6-C)

## Core statement

A `FeedItem` is created when Ownership Radar observes **new public
information** for the first time — a state transition in what the
system knows, not in what the economy did.

```text
observed today  ≠  effective today
```

## When a FeedItem is created

```text
YES   first notice observation (any run type)
YES   first observation of a semantic fact (NOD/PS/AC parse output)
YES   first observation of an ANNULS relation (incl. relation-only
      endpoints and ambiguous candidates)
YES   first observation of a disappearance streak
NO    same bytes recrawled
NO    same notice re-observed by a later run
NO    same relation seen again
NO    identical reconciliation (0 items even with new obs rows)
NO    parser-only rematerialization with unchanged identity
```

## Derivation

`feed_item` is a **materialized table** rebuilt by
`ledger.rebuild_feed()` (called from `materialize()`). The single
derivation is `store.FEED_SQL` — a UNION of:

1. `source_fact` rows joined to their first observation run
2. `notice` rows joined to their first observation run
3. `notice_relation` (ANNULS) rows at their observing run
4. disappearance-streak heads in `notice_observation`

It is derived state, not a second source of truth:
`feed_digest()` before rebuild ≡ after rebuild.

## Item unit vs observation unit

`notice_observation` is the append-only evidence row — internal.
`FeedItem` is the public unit. One observation can produce a
`NOTICE_OBSERVED` plus N semantic items (declared, not accidental);
many observations can produce zero items (deduplication).

## history_class

```text
RECONSTRUCTED_HISTORICAL   run_type = BACKFILL
OBSERVED_CURRENT           run_type = INCREMENTAL | RECONCILIATION
```

`OBSERVED_CURRENT` asserts only *how* the information was learned,
never that its `effective_date` is recent. A reconciliation that
first-observes a 2014 filing emits `OBSERVED_CURRENT` with
`effective_date = 2014-…`.

## Disappearance semantics

A `NOTICE_DISAPPEARANCE_OBSERVED` is evidence that a notice stopped
appearing on a scoped surface enumeration. It is non-destructive and
is **not** a cancellation: `cancellation_evidence_present` in the
summary says whether explicit ANNULS evidence exists. The G5
cross-surface scoping fix stays enforced — a `nod`-surface
reconciliation cannot mark `nod_legacy` notices disappeared.

## Ambiguous ANNULS

Targets annulled by >1 notice produce one feed item per relation,
each carrying `annulment_status = AMBIGUOUS` and the full candidate
list. The feed never picks a winner.

## Limitations (documented, accepted)

- A parser-version change producing a *different* fact identity will
  emit a new item under the new identity; no `SYSTEM_REPROCESSING`
  category exists yet (deferred).
- `observed_at` for relation-only annulling endpoints falls back to
  the observing run's `started_at`.
