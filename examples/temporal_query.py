"""known_at vs effective_at — the two time axes.

ps:old is ANNULS'd by ps:new. The relation was *observed* at
2024-06-01 (reconciliation) — before that observation the ledger saw
ps:old as active. AS_KNOWN_AT(2024-01-10) returns what was known
then, never reconstructed history.

Usage:  python examples/temporal_query.py [db_path]
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
from ownership_radar import OwnershipRadar  # noqa:E402

DB = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.join("demo", "ownership-radar-demo.sqlite")

radar = OwnershipRadar.open(DB)
before = datetime(2024, 1, 10, tzinfo=timezone.utc)
after = datetime(2024, 6, 2, tzinfo=timezone.utc)

for label, kw in (("known_at = 2024-01-10 (before annulment seen)",
                   dict(known_at=before)),
                  ("known_at = 2024-06-02 (after annulment seen)",
                   dict(known_at=after))):
    res = radar.company("SAN").significant_holdings(**kw)
    keys = sorted(d.notice_key for d in res.items)
    print(f"{label}\n  [{res.history_mode}] holdings: {keys}")
