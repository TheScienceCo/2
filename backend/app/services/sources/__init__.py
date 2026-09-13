"""External data sources, each behind an interface."""

from app.services.sources.aoestats import ATTRIBUTION, AoestatsError, AoestatsSource
from app.services.sources.protocol import BaselineCorpusSource, DumpRef, FetchedDump

__all__ = [
    "ATTRIBUTION",
    "AoestatsError",
    "AoestatsSource",
    "BaselineCorpusSource",
    "DumpRef",
    "FetchedDump",
]
