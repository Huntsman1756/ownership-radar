# ADR-G4 — Deterministic fact/event identity

## Decision

```text
fact_id  = sha256(canonical({notice_key, fact_type,
                             payload_sha256, dup_index}))
event_id = sha256(canonical({source_fact_id | source_notice_key,
                             event_type, rule_id,
                             derivation_version, payload_sha256}))
```

`payload_sha256` is computed over `json.dumps(..., sort_keys=True,
separators=(",",":"))` of the source-declared (fact) or event payload.

## Why

- Facts are identified by *content*: a recrawl or re-parse producing
  identical semantic output yields identical `fact_id`s — proven by
  the materialize-twice and drop/rebuild digest checks.
- `dup_index` handles the only legitimate collision: byte-identical
  payloads inside one notice (duplicate AC operation rows are real —
  e.g. same share bought twice in a day). It is the minimal
  disambiguator, not a positional identity.
- `rule_id` + `derivation_version` inside `event_id` means a changed
  derivation produces new ids instead of silently overwriting —
  old-version events remain distinguishable.
- Nothing depends on rowid, insertion order, run timestamps, paths or
  URLs.

## Consequences

- A *semantic* change to a notice (amended content parsed differently)
  produces a new `fact_id` — the old fact stays, linked only if an
  explicit notice_relation exists.
- "Same economic reality" across NOD/PS/AC never merges — identity is
  per source fact, no cross-family dedupe.
