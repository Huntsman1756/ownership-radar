# PROVENANCE

Every representation obtained from CNMV keeps:

- `run_id` of the crawl_run that observed it
- `retrieved_at` (UTC, millisecond precision)
- `source_url_observed` (as requested) and `source_url_canonical`
  (final URL after redirects)
- HTTP status + full response headers
- raw bytes on disk (`data/raw/<run_id>/NNNNN.<ext>`), immutable,
  `raw_sha256`
- `normalized_sha256` — hash of the normalized **content** fields only
  (observation context such as the observed URL — which may carry
  ephemeral `qS` session tokens — is provenance, not content; mixing it
  into the content hash was G0 defect v0.1.0, fixed in v0.1.1)
- `parser_version`

Raw captures are write-once. The normalized system can always be traced
back to the official representation observed: `notice` →
`notice_observation` rows → `raw/<run_id>/…` file + `.meta.json` →
`raw_sha256`. Documents linked via `verdocumento/ver?e=` use a
deterministic per-document token (proven durable >30h in G0); tokens are
re-resolved from listings on each crawl rather than treated as
permanent URLs.

Bitemporality: `event_date` (document), `filing_date` (registry),
`observed_at` (our run). State before first_observation is
`RECONSTRUCTED_HISTORY`; from then on, `OBSERVED_HISTORY`.
