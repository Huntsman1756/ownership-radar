# G4 — Ledger Semantics & Bitemporal Query Core — Gate Contract (frozen)

Status: **FROZEN before implementation.** Results are appended, never
used to relax the contract.

G4 turns the parsed semantic layer (G2 NOD, G3 PS/AC) into a
deterministic, rebuildable ledger. It is NOT an API or a product
surface.

## Layers

```text
notice_observation (G1, immutable)
  → source_fact        SOURCE_DECLARED content, deterministic identity
  → ledger_event       SOURCE_DECLARED or DETERMINISTIC_DERIVATION
  → state projection   derived view, never source truth
```

## Temporal model (fixed)

- `effective_date` — economic/regulatory time (transaction_date,
  threshold_date, position date, filing_date).
- `first_observed_at` — knowledge time (G1 observation). Never
  retro-projected.
- `CURRENT_KNOWLEDGE_RECONSTRUCTED` — "with all we know today, what
  occurred up to effective date X".
- `AS_KNOWN_AT(T)` — "what had Ownership Radar observed by T". If T
  precedes the first observation → `NO_OBSERVATION_HISTORY`, never a
  silent reconstruction.

## Identity rules (fixed)

- `fact_id = sha256(canonical_json({notice_key, fact_type,
  payload_sha256, dup_index}))` — `dup_index` disambiguates only
  byte-identical payloads inside one notice; never wallclock, rowid,
  run or path.
- `event_id = sha256(canonical_json({source_fact_id or
  notice_relation, event_type, rule_id, derivation_version}))`.
- Any change to derivation logic bumps `derivation_version`; old
  derived rows are rebuilt, never silently overwritten in place.

## Event taxonomy (fixed, no additions without a new rule)

```text
NOTICE_FILED                          SOURCE_DECLARED
NOTICE_CANCELLED                      SOURCE_DECLARED (notice_relation)

INSIDER_ACQUISITION                   DETERMINISTIC_DERIVATION
INSIDER_DISPOSAL                      DETERMINISTIC_DERIVATION
INSIDER_TRANSACTION_OTHER             DETERMINISTIC_DERIVATION

SIGNIFICANT_HOLDING_POSITION_DISCLOSED  DETERMINISTIC_DERIVATION

TREASURY_OPERATION_REPORTED           DETERMINISTIC_DERIVATION
TREASURY_STOCK_POSITION_DISCLOSED     DETERMINISTIC_DERIVATION
```

Explicitly NOT generated: `THRESHOLD_CROSSED`, `SHAREHOLDER_BUY/SELL`,
`TREASURY_THRESHOLD_CROSSED`, `CONTROL_CHANGED`, position-change
events — no proven rule exists yet; fail closed.

## Gates (pre-registered)

| Gate | Criterion |
|---|---|
| G4-01 G2_G3_BASELINE_UNCHANGED | G2+G3 tests and semantic digests identical before/after |
| G4-02 SOURCE_FACT_IDENTITY_DETERMINISTIC | same notice+content → same fact_id across rebuilds; material change → new id |
| G4-03 SOURCE_FACTS_REBUILDABLE | drop/rebuild facts → identical set |
| G4-04 EVENT_IDENTITY_DETERMINISTIC | same fact+rule version → same event_id |
| G4-05 EVENT_DERIVATION_IDEMPOTENT | materialize twice → identical event set |
| G4-06 SOURCE_VS_DERIVED_EXPLICIT | every event carries unambiguous event_basis |
| G4-07 NOD_EVENT_MAPPING_EXACT | BUY→INSIDER_ACQUISITION, SELL→INSIDER_DISPOSAL, else OTHER; raw preserved |
| G4-08 PS_NO_INVENTED_TRANSACTION | zero BUY/SELL-type events from PS facts |
| G4-09 AC_FLOW_AND_POSITION_DISTINCT | operation events ≠ position event; never summed |
| G4-10 NOTICE_RELATION_CHAINS_EXACT | A→B→C resolves terminal C; cycles → RELATION_GRAPH_ERROR |
| G4-11 CANCELLATION_NON_DESTRUCTIVE | annulled facts/events remain queryable |
| G4-12 AS_KNOWN_AT_TEMPORAL_SEMANTICS_EXACT | mandatory late-observation scenario |
| G4-13 RECONSTRUCTED_HISTORY_SEMANTICS_EXACT | late-observed fact included by effective_at |
| G4-14 CURRENT_AUTHORITATIVE_PROJECTION_EXACT | latest non-annulled disclosure per scope |
| G4-15 PROVENANCE_CHAIN_COMPLETE | event → fact → notice → observation → raw_sha256, no orphans |
| G4-16 HOLDOUT_EVENT_ORACLE_EXACT | hand-annotated event expectations, holdout notices |
| G4-17 SECOND_MATERIALIZATION_DETERMINISTIC | two builds → identical ledger digest |
| G4-18 DROP_REBUILD_IDENTICAL | drop derived tables, rebuild → identical digest |
| G4-19 CLEAN_CLONE_TESTS_PASS | fresh clone suite passes; corpus tests SKIP explicitly |

