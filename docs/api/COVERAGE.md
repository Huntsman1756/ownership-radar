# Coverage & Dataset Info

The product never reports one ambiguous "% parsed". Coverage is a
stack of explicit denominators.

## radar.dataset_info()

```text
dataset_version / universe_version   e.g. itf2026-v1
universe_issuers                     members of the frozen seed
schema_version                       public output contract version
notices / observations               acquisition counts
source_facts / ledger_events         semantic/ledger counts
ledger_digest                        deterministic rebuild digest
semantic_parser_versions             parser:version -> doc count
derivation_version                   ledger ruleset version
last_run                             latest ingestion run record
```

## radar.coverage()

```text
global    issuers attempted/in universe, notices, observations,
          raw blobs, doc_status distribution, templates,
          facts/events, relations, cancellation evidence split,
          failed items, discovered issuers, ambiguous ANNULS count
matrix    per issuer x surface: enumerated, with_doc_token,
          supported_era, doc_status counts
legacy    UNSUPPORTED_* / NO_DOC inventory by surface x year
```

## What the current universe is

`itf2026-v1` = the 60 issuers in the AEAT ITF-2026 list (market cap
> €1bn at 2025-12-01). It is **not** "all Spanish listed companies":
smaller caps, BME Growth, delisted issuers and non-share issuers are
out of the declared scope. `dataset_info()` always says so via
`universe_version`; `docs/gates/G5-UNIVERSE.md` defines the boundary.

## Status taxonomy

Every notice carries an explicit `doc_status`:

```text
PARSED  PARSED_WITH_UNMAPPED_VALUES
UNSUPPORTED_TEMPLATE            (free-form docs, fail-closed)
UNSUPPORTED_LEGACY_TEMPLATE
UNSUPPORTED_NO_TEXT_LAYER       (scans)
NO_DOCUMENT_AVAILABLE
NOT_FETCHED_LEGACY_ERA          (enumerated, out of semantic scope)
NOT_PDF
EXTRACTION_ERROR
```

Nothing is silently dropped: unsupported means *classified*, not
missing.
