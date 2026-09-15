"""Public read-only API — G6-B contract layer.

This module is the ONLY supported public surface. Internals
(`store`, `ledger`, `pipeline`, ...) may change without notice;
this layer must not.

Temporal semantics are explicit and never ambiguous:

  known_at=      "what had Ownership Radar observed at that instant?"
                 restricts available knowledge to
                 first_observed_at <= known_at  (AS_KNOWN_AT mode)
  effective_at=  "with the knowledge allowed by the query, what has
                 effective_date <= effective_at?"

Defaults: known_at = latest available knowledge,
effective_at = unbounded — i.e. "everything currently known".

No `date=` parameter exists anywhere. `known_at` never changes
effective dates; `effective_at` never changes available knowledge.
`known_at` earlier than the first observation returns an empty
result with status NO_OBSERVATION_HISTORY — never reconstructed
history.
"""
import base64
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from . import coverage as _coverage
from . import ledger as _ledger

SCHEMA_VERSION = "1"
NO_OBSERVATION_HISTORY = "NO_OBSERVATION_HISTORY"

SOURCE_DECLARED = "SOURCE_DECLARED"
DETERMINISTIC_DERIVATION = "DETERMINISTIC_DERIVATION"


# ----------------------------------------------------------------- errors

class OwnershipRadarError(Exception):
    """Base class for all public API errors."""


class NotFound(OwnershipRadarError):
    pass


class AmbiguousIdentifier(OwnershipRadarError):
    pass


class InvalidTemporalQuery(OwnershipRadarError):
    pass


class UnsupportedQuery(OwnershipRadarError):
    pass


class AmbiguousAnnulment(OwnershipRadarError):
    pass


class DataIntegrityError(OwnershipRadarError):
    pass


# ----------------------------------------------------------------- coercion

def _dec(v):
    """Exact decimal from stored TEXT. Never float."""
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return None


def _date(v):
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _dt(v):
    """Timezone-aware datetime. Observations carry absolute instants."""
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _json(v):
    return json.loads(v) if v else None


