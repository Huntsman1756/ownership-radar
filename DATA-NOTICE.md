# DATA-NOTICE — CNMV source terms and derived-data policy

This project consumes public information published by the Comisión
Nacional del Mercado de Valores (CNMV, www.cnmv.es). The repository's
`LICENSE` covers **code only**; CNMV content is governed by CNMV's own
Nota legal (captured as evidence in `probe/evidence/legal/`).

## Source

- Source system: CNMV public disclosure surfaces (`nod`, `nod_legacy`,
  `ps`, `ac` listings and their linked filing documents).
- Official URLs are retained per observation as provenance
  (`source_url_canonical`). Linked-document URLs carry
  deterministic per-document `e=` tokens re-resolved on each crawl —
  provenance tokens, not permanent links (see PROVENANCE.md).
- **No affiliation**: nothing here is an official CNMV product, feed
  or certification.

## Applicable terms (summary — the captured page is binding)

- All site content is © CNMV; no license is granted by default.
- Reproduction/distribution beyond private use is permitted only if
  the information is reproduced **faithfully and unaltered**.
- If CNMV information is incorporated into products distributed
  non-gratuitously, recipients must be informed — before payment and
  on each delivery — that the same information is freely available
  at www.cnmv.es.
- **Calculations derived from CNMV information may be disseminated** —
  the normalized ledger (registration numbers, dates, percentages,
  relations, classifications) is the redistributable layer.
- CNMV does not vouch for the accuracy of third-party filings; the
  registry is evidence of *what was filed*, not of its truth.
- Deep links to cnmv.es pages must open in independent windows.

## What this repository redistributes

- Code (MIT).
- **Derived metadata**: notice keys, filing/effective dates,
  percentages, relation endpoints, parse classifications, fixture
  expectations, corpus manifests/oracles, `*.meta.json` provenance
  records.
- A **synthetic** demo dataset (`demo/`, `scripts/build_demo_dataset.py`)
  containing invented filings against real issuer identifiers —
  clearly labelled synthetic, with no document payloads.

## What is NOT redistributed

- Raw CNMV listing pages and filing documents (PDF/HTML bodies) —
  captured locally for provenance, gitignored, excluded from
  packages.
- The production dataset and its raw blob store.
- Any credentials, session tokens (`qS`) or personal data beyond
  what CNMV itself publishes in filings.

## Personal data

Filings contain names of persons published by CNMV/issuers in
official regulatory disclosures. The project stores them as
published (raw declarant strings, scoped per issuer) and adds no
personal data from private sources.

## Practical rules followed here

- Raw captured CNMV documents are stored locally for provenance and
  are **not** redistributed (gitignored payloads; metadata/sha256
  only).
- Notice identity keys are factual identifiers (registration
  numbers), not CNMV content.
- Deep-link consumers should open cnmv.es pages independently.
