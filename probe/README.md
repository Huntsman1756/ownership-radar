# Ownership Radar ES — G0 Acquisition Probe

Disposable technical-viability probe. Purpose: verify whether CNMV public
sources support a bitemporal, reproducible ledger of ownership changes for
Spanish listed companies (SAN, BBVA), built on official notifications.

This is **not** the product repository. It is evidence for a go/no-go decision.

## Layout

```
probe/
  code/probe.py          ingestor: raw capture -> sqlite (stdlib only)
  code/reconcile.py      traversal stats, run diff, bounded-window NOD query
  code/window_recon.py   independent reconciliation via fechad/fechah windows
  probe.sqlite           all normalized state + append-only observations
  raw/<run_id>/          immutable raw bytes + .meta.json per HTTP fetch
  normalized/*.jsonl     table dumps for audit
  runs/<run_id>.json     per-run fetch log + stats
  evidence/
    templates/           sample PDFs per regime + extracted text
    windowed/            raw pages of the independent windowed queries
    legal/               NotaLegal capture
    oir-*.html           OIR surface spot-checks (out of scope, dup detection)
  methodology.md  sources.md  legal-reuse.md  results.md  gates.md
```

## Runs

| run_id                | started (UTC)       | parser | requests | notices observed |
|-----------------------|---------------------|--------|----------|------------------|
| run-20260913T201904Z  | 2026-09-13 20:19    | 0.1.0  | 265      | 3189             |
| run-20260913T202847Z  | 2026-09-13 20:28    | 0.1.0  | 265      | 3189             |
| run-20260914T035225Z  | 2026-09-14 03:52    | 0.1.0  | 265      | 3189             |
| run-20260914T040441Z  | 2026-09-14 04:04    | 0.1.1  | 265      | 3189             |
| run-20260914T041133Z  | 2026-09-14 04:11    | 0.1.1  | 265      | 3189             |

Identical notice sets in all five runs; identical document tokens.
v0.1.1 = `normalized_sha256` hashes content only (v0.1.0 wrongly mixed
in the observed URL with ephemeral `qS` tokens).

## Reproduce

```
python code/probe.py            # new crawl run (appends, never rewrites history)
python code/reconcile.py stats run-20260914T035225Z
python code/reconcile.py diff <runA> <runB>
python code/window_recon.py     # independent bounded-window reconciliation
```

Crawling policy implemented in the probe: ~0.9s between requests, max 3
retries with 5s+ backoff, descriptive User-Agent, GET-only, no POST form
submission, no protection bypass, raw bytes persisted before parsing.
