# Provenance

Every public entity carries `provenance()` reaching:

```text
event/fact → semantic parser → notice → observation → raw_sha256
```

`Provenance` fields:

```text
notice_key                registry identity (surface:reg_number)
registration_number       CNMV registration number
source_surface            nod | nod_legacy | ps | ac
source_url_canonical      canonical CNMV URL (from observation)
raw_sha256                sha256 of the captured document bytes
first_observed_at         first observation instant (tz-aware)
semantic_parser           parser family
semantic_parser_version   exact parser version
rule_id                   derivation rule (derived events)
derivation_version        derivation ruleset version
```

## Evidence levels

Two separate facts, never collapsed:

```text
cancellation_relation_observed   an observed A ANNULS B relation exists
cancelled_notice_raw_observed    B's own document/notice was captured
```

An official annulment relation is preserved even when the annulled
notice's own bytes were never observed — in that case
`cancelled_notice_raw_observed = False` and nothing claims otherwise.

## Basis

`LedgerEvent.event_basis` and `InsiderTransaction.event_basis` are
always explicit:

```text
SOURCE_DECLARED          taken from an observed CNMV document/listing
DETERMINISTIC_DERIVATION computed by a versioned rule from declared facts
```

`radar.events(basis="SOURCE_DECLARED")` filters at the contract level.

## Example

```python
t = issuer.insider_transactions().items[0]
p = t.provenance()
# p.notice_key -> p.raw_sha256 -> p.semantic_parser_version
```
