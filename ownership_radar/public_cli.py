"""Public CLI — G6-B machine surface.

    ownership-radar company SAN --format json
    ownership-radar insiders SAN --known-at 2026-01-01
    ownership-radar notice ps:2021016444 --format jsonl

Contract:
  - stdout carries ONLY the requested output (table / JSON / JSONL).
    Diagnostics and errors go to stderr; JSON stdout is always
    parseable and carries schema_version.
  - Temporal filters are --known-at / --effective-at only.
    There is no --date.
  - Exit codes: 0 ok, 1 error, 2 usage.
"""
import argparse
import json
import os
import sys
from datetime import date, datetime, timezone

from . import __version__
from .api import (AmbiguousIdentifier, InvalidTemporalQuery, NotFound,
                  OwnershipRadar, OwnershipRadarError, SCHEMA_VERSION,
                  _enc)

DEFAULT_DB = os.environ.get(
    "RADAR_DB",
    os.path.join("data", "production", "ownership-radar.sqlite"))


def _parse_known_at(v):
    if not v:
        return None
    d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _parse_effective_at(v):
    return date.fromisoformat(v) if v else None


def _emit(obj, fmt):
    """stdout carries only the payload."""
    if fmt == "json":
        env = {"schema_version": SCHEMA_VERSION,
               "api_version": __version__,
               "data": _to_jsonable(obj)}
        print(json.dumps(env, default=_enc, ensure_ascii=False,
                         indent=1))
    elif fmt == "jsonl":
        items = getattr(obj, "items", None)
        seq = list(items) if items is not None else [obj]
        for it in seq:
            env = {"schema_version": SCHEMA_VERSION,
                   "data": _to_jsonable(it)}
            print(json.dumps(env, default=_enc, ensure_ascii=False))
    else:
        _table(obj)


def _to_jsonable(obj):
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return obj
    return obj


def _table(obj):
    """Minimal human-readable rendering."""
    if hasattr(obj, "items"):
        print(f"[{obj.history_mode}] count={obj.count} "
              f"has_more={obj.has_more}")
        for it in obj.items:
            if hasattr(it, "to_dict"):
                d = it.to_dict()
                head = (d.get("notice_key") or d.get("event_id") or
                        d.get("issuer_id") or "")
                tail = {k: v for k, v in d.items()
                        if v is not None and k not in
                        ("notice_key", "event_id")}
                print(f"  {head}  {tail}")
            else:
                print(" ", it)
        if obj.next_cursor:
            print(f"  next_cursor={obj.next_cursor}")
    elif hasattr(obj, "to_dict"):
        for k, v in obj.to_dict().items():
            print(f"{k:32s} {v}")
    else:
        print(obj)


def build_parser():
    p = argparse.ArgumentParser(
        prog="ownership-radar",
        description="Read-only public API over an Ownership Radar "
                    "dataset. Temporal filters: --known-at (knowledge "
                    "time) and --effective-at (economic time) are "
                    "distinct axes — there is no --date.")
    p.add_argument("--db", default=DEFAULT_DB,
                   help="dataset path (env RADAR_DB)")
    p.add_argument("--format", choices=("table", "json", "jsonl"),
                   default="table")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--cursor", default=None)
    p.add_argument("--known-at", default=None,
                   help="ISO instant; restricts knowledge to "
                        "observations <= this instant")
    p.add_argument("--effective-at", default=None,
                   help="ISO date; restricts to effective_date <= "
                        "this date (knowledge unchanged)")
    p.add_argument("--include-cancelled", action="store_true")
    p.add_argument("--version", action="version",
                   version=f"%(prog)s {__version__} "
                           f"(schema {SCHEMA_VERSION})")
    # common flags accepted both before and after the subcommand:
    # SUPPRESS means an absent child flag never clobbers a value
    # already parsed at the top level.
    common = argparse.ArgumentParser(add_help=False)
    for flag, kw in (("--format", {"choices": ("table", "json", "jsonl")}),
                     ("--limit", {"type": int}),
                     ("--cursor", {}),
                     ("--known-at", {}),
                     ("--effective-at", {}),
                     ("--db", {})):
        common.add_argument(flag, default=argparse.SUPPRESS, **kw)
    common.add_argument("--include-cancelled",
                        action="store_true", default=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("company", parents=[common],
                       help="resolve an issuer exactly")
    c.add_argument("ident")
    sub.add_parser("dataset-info", parents=[common])
    sub.add_parser("coverage", parents=[common])

    for name, helptext in (("insiders", "insider transactions"),
                           ("holdings", "significant-holding "
                                         "disclosures"),
                           ("treasury-operations", "treasury op flow"),
                           ("treasury-positions", "treasury stock "
                                                  "positions"),
                           ("notices", "notices"),
                           ("events", "ledger events")):
        c = sub.add_parser(name, parents=[common], help=helptext)
        c.add_argument("ident")
    c = sub.add_parser("recent-insiders", parents=[common],
                       help="latest insider txns, all issuers")
    c = sub.add_parser("notice", parents=[common],
                       help="one notice by key")
    c.add_argument("notice_key")
    c = sub.add_parser("provenance", parents=[common],
                       help="provenance chain for a notice_key")
    c.add_argument("notice_key")
    return p


def _qkw(args, cancelled=True):
    kw = {"known_at": _parse_known_at(args.known_at),
          "effective_at": _parse_effective_at(args.effective_at),
          "limit": args.limit, "cursor": args.cursor}
    if cancelled:
        kw["include_cancelled"] = args.include_cancelled
    return kw


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        radar = OwnershipRadar.open(args.db)
    except Exception as e:  # noqa
        print(f"error: cannot open dataset {args.db}: {e!r}",
              file=sys.stderr)
        return 1
    try:
        if args.cmd == "company":
            out = radar.company(args.ident)
        elif args.cmd == "dataset-info":
            out = radar.dataset_info()
        elif args.cmd == "coverage":
            out = radar.coverage()
        elif args.cmd == "insiders":
            out = radar.company(args.ident).insider_transactions(
                **_qkw(args))
        elif args.cmd == "holdings":
            out = radar.company(args.ident).significant_holdings(
                **_qkw(args))
        elif args.cmd == "treasury-operations":
            out = radar.company(args.ident).treasury_operations(
                **_qkw(args))
        elif args.cmd == "treasury-positions":
            out = radar.company(args.ident).treasury_stock_positions(
                **_qkw(args))
        elif args.cmd == "notices":
            out = radar.company(args.ident).notices(
                limit=args.limit, cursor=args.cursor,
                known_at=_parse_known_at(args.known_at))
        elif args.cmd == "events":
            out = radar.company(args.ident).events(
                **_qkw(args, cancelled=False))
        elif args.cmd == "recent-insiders":
            out = radar.recent_insider_transactions(**_qkw(args))
        elif args.cmd == "notice":
            n = radar.notice(args.notice_key)
            out = {"notice": _to_jsonable(n),
                   "annulment": n.annulment_status().to_dict(),
                   "authoritative": n.current_authoritative().to_dict()}
        elif args.cmd == "provenance":
            out = radar.notice(args.notice_key).provenance()
        else:
            return 2
    except NotFound as e:
        print(f"not found: {e}", file=sys.stderr)
        return 1
    except AmbiguousIdentifier as e:
        print(f"ambiguous identifier: {e}", file=sys.stderr)
        return 1
    except (InvalidTemporalQuery, OwnershipRadarError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    _emit(out, args.format)
    return 0


if __name__ == "__main__":
    sys.exit(main())
