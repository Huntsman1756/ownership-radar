"""Idempotent feed consumption — replayable, NOT exactly-once.

Consumers deduplicate on feed_item_id: re-reading a cursor range may
return the same items, always with the same identity.

Usage:  python examples/feed_consumer.py [db_path]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
from ownership_radar import OwnershipRadar  # noqa:E402

DB = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.join("demo", "ownership-radar-demo.sqlite")

radar = OwnershipRadar.open(DB)
seen = set()
cursor = None
new_items = 0
while True:
    result = radar.feed(cursor=cursor, limit=10)
    for item in result.items:
        if item.feed_item_id in seen:
            continue                       # safe replay, skip dup
        seen.add(item.feed_item_id)
        new_items += 1
        print(f"{item.observed_at}  {item.feed_item_type:45}  "
              f"{item.notice_key}  [{item.history_class}]")
    if not result.has_more:
        break
    cursor = result.next_cursor

print(f"\n{new_items} new items consumed "
      f"({len(seen)} unique feed_item_id)")
