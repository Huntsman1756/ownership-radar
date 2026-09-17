"""HTTP fetcher enforcing CRAWLING-POLICY.md and writing immutable raw
captures before any parsing happens."""
import http.cookiejar
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

from .store import sha256b

DELAY_S = 0.9
MAX_RETRIES = 3
BACKOFF_S = 5.0
MAX_BODY_BYTES = 256 * 1024 * 1024   # sanity cap; CNMV PDFs are ~MB
UA = "OwnershipRadarES/0.1 (evidence-layer crawler; low frequency; see CRAWLING-POLICY.md)"

_seq = 0


class Fetcher:
    def __init__(self, run_id, raw_root, blob_root=None):
        """blob_root enables content-addressable raw storage: payloads
        land once under blob_root/ab/cd/<sha256>.<ext>; repeated bytes
        are never rewritten — only the per-run meta records the new
        observation."""
        self.run_id = run_id
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj))
        self.op.addheaders = [("User-Agent", UA)]
        self.outdir = os.path.join(raw_root, run_id)
        os.makedirs(self.outdir, exist_ok=True)
        self.blob_root = blob_root
        if blob_root:
            os.makedirs(blob_root, exist_ok=True)
        self.n = 0
        self.log = []

    def _store_payload(self, body, ext, fn):
        sha = sha256b(body)
        if self.blob_root:
            rel = os.path.join(sha[:2], sha[2:4], sha + ext)
            dest = os.path.join(self.blob_root, rel)
            if not os.path.isfile(dest):
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as f:
                    f.write(body)
            return rel, True
        with open(os.path.join(self.outdir, fn), "wb") as f:
            f.write(body)
        return os.path.join(self.run_id, fn), False

    def get(self, url, note=""):
        global _seq
        self.n += 1
        _seq += 1
        seq = _seq
        last_err = None
        for attempt in range(MAX_RETRIES):
            try:
                req = urllib.request.Request(url)
                t0 = datetime.now(timezone.utc)
                resp = self.op.open(req, timeout=120)
                body = resp.read(MAX_BODY_BYTES + 1)
                if len(body) > MAX_BODY_BYTES:
                    raise ValueError("response exceeds %d bytes"
                                     % MAX_BODY_BYTES)
                meta = {
                    "seq": seq, "run_id": self.run_id,
                    "requested_url": url, "final_url": resp.geturl(),
                    "status": resp.status,
                    "retrieved_at": t0.isoformat(timespec="milliseconds"),
                    "content_type": resp.headers.get("Content-Type"),
                    "headers": {k: v for k, v in resp.headers.items()},
                    "raw_sha256": sha256b(body), "raw_bytes": len(body),
                    "note": note, "attempt": attempt + 1,
                }
                ext = ".pdf" if "pdf" in (meta["content_type"] or "") else ".html"
                fn = f"{seq:05d}{ext}"
                rel, deduped = self._store_payload(body, ext, fn)
                meta["raw_file"] = rel
                meta["deduped_blob"] = deduped
                with open(os.path.join(self.outdir, fn + ".meta.json"),
                          "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=1)
                self.log.append(meta)
                time.sleep(DELAY_S)
                return meta, body
            except Exception as e:  # noqa
                last_err = repr(e)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_S * (attempt + 1))
        meta = {"seq": seq, "run_id": self.run_id, "requested_url": url,
                "status": "ERROR", "error": last_err,
                "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "note": note}
        self.log.append(meta)
        return meta, b""
