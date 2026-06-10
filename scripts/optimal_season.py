#!/usr/bin/env python
"""
The perfect season — what was the theoretical best score for 2025-26?

Computes hindsight optima for Ron's GW8-38 window under full FPL rules
(budget at real per-GW prices, squad shape, max 3 per club, formations,
free transfers, chip windows):

  Tier A  PERFECT WEEKLY REBUILD: a fresh optimal £100m squad every
          gameweek (per-GW MILP on actual points) + optimally placed
          TC/BB per half. The absolute ceiling — no transfer rules
          could beat it.
  Tier B  SET-AND-FORGET: the single best 15 bought at GW8 prices and
          never transferred (one season-wide MILP choosing the squad
          and each week's XI + captain), + optimal TC overlay.
  Tier C  PERFECT MANAGER: greedy hindsight transfers at 1 FT/week
          through the real simulator (bank, sell prices, FT banking
          with the AFCON top-up all enforced), + optimal TC/BB/FH
          overlay per half. A realistic-rules lower bound on the true
          optimum, which lies between Tier C and Tier A.

Usage: venv/bin/python scripts/optimal_season.py
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pulp
from scipy.optimize import linear_sum_assignment

from backtest.data import DEFAULT_DB, HistoricalDataProvider
from backtest.scoring import GK, PlayerGW, Pick
from backtest.simulate import simulate_season
from backtest.state import MAX_PER_CLUB, SQUAD_SHAPE, Transfer, sell_price
from backtest.strategy import AsOfView, GWDecision, InitialSquad, Strategy

START_GW, END_GW = 8, 38
BUDGET = 1000
HALVES = {1: range(START_GW, 20), 2: range(20, END_GW + 1)}


# ----------------------------------------------------------------------
# Tier A: perfect weekly rebuild

def solve_weekly(actuals: Dict[int, PlayerGW], prices: Dict[int, int],
                 etypes: Dict[int, int], teams: Dict[int, int],
                 bench_counts: bool) -> Tuple[float, float, float, Set[int]]:
    """Best legal £100m squad for one GW by actual points.

    Returns (xi_points_with_captain, captain_actual, bench_actual, squad)."""
    pool = [p for p in prices if p in etypes]
    pts = {p: actuals.get(p, PlayerGW()).points for p in pool}

    prob = pulp.LpProblem('weekly', pulp.LpMaximize)
    x = {p: pulp.LpVariable(f'x{p}', cat='Binary') for p in pool}
    s = {p: pulp.LpVariable(f's{p}', cat='Binary') for p in pool}
    c = {p: pulp.LpVariable(f'c{p}', cat='Binary') for p in pool}

    scorers = x if bench_counts else s
    prob += pulp.lpSum(pts[p] * scorers[p] for p in pool) + \
        pulp.lpSum(pts[p] * c[p] for p in pool)

    prob += pulp.lpSum(x.values()) == 15
    for et, n in SQUAD_SHAPE.items():
        prob += pulp.lpSum(x[p] for p in pool if etypes[p] == et) == n
    clubs: Dict[int, List[int]] = {}
    for p in pool:
        clubs.setdefault(teams.get(p), []).append(p)
    for club, members in clubs.items():
        if len(members) > MAX_PER_CLUB:
            prob += pulp.lpSum(x[p] for p in members) <= MAX_PER_CLUB
    prob += pulp.lpSum(prices[p] * x[p] for p in pool) <= BUDGET
    for p in pool:
        prob += s[p] <= x[p]
        prob += c[p] <= s[p]
    prob += pulp.lpSum(s.values()) == 11
    prob += pulp.lpSum(c.values()) == 1
    prob += pulp.lpSum(s[p] for p in pool if etypes[p] == 1) == 1
    prob += pulp.lpSum(s[p] for p in pool if etypes[p] == 2) >= 3
    prob += pulp.lpSum(s[p] for p in pool if etypes[p] == 3) >= 2
    prob += pulp.lpSum(s[p] for p in pool if etypes[p] == 4) >= 1

    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    total = pulp.value(prob.objective) or 0.0
    cap = sum(pts[p] for p in pool if c[p].varValue and c[p].varValue > 0.5)
    bench = sum(pts[p] for p in pool
                if x[p].varValue and x[p].varValue > 0.5
                and not (s[p].varValue and s[p].varValue > 0.5))
    squad = {p for p in pool if x[p].varValue and x[p].varValue > 0.5}
    return total, cap, bench, squad


def tier_a(provider, etypes, teams) -> Dict:
    price_map = provider.price_map_through(START_GW - 1)
    weekly, tc_gain, bb_gain, squads = {}, {}, {}, {}
    for gw in range(START_GW, END_GW + 1):
        price_map.update(provider.prices(gw))
        actuals = provider.actuals(gw)
        v11, cap, _, squad = solve_weekly(actuals, price_map, etypes, teams,
                                          bench_counts=False)
        v15, _, _, _ = solve_weekly(actuals, price_map, etypes, teams,
                                    bench_counts=True)
        weekly[gw] = v11
        tc_gain[gw] = cap            # 3x vs 2x = +1 x captain actual
        bb_gain[gw] = v15 - v11
        squads[gw] = squad
        print(f'  GW{gw}: best XI {v11:.0f} (captain {cap:.0f}, '
              f'BB +{v15 - v11:.0f})')
    base = sum(weekly.values())
    chips = sum(max(tc_gain[g] for g in HALVES[h]) +
                max(bb_gain[g] for g in HALVES[h]) for h in HALVES)
    return {'base': base, 'chips': chips, 'total': base + chips,
            'weekly': weekly, 'tc_gain': tc_gain, 'bb_gain': bb_gain,
            'squads': squads}


def tier_a_paid(a: Dict) -> Dict:
    """Tier A but PAYING for the rebuilds: actual squad-to-squad diffs,
    1 FT/week banking to 5 (AFCON top-up to 5 at GW16), -4 per extra
    transfer, with WC and FH placed on the most expensive rebuild weeks
    (one of each per half; a Free Hit week reverts, so the following
    week's diff is measured against the pre-FH squad). TC/BB overlay
    unchanged — they don't interact with transfers."""
    import itertools

    gws = sorted(a['squads'])

    def season_hits(wc_weeks: Set[int], fh_weeks: Set[int]) -> int:
        banked, hits = 0, 0
        prev = None   # persistent squad going into each week
        for gw in gws:
            target = a['squads'][gw]
            n = 0 if prev is None else len(target - prev)
            avail = min(5, banked + 1)
            if gw == 16:
                avail = max(avail, 5)   # AFCON top-up
            if gw in wc_weeks or gw in fh_weeks:
                pass                     # free rebuild; FTs frozen
            else:
                hits += max(0, n - avail) * 4
                banked = max(0, avail - n)
            if gw not in fh_weeks:
                prev = target            # FH reverts: keep pre-FH squad
        return hits

    h1 = [g for g in gws if g <= 19]
    h2 = [g for g in gws if g >= 20]
    best = None
    for wc1, fh1 in itertools.permutations(h1, 2):
        for wc2, fh2 in itertools.permutations(h2, 2):
            cost = season_hits({wc1, wc2}, {fh1, fh2})
            if best is None or cost < best[0]:
                best = (cost, (wc1, fh1, wc2, fh2))
    hits, chip_weeks = best
    no_chip_hits = season_hits(set(), set())
    transfers = sum(
        len(a['squads'][g] - a['squads'][prev_g])
        for prev_g, g in zip(gws, gws[1:])
    )
    return {
        'total': a['base'] - hits + a['chips'],
        'hits': hits,
        'no_chip_hits': no_chip_hits,
        'transfers': transfers,
        'chip_weeks': chip_weeks,
    }


# ----------------------------------------------------------------------
# Tier B: best set-and-forget squad

def tier_b(provider, etypes, teams) -> Dict:
    gw8_prices = provider.price_map_through(START_GW)
    actual_by_gw = {gw: provider.actuals(gw)
                    for gw in range(START_GW, END_GW + 1)}
    season_pts = {}
    for gw, acts in actual_by_gw.items():
        for pid, a in acts.items():
            season_pts[pid] = season_pts.get(pid, 0) + a.points

    # Prune the pool: strong scorers plus cheap enablers.
    scored = sorted(season_pts, key=lambda p: -season_pts[p])
    pool = {p for p in scored[:250] if p in gw8_prices and p in etypes}
    cheap = sorted((p for p in gw8_prices
                    if p in etypes and gw8_prices[p] <= 45),
                   key=lambda p: gw8_prices[p])
    pool |= set(cheap[:120])
    pool = sorted(pool)

    prob = pulp.LpProblem('setforget', pulp.LpMaximize)
    x = {p: pulp.LpVariable(f'x{p}', cat='Binary') for p in pool}
    gws = list(range(START_GW, END_GW + 1))
    s = {(p, g): pulp.LpVariable(f's{p}_{g}', cat='Binary')
         for p in pool for g in gws}
    c = {(p, g): pulp.LpVariable(f'c{p}_{g}', cat='Binary')
         for p in pool for g in gws}
    pts = {(p, g): actual_by_gw[g].get(p, PlayerGW()).points
           for p in pool for g in gws}

    prob += pulp.lpSum(pts[p, g] * s[p, g] for p in pool for g in gws) + \
        pulp.lpSum(pts[p, g] * c[p, g] for p in pool for g in gws)

    prob += pulp.lpSum(x.values()) == 15
    for et, n in SQUAD_SHAPE.items():
        prob += pulp.lpSum(x[p] for p in pool if etypes[p] == et) == n
    clubs: Dict[int, List[int]] = {}
    for p in pool:
        clubs.setdefault(teams.get(p), []).append(p)
    for members in clubs.values():
        if len(members) > MAX_PER_CLUB:
            prob += pulp.lpSum(x[p] for p in members) <= MAX_PER_CLUB
    prob += pulp.lpSum(gw8_prices[p] * x[p] for p in pool) <= BUDGET
    for g in gws:
        prob += pulp.lpSum(s[p, g] for p in pool) == 11
        prob += pulp.lpSum(c[p, g] for p in pool) == 1
        prob += pulp.lpSum(s[p, g] for p in pool if etypes[p] == 1) == 1
        prob += pulp.lpSum(s[p, g] for p in pool if etypes[p] == 2) >= 3
        prob += pulp.lpSum(s[p, g] for p in pool if etypes[p] == 3) >= 2
        prob += pulp.lpSum(s[p, g] for p in pool if etypes[p] == 4) >= 1
        for p in pool:
            prob += s[p, g] <= x[p]
            prob += c[p, g] <= s[p, g]

    prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=180))
    status = pulp.LpStatus[prob.status]
    total = pulp.value(prob.objective) or 0.0
    squad = [p for p in pool if x[p].varValue and x[p].varValue > 0.5]
    # TC overlay: best captain GW per half from the chosen lineups
    tc = 0.0
    for h, rng in HALVES.items():
        tc += max(
            sum(pts[p, g] for p in pool
                if c[p, g].varValue and c[p, g].varValue > 0.5)
            for g in rng
        )
    return {'total': total + tc, 'base': total, 'tc': tc,
            'squad': squad, 'status': status}


