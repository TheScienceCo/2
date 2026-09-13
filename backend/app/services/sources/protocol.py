"""The source seam.

Three kinds of data feed this system, and each is a separate interface so that
none of them can quietly become load-bearing for the others:

* `ReplayParser` (in `services.parser`) - our own parse of an `.aoe2record`.
* `BaselineCorpusSource` - a bulk external corpus used for peer baselines and
  for model training. Large, not ours, and not auditable line by line.
* `MatchMetadataSource` - per-match lookups from a public API. Not yet built.

Keeping the corpus behind an interface matters for a specific reason: figures it
supplies carry `EXTERNAL_DERIVED` or `EXTERNAL_LABEL` provenance, never
`OBSERVED`. Code that cannot tell where a number came from will eventually
present someone else's derivation as our measurement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class DumpRef:
    """One published dump covering a date range."""

    start: date
    end: date
    matches_url: str
    players_url: str
    #: Publisher-supplied checksum where available; used to skip re-downloads.
    checksum: str | None = None

    @property
    def key(self) -> str:
        return f"{self.start.isoformat()}_{self.end.isoformat()}"


@dataclass
class FetchedDump:
    """A dump present on local disk, with where it came from."""

    ref: DumpRef
    matches_path: Path
    players_path: Path
    fetched_at: datetime
    #: True when the files were already cached and no network call was made.
    from_cache: bool = False
    attribution: str = ""
    warnings: list[str] = field(default_factory=list)


@runtime_checkable
class BaselineCorpusSource(Protocol):
    """A bulk corpus of matches published by a third party."""

    name: str
    attribution: str

    def discover(self) -> list[DumpRef]:
        """List available dumps, newest first."""
        ...

    def fetch(self, ref: DumpRef) -> FetchedDump:
        """Download a dump, or return the cached copy when unchanged."""
        ...
