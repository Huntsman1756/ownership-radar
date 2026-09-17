# Ownership Radar ES

**An open-source, reproducible ownership ledger for Spanish listed
issuers, built from official CNMV disclosures covering insider
transactions, significant holdings and treasury stock.**

Not a scraper: a data product. CNMV filings are captured as immutable
evidence with full provenance, normalized into auditable ownership
events, and reconstructed bitemporally — history is never rewritten.

```text
CNMV official disclosures
        ↓
immutable observations (append-only)
        ↓
semantic facts (per-template parsers)
        ↓
bitemporal ledger (source-declared vs derived)
        ↓
Python API · CLI · incremental feed
```

Conceptually: OpenInsider / SEC-tooling for the Spanish CNMV
ecosystem — insider dealings (NOD/MAR), significant shareholdings
(*participaciones significativas*) and treasury stock (*autocartera*).

**Status: Alpha** (`v0.1.0-alpha.1`) — semantic core and
production-scale dataset validated; public API/CLI/feed available and
contract-tested; breaking changes still possible before 1.0.

---

## What it is

- A **bitemporal ledger**: every answer separates *when we learned
  it* (`known_at` / `observed_at`) from *when it economically
  happened* (`effective_date`) and *when it was filed* (`filing_date`).
- **Provenance-first**: every event traces back to a canonical notice,
  an append-only observation, a `raw_sha256` and a parser version.
- **Fail-closed**: no fuzzy matching, no inferred identity, no
  guessed annulments. Ambiguity (e.g. three real CNMV `AMBIGUOUS`
  ANNULS cases) is exposed, never silently resolved.
- **Reproducible**: the ledger and the feed are deterministic
  derivations with stable digests.

## What it is NOT

- Not real-time. The feed is incremental **as ingested by runs**.
- Not complete-coverage proof: historical completeness is not
  externally proven for every CNMV surface (see Coverage).
- Not an official CNMV product; no affiliation.
- Not "current holdings": disclosures are events, not positions
  reconstructed by guessing.

## Supported data families

| Surface | Content |
|---------|---------|
| `nod` + `nod_legacy` | MAR/PDMR insider transactions (person, instrument, volume, price, executions) |
| `ps` | Significant-holding disclosures (positions, thresholds, loyalty votes — never trades) |
| `ac` | Treasury stock: operation flows (sec. 4) and resulting stock (sec. 5), kept distinct |

Annulment/rectification relations (`A ANNULS B`, `A RECTIFIES B`) are
first-class, including relation-only targets and ambiguous chains.

## Quick start

```bash
pip install ownership-radar           # or: pip install .

# build the demo dataset (synthetic, ~330 KB, no CNMV raws needed)
python scripts/build_demo_dataset.py

python examples/recent_insiders.py
ownership-radar --db demo/ownership-radar-demo.sqlite insiders SAN
```

Python:

```python
from ownership_radar import OwnershipRadar

radar = OwnershipRadar.open("demo/ownership-radar-demo.sqlite")

san = radar.company("SAN")                      # exact resolution
for tx in san.insider_transactions().items[:5]:
    print(tx.transaction_date, tx.person_name_raw,
          tx.normalized_event_type, tx.declared_aggregate_price)

res = radar.feed(limit=50)                      # newly-observed info
for item in res.items:
    print(item.feed_item_id, item.feed_item_type, item.observed_at)
```

CLI:

```bash
ownership-radar --db demo/ownership-radar-demo.sqlite company SAN
ownership-radar --db demo/ownership-radar-demo.sqlite holdings SAN
ownership-radar --db demo/ownership-radar-demo.sqlite treasury-positions SAN
ownership-radar --db demo/ownership-radar-demo.sqlite feed --format json
ownership-radar --db demo/ownership-radar-demo.sqlite feed --format atom
```

Every example is executed in CI against the demo dataset
(`tests/test_r1_release.py`).

## Temporal semantics — two axes, never conflated

```text
effective_date  the economic/regulatory date the fact declares
filing_date     when it was filed at CNMV
observed_at     when Ownership Radar learned it
```

```python
issuer.events(known_at=...)      # what was KNOWN then (AS_KNOWN_AT)
issuer.events(effective_at=...)  # economic-time boundary
```

`AS_KNOWN_AT(2024)` is **not** reconstructed history — it answers
"what did the ledger know at 2024" and returns
`NO_OBSERVATION_HISTORY` before the first observation. A transaction
effective in 2024 but observed in 2026 keeps both dates distinct.
See [docs/api/TEMPORAL-QUERIES.md](docs/api/TEMPORAL-QUERIES.md).