# ----------------------------------------------------------------------
# Tier C: greedy hindsight manager through the real simulator

class HindsightGreedyStrategy(Strategy):
    """God-mode strategy: sees actuals (that's the point), but every
    move still passes the simulator's budget/FT/legality enforcement."""

    name = 'hindsight-greedy'
    HORIZON = 4
    MIN_GAIN = 4   # actual pts over horizon to justify spending a FT

    def __init__(self, provider, initial_squad_ids: List[int]):
        self._provider = provider
        self._initial = initial_squad_ids
        self._etypes = provider.player_element_types()
        self._teams = provider.player_team_ids()
        self._actuals = {gw: provider.actuals(gw)
                         for gw in range(START_GW, END_GW + 1)}
        self.history: List[Dict] = []   # per-GW: captain/bench actuals

    def _pts(self, pid: int, gw: int) -> int:
        if gw > END_GW:
            return 0
        return self._actuals[gw].get(pid, PlayerGW()).points

    def _horizon_pts(self, pid: int, gw: int) -> int:
        return sum(self._pts(pid, g) for g in range(gw, min(gw + self.HORIZON,
                                                            END_GW + 1)))

    def initial_squad(self, gameweek: int, view: AsOfView) -> InitialSquad:
        prices = view.prices()
        purchases = {pid: prices[pid] for pid in self._initial}
        return InitialSquad(purchases=purchases,
                            picks=self._picks(set(self._initial), gameweek))

    def decide(self, gameweek: int, state_info: Dict, view: AsOfView) -> GWDecision:
        prices = view.prices()
        squad = dict(state_info['squad'])
        clubs: Dict[Optional[int], int] = {}
        for pid in squad:
            clubs[self._teams.get(pid)] = clubs.get(self._teams.get(pid), 0) + 1
        bank = state_info['bank']
        transfers: List[Transfer] = []

        for _ in range(state_info['available_ft']):
            best, best_gain = None, self.MIN_GAIN
            for out_id, owned in squad.items():
                funds = bank + sell_price(
                    owned.purchase_price, prices.get(out_id, owned.purchase_price))
                out_h = self._horizon_pts(out_id, gameweek)
                out_club = self._teams.get(out_id)
                for in_id, et in self._etypes.items():
                    if in_id in squad or et != self._etypes.get(out_id):
                        continue
                    price = prices.get(in_id)
                    if price is None or price > funds:
                        continue
                    in_club = self._teams.get(in_id)
                    n = clubs.get(in_club, 0) + 1 - (in_club == out_club)
                    if n > MAX_PER_CLUB:
                        continue
                    gain = self._horizon_pts(in_id, gameweek) - out_h
                    if gain > best_gain:
                        best, best_gain = (out_id, in_id, price), gain
            if best is None:
                break
            out_id, in_id, price = best
            owned = squad.pop(out_id)
            received = sell_price(owned.purchase_price,
                                  prices.get(out_id, owned.purchase_price))
            bank += received - price
            from backtest.state import OwnedPlayer
            squad[in_id] = OwnedPlayer(in_id, price)
            clubs[self._teams.get(out_id)] -= 1
            in_club = self._teams.get(in_id)
            clubs[in_club] = clubs.get(in_club, 0) + 1
            transfers.append(Transfer(out_id=out_id, in_id=in_id))

        picks = self._picks(set(squad), gameweek)
        cap = next(p.player_id for p in picks if p.is_captain)
        self.history.append({
            'gameweek': gameweek,
            'captain_actual': self._pts(cap, gameweek),
            'bench_actual': sum(self._pts(p.player_id, gameweek)
                                for p in picks if p.position > 11),
        })
        return GWDecision(transfers=transfers, chip=None, picks=picks)

    def _picks(self, squad_ids: Set[int], gameweek: int) -> List[Pick]:
        by_type: Dict[int, List[int]] = {1: [], 2: [], 3: [], 4: []}
        for pid in squad_ids:
            by_type[self._etypes[pid]].append(pid)
        for et in by_type:
            by_type[et].sort(key=lambda p: -self._pts(p, gameweek))
        best_xi, best_total = None, -1
        for d in range(3, 6):
            for m in range(2, 6):
                f = 10 - d - m
                if not 1 <= f <= 3:
                    continue
                xi = by_type[1][:1] + by_type[2][:d] + by_type[3][:m] + by_type[4][:f]
                total = sum(self._pts(p, gameweek) for p in xi)
                if total > best_total:
                    best_xi, best_total = xi, total
        xi_set = set(best_xi)
        bench_gk = [p for p in by_type[1] if p not in xi_set]
        bench_out = sorted((p for p in squad_ids
                            if p not in xi_set and self._etypes[p] != GK),
                           key=lambda p: -self._pts(p, gameweek))
        ordered = best_xi + bench_gk + bench_out
        ranked = sorted(best_xi, key=lambda p: -self._pts(p, gameweek))
        cap, vice = ranked[0], ranked[1]
        return [Pick(player_id=pid, position=i + 1,
                     element_type=self._etypes[pid],
                     is_captain=(pid == cap), is_vice_captain=(pid == vice))
                for i, pid in enumerate(ordered)]


