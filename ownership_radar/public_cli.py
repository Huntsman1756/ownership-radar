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
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone

from . import __version__
from .api import (AmbiguousIdentifier, InvalidCursor,
                  InvalidTemporalQuery, NotFound, OwnershipRadar,
                  OwnershipRadarError, SCHEMA_VERSION, _enc)

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
        # feed cursor is metadata, not an item — goes to stderr
        nc = getattr(obj, "next_cursor", None)
        if nc:
            print(f"next_cursor={nc}", file=sys.stderr)
    elif fmt == "atom":
        print(_atom(obj))
    else:
        _table(obj)


def _to_jsonable(obj):
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return obj
    return obj


def _atom(result):
    """Atom representation of a FeedResult — same model, same order.
    published/updated = observed_at, NEVER effective_date (§25)."""
    ATOM = "http://www.w3.org/2005/Atom"
    ET.register_namespace("", ATOM)
    feed = ET.Element("{%s}feed" % ATOM)
    dv = getattr(result, "dataset_version", None) or "unknown"
    ET.SubElement(feed, "{%s}title" % ATOM).text = (
        f"Ownership Radar ES — observed feed ({dv})")
    ET.SubElement(feed, "{%s}id" % ATOM).text = (
        "urn:ownership-radar:feed:%s" % dv)
    upd = result.items[-1].observed_at if result.items else None
    ET.SubElement(feed, "{%s}updated" % ATOM).text = (
        upd.isoformat() if upd else "")
    for it in result.items:
        e = ET.SubElement(feed, "{%s}entry" % ATOM)
        ET.SubElement(e, "{%s}id" % ATOM).text = (
            "urn:ownership-radar:%s" % it.feed_item_id)
        title = "%s %s" % (it.feed_item_type, it.notice_key or
                           it.issuer_id or "")
        ET.SubElement(e, "{%s}title" % ATOM).text = title
        obs = it.observed_at.isoformat() if it.observed_at else ""
        ET.SubElement(e, "{%s}published" % ATOM).text = obs
        ET.SubElement(e, "{%s}updated" % ATOM).text = obs
        body = {"feed_item_type": it.feed_item_type,
                "history_class": it.history_class,
                "run_type": it.run_type, "issuer_id": it.issuer_id,
                "notice_key": it.notice_key,
                "event_id": it.event_id,
                "effective_date": it.effective_date,
                "filing_date": it.filing_date,
                "event_basis": it.event_basis,
                "annulment_status": it.annulment_status,
                "summary": it.summary}
        c = ET.SubElement(e, "{%s}content" % ATOM)
        c.set("type", "application/json")
        c.text = json.dumps(body, default=_enc, ensure_ascii=False)
    return ET.tostring(feed, encoding="unicode")


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
    p.add_argument("--format", choices=("table", "json", "jsonl",
                                        "atom"), default="table")
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
    for flag, kw in (("--format", {"choices": ("table", "json",
                                              "jsonl", "atom")}),
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
    c = sub.add_parser("feed", parents=[common],
                       help="newly-observed information feed "
                            "(observed_at axis, never effective)")
    c.add_argument("--issuer", default=None)
    c.add_argument("--type", dest="item_type", default=None)
    c.add_argument("--include-backfill", action="store_true")
    c.add_argument("--from-latest", action="store_true",
                   help="start after everything currently observed")
    c = sub.add_parser("feed-cursor-latest", parents=[common],
                       help="print a cursor positioned after all "
                            "currently observed items")
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
        elif args.cmd == "feed":
            cursor = args.cursor
            if args.from_latest:
                cursor = radar.feed_cursor_latest()
            out = radar.feed(
                cursor=cursor, limit=args.limit,
                issuer=args.issuer, item_type=args.item_type,
                include_backfill=args.include_backfill)
        elif args.cmd == "feed-cursor-latest":
            print(radar.feed_cursor_latest())
            return 0
        else:
            return 2
    except NotFound as e:
        print(f"not found: {e}", file=sys.stderr)
        return 1
    except AmbiguousIdentifier as e:
        print(f"ambiguous identifier: {e}", file=sys.stderr)
        return 1
    except (InvalidTemporalQuery, InvalidCursor,
            OwnershipRadarError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    _emit(out, args.format)
    return 0


if __name__ == "__main__":
    sys.exit(main())
