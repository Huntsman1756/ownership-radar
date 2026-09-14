import json
import os
import sys

from .cli import run, DB_PATH


def main():
    args = sys.argv[1:]
    if args and args[0] == "ledger":
        _ledger(args[1:])
        return
    run()


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


main()
