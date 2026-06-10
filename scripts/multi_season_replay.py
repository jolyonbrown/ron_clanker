#!/usr/bin/env python
"""
Multi-season replay — the anti-overfitting harness (ron_clanker-wxlx).

Replays the same strategy across all four recorded seasons. Every
decision-layer change this summer was validated on 2025-26 alone, and
several showed knife-edge sensitivity; a change that wins on four
seasons is a far safer bet than one tuned to win on one.

Past seasons (2022-23 .. 2024-25) run from historical_gameweek_data via
HistoricalSeasonProvider (positions inferred from scoring arithmetic,
teams from fixture structure, model-free decayed-PPG predictions).
2025-26 runs from the live provider with the same strategy for
comparability. Chips are not modelled for past seasons (rules differed)
so the chipless GreedyModelStrategy is the cross-season vehicle.

Usage: venv/bin/python scripts/multi_season_replay.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.baselines import GreedyModelStrategy
from backtest.data import DEFAULT_DB, HistoricalDataProvider
from backtest.history_provider import HistoricalSeasonProvider
from backtest.simulate import simulate_season

PAST_SEASONS = ('2022-23', '2023-24', '2024-25')


def main():
    if not DEFAULT_DB.exists():
        sys.exit('ron_clanker.db not found')

    print('=' * 68)
    print('MULTI-SEASON REPLAY — GreedyModelStrategy (chipless)')
    print('=' * 68)
    rows = []
    for season in PAST_SEASONS:
        provider = HistoricalSeasonProvider(season)
        result = simulate_season(GreedyModelStrategy(), provider,
                                 start_gw=1, end_gw=38, ft_topups={})
        n_gw = len(result.gameweeks)
        rows.append((season, result.total_net_points, n_gw,
                     sum(g.n_transfers for g in result.gameweeks),
                     'decayed-PPG (model-free)'))

    with HistoricalDataProvider() as provider:
        result = simulate_season(GreedyModelStrategy(), provider,
                                 start_gw=8, end_gw=38)
        rows.append(('2025-26', result.total_net_points,
                     len(result.gameweeks),
                     sum(g.n_transfers for g in result.gameweeks),
                     'stored ML predictions (GW8 entry)'))

    print(f'{"season":<9} {"points":>7} {"GWs":>4} {"pts/GW":>7} '
          f'{"transfers":>9}  predictions')
    for season, pts, n_gw, ntr, note in rows:
        print(f'{season:<9} {pts:>7} {n_gw:>4} {pts / n_gw:>7.1f} '
              f'{ntr:>9}  {note}')
    print()
    print('Past seasons exercise the DECISION machinery (state machine,')
    print('budget, FT banking, XI selection) on different season shapes;')
    print('the prediction quality differs by design. Use this to check')
    print('any strategy change generalizes beyond 2025-26.')


if __name__ == '__main__':
    main()
