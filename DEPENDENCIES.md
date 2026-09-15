# Dependencies — runtime audit (v0.1.0-alpha.1)

Ownership Radar ES has a deliberately minimal dependency surface.

## Direct runtime dependencies

| Package | Declared | Resolved | License | Purpose |
|---------|----------|----------|---------|---------|
| pdfminer.six | `>=20221105` | 20260107 | MIT | PDF text extraction for CNMV filing parsers |

`requires-python >=3.10`. Everything else is Python stdlib
(`sqlite3`, `urllib`, `hashlib`, `json`, `dataclasses`, …).

## Transitive (via pdfminer.six)

| Package | Version | License |
|---------|---------|---------|
| charset-normalizer | 3.4.7 | MIT |
| cryptography | 50.0.1 | Apache-2.0 OR BSD-3-Clause |

All licenses are permissive and MIT-compatible — consistent with
the project's `LICENSE` (MIT, code only; CNMV data terms live in
`DATA-NOTICE.md`).

## Dev-only tools (not shipped as runtime deps)

`pytest` (MIT), `build` (MIT), `twine` (Apache-2.0).

## Policy

- No new runtime dependency without strong justification
  (see CONTRIBUTING.md).
- Prefer versions published ≥7 days; no floating `latest`.
- Regenerate this table on dependency changes:
  `pip show <pkgs>` / `pip-licenses` equivalent.
