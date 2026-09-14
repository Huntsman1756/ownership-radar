# Ownership Radar ES

A bitemporal, reproducible ledger of ownership changes in Spanish listed
companies, built on official CNMV notifications as the evidence layer.

```
CNMV raw evidence
       ↓
crawl runs + immutable observations
       ↓
canonical notices
       ↓
1..N ownership events
       ↓
current state / reconstructed history / observed history
```

Families: NOD / PDMR transactions, significant shareholdings
(participaciones significativas), treasury stock (autocartera).

## Status

```
G0 CLOSED: INCONCLUSIVE — ACQUISITION VIABILITY PROVEN,
           HISTORICAL COMPLETENESS NOT PROVEN FOR ALL SURFACES
           → PROCEED (see probe/gates.md)
```

The disposable G0 probe (`probe/`, preserved as evidence) demonstrated on
SAN + BBVA: official registration numbers on 100% of 3,189 notices;
five identical crawl runs; immutable raw captures; 52 explicit
annulment/rectification relations (incl. multi-hop chains); append-only
observation history; regime-separated template generations.

Not demonstrated: independent historical completeness for the
per-holder surfaces (`ps`, `ac`, `nod_legacy`). The ledger therefore
exposes coverage bounds and never claims completeness.

## Core invariants (from G0)

1. `source_surface`, `notice_type` and `regulatory_template` are three
   independent dimensions — CNMV's application topology must not
   contaminate the ontology. (Before 02/03/2020, consejeros reported
   through the PS surface under Circular 8/2015 Modelo 2; `ps` mixes
   DIRECTOR_HOLDING and SIGNIFICANT_HOLDING.)
2. `notice_key = (source_surface, source_registration_number)`; the
   shared CNMV "registro de entrada" is the stable identity.
   `PROVISIONAL_CONTENT_HASH` exists only as an explicit, auditable
   fallback.
3. `notice_observation` is append-only; a disappearance is recorded as
   `SOURCE_DISAPPEARANCE_OBSERVED`, never silently deleted.
   (31 of 48 annulled notices are absent from live listings — the
   captured relation is the only durable proof.)
4. Three clocks: `event_date`, `filing_date`, `observed_at` (+ `run_id`).
   `OBSERVED_HISTORY` begins with our own runs; earlier state is
   `RECONSTRUCTED_HISTORY`.
5. No fuzzy matching, no LLM, no inferred identity. Declarants are
   stored raw, scoped per issuer.
6. Amendments are only trusted when the source states them explicitly
   ("anula", "rectifica a nº de registro").

## Roadmap

| Gate | Scope |
|------|-------|
| G0   | Acquisition feasibility — **closed** (probe/ is the evidence) |
| G1   | Evidence & Notice Core — this repo's importer: crawl_run, immutable raw, notice_observation, canonical notice, notice_relation, surface/type/template separation, provenance/replay. No full semantic parser yet. |
| G2   | NOD event parser — notice → 1..N transactions (person/linked, role, instrument, volume, price, type), template-aware, real fixtures |
| G3   | Significant holdings + treasury stock — percentages, thresholds, loyalty-vote semantics, legacy templates, cancellation/supersession |
| G4   | Public product — Python API, CLI, incremental poller/feed |

## Layout

```
ownership_radar/     G1 evidence & notice core (stdlib only)
tests/               fixture-based tests (fixtures from probe/raw)
probe/               G0 acquisition probe — preserved evidence
data/                local crawl output (gitignored)
LICENSE              code license (MIT)
DATA-NOTICE.md       CNMV source/data reuse terms — NOT the code license
PROVENANCE.md        provenance model
CRAWLING-POLICY.md   self-imposed crawling policy
```
