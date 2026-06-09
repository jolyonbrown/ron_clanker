#!/usr/bin/env python
"""
Season backtest report (ron_clanker-obi).

Validates the scoring engine against the recorded season, then reports
prediction quality, captaincy quality and benchmark comparison — the
measurement baseline every summer model change gets judged against.

Usage:
    venv/bin/python scripts/run_backtest.py [--db data/ron_clanker.db]
                                            [--season 2025-26]
"""

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.data import DEFAULT_DB, HistoricalDataProvider
from backtest.metrics import (
    captain_quality,
    prediction_quality,
    summarize_captain_quality,
    summarize_prediction_quality,
)
from backtest.replay import replay_season


def section(title):
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def report(db_path, season):
    with HistoricalDataProvider(db_path=db_path, season=season) as provider:
        replays = replay_season(provider, mode='lock_time')
        pred_rows = prediction_quality(provider)
        cap_rows = captain_quality(provider)
        names = provider.player_names()

    # ------------------------------------------------------------------
    section(f'REPLAY VALIDATION — {season}')
    bad = [r for r in replays if not r.points_match]
    n_subs = sum(len(r.computed.autosubs) for r in replays)
    if bad:
        print(f'❌ {len(bad)}/{len(replays)} gameweeks FAILED to reproduce official scores:')
        for r in bad:
            print(f'   GW{r.gameweek}: computed {r.computed.gross_points} '
                  f'vs official {r.official_points} (chip={r.active_chip})')
        print('Everything below is untrustworthy until this is fixed.')
    else:
        print(f'✅ All {len(replays)} gameweeks reproduce official FPL scores exactly')
        print(f'   ({n_subs} autosubs and all chip/captaincy mechanics re-derived from raw data)')

    # ------------------------------------------------------------------
    section('SEASON VS AVERAGE MANAGER')
    total = sum(r.official_points - r.transfer_cost for r in replays)
    have_avg = [r for r in replays if r.average_score is not None]
    avg_total = sum(r.average_score for r in have_avg)
    beat = sum(r.official_points - r.transfer_cost > r.average_score for r in have_avg)
    level = sum(r.official_points - r.transfer_cost == r.average_score for r in have_avg)
    print(f'Net points (GW{replays[0].gameweek}-{replays[-1].gameweek}):  '
          f'Ron {total}  |  average manager {avg_total}  |  delta {total - avg_total:+d}')
    print(f'Gameweeks beaten/level/lost vs average: '
          f'{beat}/{level}/{len(have_avg) - beat - level}')
    print(f'Points lost to hits: {sum(r.transfer_cost for r in replays)}')
    print(f'Points left on bench (non-BB): {sum(r.computed.bench_points for r in replays)}')
    worst = sorted(have_avg, key=lambda r: (r.official_points - r.transfer_cost) - r.average_score)[:3]
    print('Worst GWs vs average: ' + ', '.join(
        f'GW{r.gameweek} ({(r.official_points - r.transfer_cost) - r.average_score:+d})'
        for r in worst))

    # ------------------------------------------------------------------
    section('PREDICTION QUALITY (stored pre-deadline xP vs actuals)')
    print(f'{"GW":>4} {"n":>5} {"MAE":>6} {"RMSE":>6} {"bias":>6} {"rho":>6} {"top10":>6}')
    for r in pred_rows:
        rho = '   n/a' if math.isnan(r.spearman) else f'{r.spearman:>6.3f}'
        print(f'{r.gameweek:>4} {r.n:>5} {r.mae:>6.2f} {r.rmse:>6.2f} '
              f'{r.bias:>+6.2f} {rho} {r.top10_hits:>5}/10')
    s = summarize_prediction_quality(pred_rows)
    print('-' * 44)
    print(f'Season means: MAE {s["mae"]:.2f}  RMSE {s["rmse"]:.2f}  '
          f'bias {s["bias"]:+.2f}  Spearman {s["spearman"]:.3f}  '
          f'top-10 hit rate {s["top10_hit_rate"]:.0%}')
    covered = {r.gameweek for r in pred_rows}
    missing = [r.gameweek for r in replays if r.gameweek not in covered]
    if missing:
        print(f'⚠ No stored predictions for GW {", ".join(map(str, missing))} '
              f'— excluded from means')
    if s['degenerate_gameweeks']:
        print(f'⚠ {s["degenerate_gameweeks"]} GW(s) stored a constant prediction '
              f'for every player (rho=n/a) — pipeline fallback, see rows above')

    # ------------------------------------------------------------------
    section('CAPTAINCY (armband vs hindsight-best in squad)')
    print(f'{"GW":>4}  {"armband":<16} {"pts":>3}  {"hindsight best":<16} {"pts":>3} {"regret":>7}')
    for r in cap_rows:
        flag = '' if r.optimal else '  <- missed'
        print(f'{r.gameweek:>4}  {names.get(r.armband_player, "?"):<16} {r.armband_actual:>3}  '
              f'{names.get(r.best_in_squad, "?"):<16} {r.best_in_squad_actual:>3} '
              f'{r.regret:>7}{flag}')
    c = summarize_captain_quality(cap_rows)
    print('-' * 60)
    print(f'Optimal armband: {c["optimal_picks"]}/{c["gameweeks"]} GWs  |  '
          f'total regret {c["total_regret"]} pts  |  '
          f'mean {c["mean_regret"]:.1f} pts/GW')
    print('(regret = extra points a perfect within-squad captain pick would have added)')


def main():
    ap = argparse.ArgumentParser(description='Run the season backtest report')
    ap.add_argument('--db', default=str(DEFAULT_DB), help='Path to season database')
    ap.add_argument('--season', default='2025-26')
    args = ap.parse_args()
    report(Path(args.db), args.season)


if __name__ == '__main__':
    main()
