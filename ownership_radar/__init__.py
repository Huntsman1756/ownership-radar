"""Ownership Radar ES — bitemporal, reproducible ledger of ownership
changes in Spanish listed companies, built on official CNMV
notifications as the evidence layer.

Public read-only API (G6-B):

    from ownership_radar import OwnershipRadar
    radar = OwnershipRadar.open("ownership-radar.sqlite")
    issuer = radar.company("SAN")

Only names exported here form the stable contract. Modules
`store`, `ledger`, `pipeline`, `cnmv`, `ingest`, `poller`,
`coverage`, `universe` are internals and may change.
"""
from .api import (AmbiguousAnnulment, AmbiguousIdentifier,  # noqa:F401
                  AnnulmentStatus, AuthoritativeResult,
                  CursorDatasetMismatch, DataIntegrityError, DatasetInfo,
                  ExecutionLine, FeedItem, FeedResult, InsiderTransaction,
                  InvalidCursor, InvalidTemporalQuery, Issuer,
                  LedgerEvent, Notice, NotFound, OwnershipRadar,
                  OwnershipRadarError, Provenance, QueryResult,
                  SignificantHoldingDisclosure, TreasuryOperation,
                  TreasuryStockPosition, UnsupportedCursorVersion,
                  UnsupportedQuery,
                  DETERMINISTIC_DERIVATION, FEED_ITEM_TYPES,
                  NO_OBSERVATION_HISTORY, OBSERVED_CURRENT,
                  RECONSTRUCTED_HISTORICAL, SCHEMA_VERSION,
                  SOURCE_DECLARED)

__version__ = "0.1.0a1"
PARSER_VERSION = "1.0.0-g1"
