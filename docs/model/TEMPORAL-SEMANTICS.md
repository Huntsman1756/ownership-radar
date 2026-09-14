# Temporal Semantics

Ownership Radar is "bitemporal" in exactly this sense: two
independent time axes, never mixed.

## Axis 1 — effective / regulatory time

When the declared thing happened or took effect:

- `transaction_date` (NOD operations)
- `threshold_date` (PS disclosures)
- `operation_date` / `notification_date` (AC)
- `filing_date` (when CNMV registered the notice)

## Axis 2 — knowledge / observation time

When Ownership Radar observed it: `notice_observation.observed_at`,
surfaced on facts/events as `first_observed_at`.

Example:

```text
operation_date  = 2024-03-10     (effective axis)
filing_date     = 2024-03-13     (effective axis)
observed_at     = 2026-09-14     (knowledge axis)
```

We may say "a notice filed 2024-03-13 declares an operation dated
2024-03-10". We may NOT say we knew it in 2024.

## Two histories

- **RECONSTRUCTED_HISTORY** — history rebuilt today from old notices.
  Knowledge time = when we first observed each notice, not its dates.
- **OBSERVED_HISTORY** — what successive own observations recorded.
  Only this answers "what did we know at T".

## Two query modes

- `CURRENT_KNOWLEDGE_RECONSTRUCTED` — with all we know today, what
  occurred up to `effective_at=X`.
- `AS_KNOWN_AT(T)` — only observations with `observed_at <= T`. If T
  precedes the first observation → `NO_OBSERVATION_HISTORY` (never a
  silent reconstruction, never retro-projection).

## Cancellations over time

`status_as_known_at(notice, T)`:

- `NOT_OBSERVED` — no observation ≤ T
- `CANCELLED` — an ANNULS relation whose annulling notice was first
  observed ≤ T
- otherwise the latest observed status

An annulled notice keeps all its facts and events: "occurred" and
"currently authoritative" are different questions.

## What we do NOT do

- no `valid_from/valid_to` on immutable economic facts
- no retro-projection of `observed_at`
- no inference of relations (only explicit `notice_relation` rows)
