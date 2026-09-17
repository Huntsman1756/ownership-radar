# Dependencies — runtime audit (v0.1.0-alpha.2)

Ownership Radar ES has a deliberately minimal dependency surface.

## Direct runtime dependencies

| Package | Declared | Validated release snapshot | License | Purpose |
|---------|----------|----------------------------|---------|---------|
| pdfminer.six | `>=20221105` | 20260107 | MIT | PDF text extraction for CNMV filing parsers |

`requires-python >=3.10`. Everything else is Python stdlib
(`sqlite3`, `urllib`, `hashlib`, `json`, `dataclasses`, …).

`requirements.txt` pins the parser dependency to the validated release
snapshot used by CI/development. The package metadata intentionally
keeps a compatible lower bound for library consumers; parser provenance
records the PDF engine/version used for each semantic parse.

## Transitive snapshot (via pdfminer.six)

| Package | Version | License |
|---------|---------|---------|
| charset-normalizer | 3.4.7 | MIT |
| cryptography | 50.0.1 | Apache-2.0 OR BSD-3-Clause |

All licenses are permissive and MIT-compatible — consistent with the
project's `LICENSE` (MIT for code; CNMV source/data terms live in
`DATA-NOTICE.md`).

## Dev-only tools (not shipped as runtime deps)

`pytest` (MIT), `ruff` (MIT, pinned — pyflakes correctness rules only),
`build` (MIT), `twine` (Apache-2.0).

## Update policy

- No new runtime dependency without strong justification
  (see `CONTRIBUTING.md`).
- Dependabot monitors Python and GitHub Actions dependencies weekly.
- The pinned parser snapshot must only move with a green parser/
  regression suite; a dependency bump must not silently redefine
  semantic output.
- Regenerate this table on dependency changes (`pip show` /
  `pip-licenses` equivalent) and record material changes in
  `CHANGELOG.md`.
