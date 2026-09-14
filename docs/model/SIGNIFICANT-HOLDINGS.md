# Model — Significant Holdings (G3-A)

A CNMV significant-holdings notice is a **position disclosure**, not a
trade. `pspdf.py` transforms the document into the declared position,
its components and the notification context. It never emits
transactions and never derives a buy/sell from position differences.

## Semantic layers

```text
notice (G1)
  └── ps_notice_semantic            notice-level fields
        ├── ps_shares_row           §7.A voting rights attached to shares
        ├── ps_instrument_row       §7.B.1 / §7.B.2 financial instruments
        ├── ps_control_chain_row    §8 / annex chain of controlled entities
        └── ps_loyalty_row          §11 loyalty-vote rows (C2/2022 only)
```

## Templates (fingerprinted by content, never by date/URL)

| regulatory_template | Form |
|---|---|
| `CIRC_8_2015_MODEL_1` | Circular 8/2015 Modelo I / Model 1 (bilingual) |
| `CIRC_2_2022_MODEL_1` | Circular 2/2022 Model 1 (adds §11 loyalty vote) |

Other observed families are explicit non-goals:
`CIRC_8_2015_MODEL_2_DIRECTOR` (director notifications pre-2020),
`UNSUPPORTED_LEGACY_TEMPLATE` (monolingual pre-2016 forms),
`UNSUPPORTED_NO_TEXT_LAYER` (scans), `UNSUPPORTED_TEMPLATE`.

## Percentage semantics

`percentage_semantics` is mandatory because Circular 2/2022
(`legal_effective_date = 2022-08-07`) changed the meaning of "% voting
rights":

| value | meaning |
|---|---|
| `PRE_C2_2022_VOTING_RIGHTS` | plain voting rights |
| `C2_2022_INCLUDING_LOYALTY` | may include loyalty double votes |

Loyalty §11 fields are only ever populated under the C2 template; the
fingerprint and the §11 anchor share the same trigger word, so loyalty
values can never be attributed to pre-2022 semantics.

## Declared vs computed

`position_current` / `position_previous` keep the four declared §6
cells (shares %, instruments %, total %, issuer total voting rights)
as `*_raw` literals plus exact `Decimal`/`int` normalizations.
`aggregate_qa` compares `pct_shares + pct_instruments` vs declared
`pct_total` within half of the declared granularity:

```text
DECLARED_COMPUTED_MATCH / DECLARED_COMPUTED_MISMATCH / NOT_COMPUTABLE
```

The declared value is never overwritten by the computed one.

## Financial instruments (§7.B)

Each instrument row keeps type (wrapped-label merge), expiration date,
exercise/conversion period raw, settlement type, voting-rights number
and percentage — raw + normalized. Instruments are never converted
into shares.

## Control chain (§8 / annex)

`ps_control_chain_row` preserves entity name and up to three
percentages per row, in document order, with `source`
(`SECTION_8`/`ANNEX`) and a derived `chain_path_index` grouping
repeated roots. No entity resolution, no fuzzy matching.

## What is NOT produced

No `BUY`/`SELL`, no threshold-crossing events, no beneficial-owner
inference. Ledger/event generation is a later phase (G4) built on top
of this semantic layer plus `notice_relation` annulments.
