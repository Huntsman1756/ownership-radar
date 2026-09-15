# Public CLI — Ownership Radar ES

Entry points: `ownership-radar` (console script) or
`python -m ownership_radar`.

```text
ownership-radar --db <path> <command> [options]
```

`--db` defaults to `data/production/ownership-radar.sqlite`
(env `RADAR_DB` overrides).

## Commands

```text
company IDENT                  exact issuer resolution
insiders IDENT                 insider transactions
holdings IDENT                 significant-holding disclosures
treasury-positions IDENT       treasury stock (section-5 stock)
treasury-operations IDENT      treasury operations (section-4 flow)
notices IDENT                  notices for an issuer
events IDENT                   ledger events
recent-insiders                latest insider txns, all issuers
notice KEY                     one notice + annulment + authoritative
provenance KEY                 provenance chain for a notice
dataset-info                   dataset/universe/versions/digest
coverage                       explicit coverage denominators
```

## Options

```text
--format table|json|jsonl     (default table)
--limit N --cursor CURSOR     keyset pagination
--known-at ISO-INSTANT        knowledge time (AS_KNOWN_AT)
--effective-at ISO-DATE       economic time filter
--include-cancelled           include cancelled-source items
--db PATH                     dataset file
```

Temporal flags are `--known-at` / `--effective-at` only.
There is no `--date`.

Flags work both before and after the subcommand.

## Output contract

- **stdout carries only the payload.** Diagnostics and errors go to
  stderr. JSON/JSONL stdout is always parseable.
- `--format json`: one envelope
  `{"schema_version": "1", "api_version": ..., "data": ...}`.
- `--format jsonl`: one `{"schema_version": "1", "data": ...}` object
  per line.
- Decimals serialize as strings (lossless); dates/instants as
  ISO-8601 with timezone.
- `schema_version` changes only on incompatible contract changes.

## Exit codes

```text
0   ok
1   not found / ambiguous / query error (message on stderr)
2   usage error (argparse)
```

## Examples

```text
ownership-radar company SAN --format json
ownership-radar insiders SAN --limit 50 --format jsonl
ownership-radar events SAN --known-at 2026-01-01T00:00:00+00:00
ownership-radar notice ps:2021016444 --format json
ownership-radar provenance nod:2026120682 --format json
ownership-radar recent-insiders --format jsonl
```
