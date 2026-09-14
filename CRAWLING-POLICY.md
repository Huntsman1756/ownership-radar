# CRAWLING-POLICY

Self-imposed policy — CNMV publishes no official rate limit and we do
not claim one exists.

- Sequential requests only; ~0.9 s minimum spacing (DELAY_S).
- GET only. No form POSTs, no session-guard or CVFE circumvention,
  no captcha handling, no concurrent workers.
- Max 3 retries with linear backoff (≥5 s); errors are recorded as
  failed observations, never silently dropped.
- Descriptive User-Agent identifying the crawler.
- Every fetch is persisted immutably (raw bytes + meta) before parsing.
- Bounded traversals: date-windowed queries (`fechad`/`fechah`) for the
  nod surface; per-holder grids elsewhere; dedup by `notice_key`.
- Re-crawls are idempotent: canonical projection is UPSERTed, history
  is append-only.
