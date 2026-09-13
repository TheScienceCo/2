"""Cleaning the external corpus.

The publisher states the dumps are not clean, so nothing is ingested without
passing these checks, and every rejected row is recorded with its reason rather
than silently dropped. A pipeline that quietly discards 30% of its input while
reporting healthy baselines is worse than one that fails loudly.

Bounds are deliberately loose. The goal is removing impossible rows, not
opinionated outlier trimming - a 3-hour Black Forest game is unusual, not wrong,
and excluding it would bias exactly the long-game baselines it belongs to.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import pandas as pd

#: A match shorter than this is a resign-at-spawn or a broken record, not a game.
MIN_DURATION_SECONDS = 60
#: Six hours. Above this the field is almost certainly not seconds.
MAX_DURATION_SECONDS = 6 * 60 * 60
#: Ratings outside this are not reachable; the ladder record is around 2800.
MIN_RATING = 1
MAX_RATING = 4000
MAX_PLAYERS = 8


class RejectionReason(StrEnum):
    ODD_PLAYER_COUNT = "odd_player_count"
    IMPLAUSIBLE_PLAYER_COUNT = "implausible_player_count"
    MISSING_REQUIRED = "missing_required_field"
    IMPLAUSIBLE_DURATION = "implausible_duration"
    IMPLAUSIBLE_RATING = "implausible_rating"
    ORPHAN_PLAYER_ROW = "orphan_player_row"
    INCOMPLETE_MATCH = "incomplete_match"


@dataclass
class Rejection:
    game_id: str
    profile_id: str | None
    reason: RejectionReason
    detail: str


@dataclass
class CleaningReport:
    matches_in: int = 0
    matches_out: int = 0
    players_in: int = 0
    players_out: int = 0
    rejections: list[Rejection] = field(default_factory=list)

    @property
    def match_retention(self) -> float:
        return self.matches_out / self.matches_in if self.matches_in else 0.0

    @property
    def player_retention(self) -> float:
        return self.players_out / self.players_in if self.players_in else 0.0

    def by_reason(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.rejections:
            counts[r.reason.value] = counts.get(r.reason.value, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))

    def summary(self) -> str:
        return (
            f"matches {self.matches_out}/{self.matches_in} "
            f"({self.match_retention:.1%} retained), "
            f"players {self.players_out}/{self.players_in} "
            f"({self.player_retention:.1%} retained), "
            f"reasons: {self.by_reason() or 'none'}"
        )


def clean(
    matches: pd.DataFrame, players: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, CleaningReport]:
    """Drop impossible rows from a dump, recording why.

    Matches and players are cleaned together: dropping a match must drop its
    player rows, and a match whose player rows are incomplete is itself unusable
    for anything paired (which is most of what the corpus is for).
    """
    report = CleaningReport(matches_in=len(matches), players_in=len(players))
    rejected_games: dict[str, tuple[RejectionReason, str]] = {}

    def reject_match(game_id: str, reason: RejectionReason, detail: str) -> None:
        rejected_games.setdefault(str(game_id), (reason, detail))

    # --- match-level -------------------------------------------------------
    for row in matches.itertuples(index=False):
        game_id = str(getattr(row, "game_id", ""))
        num_players = getattr(row, "num_players", None)
        duration = getattr(row, "duration", None)

        if num_players is None or pd.isna(num_players):
            reject_match(game_id, RejectionReason.MISSING_REQUIRED, "num_players is null")
            continue
        count = int(num_players)  # type: ignore[arg-type]
        if count < 2 or count > MAX_PLAYERS:
            reject_match(game_id, RejectionReason.IMPLAUSIBLE_PLAYER_COUNT, f"num_players={count}")
            continue
        if count % 2 != 0:
            # Teams cannot be balanced, so nothing paired can be computed.
            reject_match(game_id, RejectionReason.ODD_PLAYER_COUNT, f"num_players={count}")
            continue

        if duration is None or pd.isna(duration):
            reject_match(game_id, RejectionReason.MISSING_REQUIRED, "duration is null")
            continue
        seconds = float(duration)  # type: ignore[arg-type]
        if not (MIN_DURATION_SECONDS <= seconds <= MAX_DURATION_SECONDS):
            reject_match(game_id, RejectionReason.IMPLAUSIBLE_DURATION, f"duration={seconds:.0f}s")

    # --- player-level ------------------------------------------------------
    valid_game_ids = set(matches["game_id"].astype(str)) - set(rejected_games)
    player_rejections: list[Rejection] = []
    keep_player = []

    for row in players.itertuples(index=False):
        game_id = str(getattr(row, "game_id", ""))
        profile_id = getattr(row, "profile_id", None)
        profile = None if pd.isna(profile_id) else str(profile_id)

        if game_id in rejected_games:
            reason, detail = rejected_games[game_id]
            player_rejections.append(Rejection(game_id, profile, reason, detail))
            keep_player.append(False)
            continue
        if game_id not in valid_game_ids:
            player_rejections.append(
                Rejection(
                    game_id, profile, RejectionReason.ORPHAN_PLAYER_ROW, "no matching match row"
                )
            )
            keep_player.append(False)
            continue
        if profile is None:
            player_rejections.append(
                Rejection(game_id, None, RejectionReason.MISSING_REQUIRED, "profile_id is null")
            )
            keep_player.append(False)
            continue

        rating = getattr(row, "old_rating", None)
        if rating is not None and not pd.isna(rating):
            value = float(rating)
            if not (MIN_RATING <= value <= MAX_RATING):
                player_rejections.append(
                    Rejection(
                        game_id,
                        profile,
                        RejectionReason.IMPLAUSIBLE_RATING,
                        f"old_rating={value:.0f}",
                    )
                )
                keep_player.append(False)
                continue

        keep_player.append(True)

    clean_players = players[pd.Series(keep_player, index=players.index)].copy()

    # A match that lost player rows can no longer support paired analysis, so
    # it and its survivors go too - otherwise a "2-player match" with one row
    # silently becomes a cohort of one.
    if not clean_players.empty and "game_id" in clean_players:
        expected = matches.set_index(matches["game_id"].astype(str))["num_players"]
        surviving = clean_players["game_id"].astype(str).value_counts()
        incomplete = {
            gid
            for gid, n in surviving.items()
            if gid in expected.index and int(expected.loc[gid]) != int(n)
        }
        for gid in incomplete:
            reject_match(gid, RejectionReason.INCOMPLETE_MATCH, "player rows lost in cleaning")
            for profile in clean_players.loc[
                clean_players["game_id"].astype(str) == gid, "profile_id"
            ]:
                player_rejections.append(
                    Rejection(
                        gid,
                        str(profile),
                        RejectionReason.INCOMPLETE_MATCH,
                        "player rows lost in cleaning",
                    )
                )
        clean_players = clean_players[~clean_players["game_id"].astype(str).isin(incomplete)]

    clean_matches = matches[~matches["game_id"].astype(str).isin(rejected_games)].copy()

    report.rejections = [
        Rejection(gid, None, reason, detail) for gid, (reason, detail) in rejected_games.items()
    ] + player_rejections
    report.matches_out = len(clean_matches)
    report.players_out = len(clean_players)
    return clean_matches, clean_players, report
