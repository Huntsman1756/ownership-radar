# DATA-NOTICE — CNMV source terms

This project consumes public information published by the Comisión
Nacional del Mercado de Valores (CNMV, www.cnmv.es). The repository's
`LICENSE` covers only the code; CNMV content is governed by CNMV's own
Nota legal (captured as evidence in `probe/evidence/legal/`).

Summary of the applicable terms (see the captured page for the binding text):

- All site content is © CNMV; no license is granted by default.
- Reproduction/distribution beyond private use is permitted only if the
  information is reproduced **faithfully and unaltered**.
- If CNMV information is incorporated into products distributed
  non-gratuitously, recipients must be informed — before payment and on
  each delivery — that the same information is freely available at
  www.cnmv.es.
- **Calculations derived from CNMV information may be disseminated** —
  the normalized ledger (registration numbers, dates, percentages,
  relations) is the redistributable layer.
- CNMV does not vouch for the accuracy of third-party filings; the
  registry is evidence of *what was filed*, not of its truth.
- Deep links to cnmv.es pages must open in independent windows.

## Practical rules followed here

- Raw captured CNMV documents are stored locally for provenance and are
  **not** redistributed (gitignored payloads; metadata/sha256 only).
- Notice identity keys are factual identifiers (registration numbers),
  not CNMV content.
- Nothing here is presented as an official CNMV product.
