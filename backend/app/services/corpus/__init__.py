"""The external baseline corpus: ingestion, cleaning and provenance."""

from app.services.corpus.clean import CleaningReport, RejectionReason, clean
from app.services.corpus.ingest import ELO_BAND_EDGES, IngestReport, elo_band, ingest_dump
from app.services.corpus.schema import COLUMNS, SchemaReport, inspect_columns, provenance_of

__all__ = [
    "COLUMNS",
    "ELO_BAND_EDGES",
    "CleaningReport",
    "IngestReport",
    "RejectionReason",
    "SchemaReport",
    "clean",
    "elo_band",
    "ingest_dump",
    "inspect_columns",
    "provenance_of",
]
