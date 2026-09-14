# ADR-G4 — Bitemporal query modes

## Decision

Query functions take `effective_at` (regulatory axis) and `mode`:

- `CURRENT_KNOWLEDGE_RECONSTRUCTED` — no knowledge-time filter.
- `AS_KNOWN_AT(known_at=T)` — only rows whose `first_observed_at <= T`
  are visible; `first_observed_at` = earliest observation of the
  source notice (or of the annulling notice, for cancellation events).

Annulments are applied at projection time (`state_for_issuer`,
`authoritative_terminal`), never by deleting facts/events. A notice
whose annulment is not yet observed at T remains `CURRENT` in
`status_as_known_at(T)`.

## Why not valid-time intervals

Economic facts are immutable once declared; what changes over time is
*our belief about notice authority*. Encoding that as
valid_from/valid_to on facts would conflate "the thing happened" with
"we now think this notice is superseded". Relations + observation
time answer the second question without rewriting the first.

## Failure modes (fail closed)

- `AS_KNOWN_AT` before first observation → `NO_OBSERVATION_HISTORY`,
  never a reconstruction.
- Relation cycle → `RELATION_GRAPH_ERROR`, no arbitrary terminal.
- Insufficient data for a derived event (e.g. threshold crossing) →
  no event, never an `UNKNOWN` event.
- Annulled notices without a `notice` row yield no cancellation event
  (relation exists but the cancelled side was never observed).

## Determinism

All queries use explicit `ORDER BY`; no result depends on SQLite
rowid or insertion order.
