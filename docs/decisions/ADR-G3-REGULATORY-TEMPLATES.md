# ADR-G3 — Regulatory template identification for PS/AC documents

## Status

Accepted (G3 freeze).

## Context

G0 proved `source_surface ≠ notice_type ≠ regulatory_template`: the
`ps` surface mixes significant-holding disclosures with director
notifications (pre-2020-03-02), and both families span two regulatory
generations (Circular 8/2015 → Circular 2/2022, effective
2022-08-07). Circular 2/2022 renumbers Modelo IV → Modelo 2 and claims
no substantive content change for treasury stock, while Model 1 gains
a loyalty-vote section.

## Decision

Templates are fingerprinted **by document content** (`g3pdf.
fingerprint`), never by filing date, URL, hostname or surface:

- **PS**: bilingual `PARTICIPACIONES SIGNIFICATIVAS` + `STANDARD FORM`
  → Model-1 family; presence of the loyalty section (`LEALTAD` /
  `LOYALTY`, i.e. §11) selects `CIRC_2_2022_MODEL_1`, otherwise
  `CIRC_8_2015_MODEL_1`.
- **Director notifications** (`CONSEJEROS` + `MODELO`): bilingual →
  `CIRC_8_2015_MODEL_2_DIRECTOR` (out of G3 scope); monolingual →
  `UNSUPPORTED_LEGACY_TEMPLATE`.
- **AC**: `ACCIONES PROPIAS` / `OWN SHARES` + `MODELO 4`/`FORM #4` →
  `CIRC_8_2015_MODEL_4`; `MODELO 2`/`FORM #2` → `CIRC_2_2022_MODEL_2`;
  monolingual → legacy; otherwise `UNSUPPORTED_TEMPLATE`.

The same trigger word that fingerprints the C2 template anchors its
§11 loyalty section, so loyalty values cannot be emitted under
pre-2022 semantics — the distinction is enforced structurally.

## Consequences

- One parser family per surface (`pspdf`, `acpdf`); no shared model is
  forced onto both.
- Pre-2016 monolingual documents and scans without a text layer are
  explicit statuses, not failures.
- `percentage_semantics` is attached to every PS parse so downstream
  consumers always know which regulatory generation produced a
  percentage.
- AC Model 4 and Model 2 share the semantic model because their
  observed structure is identical; they still carry distinct template
  labels so a later divergence is representable without re-fingerprint.
