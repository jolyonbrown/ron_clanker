"""
Pure FPL gameweek scoring engine.

Given a lock-time 15-man selection, actual per-player gameweek stats, and
the active chip, computes the official FPL gameweek score: automatic
substitutions, captain/vice-captain promotion, Triple Captain, Bench
Boost, and transfer hit deduction.

No database access — everything is passed in. This keeps the engine
trivially testable and reusable for counterfactual seasons (alternative
captains, alternative squads) where stats come from anywhere.

FPL rules implemented (2025/26):
    - Starting XI is pick positions 1-11; bench is 12-15. Position 12 is
      always the reserve goalkeeper; 13-15 are outfield in autosub
      priority order.
    - A starter who plays 0 minutes across the GW is replaced by the
      first eligible bench player. GK can only be replaced by the bench
      GK. An outfield swap is only made if the resulting formation keeps
      exactly 1 GK, at least 3 DEF and at least 1 FWD.
    - Captain scores double (triple on Triple Captain). If the captain
      plays 0 minutes, the vice-captain inherits the armband — but only
      if the vice played.
    - Bench Boost: all 15 players score, no autosubs.
    - DGW handling is the caller's responsibility: PlayerGW must carry
      points and minutes summed across all of the player's fixtures in
      the gameweek.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger('ron_clanker.backtest.scoring')

GK, DEF, MID, FWD = 1, 2, 3, 4

# Chip name constants matching the FPL API / season_team_history.active_chip
TRIPLE_CAPTAIN = '3xc'
BENCH_BOOST = 'bboost'
FREE_HIT = 'freehit'
WILDCARD = 'wildcard'


@dataclass(frozen=True)
class Pick:
    """One slot of a lock-time 15-man selection."""
    player_id: int
    position: int            # 1-15: 1-11 starting XI, 12-15 bench order
    element_type: int        # 1=GK, 2=DEF, 3=MID, 4=FWD
    is_captain: bool = False
    is_vice_captain: bool = False


@dataclass(frozen=True)
class PlayerGW:
    """A player's actual return for a whole gameweek (summed over DGW fixtures)."""
    points: int = 0
    minutes: int = 0


@dataclass
class GWScore:
    """Result of scoring one gameweek."""
    gross_points: int                 # after autosubs/captaincy/chip, before hits
    transfer_cost: int
    net_points: int                   # gross - transfer_cost
    multipliers: Dict[int, int] = field(default_factory=dict)  # player_id -> 0/1/2/3
    autosubs: List[Tuple[int, int]] = field(default_factory=list)  # (out_id, in_id)
    effective_captain: Optional[int] = None  # who actually wore the armband, if anyone
    bench_points: int = 0             # points left on the bench (0 under Bench Boost)


def _formation_valid(element_types: List[int]) -> bool:
    """Validate an 11-man lineup's formation. Squad composition (2 GK / 5 DEF /
    5 MID / 3 FWD) already bounds the maxima, so only the minima need checking."""
    return (
        element_types.count(GK) == 1
        and element_types.count(DEF) >= 3
        and element_types.count(FWD) >= 1
    )


def score_gameweek(
    picks: List[Pick],
    stats: Dict[int, PlayerGW],
    chip: Optional[str] = None,
    transfer_cost: int = 0,
) -> GWScore:
    """
    Score one gameweek exactly as FPL would.

    Args:
        picks: the 15 lock-time picks (positions 1-15, one captain, one vice).
        stats: player_id -> PlayerGW for the gameweek. Players absent from
               the dict (blank GW, unused sub) are treated as 0 points,
               0 minutes.
        chip: active chip name ('3xc', 'bboost', 'freehit', 'wildcard') or
              None. Wildcard/Free Hit don't change scoring — the squad
              passed in is already the chip squad.
        transfer_cost: points spent on hits this gameweek (positive number).
    """
    if len(picks) != 15:
        raise ValueError(f"Expected 15 picks, got {len(picks)}")

    by_position = sorted(picks, key=lambda p: p.position)
    xi = [p for p in by_position if p.position <= 11]
    bench = [p for p in by_position if p.position >= 12]

    def played(pick: Pick) -> bool:
        return stats.get(pick.player_id, PlayerGW()).minutes > 0

    def pts(pick: Pick) -> int:
        return stats.get(pick.player_id, PlayerGW()).points

    autosubs: List[Tuple[int, int]] = []

    if chip == BENCH_BOOST:
        # All 15 score; no substitutions.
        lineup = list(by_position)
    else:
        lineup = list(xi)
        bench_gk = next((p for p in bench if p.element_type == GK), None)
        bench_outfield = [p for p in bench if p.element_type != GK]
        used_subs = set()

        for i, starter in enumerate(list(lineup)):
            if played(starter):
                continue
            if starter.element_type == GK:
                if bench_gk and played(bench_gk) and bench_gk.player_id not in used_subs:
                    lineup[lineup.index(starter)] = bench_gk
                    used_subs.add(bench_gk.player_id)
                    autosubs.append((starter.player_id, bench_gk.player_id))
                continue
            for sub in bench_outfield:
                if sub.player_id in used_subs or not played(sub):
                    continue
                candidate = list(lineup)
                candidate[candidate.index(starter)] = sub
                if _formation_valid([p.element_type for p in candidate]):
                    lineup = candidate
                    used_subs.add(sub.player_id)
                    autosubs.append((starter.player_id, sub.player_id))
                    break

    # Captaincy: vice inherits only if the captain played no minutes.
    captain = next((p for p in picks if p.is_captain), None)
    vice = next((p for p in picks if p.is_vice_captain), None)
    captain_multiplier = 3 if chip == TRIPLE_CAPTAIN else 2

    effective_captain: Optional[int] = None
    if captain and played(captain):
        effective_captain = captain.player_id
    elif vice and played(vice):
        effective_captain = vice.player_id

    lineup_ids = {p.player_id for p in lineup}
    multipliers: Dict[int, int] = {}
    for p in picks:
        if p.player_id not in lineup_ids:
            multipliers[p.player_id] = 0
        elif p.player_id == effective_captain:
            multipliers[p.player_id] = captain_multiplier
        else:
            multipliers[p.player_id] = 1

    gross = sum(pts(p) * multipliers[p.player_id] for p in picks)
    bench_points = sum(pts(p) for p in picks if p.player_id not in lineup_ids)

    return GWScore(
        gross_points=gross,
        transfer_cost=transfer_cost,
        net_points=gross - transfer_cost,
        multipliers=multipliers,
        autosubs=autosubs,
        effective_captain=effective_captain,
        bench_points=bench_points,
    )
