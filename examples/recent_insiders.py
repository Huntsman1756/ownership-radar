"""Recent insider transactions across the demo dataset.

Usage:  python examples/recent_insiders.py [db_path]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
from ownership_radar import OwnershipRadar  # noqa:E402

DB = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.join("demo", "ownership-radar-demo.sqlite")

radar = OwnershipRadar.open(DB)
for tx in radar.recent_insider_transactions(limit=5).items:
    print(f"{tx.transaction_date}  {tx.issuer_id}  "
          f"{tx.person_name_raw or '-':28}  "
          f"{tx.normalized_event_type or '?':4}  "
          f"{tx.declared_aggregate_price} {tx.price_currency}")
