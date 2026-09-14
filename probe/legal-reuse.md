# Legal / reuse check — CNMV

## Evidence captured

- `evidence/legal/nota-legal-20260914.html` — full text of
  `https://www.cnmv.es/portal/Utilidades/NotaLegal` (301 -> canonical),
  retrieved 2026-09-14, sha of raw file in git/object store.

## Terms read from the Nota legal (verbatim substance)

1. Site content © CNMV; **no license is granted by default** ("no concede
   licencia de uso o autorización alguna ... salvo acuerdo expreso por
   escrito"), and CNMV reserves the right to change/limit usage
   conditions at any time.
2. **Free private use** is allowed, including local copies.
3. For non-private use, reproduction/distribution is authorized only if:
   - the information is reproduced **faithfully, without altering
     contents**;
   - when the information is incorporated into products that are **sold
     or ceded non-gratuitously**, buyers/assignees must be told — before
     they pay and on each delivery — that the same information is
     available free of charge on the CNMV website.
4. **Derived calculations may be disseminated** ("podrá utilizar para
   realizar cálculos que se difundan por el usuario") — this is the hook
   for publishing our normalized/aggregated ledger outputs.
5. Deep links must open in an independent window (no framing).
6. CNMV disclaims responsibility for accuracy of third-party filings —
   the registry is evidence of *what was filed*, not of truth.

## Consequences for the project

- No published rate limit exists → we define our own conservative policy
  (see below); we do not claim an official one.
- The future repo must keep `LICENSE` (code) strictly separate from
  `DATA-NOTICE.md` (CNMV source terms, attribution, "obtainable free of
  charge at cnmv.es" notice required for any non-gratuitous
  redistribution).
- Raw captured documents remain CNMV copyright; derived databases of
  facts (filing dates, registration numbers, percentages) are the
  defensible layer to redistribute.
- Documents to prepare in the real repo: `LICENSE`, `DATA-NOTICE.md`,
  `PROVENANCE.md`, `CRAWLING-POLICY.md`.

## Self-imposed crawling policy (implemented in probe.py)

- ~0.9 s minimum between requests; sequential only, no concurrency.
- Max 3 retries, 5 s+ linear backoff; GET only; no POST except none at all.
- Descriptive User-Agent: `OwnershipRadarES-G0-Probe/0.1 (...)`.
- No robots bypass, no CVFE/session-guard circumvention, no captcha
  workarounds. All fetches recorded immutably with metadata.
