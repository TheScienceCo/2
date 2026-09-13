"""Replay parsing backed by `mgz` (aoc-mgz).

This is the only module in the codebase that imports `mgz`. Everything else
depends on `app.services.parser.types`.

**Parse-quality caveat.** `mgz` decodes actions per replay version, and unit
queue commands in particular are not decodable on every version: on some builds
they arrive as `Action.ERROR`. Rather than silently reporting "0 villagers
queued" for such a file, the parser records whether queue data was recoverable
and the analysis marks the dependent metrics `UNAVAILABLE`.
"""

from __future__ import annotations

import io
import struct
from datetime import timedelta
from typing import Any

from app.core.logging import get_logger
from app.services.parser.reference import age_from_technology, technology_name
from app.services.parser.types import (
    Command,
    CommandType,
    ParsedPlayer,
    ParsedReplay,
    ReplayParseError,
    ResourceSample,
    ViewportSample,
)

log = get_logger(__name__)

#: Raw action names that represent queuing a unit at a production building.
_QUEUE_ACTIONS = {"QUEUE", "MULTIQUEUE", "DE_QUEUE"}

#: Above this share of undecodable actions the command stream is too damaged to
#: draw build-order conclusions from, and the report says so.
_ERROR_RATIO_UNRELIABLE = 0.25


def _ms(delta: timedelta | None) -> int:
    return int(delta.total_seconds() * 1000) if delta is not None else 0


