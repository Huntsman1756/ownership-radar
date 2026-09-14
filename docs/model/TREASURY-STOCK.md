# Model — Treasury Stock (G3-B)

A CNMV own-shares (autocartera) notice carries **three distinct
layers** that must never be conflated:

```text
§4  operation FLOW      each row = one acquisition or transmission
§5  resulting STOCK     final position in own shares / voting rights
§2  declared TRIGGER    2.2 = "1% acquisitions" checkbox (declared)
```

`acpdf.py` preserves all three. The 1% trigger is a *declared*
checkbox: it is never recomputed, and disposals are never netted
against cumulative acquisitions (the regulation aggregates
acquisitions since the previous notification without deducting
sales).

## Semantic tables

```text
notice (G1)
  └── ac_notice_semantic      issuer, reasons, dates, totals,
                              final position, flow QA
        ├── ac_operation      §4 rows (A/T flag raw + normalized)
        └── ac_indirect_row   §6.1/6.2/6.3 indirect-position details
```

## Templates

| regulatory_template | Form |
|---|---|
| `CIRC_8_2015_MODEL_4` | Circular 8/2015 Modelo IV |
| `CIRC_2_2022_MODEL_2` | Circular 2/2022 Model 2 (renumbering; observed structure identical) |

Fingerprint is content-based (title + model anchors); the filing date
is never used for identification.

## Flow QA

`operations_flow_qa` compares, per side, the declared §4 total row
against the computed sums of the operation rows — acquisitions vs
acquisition rows only, transmissions vs transmission rows only:

```text
{ acquisitions: {computed_*, declared_*_raw, status},
  transmissions: {computed_*, declared_*_raw, status} }
```

status: `MATCH` / `DIVERGENT`. Declared totals are never rewritten.

## Column identity

The CNMV grid renders eight value columns (direct/indirect shares,
prices, voting rights, percentages). Data-cell x0 drifts a few points
from the header anchors, so each cell snaps to the **nearest** column
anchor (tolerance 42 pt). Empty columns emit no cell — column identity
comes from position, never from cell order.

## What is NOT produced

No derived "net change" trigger, no position reconstruction beyond
the declared §5 result, no netting of disposals. Annulled notices keep
their semantic rows; `notice_relation` links replacements without
deleting history.