def _enc(obj):
    """Lossless JSON encoder: Decimal -> str, date/datetime -> ISO."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    raise TypeError(repr(obj))


# ----------------------------------------------------------------- objects

@dataclass(frozen=True)
class Provenance:
    """event/fact -> semantic parser -> notice -> observation -> raw."""
    notice_key: str
    registration_number: str
    source_surface: str
    source_url_canonical: Optional[str]
    raw_sha256: Optional[str]
    first_observed_at: Optional[datetime]
    semantic_parser: Optional[str]
    semantic_parser_version: Optional[str]
    rule_id: Optional[str] = None
    derivation_version: Optional[str] = None

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}


@dataclass(frozen=True)
class AnnulmentStatus:
    """Public annulment view. AMBIGUOUS keeps every candidate —
    resolution to a single terminal is never performed."""
    status: str                    # NONE | RESOLVED | AMBIGUOUS | CYCLE
    annulled_notice: str
    annulling_notices: tuple
    terminal: Optional[str]
    detail: Optional[str] = None
    cancellation_relation_observed: bool = False
    cancelled_notice_raw_observed: bool = False

    def to_dict(self):
        return {"status": self.status,
                "annulled_notice": self.annulled_notice,
                "annulling_notices": list(self.annulling_notices),
                "terminal": self.terminal, "detail": self.detail,
                "cancellation_relation_observed":
                self.cancellation_relation_observed,
                "cancelled_notice_raw_observed":
                self.cancelled_notice_raw_observed}


@dataclass(frozen=True)
class AuthoritativeResult:
    status: str          # AUTHORITATIVE | SUPERSEDED | AMBIGUOUS | CYCLE
    notice_key: str
    authoritative: Optional[str]
    annulling_notices: tuple = ()

    def to_dict(self):
        return {"status": self.status, "notice_key": self.notice_key,
                "authoritative": self.authoritative,
                "annulling_notices": list(self.annulling_notices)}


@dataclass(frozen=True)
class ExecutionLine:
    line_index: int
    price: Optional[Decimal]
    price_raw: Optional[str]
    price_currency: Optional[str]
    volume: Optional[Decimal]
    volume_raw: Optional[str]


@dataclass(frozen=True)
class InsiderTransaction:
    event_id: str
    notice_key: str
    issuer_id: str
    person_name_raw: Optional[str]
    related_pdmr_name_raw: Optional[str]
    role: Optional[str]
    notification_kind: Optional[str]
    transaction_nature_raw: Optional[str]
    normalized_event_type: Optional[str]
    instrument: Optional[str]
    transaction_date: Optional[date]
    filing_date: Optional[date]
    declared_aggregate_volume: Optional[Decimal]
    declared_aggregate_price: Optional[Decimal]
    price_currency: Optional[str]
    executions: tuple
    venue_raw: Optional[str]
    notice_status: Optional[str]
    event_basis: str
    _radar: object = field(repr=False, compare=False, default=None)

    def provenance(self):
        return self._radar._provenance(self.notice_key,
                                       self.event_id)

    def to_dict(self):
        d = {k: v for k, v in self.__dict__.items()
             if not k.startswith("_")}
        d["executions"] = [e.__dict__ for e in self.executions]
        return d


@dataclass(frozen=True)
class SignificantHoldingDisclosure:
    """A position disclosure — never a trade. No BUY/SELL labels are
    derived from percentage differences."""
    notice_key: str
    issuer_id: str
    obliged_subject: Optional[str]
    threshold_date: Optional[date]
    filing_date: Optional[date]
    position_current: Optional[dict]
    position_previous: Optional[dict]
    shares_rows: tuple
    instrument_rows: tuple
    percentage_semantics: Optional[str]
    reasons: dict
    regulatory_template: Optional[str]
    notice_status: Optional[str]
    _radar: object = field(repr=False, compare=False, default=None)

    def provenance(self):
        return self._radar._provenance(self.notice_key)

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()
                if not k.startswith("_")}


@dataclass(frozen=True)
class TreasuryOperation:
    """Section-4 operation FLOW — never a position/stock figure."""
    notice_key: str
    issuer_id: str
    row_index: int
    operation_date: Optional[date]
    operation_flag: Optional[str]
    isin: Optional[str]
    shares_direct: Optional[Decimal]
    price_direct: Optional[Decimal]
    shares_indirect: Optional[Decimal]
    price_indirect: Optional[Decimal]
    filing_date: Optional[date]
    notice_status: Optional[str]
    _radar: object = field(repr=False, compare=False, default=None)

    def provenance(self):
        return self._radar._provenance(self.notice_key)

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()
                if not k.startswith("_")}


@dataclass(frozen=True)
class TreasuryStockPosition:
    """Section-5 resulting STOCK — the position after the reported
    operations, kept separate from the flow."""
    notice_key: str
    issuer_id: str
    notification_date: Optional[date]
    filing_date: Optional[date]
    final_position: Optional[dict]
    reason_acquisitions_1pct: Optional[bool]
    reason_voting_rights_update: Optional[bool]
    regulatory_template: Optional[str]
    notice_status: Optional[str]
    _radar: object = field(repr=False, compare=False, default=None)

    def provenance(self):
        return self._radar._provenance(self.notice_key)

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()
                if not k.startswith("_")}


@dataclass(frozen=True)
class LedgerEvent:
    event_id: str
    event_type: str
    event_basis: str              # SOURCE_DECLARED | DETERMINISTIC_DERIVATION
    issuer_id: Optional[str]
    effective_date: Optional[date]
    filing_date: Optional[date]
    source_notice_key: Optional[str]
    rule_id: Optional[str]
    derivation_version: Optional[str]
    first_observed_at: Optional[datetime]
    payload: Optional[dict]
    _radar: object = field(repr=False, compare=False, default=None)

    def provenance(self):
        return self._radar._provenance(self.source_notice_key,
                                       self.event_id, self.rule_id,
                                       self.derivation_version)

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()
                if not k.startswith("_")}


@dataclass(frozen=True)
class Notice:
    notice_key: str
    source_surface: str
    registration_number: str
    notice_type: str
    issuer_id: Optional[str]
    filing_date: Optional[date]
    regulatory_template: Optional[str]
    notice_status: Optional[str]
    doc_status: Optional[str]
    parse_status: Optional[str]
    raw_available: bool
    first_observed_at: Optional[datetime]
    _radar: object = field(repr=False, compare=False, default=None)

    def annulment_status(self):
        return self._radar._annulment(self.notice_key)

    def current_authoritative(self):
        return self._radar._authoritative(self.notice_key)

    def require_authoritative(self):
        """Strict variant: raises AmbiguousAnnulment on AMBIGUOUS/
        CYCLE instead of returning a status object."""
        r = self.current_authoritative()
        if r.status in ("AMBIGUOUS", "CYCLE"):
            raise AmbiguousAnnulment(
                f"{self.notice_key}: {r.status}, candidates "
                f"{list(r.annulling_notices)}")
        return r

    def provenance(self):
        return self._radar._provenance(self.notice_key)

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()
                if not k.startswith("_")}


@dataclass(frozen=True)
class QueryResult:
    """Paginated public result with explicit query metadata."""
    status: str                   # OK | NO_OBSERVATION_HISTORY
    history_mode: str             # AS_KNOWN_AT |
                                  # CURRENT_KNOWLEDGE_RECONSTRUCTED
    known_at: Optional[datetime]
    effective_at: Optional[date]
    items: tuple
    count: int
    has_more: bool
    next_cursor: Optional[str]
    dataset_version: Optional[str]
    query: str = ""

    def to_dict(self):
        return {"status": self.status, "history_mode":
                self.history_mode, "known_at": self.known_at,
                "effective_at": self.effective_at,
                "count": self.count, "has_more": self.has_more,
                "next_cursor": self.next_cursor,
                "dataset_version": self.dataset_version,
                "query": self.query,
                "items": [i.to_dict() if hasattr(i, "to_dict")
                          else i for i in self.items]}


@dataclass(frozen=True)
class DatasetInfo:
    dataset_version: Optional[str]
    universe_version: Optional[str]
    universe_issuers: int
    schema_version: str
    notices: int
    observations: int
    source_facts: int
    ledger_events: int
    ledger_digest: Optional[str]
    semantic_parser_versions: dict
    derivation_version: Optional[str]
    last_run: Optional[dict]

    def to_dict(self):
        return dict(self.__dict__)


# ----------------------------------------------------------------- cursor

def _cursor_encode(key):
    return base64.urlsafe_b64encode(
        json.dumps(key, separators=(",", ":")).encode()).decode()


def _cursor_decode(cur):
    try:
        return json.loads(base64.urlsafe_b64decode(
            cur.encode()).decode())
    except Exception as e:  # noqa
        raise InvalidTemporalQuery(f"invalid cursor: {e!r}")


# ----------------------------------------------------------------- facade

class OwnershipRadar:
    """Read-only public facade over a dataset file.

        radar = OwnershipRadar.open("ownership-radar.sqlite")
        issuer = radar.company("SAN")

    The connection is opened SQLite read-only: no schema migrations,
    no writes, no network. Ingestion is a separate admin surface."""

    def __init__(self, cx):
        self._cx = cx
        self._earliest = None

    @classmethod
    def open(cls, path):
        uri = "file:%s?mode=ro" % path.replace("\\", "/")
        cx = sqlite3.connect(uri, uri=True)
        cx.execute("PRAGMA query_only=ON")
        return cls(cx)

    # ------------------------------------------------- issuer resolution

    def _resolve_issuer_id(self, ident):
        """Exact resolution: issuer_id/NIF, LEI, ISIN, registered alias.
        1 hit -> id; 0 -> NotFound; >1 distinct -> AmbiguousIdentifier."""
        ident = ident.strip()
        hits = set()
        for (iid,) in self._cx.execute(
                "SELECT DISTINCT issuer_id FROM universe_issuer "
                "WHERE issuer_id=? OR nif=?", (ident, ident)):
            hits.add(iid)
        for (iid,) in self._cx.execute(
                "SELECT issuer_id FROM issuer WHERE nif=? OR lei=?",
                (ident, ident)):
            hits.add(iid)
        for (iid,) in self._cx.execute(
                "SELECT issuer_id FROM issuer_alias WHERE alias=?",
                (ident,)):
            hits.add(iid)
        for iid, js in self._cx.execute(
                "SELECT issuer_id, isins_json FROM universe_issuer"):
            if ident in (_json(js) or []):
                hits.add(iid)
        if not hits:
            raise NotFound(f"issuer identifier not found: {ident}")
        if len(hits) > 1:
            raise AmbiguousIdentifier(
                f"{ident} resolves to {sorted(hits)}")
        return hits.pop()

    def company(self, ident):
        """Exact issuer resolution. Ticker is an alias, never identity."""
        iid = self._resolve_issuer_id(ident)
        u = self._cx.execute(
            "SELECT nif,name_raw,isins_json,identifier_basis,"
            "identity_quality FROM universe_issuer WHERE issuer_id=? "
            "LIMIT 1", (iid,)).fetchone()
        i = self._cx.execute(
            "SELECT lei,name_raw FROM issuer WHERE issuer_id=? LIMIT 1",
            (iid,)).fetchone()
        aliases = sorted(r[0] for r in self._cx.execute(
            "SELECT alias FROM issuer_alias WHERE issuer_id=?", (iid,)))
        nif, name, isins = (u[0], u[1], _json(u[2])) if u else \
            (iid, i[1] if i else iid, [])
        return Issuer(issuer_id=iid, nif=nif, name=name,
                      lei=i[0] if i else None, isins=tuple(isins or ()),
                      aliases=tuple(aliases), _radar=self)

    # ------------------------------------------------- temporal guards

    def _check_known_at(self, known_at):
        """Returns 'AS_KNOWN_AT', 'NO_OBSERVATION_HISTORY' or
        'CURRENT_KNOWLEDGE_RECONSTRUCTED'."""
        if known_at is None:
            return "CURRENT_KNOWLEDGE_RECONSTRUCTED"
        if self._earliest is None:
            self._earliest = self._cx.execute(
                "SELECT MIN(observed_at) FROM notice_observation"
            ).fetchone()[0]
        if self._earliest and known_at.isoformat() < self._earliest:
            return NO_OBSERVATION_HISTORY
        return "AS_KNOWN_AT"

    def _kat(self, known_at):
        return known_at.isoformat() if known_at else None

    def _cancelled_as_of(self, known_at):
        """Notices cancelled under knowledge <= known_at: an ANNULS
        relation whose annulling notice was first observed by then."""
        q = ("SELECT DISTINCT r.annulled_key FROM notice_relation r "
             "JOIN (SELECT notice_key, MIN(observed_at) o FROM "
             "notice_observation GROUP BY notice_key) fo "
             "ON fo.notice_key=r.annulling_key "
             "WHERE r.relation_type='ANNULS'")
        args = []
        if known_at:
            q += " AND fo.o<=?"
            args.append(self._kat(known_at))
        return {r[0] for r in self._cx.execute(q, args)}

    def _dataset_version(self):
        r = self._cx.execute("SELECT universe_version FROM "
                             "universe_version LIMIT 1").fetchone()
        return r[0] if r else None

    def _result(self, items, status, mode, known_at, effective_at,
                has_more, next_cursor, query):
        return QueryResult(
            status=status, history_mode=mode, known_at=known_at,
            effective_at=effective_at, items=tuple(items),
            count=len(items), has_more=has_more,
            next_cursor=next_cursor,
            dataset_version=self._dataset_version(), query=query)

    # ------------------------------------------------- provenance

    def _provenance(self, notice_key, event_id=None, rule_id=None,
                    derivation_version=None):
        if notice_key is None:
            return None
        n = self._cx.execute(
            "SELECT source_registration_number,source_surface FROM "
            "notice WHERE notice_key=?", (notice_key,)).fetchone()
        obs = self._cx.execute(
            "SELECT source_url_canonical,MIN(observed_at) FROM "
            "notice_observation WHERE notice_key=? GROUP BY "
            "notice_key", (notice_key,)).fetchone()
        doc = self._cx.execute(
            "SELECT raw_sha256,semantic_parser_version FROM notice_doc "
            "WHERE notice_key=?", (notice_key,)).fetchone()
        parser = None
        for t in ("nod_notice_semantic", "ps_notice_semantic",
                  "ac_notice_semantic"):
            r = self._cx.execute(
                f"SELECT semantic_parser_version FROM {t} WHERE "
                f"notice_key=?", (notice_key,)).fetchone()
            if r:
                parser = r[0]
                break
        return Provenance(
            notice_key=notice_key,
            registration_number=n[0] if n else notice_key.split(":")[-1],
            source_surface=n[1] if n else None,
            source_url_canonical=obs[0] if obs else None,
            raw_sha256=doc[0] if doc else None,
            first_observed_at=_dt(obs[1]) if obs else None,
            semantic_parser=(notice_key.split(":")[0]
                             if notice_key else None),
            semantic_parser_version=parser or (doc[1] if doc else None),
            rule_id=rule_id, derivation_version=derivation_version)

    # ------------------------------------------------- annulment

    def _annulment(self, notice_key):
        st = _ledger.annulment_status(self._cx, notice_key)
        raw_obs = self._cx.execute(
            "SELECT 1 FROM notice WHERE notice_key=?",
            (notice_key,)).fetchone() is not None
        rel_obs = self._cx.execute(
            "SELECT 1 FROM notice_relation WHERE annulled_key=? AND "
            "relation_type='ANNULS'", (notice_key,)).fetchone() is not None
        return AnnulmentStatus(
            status=st["relation_status"],
            annulled_notice=notice_key,
            annulling_notices=tuple(st["annulling_notices"]),
            terminal=st["terminal"], detail=st.get("detail"),
            cancellation_relation_observed=rel_obs,
            cancelled_notice_raw_observed=raw_obs)

    def _authoritative(self, notice_key):
        r = _ledger.current_authoritative(self._cx, notice_key)
        return AuthoritativeResult(
            status=r["status"], notice_key=notice_key,
            authoritative=r.get("authoritative"),
            annulling_notices=tuple(r.get("annulling_notices") or ()))

    def annulment_status(self, notice_key):
        """Public annulment view for ANY key — including annulled
        notices known only through the relation evidence (never
        observed in a listing, so `notice()` raises NotFound)."""
        return self._annulment(notice_key)

    def current_authoritative(self, notice_key):
        """Resolve a key to its authoritative version. AMBIGUOUS and
        CYCLE are reported, never resolved to a single candidate."""
        return self._authoritative(notice_key)

    def require_authoritative(self, notice_key):
        """Strict variant: raises AmbiguousAnnulment on AMBIGUOUS/
        CYCLE instead of returning a status object."""
        r = self._authoritative(notice_key)
        if r.status in ("AMBIGUOUS", "CYCLE"):
            raise AmbiguousAnnulment(
                f"{notice_key}: {r.status}, candidates "
                f"{list(r.annulling_notices)}")
        return r

    # ------------------------------------------------- notices

    def notice(self, notice_key):
        n = self._cx.execute(
            "SELECT notice_key,source_surface,"
            "source_registration_number,notice_type,issuer_id,"
            "filing_date,regulatory_template,notice_status,doc_token "
            "FROM notice WHERE notice_key=?", (notice_key,)).fetchone()
        if not n:
            raise NotFound(f"notice not found: {notice_key}")
        doc = self._cx.execute(
            "SELECT doc_status,parse_status,raw_sha256 FROM notice_doc "
            "WHERE notice_key=?", (notice_key,)).fetchone()
        fo = self._cx.execute(
            "SELECT MIN(observed_at) FROM notice_observation WHERE "
            "notice_key=?", (notice_key,)).fetchone()[0]
        return Notice(
            notice_key=n[0], source_surface=n[1],
            registration_number=n[2], notice_type=n[3], issuer_id=n[4],
            filing_date=_date(n[5]), regulatory_template=n[6],
            notice_status=n[7],
            doc_status=doc[0] if doc else None,
            parse_status=doc[1] if doc else None,
            raw_available=bool(doc and doc[2]),
            first_observed_at=_dt(fo), _radar=self)

    def notices(self, issuer=None, surface=None, known_at=None,
                limit=200, cursor=None):
        issuer_id = issuer.issuer_id if isinstance(issuer, Issuer) \
            else issuer
        mode = self._check_known_at(known_at)
        if mode == NO_OBSERVATION_HISTORY:
            return self._result([], NO_OBSERVATION_HISTORY, mode,
                                known_at, None, False, None, "notices")
        q = ("SELECT n.notice_key FROM notice n WHERE 1=1")
        args = []
        if issuer_id:
            q += " AND n.issuer_id=?"
            args.append(issuer_id)
        if surface:
            q += " AND n.source_surface=?"
            args.append(surface)
        if known_at:
            q += (" AND EXISTS(SELECT 1 FROM notice_observation o "
                  "WHERE o.notice_key=n.notice_key AND "
                  "o.observed_at<=?)")
            args.append(self._kat(known_at))
        if cursor:
            k = _cursor_decode(cursor)
            q += " AND n.notice_key<?"
            args.append(k[0])
        q += " ORDER BY n.notice_key DESC LIMIT ?"
        args.append(limit + 1)
        keys = [r[0] for r in self._cx.execute(q, args)]
        has_more = len(keys) > limit
        keys = keys[:limit]
        items = [self.notice(k) for k in keys]
        nc = _cursor_encode([keys[-1]]) if has_more and keys else None
        return self._result(items, "OK", mode, known_at, None,
                            has_more, nc, "notices")

    # ------------------------------------------------- ledger events

    def events(self, issuer=None, known_at=None, effective_at=None,
               basis=None, limit=200, cursor=None):
        issuer_id = issuer.issuer_id if isinstance(issuer, Issuer) \
            else issuer
        if basis and basis not in (SOURCE_DECLARED,
                                   DETERMINISTIC_DERIVATION):
            raise InvalidTemporalQuery(
                f"basis must be {SOURCE_DECLARED} or "
                f"{DETERMINISTIC_DERIVATION}")
        mode = self._check_known_at(known_at)
        if mode == NO_OBSERVATION_HISTORY:
            return self._result([], NO_OBSERVATION_HISTORY, mode,
                                known_at, effective_at, False, None,
                                "events")
        q = ("SELECT event_id,event_type,event_basis,issuer_id,"
             "effective_date,filing_date,source_notice_key,rule_id,"
             "derivation_version,payload_json,first_observed_at "
             "FROM ledger_event WHERE 1=1")
        args = []
        if issuer_id:
            q += " AND issuer_id=?"
            args.append(issuer_id)
        if basis:
            q += " AND event_basis=?"
            args.append(basis)
        if effective_at:
            q += " AND effective_date<=?"
            args.append(effective_at.isoformat())
        if known_at:
            q += " AND first_observed_at<=?"
            args.append(self._kat(known_at))
        # keyset cursor on (effective_date DESC, event_id DESC)
        if cursor:
            k = _cursor_decode(cursor)
            q += (" AND (effective_date<? OR (effective_date=? AND "
                  "event_id<?) OR (effective_date IS NULL AND ? IS "
                  "NOT NULL))")
            args += [k[0], k[0], k[1], k[0]]
        q += (" ORDER BY effective_date DESC,event_id DESC LIMIT ?")
        args.append(limit + 1)
        rows = self._cx.execute(q, args).fetchall()
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = [LedgerEvent(
            event_id=r[0], event_type=r[1], event_basis=r[2],
            issuer_id=r[3], effective_date=_date(r[4]),
            filing_date=_date(r[5]), source_notice_key=r[6],
            rule_id=r[7], derivation_version=r[8],
            first_observed_at=_dt(r[10]), payload=_json(r[9]),
            _radar=self) for r in rows]
        nc = None
        if has_more and rows:
            nc = _cursor_encode([rows[-1][4], rows[-1][0]])
        return self._result(items, "OK", mode, known_at, effective_at,
                            has_more, nc, "events")

    # ------------------------------------------------- insider txns

    def insider_transactions(self, issuer=None, known_at=None,
                             effective_at=None, include_cancelled=False,
                             limit=200, cursor=None):
        issuer_id = issuer.issuer_id if isinstance(issuer, Issuer) \
            else issuer
        mode = self._check_known_at(known_at)
        if mode == NO_OBSERVATION_HISTORY:
            return self._result([], NO_OBSERVATION_HISTORY, mode,
                                known_at, effective_at, False, None,
                                "insider_transactions")
        q = ("""SELECT t.event_id,t.notice_key,n.issuer_id,
                s.notifying_party_name_raw,s.related_pdmr_name_raw,
                s.related_pdmr_position_raw,s.notification_kind,
                t.transaction_nature_raw,t.transaction_nature_normalized,
                t.instrument_type_raw,t.transaction_date,
                n.filing_date,t.declared_aggregate_volume,
                t.declared_aggregate_price,t.declared_price_currency,
                t.venue_raw,n.notice_status
                FROM transaction_event t
                JOIN notice n ON n.notice_key=t.notice_key
                LEFT JOIN nod_notice_semantic s
                  ON s.notice_key=t.notice_key
                WHERE n.source_surface='nod'""")
        args = []
        if issuer_id:
            q += " AND n.issuer_id=?"
            args.append(issuer_id)
        if effective_at:
            q += " AND t.transaction_date<=?"
            args.append(effective_at.isoformat())
        if known_at:
            q += (" AND EXISTS(SELECT 1 FROM notice_observation o "
                  "WHERE o.notice_key=t.notice_key AND "
                  "o.observed_at<=?)")
            args.append(self._kat(known_at))
        if cursor:
            k = _cursor_decode(cursor)
            q += (" AND (n.filing_date<? OR (n.filing_date=? AND "
                  "t.event_id<?))")
            args += [k[0], k[0], k[1]]
        q += (" ORDER BY n.filing_date DESC,t.event_id DESC LIMIT ?")
        args.append(limit + 1)
        rows = self._cx.execute(q, args).fetchall()
        cancelled = self._cancelled_as_of(known_at) \
            if not include_cancelled else set()
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = []
        last_key = None
        for r in rows:
            last_key = [r[11], r[0]]
            if r[1] in cancelled:
                continue
            exs = tuple(ExecutionLine(
                line_index=e[0], price=_dec(e[1]), price_raw=e[2],
                price_currency=e[3], volume=_dec(e[4]), volume_raw=e[5])
                for e in self._cx.execute(
                    "SELECT line_index,price,price_raw,price_currency,"
                    "volume,volume_raw FROM execution_line WHERE "
                    "event_id=? ORDER BY line_index", (r[0],)))
            items.append(InsiderTransaction(
                event_id=r[0], notice_key=r[1], issuer_id=r[2],
                person_name_raw=r[3], related_pdmr_name_raw=r[4],
                role=r[5], notification_kind=r[6],
                transaction_nature_raw=r[7],
                normalized_event_type=r[8], instrument=r[9],
                transaction_date=_date(r[10]), filing_date=_date(r[11]),
                declared_aggregate_volume=_dec(r[12]),
                declared_aggregate_price=_dec(r[13]),
                price_currency=r[14], executions=exs,
                venue_raw=r[15], notice_status=r[16],
                event_basis=DETERMINISTIC_DERIVATION, _radar=self))
        nc = _cursor_encode(last_key) if has_more and last_key else None
        return self._result(items, "OK", mode, known_at, effective_at,
                            has_more, nc, "insider_transactions")

    def recent_insider_transactions(self, **kw):
        return self.insider_transactions(**kw)

    # ------------------------------------------------- significant hold.

    def significant_holdings(self, issuer=None, known_at=None,
                             effective_at=None, include_cancelled=False,
                             limit=200, cursor=None):
        issuer_id = issuer.issuer_id if isinstance(issuer, Issuer) \
            else issuer
        mode = self._check_known_at(known_at)
        if mode == NO_OBSERVATION_HISTORY:
            return self._result([], NO_OBSERVATION_HISTORY, mode,
                                known_at, effective_at, False, None,
                                "significant_holdings")
        q = ("""SELECT s.notice_key,n.issuer_id,
                s.obliged_subject_name_raw,s.threshold_date,
                n.filing_date,s.position_current_json,
                s.position_previous_json,s.percentage_semantics,
                s.regulatory_template,n.notice_status,
                s.reason_voting_rights,s.reason_voting_rights_regulated,
                s.reason_instruments,s.reason_instruments_regulated,
                s.reason_issuer_voting_rights_change,s.reason_other,
                s.reason_other_text_raw,s.concerted_agreement
                FROM ps_notice_semantic s
                JOIN notice n ON n.notice_key=s.notice_key
                WHERE s.parse_status IN
                  ('PARSED','PARSED_WITH_UNMAPPED_VALUES')""")
        args = []
        if issuer_id:
            q += " AND n.issuer_id=?"
            args.append(issuer_id)
        if effective_at:
            q += " AND s.threshold_date<=?"
            args.append(effective_at.isoformat())
        if known_at:
            q += (" AND EXISTS(SELECT 1 FROM notice_observation o "
                  "WHERE o.notice_key=s.notice_key AND "
                  "o.observed_at<=?)")
            args.append(self._kat(known_at))
        if cursor:
            k = _cursor_decode(cursor)
            q += " AND s.notice_key<?"
            args.append(k[0])
        q += " ORDER BY s.threshold_date DESC,s.notice_key DESC LIMIT ?"
        args.append(limit + 1)
        rows = self._cx.execute(q, args).fetchall()
        cancelled = self._cancelled_as_of(known_at) \
            if not include_cancelled else set()
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = []
        last_key = None
        for r in rows:
            last_key = [r[0]]
            if r[0] in cancelled:
                continue
            shares = tuple(dict(zip(
                ("isin", "vr_direct", "vr_indirect", "pct_direct",
                 "pct_indirect"), rr)) for rr in self._cx.execute(
                "SELECT isin,vr_direct,vr_indirect,pct_direct,"
                "pct_indirect FROM ps_shares_row WHERE notice_key=? "
                "ORDER BY row_index", (r[0],)))
            insts = tuple(dict(zip(
                ("section", "instrument_type", "voting_rights", "pct"),
                rr)) for rr in self._cx.execute(
                "SELECT section,instrument_type_raw,voting_rights,"
                "pct FROM ps_instrument_row WHERE notice_key=? "
                "ORDER BY section,row_index", (r[0],)))
            reasons = {"voting_rights": bool(r[10]),
                       "voting_rights_regulated": bool(r[11]),
                       "instruments": bool(r[12]),
                       "instruments_regulated": bool(r[13]),
                       "issuer_voting_rights_change": bool(r[14]),
                       "other": bool(r[15]),
                       "other_text": r[16],
                       "concerted_agreement": bool(r[17])}
            items.append(SignificantHoldingDisclosure(
                notice_key=r[0], issuer_id=r[1], obliged_subject=r[2],
                threshold_date=_date(r[3]), filing_date=_date(r[4]),
                position_current=_json(r[5]),
                position_previous=_json(r[6]),
                shares_rows=shares, instrument_rows=insts,
                percentage_semantics=r[7], reasons=reasons,
                regulatory_template=r[8], notice_status=r[9],
                _radar=self))
        nc = _cursor_encode(last_key) if has_more and last_key else None
        return self._result(items, "OK", mode, known_at, effective_at,
                            has_more, nc, "significant_holdings")

    # ------------------------------------------------- treasury

    def treasury_stock_positions(self, issuer=None, known_at=None,
                                 effective_at=None,
                                 include_cancelled=False,
                                 limit=200, cursor=None):
        issuer_id = issuer.issuer_id if isinstance(issuer, Issuer) \
            else issuer
        mode = self._check_known_at(known_at)
        if mode == NO_OBSERVATION_HISTORY:
            return self._result([], NO_OBSERVATION_HISTORY, mode,
                                known_at, effective_at, False, None,
                                "treasury_stock_positions")
        q = ("""SELECT s.notice_key,n.issuer_id,s.notification_date,
                n.filing_date,s.final_position_json,
                s.reason_acquisitions_1pct,
                s.reason_voting_rights_update,s.regulatory_template,
                n.notice_status
                FROM ac_notice_semantic s
                JOIN notice n ON n.notice_key=s.notice_key
                WHERE s.parse_status IN
                  ('PARSED','PARSED_WITH_UNMAPPED_VALUES')
                  AND s.final_position_json IS NOT NULL""")
        args = []
        if issuer_id:
            q += " AND n.issuer_id=?"
            args.append(issuer_id)
        if effective_at:
            q += " AND s.notification_date<=?"
            args.append(effective_at.isoformat())
        if known_at:
            q += (" AND EXISTS(SELECT 1 FROM notice_observation o "
                  "WHERE o.notice_key=s.notice_key AND "
                  "o.observed_at<=?)")
            args.append(self._kat(known_at))
        if cursor:
            k = _cursor_decode(cursor)
            q += " AND s.notice_key<?"
            args.append(k[0])
        q += (" ORDER BY s.notification_date DESC,s.notice_key DESC "
              "LIMIT ?")
        args.append(limit + 1)
        rows = self._cx.execute(q, args).fetchall()
        cancelled = self._cancelled_as_of(known_at) \
            if not include_cancelled else set()
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = [TreasuryStockPosition(
            notice_key=r[0], issuer_id=r[1],
            notification_date=_date(r[2]), filing_date=_date(r[3]),
            final_position=_json(r[4]),
            reason_acquisitions_1pct=bool(r[5]),
            reason_voting_rights_update=bool(r[6]),
            regulatory_template=r[7], notice_status=r[8], _radar=self)
            for r in rows if r[0] not in cancelled]
        nc = (_cursor_encode([rows[-1][0]])
              if has_more and rows else None)
        return self._result(items, "OK", mode, known_at, effective_at,
                            has_more, nc, "treasury_stock_positions")

    def treasury_operations(self, issuer=None, known_at=None,
                            effective_at=None, include_cancelled=False,
                            limit=200, cursor=None):
        issuer_id = issuer.issuer_id if isinstance(issuer, Issuer) \
            else issuer
        mode = self._check_known_at(known_at)
        if mode == NO_OBSERVATION_HISTORY:
            return self._result([], NO_OBSERVATION_HISTORY, mode,
                                known_at, effective_at, False, None,
                                "treasury_operations")
        q = ("""SELECT o.notice_key,n.issuer_id,o.row_index,
                o.operation_date,o.operation_flag_normalized,o.isin,
                o.shares_direct,o.price_direct,o.shares_indirect,
                o.price_indirect,n.filing_date,n.notice_status
                FROM ac_operation o
                JOIN notice n ON n.notice_key=o.notice_key
                JOIN ac_notice_semantic s ON s.notice_key=o.notice_key
                WHERE s.parse_status IN
                  ('PARSED','PARSED_WITH_UNMAPPED_VALUES')""")
        args = []
        if issuer_id:
            q += " AND n.issuer_id=?"
            args.append(issuer_id)
        if effective_at:
            q += " AND o.operation_date<=?"
            args.append(effective_at.isoformat())
        if known_at:
            q += (" AND EXISTS(SELECT 1 FROM notice_observation ob "
                  "WHERE ob.notice_key=o.notice_key AND "
                  "ob.observed_at<=?)")
            args.append(self._kat(known_at))
        if cursor:
            k = _cursor_decode(cursor)
            q += (" AND (o.operation_date<? OR (o.operation_date=? "
                  "AND o.notice_key<?))")
            args += [k[0], k[0], k[1]]
        q += (" ORDER BY o.operation_date DESC,o.notice_key DESC,"
              "o.row_index LIMIT ?")
        args.append(limit + 1)
        rows = self._cx.execute(q, args).fetchall()
        cancelled = self._cancelled_as_of(known_at) \
            if not include_cancelled else set()
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = []
        last_key = None
        for r in rows:
            last_key = [r[3], r[0]]
            if r[0] in cancelled:
                continue
            items.append(TreasuryOperation(
                notice_key=r[0], issuer_id=r[1], row_index=r[2],
                operation_date=_date(r[3]), operation_flag=r[4],
                isin=r[5], shares_direct=_dec(r[6]),
                price_direct=_dec(r[7]), shares_indirect=_dec(r[8]),
                price_indirect=_dec(r[9]), filing_date=_date(r[10]),
                notice_status=r[11], _radar=self))
        nc = _cursor_encode(last_key) if has_more and last_key else None
        return self._result(items, "OK", mode, known_at, effective_at,
                            has_more, nc, "treasury_operations")

    # ------------------------------------------------- dataset / coverage

    def dataset_info(self):
        q = lambda s: self._cx.execute(s).fetchone()[0]
        vers = {}
        for t in ("nod_notice_semantic", "ps_notice_semantic",
                  "ac_notice_semantic"):
            for r in self._cx.execute(
                    f"SELECT semantic_parser_version,COUNT(*) FROM {t} "
                    f"GROUP BY 1"):
                vers[f"{t.split('_')[0]}:{r[0]}"] = r[1]
        last = self._cx.execute(
            "SELECT run_id,run_type,started_at,completed_at,status "
            "FROM crawl_run ORDER BY started_at DESC LIMIT 1").fetchone()
        return DatasetInfo(
            dataset_version=self._dataset_version(),
            universe_version=self._dataset_version(),
            universe_issuers=q("SELECT COUNT(*) FROM universe_issuer"),
            schema_version=SCHEMA_VERSION,
            notices=q("SELECT COUNT(*) FROM notice"),
            observations=q("SELECT COUNT(*) FROM notice_observation"),
            source_facts=q("SELECT COUNT(*) FROM source_fact"),
            ledger_events=q("SELECT COUNT(*) FROM ledger_event"),
            ledger_digest=_ledger.ledger_digest(self._cx),
            semantic_parser_versions=vers,
            derivation_version=_ledger.DERIVATION_VERSION,
            last_run=dict(zip(("run_id", "run_type", "started_at",
                               "completed_at", "status"), last))
            if last else None)

    def coverage(self):
        """Explicit denominators — never one ambiguous percentage."""
        return {
            "universe_version": self._dataset_version(),
            "global": _coverage.global_metrics(
                self._cx, universe_issuers=None),
            "matrix": _coverage.coverage_matrix(self._cx),
            "legacy": _coverage.legacy_inventory(self._cx)}


@dataclass(frozen=True)
class Issuer:
    issuer_id: str
    nif: Optional[str]
    name: Optional[str]
    lei: Optional[str]
    isins: tuple
    aliases: tuple
    _radar: object = field(repr=False, compare=False, default=None)

    def insider_transactions(self, **kw):
        return self._radar.insider_transactions(issuer=self, **kw)

    def significant_holdings(self, **kw):
        return self._radar.significant_holdings(issuer=self, **kw)

    def treasury_stock_positions(self, **kw):
        return self._radar.treasury_stock_positions(issuer=self, **kw)

    def treasury_operations(self, **kw):
        return self._radar.treasury_operations(issuer=self, **kw)

    def notices(self, **kw):
        return self._radar.notices(issuer=self, **kw)

    def events(self, **kw):
        return self._radar.events(issuer=self, **kw)

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()
                if not k.startswith("_")}