class MgzReplayParser:
    """Parses `.aoe2record` / `.mgz` files via `mgz.model.parse_match`."""

    name = "mgz"

    def parse(self, data: bytes) -> ParsedReplay:
        if not data:
            raise ReplayParseError("empty file")

        try:
            from mgz.model import parse_match
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise ReplayParseError(f"mgz is not installed: {exc}") from exc

        try:
            match = parse_match(io.BytesIO(data))
        except Exception as exc:
            # mgz raises a wide range of types (struct.error, RuntimeError,
            # EOFError, zlib.error) for a malformed or unsupported file. The
            # caller only needs to know it was not parseable.
            raise ReplayParseError(f"{type(exc).__name__}: {exc}") from exc

        warnings: list[str] = []
        players = self._players(match)
        commands, queue_seen, error_ratio = self._commands(match, warnings)
        samples = self._samples(match)
        age_commands = self._age_commands(match)

        if error_ratio > _ERROR_RATIO_UNRELIABLE:
            warnings.append(
                f"{error_ratio:.0%} of actions could not be decoded for this replay "
                f"version; build-order detail is incomplete."
            )
        if not queue_seen:
            warnings.append(
                "Unit-queue commands are not decodable for this replay version, so "
                "production metrics (villager uptime, TC idle time) are unavailable."
            )

        viewport, viewport_player = self._viewport(data)

        return ParsedReplay(
            viewport=viewport,
            viewport_player=viewport_player,
            map_name=getattr(match.map, "name", None),
            map_size=getattr(match.map, "size", None),
            duration_ms=_ms(match.duration),
            version=str(getattr(match, "game_version", "") or "") or None,
            played_at=(ts.isoformat() if (ts := getattr(match, "timestamp", None)) else None),
            players=players,
            commands=sorted(commands + age_commands, key=lambda c: c.timestamp_ms),
            resource_samples=samples,
            postgame=self._postgame(match),
            warnings=warnings,
        )

    # -- pieces ------------------------------------------------------------

    def _players(self, match: Any) -> list[ParsedPlayer]:
        out: list[ParsedPlayer] = []
        for p in match.players:
            out.append(
                ParsedPlayer(
                    player_number=p.number,
                    name=p.name,
                    civilization=str(p.civilization),
                    team=getattr(p, "team_id", None),
                    winner=bool(getattr(p, "winner", False)),
                    rating=getattr(p, "rate_snapshot", None),
                    profile_id=getattr(p, "profile_id", None),
                    color_id=getattr(p, "color_id", None),
                    eapm=getattr(p, "eapm", None),
                )
            )
        return out

    def _age_commands(self, match: Any) -> list[Command]:
        """Age advances, from the model's `uptimes`.

        These are the single most reliable timing signal in a replay: mgz
        derives them from the game's own age transitions rather than from a
        command we have to decode.
        """
        out: list[Command] = []
        for up in getattr(match, "uptimes", []) or []:
            player = getattr(up, "player", None)
            if player is None:
                continue
            age = getattr(up.age, "name", "").replace("_AGE", "").lower()
            if not age:
                continue
            out.append(
                Command(
                    timestamp_ms=_ms(up.timestamp),
                    player_number=player.number,
                    type=CommandType.AGE_UP,
                    payload={"age": age},
                )
            )
        return out

    def _commands(self, match: Any, warnings: list[str]) -> tuple[list[Command], bool, float]:
        out: list[Command] = []
        queue_seen = False
        total = 0
        errors = 0

        for action in getattr(match, "actions", []) or []:
            total += 1
            type_name = getattr(action.type, "name", "")
            if type_name == "ERROR":
                errors += 1
                continue

            player = getattr(action, "player", None)
            if player is None:
                continue
            payload = action.payload or {}
            ts = _ms(action.timestamp)

            position = getattr(action, "position", None)
            command = self._to_command(type_name, ts, player.number, payload, position)
            if command is None:
                continue
            if command.type is CommandType.QUEUE_UNIT:
                queue_seen = True
            out.append(command)

        return out, queue_seen, (errors / total if total else 0.0)

    def _to_command(
        self,
        type_name: str,
        ts: int,
        player_number: int,
        payload: dict,
        position: Any = None,
    ) -> Command | None:
        """Map one raw mgz action onto our normalised command vocabulary.

        Unrecognised actions are dropped rather than guessed at.
        """
        if type_name == "BUILD":
            from app.services.parser.reference import object_name

            building_id = payload.get("building_id")
            return Command(
                ts,
                player_number,
                CommandType.BUILD,
                {
                    "building_id": building_id,
                    "building": object_name(building_id) if building_id else None,
                    "x": payload.get("x"),
                    "y": payload.get("y"),
                },
            )

        if type_name == "RESEARCH":
            tech_id = payload.get("technology_id")
            if tech_id is None:
                return None
            # An age advance is a research command, but we take age timings from
            # `uptimes` instead, which is more reliable. Drop the duplicate.
            if age_from_technology(tech_id) is not None:
                return None
            return Command(
                ts,
                player_number,
                CommandType.RESEARCH,
                {"technology_id": tech_id, "technology": technology_name(tech_id)},
            )

        if type_name in _QUEUE_ACTIONS:
            from app.services.parser.reference import object_name

            unit_id = payload.get("unit_id")
            return Command(
                ts,
                player_number,
                CommandType.QUEUE_UNIT,
                {
                    "unit_id": unit_id,
                    "unit": object_name(unit_id) if unit_id else None,
                    "amount": payload.get("amount", 1),
                    "building_object_ids": list(payload.get("object_ids") or []),
                },
            )

        if type_name in ("TRIBUTE", "DE_TRIBUTE"):
            return Command(
                ts,
                player_number,
                CommandType.TRIBUTE,
                {
                    k: payload.get(k)
                    for k in ("player_id_to", "food", "wood", "gold", "stone", "amount")
                },
            )

        if type_name == "WALL":
            # A wall command places a run of segments between two points, so one
            # command is many tiles. Chebyshev distance is the tile count, since
            # walls step diagonally.
            x = payload.get("x", getattr(position, "x", None))
            y = payload.get("y", getattr(position, "y", None))
            x_end, y_end = payload.get("x_end"), payload.get("y_end")
            tiles = None
            corners = (x, y, x_end, y_end)
            if all(isinstance(v, int | float) for v in corners):
                x0, y0, x1, y1 = (int(v) for v in corners)  # type: ignore[arg-type]
                tiles = max(abs(x1 - x0), abs(y1 - y0)) + 1
            return Command(
                ts,
                player_number,
                CommandType.WALL,
                {"x": x, "y": y, "x_end": x_end, "y_end": y_end, "tiles": tiles},
            )

        if type_name == "DELETE":
            return Command(ts, player_number, CommandType.DELETE, {})
        if type_name == "BUY":
            return Command(ts, player_number, CommandType.MARKET_BUY, dict(payload))
        if type_name == "SELL":
            return Command(ts, player_number, CommandType.MARKET_SELL, dict(payload))
        if type_name == "TOWN_BELL":
            return Command(ts, player_number, CommandType.TOWN_BELL, {})
        if type_name == "BACK_TO_WORK":
            return Command(ts, player_number, CommandType.BACK_TO_WORK, {})
        if type_name == "RESIGN":
            return Command(ts, player_number, CommandType.RESIGN, {})
        return None

    def _samples(self, match: Any) -> list[ResourceSample]:
        """The banked-resource curve, from DE sync packets.

        `total_resources` is food+wood+gold+stone combined; the per-type split is
        not transmitted. Marked `INFERRED` downstream because the field meanings
        are community-reverse-engineered rather than documented.
        """
        out: list[ResourceSample] = []
        for p in match.players:
            for row in getattr(p, "timeseries", []) or []:
                out.append(
                    ResourceSample(
                        timestamp_ms=_ms(row.timestamp),
                        player_number=p.number,
                        total_resources=int(row.total_resources),
                        object_count=int(row.total_objects),
                    )
                )
        out.sort(key=lambda s: (s.timestamp_ms, s.player_number))
        return out

    def _viewport(self, data: bytes) -> tuple[list[ViewportSample], int | None]:
        """Camera positions, from a second pass over the raw command stream.

        `mgz.model` decodes viewlocks but does not expose them on `Match`, so
        this walks the body directly. A replay holds exactly one perspective -
        whoever saved it - so this is that player's camera and nobody else's.

        Best-effort: a stream that will not decode yields no viewport, and the
        dependent metrics report unavailable rather than failing the parse.
        """
        import io

        import mgz.fast as fast
        from mgz.fast.header import parse as parse_header

        try:
            handle = io.BytesIO(data)
            header = parse_header(handle)
            handle.seek(handle.tell() - 4)  # step back over the log version
            fast.meta(handle)
            owner = header.get("metadata", {}).get("owner_id")
        except Exception as exc:
            log.warning("viewport.header_failed", error=str(exc))
            return [], None

        samples: list[ViewportSample] = []
        timestamp = 0
        previous: tuple[float, float] | None = None
        try:
            while True:
                op_type, payload = fast.operation(handle)
                if op_type is fast.Operation.SYNC:
                    timestamp += payload[0]
                # The camera emits on every sync; keep only real movements.
                elif op_type is fast.Operation.VIEWLOCK and payload != previous:
                    samples.append(ViewportSample(timestamp, payload[0], payload[1]))
                    previous = payload
        except EOFError:
            pass  # the expected end of the stream
        except (struct.error, RuntimeError, ValueError) as exc:
            # A stream we cannot follow any further. What we gathered is still
            # valid, but say so - a silent empty result is indistinguishable
            # from a replay that genuinely has no camera data.
            log.warning("viewport.stream_truncated", at_ms=timestamp, error=str(exc))

        return samples, (int(owner) if isinstance(owner, int) else None)

    def _postgame(self, match: Any) -> dict[str, Any] | None:
        pg = getattr(match, "postgame", None)
        return dict(pg) if isinstance(pg, dict) else None
