# Contributing

Alpha-stage project — the semantic contract is more important than
convenience. Read this before proposing changes.

## Setup

```bash
git clone https://github.com/Huntsman1756/ownership-radar.git
cd ownership-radar
pip install -e .
python -m pytest tests/          # corpus-dependent tests SKIP
python scripts/build_demo_dataset.py
python examples/recent_insiders.py
```

Corpus tests requiring private CNMV raw documents SKIP with
`LOCAL_CNMV_CORPUS_NOT_AVAILABLE` — that is expected on a public
clone.

## Rules that are not negotiable

- **No fuzzy matching.** Identity is exact (NIF/LEI/ISIN/registered
  alias). No similarity scoring, no LLM inference.
- **Provenance is mandatory.** New derivations must keep a path to
  notice → observation → raw_sha256 → parser version.
- **Three clocks stay separate.** `effective_date`, `filing_date`,
  `observed_at` are never merged, renamed to `date`, or conflated.
- **Append-only history.** Never delete or mutate observations;
  corrections are new evidence, not edits.
- **Fail closed.** Unknown templates, ambiguous ANNULS, ambiguous
  identifiers → explicit status/error, never a best guess.
- **No CNMV raw redistribution.** Fixtures must be synthetic or
  derived metadata — never commit raw filings (see DATA-NOTICE.md).
- **Style**: compact stdlib-first code, no new dependencies without
  strong reason; run the full suite before proposing a change.

## Adding a regulatory template

1. Capture the template's regime/surface boundaries
   (`SURFACE_TYPE_DEFAULT` context in `store.py`).
2. Add a fixture under `tests/` built from synthetic or derived
   content — expected values asserted, no raw PDFs.
3. Fail closed for variants not yet understood
   (`UNSUPPORTED_TEMPLATE`, `parse_status` explicit).
4. Keep `semantic_parser_version` bumped and deterministic — it is
   part of provenance.

## Repository map

`ownership_radar/` library · `tests/` contract tests · `docs/`
model/API/ADRs/gates · `probe/` G0 evidence (not runtime) ·
`corpus/` manifests+oracles · `scripts/` dataset tooling ·
`examples/` runnable demos.
