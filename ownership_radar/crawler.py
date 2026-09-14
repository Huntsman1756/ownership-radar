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
UA = "OwnershipRadarES/0.1 (evidence-layer crawler; low frequency; see CRAWLING-POLICY.md)"

_seq = 0


class Fetcher:
    def __init__(self, run_id, raw_root):
        self.run_id = run_id
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj))
        self.op.addheaders = [("User-Agent", UA)]
        self.outdir = os.path.join(raw_root, run_id)
        os.makedirs(self.outdir, exist_ok=True)
        self.n = 0
        self.log = []

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
                body = resp.read()
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
                with open(os.path.join(self.outdir, fn), "wb") as f:
                    f.write(body)
                meta["raw_file"] = f"{self.run_id}/{fn}"
                with open(os.path.join(self.outdir, fn + ".meta.json"),
                          "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=1)
                self.log.append(meta)
                time.sleep(DELAY_S)
                return meta, body
            except Exception as e:  # noqa
                last_err = repr(e)
                time.sleep(BACKOFF_S * (attempt + 1))
        meta = {"seq": seq, "run_id": self.run_id, "requested_url": url,
                "status": "ERROR", "error": last_err,
                "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "note": note}
        self.log.append(meta)
        return meta, b""
