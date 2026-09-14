# NOD Event Model (G2)

How a NOD/MAR notice (`source_surface=nod`,
`notice_type=PDMR_NOTIFICATION`) becomes economic events.

## Hierarchy

```
notice (G1 canonical identity: nod:<registration_number>)
  └── nod_notice_semantic        notice-level fields, 1 row/notice
        └── transaction_event    one repetition block of section 4
              └── execution_line one price/volume grid row
```

`transaction_event.event_id = <notice_key>:<source_order:02d>` —
`source_order` is document order only; it is NOT a stable economic
identity across amendments (an amendment may reorder blocks).

## Notice-level fields

| field | source |
|---|---|
| `notifying_party_name_raw` | §1.a literal |
| `notifying_party_kind` | `NATURAL_PERSON` iff the PDMR checkbox is checked (a PDMR is by definition a natural person); `LEGAL_PERSON` iff the name carries a corporate-form suffix (deterministic lexical list); else `UNKNOWN` |
| `closely_associated` | checkboxes §2 — CA only → `TRUE`; PDMR only → `FALSE`; neither/both → `UNKNOWN` + unmapped note |
| `position_status_raw` | §2.a literal, verbatim |
| `related_pdmr_name_raw` / `related_pdmr_position_raw` | For CA notices the §2.a field carries `"PDMR name - position"` or `"name, position"`. Deterministic split: first `" - "`, else first `", "`. No separator → `PARSED_WITH_UNMAPPED_VALUES` (`related_pdmr_unsplittable`), never a silent NULL for a present field |
| `notification_kind` | §2.b value: `Inicial`→`INITIAL`, `Modificación`→`AMENDMENT`, else `UNKNOWN` |
| `amendment_text_raw` | text between the kind value and §3 — the corrected-error explanation; NULL when absent (never the kind value itself) |
| `issuer_name_document` / `issuer_lei_document` | §3 as stated in the document (cross-checkable against the listing identity, not overwritten by it) |
| `additional_info_raw` | "Otra información" body, verbatim |

## Event-level fields

One event per maximal consecutive run of grid rows sharing
(instrument code, instrument nature, transaction nature, date, venue).

| field | note |
|---|---|
| `instrument_code_raw` | grid col 4.a (e.g. ISIN) |
| `instrument_type_raw` | col 4.b (`Acción`, `Derivados`, …) |
| `transaction_nature_raw` / `_normalized` | col 4.c; normalized only via exact map `Compra→BUY`, `Venta→SELL`; anything else NULL |
| `transaction_date(_raw)` | col 4.d — the economic date, ≠ `notice.filing_date` |
| `venue_raw` / `venue_code_raw` / `outside_trading_venue` | col 4.e; MIC-shaped codes kept; `XOFF` and `XXXX` → `TRUE` (ISO 10383 non-venue MICs), other MICs → `FALSE`, empty → `UNKNOWN` |
| `share_option_program_linked` | `UNKNOWN` in G2 — the CNMV grid rendering carries no such field |
| `declared_aggregate_volume/price` | the `Total Agregado` row, verbatim literals — the source's own aggregation |
| `computed_volume` / `computed_vwap` / `aggregate_qa` | QA only: exact-decimal sum / VWAP of executions vs declared; `MATCH`, `DIVERGENT`, `NO_DECLARED_AGGREGATE`, `NOT_COMPUTABLE`. Divergence is evidence, never a silent rewrite |

## Execution lines

Each 8-cell grid row → one `execution_line` with `volume_raw`/`price_raw`
literals plus exact-decimal `volume`/`price` (stored as TEXT — no
floats) and `price_currency` (col 4.h). `quantity_currency` is NULL:
the grid's currency column qualifies the price; volume is an
instrument count.

## Economic no-double-count invariant

Execution lines and the declared aggregate are two representations of
the SAME economic set. Consumers must never sum both. The aggregate is
metadata on the event; executions are the line items.

## Provenance

Every parse records `doc_sha256` (the raw PDF), `semantic_parser_version`
(`nodpdf-0.1.0`), and `corpus_split`. `notice_key` links back to the G1
notice/observation layer (`raw_sha256`, `run_id`). Amendments extracted
here never create `notice_relation` rows — that table remains the
explicit-relation layer only.

## Fail-closed statuses

`PARSED`, `PARSED_WITH_UNMAPPED_VALUES` (fields listed in
`parse_notes`), `UNSUPPORTED_TEMPLATE`, `UNSUPPORTED_NO_TEXT_LAYER`,
`MALFORMED_SOURCE`, `EXTRACTION_ERROR`.