## Feed semantics — observation time, not publication spin

`radar.feed()` returns **newly observed information since a cursor**,
ordered `(observed_at, feed_item_id)`:

- `BACKFILL` items are `RECONSTRUCTED_HISTORICAL` and **excluded by
  default** — opt in with `include_backfill=True`.
- `INCREMENTAL`/`RECONCILIATION` items are `OBSERVED_CURRENT` — new
  *information*, regardless of its economic date.
- Identical reconciliations produce **zero** items.
- Contract: **replayable + idempotent, not exactly-once** — dedupe on
  the stable `feed_item_id`. See [docs/api/FEED.md](docs/api/FEED.md).

## Annulment semantics

```text
CANCELLATION_RELATION_OBSERVED  ≠  cancelled_notice_raw_observed
AMBIGUOUS                       ≠  best guess
```

```python
radar.annulment_status("ps:amb")       # AMBIGUOUS + all candidates
radar.require_authoritative("ps:amb")  # raises AmbiguousAnnulment
```

## Coverage

Current production universe: **`itf2026-v1` — 60 issuers** (ITF-scope,
not "all Spanish issuers"). `radar.coverage()` exposes separate
denominators — acquisition / document / template / semantic parse /
ledger — instead of one ambiguous percentage. Production scale
(reference): 34,981 notices, 158,083 ledger events, 179,129 feed
items.

## Provenance

```text
FeedItem / API object → LedgerEvent → SourceFact → Notice
      → NoticeObservation → raw_sha256 → CNMV source
```

See [PROVENANCE.md](PROVENANCE.md) and `examples/provenance.py`.

## Installation

```bash
pip install ownership-radar        # PyPI (when published)
pip install .                      # from a checkout
```

Requires Python ≥3.10; single runtime dependency `pdfminer.six`.

## Repository layout

```text
ownership_radar/   library + public API/CLI
tests/             contract + regression tests
docs/              model, API, ADRs, gates
corpus/            parser corpus manifests/oracles (raws not shipped)
probe/             G0 acquisition probe — preserved evidence,
                   not a runtime dependency
scripts/           dataset/universe tooling (incl. demo builder)
examples/          runnable API/feed examples
demo/              generated demo dataset (see DATA-NOTICE.md)
data/              local crawl output — gitignored
ownership_radar/seeds/  frozen issuer-universe seeds (shipped in the
                   package)
```

## Data / reuse notice

`LICENSE` (MIT) covers **code only**. CNMV source terms and the
raw-document policy live in [DATA-NOTICE.md](DATA-NOTICE.md) — raw
CNMV documents are **not** redistributed; the demo dataset is
synthetic.

## Known limitations

- Historical completeness is **not externally proven** for every
  CNMV surface (legacy `nod_legacy`, per-holder `ps`/`ac` grids).
- Legacy/scanned documents may be `UNSUPPORTED_TEMPLATE` (fail-closed,
  never OCR-guessed).
- Raw CNMV documents are not redistributed.
- No global physical-person identity resolution — declarants are
  stored raw, scoped per issuer. No fuzzy issuer/person matching.
- Three real ANNULS chains are ambiguous and fail closed.
- The free-text cancellation-letter extractor is not yet implemented
  (measured: marginal yield — see G6-A4).
- Universe is `itf2026-v1` / 60 issuers today.

## Project status & roadmap

```text
G1 Evidence & Notice Core ............... done
G2 NOD event parser ..................... PASS
G3 Significant holdings + treasury ...... PASS
G4 Bitemporal ledger .................... PASS
G5 Production scale-out (60 issuers) .... PASS
G6 Public API + CLI + incremental feed .. PASS
R1 Public release engineering ........... this release
```

Likely next (not committed): wider issuer universe, legacy/OCR
support, additional CNMV families, a web layer — driven by real use.

## Documentation

```text
docs/ARCHITECTURE.md          end-to-end design
docs/api/                     PYTHON, CLI, FEED, ATOM,
                              TEMPORAL-QUERIES, COVERAGE, PROVENANCE
docs/model/                   LEDGER, FEED-SEMANTICS, event taxonomy
docs/decisions/               ADRs (event identity, bitemporal
                              queries, feed identity/cursor)
docs/gates/                   frozen gate contracts + results
CHANGELOG.md                  release history
SECURITY.md                   reporting + supported versions
CONTRIBUTING.md               development setup + rules
```

## License

[MIT](LICENSE) — code only. Data/source terms: [DATA-NOTICE.md](DATA-NOTICE.md).
