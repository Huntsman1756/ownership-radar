# PROVENANCE — end to end

Every public answer can be walked back to the official CNMV
representation the system observed:

```text
FeedItem / API object
      │  feed_item_id / event_id / fact_id
      ▼
LedgerEvent          event_basis = SOURCE_DECLARED | DETERMINISTIC_DERIVATION
      │  source_fact_id, rule_id + derivation_version
      ▼
SourceFact           deterministic fact_id, semantic_parser(_version),
      │              raw_sha256, first_observed_at
      ▼
Notice               notice_key = (source_surface, registration_number)
      │
      ▼
NoticeObservation    append-only: run_id, observed_at,
      │              source_url_observed / source_url_canonical,
      │              present_in_source / SOURCE_DISAPPEARANCE_OBSERVED
      ▼
raw_sha256           content-addressed raw capture (local, not
      │              redistributed — see DATA-NOTICE.md)
      ▼
CNMV source          official listing / filing document
```

`radar.notice(key).provenance()` and `FeedItem.provenance()` expose
this chain programmatically; `examples/provenance.py` walks a real
item end to end.

## What is recorded per observation

- `run_id` of the `crawl_run` (typed BACKFILL / INCREMENTAL /
  RECONCILIATION)
- `observed_at` (UTC, millisecond precision)
- `source_url_observed` (as requested) and `source_url_canonical`
  (final URL after redirects)
- HTTP status + response headers (in run/raw metadata)
- raw bytes on disk (`data/raw/…`), immutable, `raw_sha256`
- `normalized_sha256` — hash of normalized **content** fields only;
  observation context (e.g. ephemeral `qS` session tokens in URLs)
  is provenance, not content, and never enters the content hash
- `semantic_parser` + `semantic_parser_version`

Raw captures are write-once. Linked documents use deterministic
per-document `verdocumento/ver?e=` tokens (proven durable in G0);
they are re-resolved from listings on each crawl rather than treated
as permanent URLs — provenance tokens, documented as such.

## Three clocks

```text
effective_date   the economic/regulatory date the fact declares
filing_date      the CNMV registry date
observed_at      when Ownership Radar observed it (run-scoped)
```

State before the first observation is `RECONSTRUCTED_HISTORY`;
from then on `OBSERVED_HISTORY` (`AS_KNOWN_AT` queries). Feed items
anchor on `observed_at` — publication time is observation time,
never the economic date.
