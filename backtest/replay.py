"""
Replay a recorded season through the scoring engine.

This is the framework's own validation. If the engine can't reproduce
Ron's actual official scores from raw player data, nothing downstream
(counterfactual strategies, prediction-driven squads) can be trusted.

Two replay modes, because the FPL API rewrites picks once a GW ends:

    effective  - score the POST-autosub lineup stored in
                 season_team_history. Validates scoring/captaincy maths
                 and DGW aggregation, but autosubs are already applied
                 in the data so that path isn't exercised.

    lock_time  - reconstruct the true deadline-time selection by
                 inverting the automatic_subs recorded in the archive's
                 ron_picks_by_gw.json, then require the engine to
                 re-derive FPL's exact substitutions, armband and score.
                 This is the full-strength keystone.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from backtest.data import HistoricalDataProvider
from backtest.scoring import GWScore, Pick, score_gameweek

logger = logging.getLogger('ron_clanker.backtest.replay')


@dataclass
class GWReplay:
    gameweek: int
    computed: GWScore
    official_points: int          # event_points from the FPL API
    official_bench_points: int    # points_on_bench from the FPL API
    active_chip: Optional[str]
    transfer_cost: int
    average_score: Optional[int]  # average manager benchmark
    overall_rank: Optional[int]
    official_autosubs: Optional[List[Tuple[int, int]]] = None  # lock_time mode only
    official_captain: Optional[int] = None                     # effective armband

    @property
    def points_match(self) -> bool:
        return self.computed.gross_points == self.official_points

    @property
    def bench_match(self) -> bool:
        return self.computed.bench_points == self.official_bench_points

    @property
    def autosubs_match(self) -> Optional[bool]:
        if self.official_autosubs is None:
            return None
        return sorted(self.computed.autosubs) == sorted(self.official_autosubs)

    @property
    def captain_match(self) -> Optional[bool]:
        if self.official_captain is None:
            return None
        return self.computed.effective_captain == self.official_captain


def reconstruct_lock_time_picks(
    gw_data: Dict,
    element_types: Dict[int, int],
) -> List[Pick]:
    """Invert the FPL API's post-GW rearrangement back to the deadline
    selection.

    The picks array positions players post-autosub (subbed-out starters
    moved to the bench, subs promoted into 1-11). Each automatic_subs
    entry records (element_in, element_out); swapping their positions
    back restores the lock-time arrangement. Captain/vice flags are
    already lock-time and need no inversion.
    """
    positions = {p['element']: p['position'] for p in gw_data['picks']}
    for sub in gw_data.get('automatic_subs', []):
        pin, pout = sub['element_in'], sub['element_out']
        positions[pin], positions[pout] = positions[pout], positions[pin]
    return [
        Pick(
            player_id=p['element'],
            position=positions[p['element']],
            element_type=element_types[p['element']],
            is_captain=bool(p['is_captain']),
            is_vice_captain=bool(p['is_vice_captain']),
        )
        for p in gw_data['picks']
    ]


def replay_season(
    provider: HistoricalDataProvider,
    mode: str = 'lock_time',
) -> List[GWReplay]:
    """Score every recorded gameweek and pair it with the official result.

    Falls back to 'effective' mode if no archive picks JSON is available.
    """
    api_picks = provider.api_picks() if mode == 'lock_time' else None
    if mode == 'lock_time' and api_picks is None:
        logger.warning(
            "No ron_picks_by_gw.json archive found — falling back to "
            "effective (post-autosub) replay"
        )
        mode = 'effective'

    element_types = provider.player_element_types() if mode == 'lock_time' else {}

    results = []
    for gw in provider.gameweeks():
        entry = provider.entry(gw)
        official_autosubs = None
        official_captain = None

        if mode == 'lock_time':
            gw_data = api_picks[str(gw)]
            picks = reconstruct_lock_time_picks(gw_data, element_types)
            official_autosubs = [
                (s['element_out'], s['element_in'])
                for s in gw_data.get('automatic_subs', [])
            ]
            official_captain = next(
                (p['element'] for p in gw_data['picks'] if p['multiplier'] >= 2),
                None,
            )
        else:
            picks = provider.picks(gw)

        computed = score_gameweek(
            picks=picks,
            stats=provider.actuals(gw),
            chip=entry.active_chip,
            transfer_cost=entry.event_transfers_cost,
        )
        result = GWReplay(
            gameweek=gw,
            computed=computed,
            official_points=entry.event_points,
            official_bench_points=entry.points_on_bench,
            active_chip=entry.active_chip,
            transfer_cost=entry.event_transfers_cost,
            average_score=provider.average_entry_score(gw),
            overall_rank=entry.overall_rank,
            official_autosubs=official_autosubs,
            official_captain=official_captain,
        )
        results.append(result)
        if not result.points_match:
            logger.warning(
                "GW%d replay mismatch: computed %d vs official %d (chip=%s)",
                gw, computed.gross_points, entry.event_points, entry.active_chip,
            )
        if result.autosubs_match is False:
            logger.warning(
                "GW%d autosub mismatch: derived %s vs official %s",
                gw, computed.autosubs, official_autosubs,
            )
    return results
