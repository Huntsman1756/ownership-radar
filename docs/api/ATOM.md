# ATOM — feed representation (G6-C)

`ownership-radar feed --format atom` renders the **same** FeedItem
model as JSON — it is not a second semantics.

## Mapping

```text
<feed>
  id        urn:ownership-radar:feed:<dataset_version>
  title     Ownership Radar ES — observed feed (<dataset_version>)
  updated   max observed_at of the page

<entry>
  id         urn:ownership-radar:<feed_item_id>     (stable)
  published  observed_at                          (observation time)
  updated    observed_at
  title      <feed_item_type> <notice_key|issuer_id>
  content    application/json — the full item body:
             feed_item_type, history_class, run_type, issuer_id,
             notice_key, event_id, effective_date, filing_date,
             event_basis, annulment_status, summary
```

## Date semantics — critical

`published`/`updated` are **observation times**, never
`effective_date`. An operation of 2024 discovered in 2026 has
`published = 2026-<observation>` and `effective_date = "2024-..."`
inside the JSON content. Readers must not confuse feed position with
the economic date of the fact.

## Ordering

Entries follow the canonical feed order:

```text
observed_at ASC, feed_item_id ASC
```

— identical to JSON/JSONL output, never effective-date order.

## Coverage disclosure

The feed `<id>`/`title` carry the real `dataset_version`
(e.g. `itf2026-v1`). The feed never claims broader coverage than the
universe actually ingested.

## Generation

XML is produced via `xml.etree.ElementTree` — never string
concatenation — so ampersands, accents and raw Spanish text are
escaped correctly. stdout carries the valid XML document only;
diagnostics go to stderr.
