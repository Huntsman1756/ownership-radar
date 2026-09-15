# Model — Ledger (G4)

```text
notice_observation (G1, immutable, knowledge time)
  → source_fact            SOURCE_DECLARED content
  → fact_version_relation  SUPERSEDED/CANCELLED/RECTIFIED links
  → ledger_event           SOURCE_DECLARED or DETERMINISTIC_DERIVATION
  → projections            derived views (state_for_issuer)
```

## source_fact

Directly declared semantic content. One row per:

| fact_type | source | effective_date |
|---|---|---|
| `NOD_TRANSACTION_EVENT` | `transaction_event` (+ executions, notice-level fields) | transaction_date |
| `SIGNIFICANT_HOLDING_DISCLOSURE` | `ps_notice_semantic` | threshold_date |
| `TREASURY_OPERATION` | `ac_operation` row | operation_date |
| `TREASURY_RESULTING_POSITION` | `ac_notice_semantic` §5 | notification_date |

`source_payload_json` contains only declared fields — QA/derived
values stay out. Identity is content-based:

```text
fact_id = sha256({notice_key, fact_type, payload_sha256, dup_index})
```

`dup_index` disambiguates byte-identical payloads inside one notice;
nothing else depends on row order.

## ledger_event

```text
event_id = sha256({source_fact_id | source_notice_key,
                   event_type, rule_id, derivation_version,
                   payload_sha256})
event_basis ∈ {SOURCE_DECLARED, DETERMINISTIC_DERIVATION}
```

Every event names its `rule_id` (derivation_rule registry) and
`derivation_version`. No wallclock fields — rebuilds are byte-
identical.

## fact_version_relation

Notice-level `ANNULS`/`RECTIFIES` relations are projected to fact
level: every fact of the annulled notice is `CANCELLED_BY` every fact
of the annulling notice, `basis = NOTICE_RELATION:<type>`, with the
annulling notice's first-observation time as `observed_at`. Never
inferred — only explicit `notice_relation` rows.

Since G6-A this is a SQL **view** over `notice_relation` x
`source_fact`, not a stored table: identical logical rows and
identical `ledger_digest`, without storing the quadratic expansion
(7.65M rows at Stage B scale).

## Rebuildability

`ledger.materialize(cx)` deletes and rebuilds the derived tables
from the semantic layer + `notice_relation`. Same inputs → identical
`ledger_digest`. The semantic and observation layers are never
touched.
