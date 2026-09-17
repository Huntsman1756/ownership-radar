import json
import os
import sys

from .cli import run, DB_PATH


def main():
    args = sys.argv[1:]
    if args and args[0] == "ledger":
        _ledger(args[1:])
        return
    if args and args[0] == "ingest":
        _ingest(args[1:])
        return
    if args and args[0] == "crawl":
        run()
        return
    # public G6-B CLI is the default surface
    from . import public_cli
    sys.exit(public_cli.main(args))


def _ingest(args):
    """Production ingestion — separate DB under data/production/."""
    from . import coverage, ingest, ledger, poller, store, universe
    db = os.environ.get("RADAR_PROD_DB", ingest.DB_PATH)
    u = universe.load_universe()
    cmd = args[0] if args else "report"
    if cmd in ("report", "invariants") and not os.path.exists(db):
        print("error: dataset not found: " + db, file=sys.stderr)
        sys.exit(1)
    cx = store.init_db(db)
    # read commands must not mutate the dataset — the universe seed is
    # persisted only by commands that write observations
    if cmd in ("backfill", "reconcile", "poll", "materialize"):
        universe.persist_universe(cx, u[0])
    if cmd == "backfill":
        ids = _opt(args, "--issuers")
        sub = {k: u[1][k] for k in ids.split(",")} if ids else None
        rid, stats = ingest.backfill(
            db, u, issuers=sub,
            docs="--no-docs" not in args,
            filing_since=_opt(args, "--docs-since"),
            run_id=_opt(args, "--run-id"))
        print(json.dumps({"run_id": rid}, indent=1))
    elif cmd == "reconcile":
        rid, stats = ingest.reconcile(db, u)
        print(json.dumps({"run_id": rid, "new_notices":
                          stats["new_notices"]}, indent=1))
    elif cmd == "poll":
        rid, stats = poller.run(db, u)
        print(json.dumps({"run_id": rid, "stats": stats},
                         indent=1, ensure_ascii=False))
    elif cmd == "report":
        print(json.dumps(coverage.report(cx, u),
                         indent=1, ensure_ascii=False))
    elif cmd == "invariants":
        print(json.dumps(coverage.invariants(cx), indent=1))
    elif cmd == "materialize":
        print(ledger.materialize(cx)["digest"])
    else:
        print("usage: ingest backfill|reconcile|poll|report|"
              "invariants|materialize")
        sys.exit(2)


def _ledger(args):
    """Internal ledger CLI — validation surface only, not a product."""
    from . import ledger, store
    db = os.environ.get("RADAR_DB", DB_PATH)
    cx = store.init_db(db)
    cmd = args[0] if args else "build"
    if cmd == "build":
        out = ledger.materialize(cx)
        print(json.dumps(out, indent=1))
    elif cmd == "events":
        issuer = _opt(args, "--issuer")
        known = _opt(args, "--known-at")
        eff = _opt(args, "--effective-at")
        mode = "AS_KNOWN_AT" if known else \
            "CURRENT_KNOWLEDGE_RECONSTRUCTED"
        print(json.dumps(ledger.events_for_issuer(
            cx, issuer, mode=mode, effective_at=eff,
            known_at=known), indent=1, ensure_ascii=False))
    elif cmd == "state":
        issuer = _opt(args, "--issuer")
        known = _opt(args, "--known-at")
        print(json.dumps(ledger.state_for_issuer(
            cx, issuer, known_at=known), indent=1, ensure_ascii=False))
    elif cmd == "provenance":
        print(json.dumps(ledger.provenance(cx, args[1] if len(
            args) > 1 else None), indent=1, ensure_ascii=False))
    elif cmd == "digest":
        print(ledger.ledger_digest(cx))
    else:
        print("usage: ledger build|events|state|provenance|digest")
        sys.exit(2)


def _opt(args, name):
    return args[args.index(name) + 1] if name in args else None


if __name__ == "__main__":
    main()