def tier_c(provider, etypes, teams, tier_a_result, initial_squad_ids) -> Dict:
    strat = HindsightGreedyStrategy(provider, initial_squad_ids)
    result = simulate_season(strat, provider, start_gw=START_GW, end_gw=END_GW)
    base = result.total_net_points

    by_gw = {h['gameweek']: h for h in strat.history}
    achieved = {g.gameweek: g.score.gross_points for g in result.gameweeks}
    # GW8 has no history entry captain... initial GW: derive from picks
    # (history only covers decide() GWs); compute GW8 from the result.
    # Chip overlays are additive: TC = +captain actual, BB = +bench
    # actual, FH = best weekly XI minus achieved XI. One chip per GW —
    # optimal assignment per half via the Hungarian algorithm.
    chips_total = 0.0
    assignments = {}
    for h, rng in HALVES.items():
        gws = [g for g in rng if g in by_gw]
        gains = []   # rows: chips [TC, BB, FH]; cols: gws
        tc_row = [by_gw[g]['captain_actual'] for g in gws]
        bb_row = [by_gw[g]['bench_actual'] for g in gws]
        fh_row = [max(0.0, tier_a_result['weekly'][g] - achieved[g]) for g in gws]
        import numpy as np
        cost = -np.array([tc_row, bb_row, fh_row])
        rows, cols = linear_sum_assignment(cost)
        for r, cidx in zip(rows, cols):
            chip = ['3xc', 'bboost', 'freehit'][r]
            gain = -cost[r, cidx]
            assignments[(h, chip)] = (gws[cidx], gain)
            chips_total += gain
    return {'base': base, 'chips': chips_total, 'total': base + chips_total,
            'assignments': assignments,
            'transfers': sum(g.n_transfers for g in result.gameweeks)}


