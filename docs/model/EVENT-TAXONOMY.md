# Event Taxonomy (G4)

Closed set. No additions without a new versioned derivation rule.

| event_type | basis | rule | source |
|---|---|---|---|
| `NOTICE_FILED` | SOURCE_DECLARED | `NOTICE_FILED/v1` | every observed notice with facts |
| `NOTICE_CANCELLED` | SOURCE_DECLARED | `NOTICE_CANCELLED_FROM_ANNULS/v1` | `notice_relation` ANNULS |
| `INSIDER_ACQUISITION` | DETERMINISTIC_DERIVATION | `NOD_TXN_TO_INSIDER_EVENT/v1` | transaction_nature_normalized = BUY |
| `INSIDER_DISPOSAL` | DETERMINISTIC_DERIVATION | same | nature = SELL |
| `INSIDER_TRANSACTION_OTHER` | DETERMINISTIC_DERIVATION | same | any other nature (gift, inheritance, ...) — raw preserved |
| `SIGNIFICANT_HOLDING_POSITION_DISCLOSED` | DETERMINISTIC_DERIVATION | `PS_DISCLOSURE_TO_POSITION_EVENT/v1` | one per parsed PS notice |
| `TREASURY_OPERATION_REPORTED` | DETERMINISTIC_DERIVATION | `AC_OPERATION_TO_TREASURY_EVENT/v1` | one per §4 operation row (A/T flag preserved) |
| `TREASURY_STOCK_POSITION_DISCLOSED` | DETERMINISTIC_DERIVATION | `AC_POSITION_TO_TREASURY_EVENT/v1` | one per §5 resulting position |

## Deliberately absent

`THRESHOLD_CROSSED`, `TREASURY_THRESHOLD_CROSSED`,
`SHAREHOLDER_BUY/SELL`, `CONTROL_CHANGED`, position-change events —
no proven mechanical rule exists; they fail closed (no event).

`NOTICE_RECTIFIED`/`NOTICE_SUPERSEDED` are defined but only emitted
when explicit `notice_relation` evidence appears (corpus so far only
contains ANNULS).

## Cardinality rules

- 1 `transaction_event` → 1 insider event (execution lines are inside
  the payload, never extra events)
- 1 PS notice → 1 position-disclosure event (never a trade)
- 1 AC operation row → 1 `TREASURY_OPERATION_REPORTED`
- 1 AC notice → 1 `TREASURY_STOCK_POSITION_DISCLOSED`
- flow ≠ stock: operation events and the position event never sum
