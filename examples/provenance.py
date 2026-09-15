"""End-to-end provenance: feed item -> event -> notice -> raw_sha256.

Usage:  python examples/provenance.py [db_path]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
from ownership_radar import OwnershipRadar  # noqa:E402

DB = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.join("demo", "ownership-radar-demo.sqlite")

radar = OwnershipRadar.open(DB)
res = radar.feed(item_type="INSIDER_TRANSACTION_OBSERVED", limit=1)
item = res.items[0]
print(f"FeedItem    {item.feed_item_id}")
print(f"  type      {item.feed_item_type}")
print(f"  observed  {item.observed_at}")
print(f"  notice    {item.notice_key}")
print(f"  event     {item.event_id}  basis={item.event_basis}")
p = item.provenance()
print(f"Provenance  notice={p.notice_key}")
print(f"  raw_sha256  {p.raw_sha256}")
print(f"  source_url  {p.source_url_canonical}")
print(f"  parser      {p.semantic_parser_version}")
print(f"  rule        {p.rule_id} v{p.derivation_version}")
