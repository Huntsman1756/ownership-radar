# ADR G2 — PDF text extraction library

Status: accepted (G2).

## Context

G2 parses CNMV NOD PDFs (EU 2016/523 bilingual form rendered by CNMV).
Requirements from the gate contract: permissive license, deterministic
local extraction, no cloud, no OCR, no LLM.

## Candidates

| Candidate | License | Verdict |
|---|---|---|
| **pdfminer.six 20260107** | MIT | **Selected** — pure Python, per-character coordinates (LTChar), deterministic; word/line reconstruction is under our control |
| pypdf 6.x | BSD | Rejected — text extraction API offers no stable positional primitives for grid reconstruction |
| PyMuPDF 1.28 | AGPL-3.0 / commercial | Rejected — AGPL incompatible with redistribution of a permissively licensed tool |
| poppler `pdftotext` | external binary (GPL) | Rejected as runtime dep — not present on a clean clone; kept only as a manual inspection aid during development |

## Approach

`ownership_radar/nodpdf.py` uses pdfminer `LTChar` objects: characters
are clustered into physical lines by y coordinate and into fields by x
gaps. The parser consumes a line stream, so unit tests can feed
synthetic text fixtures without any PDF dependency or real CNMV
content.

## Known limitations

- Scanned/image-only PDFs yield no LTChars → `UNSUPPORTED_NO_TEXT_LAYER`
  (no OCR, per contract).
- pdfminer version changes may alter char ordering: pinned in
  `requirements.txt`; determinism gate G2-15 covers same-version
  reproducibility.
