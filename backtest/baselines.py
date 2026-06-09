"""
Baseline strategies for counterfactual simulation.

GreedyModelStrategy is the simplest faithful model-follower: every
decision comes straight from the stored pre-deadline predictions with
no human-style judgement layered on top. It answers the question
"what would pure, naive adherence to the model have scored?" — the
floor that any smarter strategy (and Ron himself) should beat.

Behaviour:
    - Initial squad: greedy by predicted xP under budget, reserving
      enough to fill remaining slots at the cheapest available price.
    - Weekly: at most one transfer — the best same-position swap by
      predicted xP gain, taken only if it gains > 0.5 xP and is
      affordable. Never takes hits. Banks FTs otherwise.
    - Lineup: highest-xP valid formation; captain/vice = top two
      predicted in the XI; bench ordered by xP.
    - Blank-aware: players whose club has no fixture this GW count as
      0 xP (the GW34-style failure the live optimizer once had).
    - No chips. Chip strategy is a later, separate baseline.
    - Fallback xP when a GW has no stored predictions (GW20/23
      2025-26): points-per-appearance from history before the GW.
"""

import logging
from typing import Dict, List, Optional

from backtest.scoring import GK, Pick
from backtest.state import MAX_PER_CLUB, SQUAD_SHAPE, Transfer, sell_price
from backtest.strategy import AsOfView, GWDecision, InitialSquad, Strategy

logger = logging.getLogger('ron_clanker.backtest.baselines')

MIN_XP_GAIN_TO_TRANSFER = 0.5


def _valid_formations():
    for d in range(3, 6):
        for m in range(2, 6):
            f = 10 - d - m
            if 1 <= f <= 3:
                yield d, m, f


class GreedyModelStrategy(Strategy):
    name = 'greedy-model'

    # ------------------------------------------------------------------

    def _xp_table(self, view: AsOfView) -> Dict[int, float]:
        """Predicted points per player, zeroed for blanking clubs."""
        xp = dict(view.predictions())
        if not xp:
            history = view.history()
            xp = {
                pid: h['points'] / h['appearances']
                for pid, h in history.items()
                if h['appearances'] > 0
            }
            logger.info(
                "GW%d: no stored predictions, falling back to "
                "points-per-appearance", view.gameweek,
            )
        fixtures = view.fixture_counts()
        teams = view.team_ids()
        return {
            pid: (v if fixtures.get(teams.get(pid), 0) > 0 else 0.0)
            for pid, v in xp.items()
        }

    # ------------------------------------------------------------------

    def initial_squad(self, gameweek: int, view: AsOfView) -> InitialSquad:
        xp = self._xp_table(view)
        prices = view.prices()
        etypes = view.element_types()
        teams = view.team_ids()

        pool = [pid for pid in prices if pid in etypes]
        min_price = {
            et: min(prices[p] for p in pool if etypes[p] == et)
            for et in SQUAD_SHAPE
        }

        slots = dict(SQUAD_SHAPE)
        clubs: Dict[int, int] = {}
        bank = 1000
        chosen: Dict[int, int] = {}

        for pid in sorted(pool, key=lambda p: (-xp.get(p, 0.0), prices[p])):
            et = etypes[pid]
            if slots.get(et, 0) == 0:
                continue
            club = teams.get(pid)
            if clubs.get(club, 0) >= MAX_PER_CLUB:
                continue
            price = prices[pid]
            remaining_after = {
                t: (n - 1 if t == et else n) for t, n in slots.items()
            }
            reserve = sum(min_price[t] * n for t, n in remaining_after.items())
            if price > bank - reserve:
                continue
            chosen[pid] = price
            bank -= price
            slots[et] -= 1
            clubs[club] = clubs.get(club, 0) + 1
            if sum(slots.values()) == 0:
                break

        if sum(slots.values()) != 0:
            raise RuntimeError(f"Could not fill squad: remaining slots {slots}")

        picks = self._build_picks(list(chosen), xp, etypes)
        return InitialSquad(purchases=chosen, picks=picks)

    # ------------------------------------------------------------------

    def decide(self, gameweek: int, state_info: Dict, view: AsOfView) -> GWDecision:
        xp = self._xp_table(view)
        prices = view.prices()
        etypes = view.element_types()
        teams = view.team_ids()
        squad = state_info['squad']           # pid -> OwnedPlayer
        bank = state_info['bank']

        transfers: List[Transfer] = []
        if state_info['available_ft'] >= 1:
            best = self._best_swap(squad, bank, xp, prices, etypes, teams)
            if best is not None:
                transfers = [best]

        squad_ids = set(squad)
        for t in transfers:
            squad_ids.discard(t.out_id)
            squad_ids.add(t.in_id)

        picks = self._build_picks(list(squad_ids), xp, etypes)
        return GWDecision(transfers=transfers, chip=None, picks=picks)

    def _best_swap(
        self, squad: Dict, bank: int,
        xp: Dict[int, float], prices: Dict[int, int],
        etypes: Dict[int, int], teams: Dict[int, int],
    ) -> Optional[Transfer]:
        club_counts: Dict[int, int] = {}
        for pid in squad:
            club_counts[teams.get(pid)] = club_counts.get(teams.get(pid), 0) + 1

        best, best_gain = None, MIN_XP_GAIN_TO_TRANSFER
        for out_id, owned in squad.items():
            out_et = etypes.get(out_id)
            out_club = teams.get(out_id)
            funds = bank + sell_price(
                owned.purchase_price, prices.get(out_id, owned.purchase_price)
            )
            for in_id, in_xp in xp.items():
                if in_id in squad or etypes.get(in_id) != out_et:
                    continue
                price = prices.get(in_id)
                if price is None or price > funds:
                    continue
                in_club = teams.get(in_id)
                count = club_counts.get(in_club, 0) - (1 if in_club == out_club else 0)
                if count >= MAX_PER_CLUB:
                    continue
                gain = in_xp - xp.get(out_id, 0.0)
                if gain > best_gain:
                    best, best_gain = Transfer(out_id=out_id, in_id=in_id), gain
        return best

    # ------------------------------------------------------------------

    def _build_picks(
        self, squad_ids: List[int],
        xp: Dict[int, float], etypes: Dict[int, int],
    ) -> List[Pick]:
        by_type: Dict[int, List[int]] = {1: [], 2: [], 3: [], 4: []}
        for pid in squad_ids:
            by_type[etypes[pid]].append(pid)
        for et in by_type:
            by_type[et].sort(key=lambda p: -xp.get(p, 0.0))

        best_xi, best_total = None, -1.0
        for d, m, f in _valid_formations():
            if len(by_type[2]) < d or len(by_type[3]) < m or len(by_type[4]) < f:
                continue
            xi = by_type[1][:1] + by_type[2][:d] + by_type[3][:m] + by_type[4][:f]
            total = sum(xp.get(p, 0.0) for p in xi)
            if total > best_total:
                best_xi, best_total = xi, total

        xi_set = set(best_xi)
        bench_gk = [p for p in by_type[1] if p not in xi_set]
        bench_out = sorted(
            (p for p in squad_ids if p not in xi_set and etypes[p] != GK),
            key=lambda p: -xp.get(p, 0.0),
        )
        ordered = best_xi + bench_gk + bench_out

        ranked = sorted(best_xi, key=lambda p: -xp.get(p, 0.0))
        captain, vice = ranked[0], ranked[1]

        return [
            Pick(
                player_id=pid,
                position=i + 1,
                element_type=etypes[pid],
                is_captain=(pid == captain),
                is_vice_captain=(pid == vice),
            )
            for i, pid in enumerate(ordered)
        ]
