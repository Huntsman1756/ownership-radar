# ADR-G6-FEED-CURSOR — cursor format and semantics

Status: accepted (G6-C)

## Format

```text
v1.<base64url(JSON)>
JSON = {
  "k":  [observed_at, item_key],   keyset position (exclusive)
  "w":  observed_at | null,        snapshot watermark (inclusive bound)
  "q":  sha256(query filter set)[:16],
  "dv": dataset_version
}
```

Opaque to consumers; URL-safe; survives process restarts and DB
reopens; contains no rowid or process state.

## Semantics

- **Keyset pagination** on `(observed_at, item_key)` — never OFFSET,
  never `observed_at > t` alone. Ties at one timestamp paginate
  exactly: `observed_at > k0 OR (observed_at = k0 AND item_key > k1)`.
- **`cursor=None` → beginning of the selected feed** (frozen).
  `feed_cursor_latest()` / `--from-latest` → position after the
  current maximum, unbounded watermark: future items flow in.
- **Watermark**: the first page of a traversal fixes `w` at the
  current `MAX(observed_at)` of the filtered scope and carries it in
  the cursor; subsequent pages are bounded `observed_at <= w`. Items
  arriving mid-traversal cannot reorder or inject into the active
  read — they appear on the *next* traversal.
- **Query-bound** (`q`): reusing a cursor with a different
  `issuer`/`item_type`/`include_backfill` set raises
  `CursorDatasetMismatch` — no silent reuse across query shapes.
- **Dataset-bound** (`dv`): a cursor issued against a different
  dataset generation raises `CursorDatasetMismatch`.
- **Versioned**: an unknown prefix raises
  `UnsupportedCursorVersion`; malformed payloads raise
  `InvalidCursor`. Incompatible future changes must not silently
  reinterpret old cursors.

## Error taxonomy

```text
InvalidCursor                malformed / undecodable
UnsupportedCursorVersion     prefix != v1
CursorDatasetMismatch        query set or dataset version differs
```
