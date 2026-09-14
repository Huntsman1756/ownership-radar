"""Parse the G3 corpus (corpus/manifests/g3_manifest.json) into the
G3 semantic tables and emit a canonical-digest report.

PS notices go through pspdf (significant-holding position disclosure —
never a trade), AC notices through acpdf (treasury operations flow +
resulting stock + declared 1% trigger). Unsupported templates are
persisted with their parse_status; they are not silently dropped.

Two runs must produce byte-identical digests (G3-C06).
"""
import hashlib
import json
import os
import sys
import warnings
import logging
from collections import Counter
from datetime import datetime, timezone

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ownership_radar import pspdf, acpdf, store  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "corpus", "manifests", "g3_manifest.json")
DB = os.path.join(ROOT, "corpus", "corpus.sqlite")


def canonical_digest(p):
    keep = {k: v for k, v in p.items() if k != "parsed_at"}
    return hashlib.sha256(json.dumps(
        keep, sort_keys=True, ensure_ascii=False,
        default=str).encode()).hexdigest()


def run(tag=""):
    m = json.load(open(MANIFEST, encoding="utf-8"))
    cx = store.init_db(DB)
    report = []
    for surface, parser in (("ps", pspdf), ("ac", acpdf)):
        for split in ("dev", "holdout"):
            key = f"{surface}_{split}"
            for e in m.get(key) or []:
                path = os.path.join(ROOT, e["file"]) \
                    if e.get("file") else None
                if not path or not os.path.isfile(path):
                    report.append({"notice_key": e["notice_key"],
                                   "split": key, "status":
                                   e.get("error") or "MISSING_FILE"})
                    continue
                p = parser.parse_pdf(open(path, "rb").read())
                if surface == "ps":
                    store.store_ps_semantic(cx, e["notice_key"], p,
                                            corpus_split=split)
                else:
                    store.store_ac_semantic(cx, e["notice_key"], p,
                                            corpus_split=split)
                report.append({
                    "notice_key": e["notice_key"], "split": key,
                    "file": e["file"], "doc_sha256": p.get("doc_sha256"),
                    "status": p["parse_status"],
                    "template": p.get("regulatory_template"),
                    "unmapped": p.get("unmapped"),
                    "digest": canonical_digest(p)})
    cx.commit()
    out = os.path.join(ROOT, "corpus", f"g3_parse_report{tag}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"parsed_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
            "parsers": {"ps": pspdf.SEMANTIC_PARSER_VERSION,
                        "ac": acpdf.SEMANTIC_PARSER_VERSION},
            "results": report}, f, ensure_ascii=False, indent=1)
    print(json.dumps(Counter(r["status"] for r in report), indent=1))
    return report


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "")
