"""
Prediction quality and decision quality metrics, computed walk-forward.

Everything here compares what the model said BEFORE a gameweek
(player_predictions, stored at decision time, so inherently
lookahead-free) against what actually happened.

Conventions:
    - A player with a prediction but no gameweek history row didn't play:
      actual = 0. These count toward error metrics — minutes risk is part
      of the prediction job, not an excuse.
    - Captain regret is measured on the armband delta: 2 x (best actual
      in squad - effective captain's actual), i.e. the points a perfect
      within-squad captain pick would have added.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
from scipy import stats as scipy_stats

from backtest.data import HistoricalDataProvider
from backtest.scoring import PlayerGW

logger = logging.getLogger('ron_clanker.backtest.metrics')


@dataclass
class GWPredictionQuality:
    gameweek: int
    n: int                    # players with a prediction
    mae: float
    rmse: float
    bias: float               # mean (predicted - actual); positive = over-predicts
    spearman: float           # rank correlation, predictions vs actuals
    top10_hits: int           # |model top-10 ∩ actual top-10|


@dataclass
class GWCaptainQuality:
    gameweek: int
    armband_player: Optional[int]      # who actually wore it (post vice-promotion)
    armband_actual: int                # that player's actual GW points (single)
    model_pick: Optional[int]          # argmax predicted among the lock-time XI
    model_pick_actual: int
    best_in_squad: Optional[int]       # hindsight argmax actual among all 15
    best_in_squad_actual: int
    multiplier: int                    # 2, or 3 on Triple Captain

    @property
    def regret(self) -> int:
        """Extra points a perfect within-squad armband would have earned."""
        return (self.multiplier - 1) * (self.best_in_squad_actual - self.armband_actual)

    @property
    def optimal(self) -> bool:
        return self.armband_actual >= self.best_in_squad_actual


def prediction_quality(
    provider: HistoricalDataProvider,
    gameweeks: Optional[List[int]] = None,
) -> List[GWPredictionQuality]:
    """Per-GW accuracy of the stored pre-deadline predictions."""
    results = []
    for gw in gameweeks or provider.gameweeks():
        preds = provider.predictions(gw)
        if not preds:
            logger.warning("No stored predictions for GW%d — skipping", gw)
            continue
        actuals = provider.actuals(gw)
        ids = sorted(preds)
        predicted = np.array([preds[pid] for pid in ids], dtype=float)
        actual = np.array(
            [actuals.get(pid, PlayerGW()).points for pid in ids], dtype=float
        )
        errors = predicted - actual
        if np.ptp(predicted) == 0:
            # Degenerate week: the pipeline stored a constant fallback for
            # every player (e.g. GW15 2025-26, all 2.0). Rank metrics are
            # undefined; surfacing nan beats silently averaging it away.
            rho = float('nan')
        else:
            rho = scipy_stats.spearmanr(predicted, actual).statistic
        top10_pred = set(np.array(ids)[np.argsort(-predicted)[:10]])
        top10_actual = set(np.array(ids)[np.argsort(-actual)[:10]])
        results.append(
            GWPredictionQuality(
                gameweek=gw,
                n=len(ids),
                mae=float(np.mean(np.abs(errors))),
                rmse=float(np.sqrt(np.mean(errors ** 2))),
                bias=float(np.mean(errors)),
                spearman=float(rho),
                top10_hits=len(top10_pred & top10_actual),
            )
        )
    return results


def captain_quality(
    provider: HistoricalDataProvider,
    gameweeks: Optional[List[int]] = None,
) -> List[GWCaptainQuality]:
    """Per-GW armband outcome vs the model's pick vs hindsight-best."""
    api_picks = provider.api_picks()
    results = []
    for gw in gameweeks or provider.gameweeks():
        picks = provider.picks(gw)  # post-autosub positions; flags are lock-time
        actuals = provider.actuals(gw)
        preds = provider.predictions(gw)
        entry = provider.entry(gw)

        def actual_pts(pid):
            return actuals.get(pid, PlayerGW()).points

        # Effective armband: the multiplier>=2 element in the API picks.
        armband = None
        if api_picks and str(gw) in api_picks:
            armband = next(
                (p['element'] for p in api_picks[str(gw)]['picks']
                 if p['multiplier'] >= 2),
                None,
            )
        if armband is None:
            armband = next((p.player_id for p in picks if p.is_captain), None)

        # Model's pick: highest predicted among the players Ron started.
        xi = [p.player_id for p in picks if p.position <= 11]
        with_preds = [pid for pid in xi if pid in preds]
        model_pick = max(with_preds, key=lambda pid: preds[pid]) if with_preds else None

        squad = [p.player_id for p in picks]
        best = max(squad, key=actual_pts) if squad else None

        results.append(
            GWCaptainQuality(
                gameweek=gw,
                armband_player=armband,
                armband_actual=actual_pts(armband) if armband else 0,
                model_pick=model_pick,
                model_pick_actual=actual_pts(model_pick) if model_pick else 0,
                best_in_squad=best,
                best_in_squad_actual=actual_pts(best) if best else 0,
                multiplier=3 if entry.active_chip == '3xc' else 2,
            )
        )
    return results


def summarize_prediction_quality(rows: List[GWPredictionQuality]) -> Dict[str, float]:
    return {
        'gameweeks': len(rows),
        'degenerate_gameweeks': sum(1 for r in rows if np.isnan(r.spearman)),
        'mae': float(np.mean([r.mae for r in rows])),
        'rmse': float(np.mean([r.rmse for r in rows])),
        'bias': float(np.mean([r.bias for r in rows])),
        'spearman': float(np.nanmean([r.spearman for r in rows])),
        'top10_hit_rate': float(np.mean([r.top10_hits for r in rows])) / 10.0,
    }


def summarize_captain_quality(rows: List[GWCaptainQuality]) -> Dict[str, float]:
    return {
        'gameweeks': len(rows),
        'optimal_picks': sum(r.optimal for r in rows),
        'total_regret': sum(r.regret for r in rows),
        'mean_regret': float(np.mean([r.regret for r in rows])),
    }