Verdicts: `PASS` / `FAIL` / `INCONCLUSIVE` only.

## Kill criteria

K1 source facts inseparable from derived events → FAIL.
K2 cancellation requires overwriting/deleting history → FAIL.
K3 AS_KNOWN_AT requires retro-projection → FAIL.
K4 event identity needs fuzzy matching → FAIL.
K5 ledger not identically rebuildable from facts+rules → FAIL.

## Results (appended after implementation)

Baseline: HEAD `f48cf0d`, 42 tests, clean tree. After G4: **60 tests
pass, 30 subtests, 0 regressions** in G1–G3.

Materialized on `corpus/corpus.sqlite`:

```text
source_fact:        4,862
  NOD_TRANSACTION_EVENT            16
  SIGNIFICANT_HOLDING_DISCLOSURE   54
  TREASURY_OPERATION            4,745
  TREASURY_RESULTING_POSITION      47
ledger_event:       4,999
  SOURCE_DECLARED                 137  (116 NOTICE_FILED + 21 NOTICE_CANCELLED)
  DETERMINISTIC_DERIVATION      4,862  (1 per source fact)
  INSIDER_ACQUISITION              10
  INSIDER_DISPOSAL                  2
  INSIDER_TRANSACTION_OTHER         4
  SIGNIFICANT_HOLDING_POSITION_DISCLOSED  54
  TREASURY_OPERATION_REPORTED   4,745
  TREASURY_STOCK_POSITION_DISCLOSED    47
issuers: 5 · effective dates 2015-04-02 .. 2026-09-10
derivation rules: 6 @ version 1
```

Relations: 135 `ANNULS` chains resolved, 0 errors, 0 cycles; one
two-hop chain `ps:2020135555 → ps:2021016415 → ps:2021016444`
(terminals of all three = `ps:2021016444`). 21 of 135 annulled
notices have `notice` rows → 21 `NOTICE_CANCELLED`; the rest were
never observed (they had already left the listings) — no event,
consistent with fail-closed rules.

Determinism (`corpus/corpus.sqlite`):

```text
materialize #1 digest: 986d6ff2d0330527558e3d9ea86f3e04aadcda90917ea92f2490535c74695211
materialize #2 digest: identical
drop + rebuild digest: identical
```

Holdout oracle: `corpus/oracle/g4_holdout_expected.json`, annotated
from semantic tables + relations only (never from `ledger.py`).
36 notices (11 PS, 10 AC, 15 NOD): event counts, types, bases,
effective dates and annulment terminals — **0 mismatches**.
One annotation error found during review (chain terminal), corrected
in the oracle before freeze — the code was right.

Gates: G4-01..G4-19 all PASS. Kill criteria: none triggered.

Verdict: **G4 PASS**.