# ----------------------------------------------------------------------

def main():
    if not DEFAULT_DB.exists():
        sys.exit('ron_clanker.db not found')
    with HistoricalDataProvider() as provider:
        etypes = provider.player_element_types()
        teams = provider.player_team_ids()

        print('=' * 70)
        print('TIER A — perfect £100m rebuild every week')
        print('=' * 70)
        a = tier_a(provider, etypes, teams)
        print(f"base {a['base']:.0f} + chips {a['chips']:.0f} "
              f"= {a['total']:.0f}")

        paid = tier_a_paid(a)
        wc1, fh1, wc2, fh2 = paid['chip_weeks']
        print()
        print(f"Tier A PAYING for the rebuilds: {paid['transfers']} transfers "
              f"-> {paid['hits']} pts of hits")
        print(f"  (would be {paid['no_chip_hits']} without chips; "
              f"WC@GW{wc1}/GW{wc2} + FH@GW{fh1}/GW{fh2} absorb the worst weeks)")
        print(f"  {a['base']:.0f} - {paid['hits']} + chips {a['chips']:.0f} "
              f"= {paid['total']:.0f}")
        print('  NB: assumes £100m available every week — real sell-on fees '
              'would erode that, so treat as an estimate.')

        print()
        print('=' * 70)
        print('TIER B — best set-and-forget squad (bought GW8, never touched)')
        print('=' * 70)
        b = tier_b(provider, etypes, teams)
        names = provider.player_names()
        print(f"status {b['status']} | base {b['base']:.0f} "
              f"+ TC {b['tc']:.0f} = {b['total']:.0f}")
        print('squad:', ', '.join(sorted(names.get(p, str(p))
                                         for p in b['squad'])))

        print()
        print('=' * 70)
        print('TIER C — perfect manager (1 FT/week, hindsight, real rules)')
        print('=' * 70)
        c = tier_c(provider, etypes, teams, a, b['squad'])
        print(f"base {c['base']} + chips {c['chips']:.0f} = {c['total']:.0f} "
              f"({c['transfers']} transfers, no hits)")
        for (h, chip), (gw, gain) in sorted(c['assignments'].items()):
            print(f'  half {h}: {chip}@GW{gw} +{gain:.0f}')

        print()
        print('=' * 70)
        print('THE PERFECT SEASON — GW8-38, 2025-26')
        print('=' * 70)
        rows = [
            ('Tier A: perfect weekly rebuild, free transfers', a['total']),
            ('Tier A: perfect weekly rebuild, PAYING hits', paid['total']),
            ('Tier C: perfect manager (real transfer rules)', c['total']),
            ('Tier B: best set-and-forget squad', b['total']),
            ('best backtest strategy (live+chips+shrink)', 1739),
            ("Ron's actual season", 1704),
            ('average manager', 1531),
        ]
        for label, pts in sorted(rows, key=lambda r: -r[1]):
            print(f'{label:<48} {pts:>6.0f}')
        print()
        print('The true rules-optimal lies between Tier C and Tier A.')


if __name__ == '__main__':
    main()
