"""Significant-holding disclosures for one issuer.

Usage:  python examples/issuer_holdings.py [issuer] [db_path]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
from ownership_radar import OwnershipRadar  # noqa:E402

issuer = sys.argv[1] if len(sys.argv) > 1 else "SAN"
DB = sys.argv[2] if len(sys.argv) > 2 else \
    os.path.join("demo", "ownership-radar-demo.sqlite")

radar = OwnershipRadar.open(DB)
res = radar.company(issuer).significant_holdings()
print(f"{res.count} significant-holding disclosure(s) "
      f"[{res.history_mode}]")
for d in res.items:
    print(f"  {d.notice_key}  {d.obliged_subject}  "
          f"threshold_date={d.threshold_date}  "
          f"current={d.position_current}")
