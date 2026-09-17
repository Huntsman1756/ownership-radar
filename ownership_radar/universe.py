"""Issuer universe — versioned seed + resolution boundary.

The product crawls a *defined* universe, not "whatever the search form
returns". A universe is a frozen seed file (seeds/<version>.json,
shipped inside the package) with its own content_sha256; production
runs record which version they executed against.

Identity policy: issuer_id = official NIF. Tickers live in
`issuer_alias` as conveniences only — never identity, never fuzzy.
"""
import json
import os

UNIVERSE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "seeds")
DEFAULT_UNIVERSE = "itf2026-v1"

# Market tickers, source-annotated conveniences. Coverage: only
# issuers whose common short name is unambiguous; absence of an alias
# is normal, not an error.
TICKER_ALIASES = {
    "A01004324": "VID", "A08000143": "SAB", "A08001851": "ANA",
    "A08015497": "NTGY", "A08017535": "CMO", "A08055741": "MAP",
    "A08168064": "GCO", "A08663619": "CABK", "A15075062": "ITX",
    "A17728593": "FDR", "A20001020": "CAF", "A20014452": "CIE",
    "A28004885": "ACS", "A28013811": "SCYR", "A28015865": "TEF",
    "A28023430": "ELE", "A28027399": "COL", "A28037224": "FCC",
    "A28041283": "ROVI", "A28092583": "TRE", "A28157360": "BKT",
    "A28164754": "DIA", "A28250777": "ACX", "A28294726": "ENG",
    "A28430882": "PSG", "A28599033": "IDR", "A31065501": "VIS",
    "A39000013": "SAN", "A47412333": "EBRO", "A48004360": "FAE",
    "A48010615": "IBE", "A48027056": "ENO", "A48265169": "BBVA",
    "A48943864": "GEST", "A58389123": "GRF", "A58869389": "ALM",
    "A64907306": "CLNX", "A66674904": "PUIG", "A74219304": "EDPR",
    "A78003662": "RED", "A78267176": "PHM", "A78304516": "MEL",
    "A78374725": "REP", "A78839271": "A3M", "A80871031": "LDA",
    "A81787889": "RLIA", "A83511501": "SLR", "A84236934": "AMS",
    "A85130821": "GRE", "A85483311": "ANE", "A85845535": "IAG",
    "A86212420": "AENA", "A86977790": "MRL", "A87008579": "LOG",
    "A87471264": "MVC", "A87586483": "AEDAS", "A87959649": "CIRSA",
    "A93139053": "UNI",
}


def load_universe(version=DEFAULT_UNIVERSE, directory=UNIVERSE_DIR):
    """Load a frozen universe seed. Returns (meta, issuers dict keyed
    by issuer_id). Raises FileNotFoundError for unknown versions —
    a run must never silently fall back to a different universe."""
    path = os.path.join(directory, version + ".json")
    with open(path, encoding="utf-8") as f:
        seed = json.load(f)
    issuers = {e["issuer_id"]: e for e in seed["issuers"]}
    return seed, issuers


def resolve(issuers, ident):
    """Exact resolution only: NIF, issuer_id or a known alias.
    Returns issuer_id or None. No fuzzy matching anywhere."""
    if ident in issuers:
        return ident
    for iid, e in issuers.items():
        if e.get("nif") == ident:
            return iid
        if TICKER_ALIASES.get(e["nif"]) == ident:
            return iid
        for a in e.get("aliases") or []:
            if a == ident:
                return iid
    return None


def issuer_for_crawler(entry):
    """Shape expected by cnmv.collect_* callers."""
    return {"nif": entry["nif"], "name": entry["name"]}


def persist_universe(cx, seed, aliases=TICKER_ALIASES):
    """Record the universe version + members in the DB (idempotent)."""
    cx.execute("""INSERT OR REPLACE INTO universe_version
                  VALUES(?,?,?,?,?)""",
               (seed["universe_version"], json.dumps(seed["source"],
                                                     ensure_ascii=False),
                seed["generated_at"], seed["content_sha256"],
                seed.get("scope_note")))
    for e in seed["issuers"]:
        cx.execute("""INSERT OR REPLACE INTO universe_issuer
                      VALUES(?,?,?,?,?,?,?)""",
                   (seed["universe_version"], e["issuer_id"], e["nif"],
                    e["name"], json.dumps(e["isins"]), e["identifier_basis"],
                    e["identity_quality"]))
        if e["nif"] in aliases:
            cx.execute("""INSERT OR REPLACE INTO issuer_alias
                          VALUES(?,?,?,?)""",
                       (aliases[e["nif"]], e["issuer_id"], "TICKER",
                        "universe.py:TICKER_ALIASES"))
    cx.commit()
