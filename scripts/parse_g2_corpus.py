"""Parse the G2 corpus (manifest.json) into the semantic tables.

DEV notices persist into data/radar.sqlite; HOLDOUT into
corpus/corpus.sqlite. Emits a per-parse canonical digest so two runs
can be compared byte-for-byte (determinism gate G2-15).
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ownership_radar import nodpdf, store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "corpus", "manifest.json")


def canonical_digest(p):
    """Order-stable digest of everything semantic the parser produced."""
    keep = {k: v for k, v in p.items() if k != "parsed_at"}
    return hashlib.sha256(json.dumps(
        keep, sort_keys=True, ensure_ascii=False,
        default=str).encode()).hexdigest()


def run(tag=""):
    m = json.load(open(MANIFEST, encoding="utf-8"))
    dbs = {"dev": os.path.join(ROOT, "data", "radar.sqlite"),
           "holdout": os.path.join(ROOT, "corpus", "corpus.sqlite")}
    conns = {k: store.init_db(v) for k, v in dbs.items()}
    report = []
    for split in ("dev", "holdout"):
        for e in m[split]:
            path = os.path.join(ROOT, e["file"])
            if not os.path.isfile(path):
                report.append({"notice_key": e["notice_key"], "split": split,
                               "status": "MISSING_FILE"})
                continue
            p = nodpdf.parse_pdf(open(path, "rb").read())
            store.store_semantic(conns[split], e["notice_key"], p,
                                 corpus_split=split)
            report.append({
                "notice_key": e["notice_key"], "split": split,
                "file": e["file"], "doc_sha256": p.get("doc_sha256"),
                "status": p["parse_status"],
                "template": p.get("regulatory_template"),
                "kind": p.get("notification_kind"),
                "events": len(p["events"]),
                "lines": sum(len(ev["executions"]) for ev in p["events"]),
                "qa": [ev.get("aggregate_qa") for ev in p["events"]],
                "digest": canonical_digest(p)})
    for cx in conns.values():
        cx.commit()
    out = os.path.join(ROOT, "corpus", f"parse_report{tag}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"parsed_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"), "parser": nodpdf.SEMANTIC_PARSER_VERSION,
            "results": report}, f, ensure_ascii=False, indent=1)
    import collections
    print(json.dumps(collections.Counter(
        r["status"] for r in report), indent=1))
    return report


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "")
