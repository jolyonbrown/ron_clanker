"""
Walk-forward prediction calibration — the winner's-curse correction.

Stored predictions are over-dispersed: high predictions systematically
over-promise. Measured on 2025-26 (18,307 pairs, DGW-normalized):
the global regression of actual on predicted has slope ~0.80, the
decision-relevant 4-7 xP band realizes at 0.68-0.77, and per-position
slopes range 0.73 (FWD) to 0.85 (MID). Any consumer that argmaxes or
sums raw predictions (transfer gains, chip EV, MILP squad build)
therefore overweights its top picks — the winner's curse.

PredictionShrinker fits, per position, the best linear predictor
    E[actual | pred] = a + b * pred
on (prediction, actual) pairs STRICTLY BEFORE a given as-of gameweek,
and applies it with a floor at zero. Fitting walk-forward keeps the
backtest honest and mirrors what the live system can do next season
(it always has all completed-GW pairs at decision time).

The as-of gameweek is the DECISION gameweek, not the prediction's
target gameweek: shrinking a GW+3 prediction with parameters fitted
through GW+2 would leak actuals that don't exist yet at the deadline.

Note shrinkage is monotone per position, so within-position argmax
(e.g. captain choice) is unchanged; what changes is the LEVEL —
transfer gains compress, chip EV compresses, and the MILP rebalances
spend away from premium price tags whose predictions shrink most in
absolute terms.
"""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

from backtest.data import HistoricalDataProvider
from backtest.scoring import PlayerGW

logger = logging.getLogger('ron_clanker.backtest.calibration')

# Below this, pairs are fringe players whose 0-0 mass tells us nothing
# about the decision region.
MIN_PRED_FOR_FIT = 0.5
# Identity transform until at least this many gameweeks of pairs exist.
MIN_HISTORY_GWS = 3


class PredictionShrinker:
    """Per-position linear calibration fitted walk-forward."""

    def __init__(self, provider: HistoricalDataProvider,
                 min_history_gws: int = MIN_HISTORY_GWS):
        self._etypes = provider.player_element_types()
        self._min_history_gws = min_history_gws
        self._pairs_by_gw: Dict[int, List[Tuple[int, float, float]]] = {}
        for gw in provider.gameweeks():
            preds = provider.predictions(gw)
            if not preds:
                continue
            actuals = provider.actuals(gw)
            self._pairs_by_gw[gw] = [
                (self._etypes.get(pid, 0), xp,
                 float(actuals.get(pid, PlayerGW()).points))
                for pid, xp in preds.items()
                if xp >= MIN_PRED_FOR_FIT
            ]
        self._params_cache: Dict[int, Optional[Dict[int, Tuple[float, float]]]] = {}

    def params_as_of(self, gameweek: int) -> Optional[Dict[int, Tuple[float, float]]]:
        """(a, b) per element_type, fitted on pairs strictly before
        `gameweek`. None while history is too thin (identity)."""
        if gameweek in self._params_cache:
            return self._params_cache[gameweek]

        history_gws = [g for g in self._pairs_by_gw if g < gameweek]
        params: Optional[Dict[int, Tuple[float, float]]] = None
        if len(history_gws) >= self._min_history_gws:
            pairs = [p for g in history_gws for p in self._pairs_by_gw[g]]
            params = {}
            arr = np.array(pairs)  # columns: pos, pred, actual
            for et in (1, 2, 3, 4):
                sub = arr[arr[:, 0] == et]
                if len(sub) >= 30 and np.ptp(sub[:, 1]) > 0:
                    b, a = np.polyfit(sub[:, 1], sub[:, 2], 1)
                else:
                    # Pool everything as fallback for a thin position
                    b, a = np.polyfit(arr[:, 1], arr[:, 2], 1)
                params[et] = (float(a), float(b))
        self._params_cache[gameweek] = params
        return params

    def shrink(self, predictions: Dict[int, float],
               as_of_gw: int) -> Dict[int, float]:
        """Apply calibration to a {player_id: xP} map. Identity while
        fewer than min_history_gws of completed pairs exist."""
        params = self.params_as_of(as_of_gw)
        if params is None:
            return dict(predictions)
        out = {}
        for pid, xp in predictions.items():
            a, b = params.get(self._etypes.get(pid, 0), (0.0, 1.0))
            out[pid] = max(0.0, a + b * xp)
        return out
