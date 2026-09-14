# Gates — G0 Acquisition Probe

Verdicts limited to PASS / FAIL / INCONCLUSIVE. Evidence pointers per gate.

| # | Gate | Verdict | Evidence |
|---|------|---------|----------|
| 01 | SOURCE_TRANSPORT_PROVEN | **PASS** | HTTPS+HTML surfaces documented end-to-end (`sources.md`); no JSON API exists (api./internet. → WAP). 265-request runs reproduced 3×. Doc service `/webservices/verdocumento/ver?e=` serves PDFs. |
| 02 | REGISTRATION_NUMBER_PRESENT | **PASS** | 3189/3189 notices carry "Número de registro de entrada" (`notice.identity_status` = OFFICIAL_REGISTRY_NUMBER 100%). |
| 03 | REGISTRATION_NUMBER_RECRAWL_STABLE | **PASS** | Identical notice sets across 3 runs (~9h apart): 3189 each, 0 divergence; doc tokens byte-identical per notice. |
| 04 | HISTORICAL_ENUMERATION_RECONCILED | **INCONCLUSIVE** | `nod`: PASS — disjoint windowed queries union == traversal exactly (evidence/windowed/, recon_result.json). `ps`/`ac`/`nod_legacy`: enumeration deterministic and run-stable but **no independent per-notice comparator exists**; últimos-5-días reconciles only issuer-level and excludes nod. Divergence found: none; completeness for 3/4 families: unprovable from inside the source. |
| 05 | INSERTION_SAFE_PAGINATION | **PASS** | Mechanism built and exercised: `fechad/fechah` windows + per-holder grids (non-paginated) + dedup by `notice_key` + UPSERT canonical + append-only observations. Windowed re-enumeration identical to traversal. |
| 06 | REGIME_BOUNDARY_PROVEN | **PASS** | App boundary 01/05/2018 clean (legacy max 2018-04-20 vs nod min 2018-07-02, no overlap); template transition at Circ. 2/2022 proven in PDFs; `legal_effective_date` (07/08/2022) vs `observed_template_transition` (first filings 14/26-08-2022) recorded separately. |
| 07 | TEMPLATE_GENERATION_PROVEN | **PASS** | 5 distinct generations fingerprinted from raw PDFs (evidence/templates/): MODELO III legacy; MAR bilingual PDMR (uniform 2019–2025); Circ. 8/2015 Modelo 1 + Modelo 2 (consejeros) + Modelo 4 (ac); Circ. 2/2022 Modelo 1 (ps) + Modelo 2 (ac). Caveat: bulk fingerprinting of all docs is future work. |
| 08 | AMENDMENT_CANCELLATION_RELATION_PROVEN | **PASS** | 52 explicit relations (48 ANNULS, 4 RECTIFIES), machine-readable source text, zero inference; 3-hop chains documented (results.md §4). |
| 09 | ISSUER_IDENTITY_EXACT | **PASS** | NIF used as query key; NIF+LEI verified via datosgenerales (SAN LEI 5493006QMFDDMYWIAM13, BBVA K8MS7FD7N5Z2WQ51AZ71). |
| 10 | DECLARANT_IDENTITY_CONSERVATIVE | **PASS** | 0 global identities, 0 merges; raw names + issuer scope stored; noise metrics in results.md §6. |
| 11 | CANONICAL_SOURCE_IDENTITY | **PASS** | `notice_key`=(family, reg) stable across runs; `verdocumento` token = deterministic durable doc id (>30h proven); ephemeral `qS` nav tokens documented and excluded from identity. |
| 12 | RAW_PROVENANCE_REPLAYABLE | **PASS** | Every fetch persisted: raw bytes + meta.json (sha256, urls, headers, retrieved_at, run_id). Doc PDFs re-fetched from stored tokens the next day — replay works. |
| 13 | SECOND_RUN_SET_STABLE | **PASS** | 5 runs, identical notice sets (0 divergence across all pairs), identical doc tokens. Note: parser v0.1.0 included the observed URL (ephemeral `qS`) inside `normalized_sha256`, making the content hash unstable for ps/ac/nod_legacy — fixed in v0.1.1 (content-only hash) and re-verified identical across runs 4–5. The defect is exactly what this gate exists to catch. |
| 14 | REUSE_TERMS_RECORDED | **PASS** | NotaLegal captured (evidence/legal/) and summarized (legal-reuse.md); code-license vs data-terms separation stated. |
| — | OBSERVATION_HISTORY_APPEND_ONLY | **PASS** | `notice_observation` written by INSERT only (no UPDATE/DELETE paths in code); 15945 rows = 3189 × 5 runs, monotone growth; disappearance events modeled as `present_in_source=0` observations. |

## Kill criteria

| Criterion | Triggered? |
|-----------|------------|
| K1 — cannot enumerate history reproducibly | **NO** — 5 identical runs; nod independently reconciled; other families deterministic (completeness caveat recorded, not a K1 trigger) |
| K2 — no stable notice identity | **NO** — 100% official registration numbers; fallback never needed |
| K3 — amendments need heuristics/fuzzy/IA | **NO** — all 52 relations are explicit source statements |

## Overall verdict

```
G0 INCONCLUSIVE — ACQUISITION VIABILITY PROVEN,
HISTORICAL COMPLETENESS NOT PROVEN FOR ALL SURFACES
```

INCONCLUSIVE here has a precise meaning: acquisition is sufficiently
demonstrated to build the product, but independent historical
completeness of three of the four surfaces (ps / ac / nod_legacy) is
not proven. The crawler can reproducibly enumerate what CNMV exposes;
it cannot prove that the exposed universe is exhaustive against an
external ground truth. That limitation does not trigger K1 and does
not block the product — it constrains what the ledger may ever claim.

No kill criterion fired. Identity, provenance, determinism, explicit
amendment linkage and regime separation are all proven.

## Recommendation

**OPEN OWNERSHIP RADAR ES REPOSITORY** — with the ingest model used here
(raw immutable captures, append-only observations, reg-number identity,
explicit-relation extraction, windowed nod traversal) carried over as-is.
The ledger must expose coverage bounds; it must never claim historical
completeness for surfaces without an independent enumeration check.
