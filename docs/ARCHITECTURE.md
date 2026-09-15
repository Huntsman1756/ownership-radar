# ARCHITECTURE — Ownership Radar ES

End-to-end design of the current system (v0.1.0-alpha.1). Functional
contract frozen at G6-C.

```text
CNMV official disclosures
   │
   ▼  acquisition (cnmv.py, ingest.py, poller.py)
crawl_run  +  notice_observation (append-only)  +  raw_blob
   │            immutable, content-addressed evidence
   ▼  canonical projection (store.py)
notice  +  notice_relation (ANNULS/RECTIFIES)
   │
   ▼  semantic parsers (nodpdf/pspdf/acpdf + regime separation)
nod/ps/ac_*_semantic tables  ·  notice_doc
   │
   ▼  ledger derivation (ledger.py — deterministic)
source_fact  →  ledger_event  (+ derivation_rule)
   │
   ▼  query layer
bitemporal core (known_at / effective_at)
   │
   ├─► public read-only API + CLI (api.py, public_cli.py)
   └─► incremental feed (feed_item, derived by store.FEED_SQL)
```

## Acquisition

- Typed runs: `BACKFILL` / `INCREMENTAL` / `RECONCILIATION`
  (`crawl_run`), resumable via checkpoints.
- Every listing fetch is persisted **before** parsing: raw bytes →
  content-addressed `raw_blob` (`raw_sha256`), plus observation
  context (`source_url_observed`/`canonical`, headers).
- `notice_observation` is append-only — presence *and* absence
  (`SOURCE_DISAPPEARANCE_OBSERVED`) are evidence, scoped per surface
  family (the G5 cross-surface scoping fix).
- Policy: `CRAWLING-POLICY.md` — sequential GETs, bounded windows.

## Canonical layer

- `notice_key = (source_surface, source_registration_number)` —
  the shared CNMV registry number is stable identity.
- `source_surface`, `notice_type` and `regulatory_template` are
  **independent** dimensions: the PS surface pre-2020 mixes
  DIRECTOR_HOLDING and SIGNIFICANT_HOLDING.
- `notice_relation` stores explicit source-stated relations only —
  "anula"/"rectifica a nº registro" — never inferred.

## Semantic layer

- Per-regime template parsers (Circular 8/2015 Modelos 1–4, NOD/MAR
  variants, legacy generations). Unknown templates fail closed to
  `UNSUPPORTED_TEMPLATE`.
- NOD → `transaction_event` + `execution_line` (exact decimals, PDMR
  / closely-associated classification, amendment text raw).
- PS → disclosure positions + control chains (never trades).
- AC → `ac_operation` flows (sec. 4) + `ac_resulting_position` stock
  (sec. 5) — separate structures.

## Ledger (bitemporal)

- `source_fact`: deterministic identity (`fact_id` = content hash),
  `first_observed_at`, `event_basis` lineage.
- `ledger_event`: 1..N per fact, `SOURCE_DECLARED` vs
  `DETERMINISTIC_DERIVATION`, `derivation_rule` versioned.
- `fact_version_relation`: SQL **view** (G6-A) — logical fact-level
  annulment projection without all-pairs storage.
- Two time axes: `known_at` (AS_KNOWN_AT — what was *known* then;
  pre-history → `NO_OBSERVATION_HISTORY`) and `effective_at`
  (CURRENT_KNOWLEDGE_RECONSTRUCTED).
- Annulment chains resolve fail-closed: `NONE | RESOLVED | AMBIGUOUS
  | CYCLE`; ambiguous targets never pick a winner.
- `ledger_digest`: whole-ledger content hash — rebuild must be
  identical.

## Public surface

- `api.py`: read-only SQLite (`mode=ro` + `query_only`), zero
  network, frozen dataclasses, `Decimal` preserved, keyset cursors.
- `public_cli.py`: `ownership-radar` — stdout payload only,
  `schema_version:"1"`, exit 0/1/2.
- `feed_item`: materialized derived table rebuilt by
  `ledger.rebuild_feed()` from `store.FEED_SQL` — notices, semantic
  facts, ANNULS relations, disappearance streak-heads. Stable
  `feed_item_id = v1:<sha256(item_key)>`; replayable + idempotent;
  `feed_digest` deterministic.

## Storage

Single SQLite file. Production reference (itf2026-v1, 60 issuers):
~459 MB canonical+derived; ~4.66 GB raw blobs kept out of the DB and
never redistributed.
