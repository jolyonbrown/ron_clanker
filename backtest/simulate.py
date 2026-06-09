"""
Season simulator: runs a Strategy through a recorded season under full
FPL rules, scoring each gameweek with the validated scoring engine.

The simulator owns all rule enforcement — budget, selling prices, free
transfers, hits, chip windows, Free Hit reversion, squad legality — so
a Strategy can't cheat even accidentally. Lineups are checked against
the post-transfer squad every gameweek.

RonReplayStrategy replays Ron's recorded 2025-26 season (actual
transfers at actual transaction prices, actual lock-time lineups) and
exists to validate the simulator itself: bank, hit costs, squad and
points must all reproduce the official record.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from backtest.data import HistoricalDataProvider
from backtest.replay import reconstruct_lock_time_picks
from backtest.scoring import FREE_HIT, WILDCARD, GWScore, score_gameweek
from backtest.state import EntryState, Transfer, validate_squad
from backtest.strategy import AsOfView, GWDecision, InitialSquad, Strategy

logger = logging.getLogger('ron_clanker.backtest.simulate')

# AFCON December 2025: all managers topped up to 5 FTs from GW16
# (mirrors config/special_events.yaml).
SEASON_2025_26_FT_TOPUPS = {16: 5}


@dataclass
class SimGW:
    gameweek: int
    score: GWScore
    chip: Optional[str]
    n_transfers: int
    hit_cost: int
    bank: int                  # persistent bank after the GW (tenths)
    squad_value: int           # market value + bank (tenths)
    free_transfers_used: int


@dataclass
class SeasonResult:
    strategy_name: str
    gameweeks: List[SimGW] = field(default_factory=list)

    @property
    def total_net_points(self) -> int:
        return sum(g.score.net_points for g in self.gameweeks)

    @property
    def total_hits(self) -> int:
        return sum(g.hit_cost for g in self.gameweeks)


def simulate_season(
    strategy: Strategy,
    provider: HistoricalDataProvider,
    start_gw: int = 8,
    end_gw: int = 38,
    ft_topups: Optional[Dict[int, int]] = None,
) -> SeasonResult:
    element_types = provider.player_element_types()
    team_ids = provider.player_team_ids()

    state = EntryState(
        ft_topups=SEASON_2025_26_FT_TOPUPS if ft_topups is None else ft_topups
    )
    result = SeasonResult(strategy_name=strategy.name)

    # Prices carry forward GW to GW so blanking players keep a price.
    price_map = provider.price_map_through(start_gw - 1) if start_gw > 1 else {}

    for gw in range(start_gw, end_gw + 1):
        price_map.update(provider.prices(gw))
        view = AsOfView(provider, gw, dict(price_map))

        if gw == start_gw:
            initial = strategy.initial_squad(gw, view)
            state.buy_initial_squad(
                initial.purchases, element_types, team_ids,
                bank_override=initial.bank_override,
                check_clubs=strategy.check_clubs,
            )
            decision = GWDecision(transfers=[], chip=None, picks=initial.picks)
            hit = 0
            n_transfers = 0
            ft_used = 0
        else:
            state_info = {
                'squad': dict(state.squad),
                'bank': state.bank,
                'available_ft': state.available_ft(gw),
                'chips_used': list(state.chips_used),
            }
            decision = strategy.decide(gw, state_info, view)
            n_transfers = len(decision.transfers)
            is_free_hit = decision.chip == FREE_HIT
            snap = state.snapshot() if is_free_hit else None
            hit = state.apply_gameweek(
                gw, decision.transfers, decision.chip, price_map,
                element_types=element_types, team_ids=team_ids,
                check_clubs=strategy.check_clubs,
            )
            ft_used = min(n_transfers, state_info['available_ft']) \
                if decision.chip not in (FREE_HIT, WILDCARD) else 0

        # Lineup must be exactly the (post-transfer) squad.
        pick_ids = {p.player_id for p in decision.picks}
        if pick_ids != set(state.squad):
            raise ValueError(
                f"GW{gw}: lineup does not match squad. "
                f"Missing {set(state.squad) - pick_ids}, "
                f"extra {pick_ids - set(state.squad)}"
            )

        score = score_gameweek(
            picks=decision.picks,
            stats=provider.actuals(gw),
            chip=decision.chip,
            transfer_cost=hit,
        )

        if decision.chip == FREE_HIT and snap is not None:
            state.restore(snap)

        result.gameweeks.append(
            SimGW(
                gameweek=gw,
                score=score,
                chip=decision.chip,
                n_transfers=n_transfers,
                hit_cost=hit,
                bank=state.bank,
                squad_value=state.squad_market_value(price_map) + state.bank,
                free_transfers_used=ft_used,
            )
        )
    return result


class RonReplayStrategy(Strategy):
    """Replays Ron's recorded season — the simulator's validation rig.

    Transfers use the archived transaction prices (element_out_cost is
    the sale price actually received), so bank evolution is exact and
    independent of deadline-price approximations.
    """

    name = 'ron-replay'
    check_clubs = False   # recorded squads were legal at the time

    def __init__(self, provider: HistoricalDataProvider):
        self._provider = provider
        self._api_picks = provider.api_picks()
        self._transfers = provider.transfers_by_gw() or {}
        self._element_types = provider.player_element_types()
        if self._api_picks is None:
            raise RuntimeError(
                "RonReplayStrategy needs the season archive "
                "(ron_picks_by_gw.json) — none found"
            )

    def _lock_time_picks(self, gameweek: int):
        return reconstruct_lock_time_picks(
            self._api_picks[str(gameweek)], self._element_types
        )

    def initial_squad(self, gameweek: int, view: AsOfView) -> InitialSquad:
        picks = self._lock_time_picks(gameweek)
        entry = self._provider.entry(gameweek)
        prices = view.prices()
        purchases = {p.player_id: prices[p.player_id] for p in picks}
        return InitialSquad(
            purchases=purchases,
            picks=picks,
            bank_override=entry.bank,   # trust the recorded bank
        )

    def decide(self, gameweek: int, state_info: Dict, view: AsOfView) -> GWDecision:
        entry = self._provider.entry(gameweek)
        transfers = [
            Transfer(
                out_id=t['element_out'],
                in_id=t['element_in'],
                out_price=t['element_out_cost'],
                in_price=t['element_in_cost'],
            )
            for t in self._transfers.get(gameweek, [])
        ]
        return GWDecision(
            transfers=transfers,
            chip=entry.active_chip,
            picks=self._lock_time_picks(gameweek),
        )
