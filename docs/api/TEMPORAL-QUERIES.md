# Temporal Queries — known_at vs effective_at

Two axes, never interchangeable:

```text
effective_date     when the economic/regulatory thing happened
first_observed_at  when Ownership Radar learned it
```

A notice filed in 2021 but discovered by the crawler today has
`effective_date = 2021…` and `first_observed_at = today`. Queries
must say which axis they mean — the API has no `date=` parameter.

## known_at= (knowledge axis)

> "What had Ownership Radar observed at that instant?"

Restricts available information to `first_observed_at <= known_at`
(AS_KNOWN_AT mode). Cancellations are only known once the annulling
notice itself was observed.

- `known_at` earlier than the first observation in the dataset
  returns `status = NO_OBSERVATION_HISTORY` with empty items —
  never silently reconstructed history.
- `known_at` never changes effective dates.

## effective_at= (economic axis)

> "With the knowledge the query allows, what has
>  effective_date <= effective_at?"

- `effective_at` never changes what knowledge is available —
  a notice observed tomorrow cannot appear today by filtering
  effective dates.

## Defaults

```text
known_at     = latest available knowledge
effective_at = unbounded
```

i.e. "everything currently known". `history_mode` in every
`QueryResult` states which mode ran:
`CURRENT_KNOWLEDGE_RECONSTRUCTED` or `AS_KNOWN_AT`.

## Cancellation and knowledge

`include_cancelled=False` (default) excludes items whose source
notice is cancelled *as of the knowledge bound*: with `known_at=T`,
a notice annulled by a filing first observed at T+1d is still
present — that is what was known at T.

## Examples

```python
# what was known on 2024-03-01
radar.events(known_at=datetime(2024, 3, 1, tzinfo=timezone.utc))

# everything known today, economically up to 2024
radar.events(effective_at=date(2024, 12, 31))

# combined: knowledge at T, economically up to D
issuer.insider_transactions(known_at=..., effective_at=...)
```
