"""aoestats.io as a baseline corpus source.

aoestats.io publishes periodic database dumps of ranked Age of Empires II
matches as parquet. It is a free, hobbyist-run service, so this client is
deliberately unhurried: one file at a time, no parallelism, a descriptive
User-Agent, and a local cache keyed by date range that is never re-downloaded
unless the publisher's checksum changes.

**Not verified against the live service.** The environment this was written in
cannot reach aoestats.io, so the response shape below is handled defensively -
several plausible key spellings are accepted and anything unrecognised raises a
clear error naming what was received, rather than silently yielding zero dumps.
Treat the first real run as the thing that confirms it.

Everything this returns carries `EXTERNAL_DERIVED` or `EXTERNAL_LABEL`
provenance downstream. We did not compute it.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

from app.core.logging import get_logger
from app.services.sources.protocol import DumpRef, FetchedDump

log = get_logger(__name__)

API_ROOT = "https://aoestats.io"
DUMPS_ENDPOINT = f"{API_ROOT}/api/db_dumps"

ATTRIBUTION = (
    "Match data from aoestats.io (https://aoestats.io), used with attribution. "
    "aoestats.io is an independent community project."
)

USER_AGENT = "AoE2Lab/0.1 (+https://github.com/TheScienceCo/2) python-httpx"

#: Keys the discovery payload might use, in preference order. The publisher's
#: exact spelling is unconfirmed from here.
_START_KEYS = ("start_date", "start", "from", "period_start")
_END_KEYS = ("end_date", "end", "to", "period_end")
_MATCHES_KEYS = ("matches_url", "matches", "matches_parquet", "match_url")
_PLAYERS_KEYS = ("players_url", "players", "players_parquet", "player_url")
_CHECKSUM_KEYS = ("checksum", "sha256", "md5", "etag", "hash")


class AoestatsError(RuntimeError):
    """Discovery or download failed in a way the caller must see."""


def _first(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if mapping.get(key) not in (None, ""):
            return mapping[key]
    return None


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def _absolute(url: str) -> str:
    return url if url.startswith("http") else f"{API_ROOT}{'' if url.startswith('/') else '/'}{url}"


class AoestatsSource:
    """Discovers and downloads aoestats.io dumps into a local cache."""

    name = "aoestats.io"
    attribution = ATTRIBUTION

    def __init__(self, cache_dir: str | Path, timeout: float = 60.0) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._timeout = timeout

    # -- discovery ---------------------------------------------------------

    def discover(self) -> list[DumpRef]:
        """List published dumps, newest first."""
        try:
            with httpx.Client(timeout=self._timeout, headers={"User-Agent": USER_AGENT}) as client:
                response = client.get(DUMPS_ENDPOINT)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            raise AoestatsError(f"could not reach {DUMPS_ENDPOINT}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise AoestatsError(f"{DUMPS_ENDPOINT} did not return JSON: {exc}") from exc

        return self.parse_discovery(payload)

    def parse_discovery(self, payload: Any) -> list[DumpRef]:
        """Turn a discovery payload into refs.

        Separate from the HTTP call so it can be tested against a recorded
        payload without a network round trip.
        """
        rows = payload
        if isinstance(payload, dict):
            for key in ("db_dumps", "dumps", "data", "results", "items"):
                if isinstance(payload.get(key), list):
                    rows = payload[key]
                    break
        if not isinstance(rows, list):
            raise AoestatsError(
                f"unexpected discovery shape: {type(payload).__name__} "
                f"with keys {list(payload)[:8] if isinstance(payload, dict) else 'n/a'}"
            )

        refs: list[DumpRef] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            start = _as_date(_first(row, _START_KEYS))
            end = _as_date(_first(row, _END_KEYS))
            matches = _first(row, _MATCHES_KEYS)
            players = _first(row, _PLAYERS_KEYS)
            if not (start and end and matches and players):
                log.warning("aoestats.dump_row_skipped", keys=sorted(row)[:10])
                continue
            refs.append(
                DumpRef(
                    start=start,
                    end=end,
                    matches_url=_absolute(str(matches)),
                    players_url=_absolute(str(players)),
                    checksum=(str(c) if (c := _first(row, _CHECKSUM_KEYS)) is not None else None),
                )
            )

        if rows and not refs:
            raise AoestatsError(
                f"discovery returned {len(rows)} rows but none had recognisable "
                f"date and URL fields; first row keys: "
                f"{sorted(rows[0])[:12] if isinstance(rows[0], dict) else 'n/a'}"
            )

        refs.sort(key=lambda r: r.start, reverse=True)
        return refs

    # -- fetching ----------------------------------------------------------

    def fetch(self, ref: DumpRef) -> FetchedDump:
        """Download a dump, or reuse the cached copy when it is unchanged."""
        target = self.cache_dir / ref.key
        target.mkdir(parents=True, exist_ok=True)
        matches_path = target / "matches.parquet"
        players_path = target / "players.parquet"
        marker = target / "fetch.json"

        if self._cache_is_valid(marker, ref, matches_path, players_path):
            log.info("aoestats.cache_hit", range=ref.key)
            return FetchedDump(
                ref=ref,
                matches_path=matches_path,
                players_path=players_path,
                fetched_at=datetime.fromisoformat(json.loads(marker.read_text())["fetched_at"]),
                from_cache=True,
                attribution=self.attribution,
            )

        warnings: list[str] = []
        with httpx.Client(
            timeout=self._timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        ) as client:
            # Sequential on purpose: this is a free service, not a CDN to hammer.
            self._download(client, ref.matches_url, matches_path)
            self._download(client, ref.players_url, players_path)

        fetched_at = datetime.now(UTC)
        marker.write_text(
            json.dumps(
                {
                    "range": ref.key,
                    "fetched_at": fetched_at.isoformat(),
                    "checksum": ref.checksum,
                    "matches_sha256": _sha256(matches_path),
                    "players_sha256": _sha256(players_path),
                    "source": self.name,
                    "attribution": self.attribution,
                },
                indent=1,
            )
        )
        log.info(
            "aoestats.fetched",
            range=ref.key,
            matches_bytes=matches_path.stat().st_size,
            players_bytes=players_path.stat().st_size,
        )
        return FetchedDump(
            ref=ref,
            matches_path=matches_path,
            players_path=players_path,
            fetched_at=fetched_at,
            from_cache=False,
            attribution=self.attribution,
            warnings=warnings,
        )

    def _cache_is_valid(self, marker: Path, ref: DumpRef, matches: Path, players: Path) -> bool:
        if not (marker.exists() and matches.exists() and players.exists()):
            return False
        try:
            recorded = json.loads(marker.read_text())
        except (OSError, json.JSONDecodeError):
            return False
        # Only a changed publisher checksum forces a re-download. When they
        # publish none, a cached range is treated as immutable - dumps cover a
        # closed date range, so their content should not change.
        if ref.checksum and recorded.get("checksum") != ref.checksum:
            log.info("aoestats.checksum_changed", range=ref.key)
            return False
        return True

    def _download(self, client: httpx.Client, url: str, destination: Path) -> None:
        tmp = destination.with_suffix(destination.suffix + ".part")
        try:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                with tmp.open("wb") as handle:
                    for chunk in response.iter_bytes(chunk_size=1 << 20):
                        handle.write(chunk)
        except httpx.HTTPError as exc:
            tmp.unlink(missing_ok=True)
            raise AoestatsError(f"download failed for {url}: {exc}") from exc
        # Rename only once the body is complete, so an interrupted transfer can
        # never be mistaken for a valid cache entry.
        tmp.replace(destination)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
