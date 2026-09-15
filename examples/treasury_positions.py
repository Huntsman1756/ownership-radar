"""Treasury-stock operations vs resulting positions (distinct types).

Usage:  python examples/treasury_positions.py [db_path]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
from ownership_radar import OwnershipRadar  # noqa:E402

DB = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.join("demo", "ownership-radar-demo.sqlite")

radar = OwnershipRadar.open(DB)
for op in radar.treasury_operations().items:
    print(f"op   {op.operation_date}  "
          f"{op.operation_flag:11}  "
          f"shares={op.shares_direct}  price={op.price_direct}")
for pos in radar.treasury_stock_positions().items:
    print(f"pos  {pos.notice_key}  resulting={pos.final_position}")
