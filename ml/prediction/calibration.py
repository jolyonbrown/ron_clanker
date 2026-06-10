"""
Prediction calibration — the winner's-curse correction, live edition.

Stored predictions are over-dispersed: the regression of actual points
on predicted has slope ~0.80 (measured on 18,307 pairs, 2025-26 —
FWD 0.73, DEF 0.77, GK 0.78, MID 0.85), and the decision-relevant
4-7 xP band realizes at only 0.68-0.77. Consumers that argmax or sum
raw predictions (chip EV, Wildcard/Free Hit rebuilds — 15 simultaneous
argmax bets) therefore systematically overweight their top picks.

PredictionCalibrator fits, per position, the best linear predictor
    E[actual | pred] = a + b * pred
on (prediction, actual) pairs from completed gameweeks STRICTLY BEFORE
the as-of gameweek, and applies it with a floor at zero. Until enough
pairs exist (early season) it falls back to the 2025-26 prior below.

Scope, per the 2025-26 backtest A/B (ron_clanker-kkrx / -2qop):
    APPLY to chip strategy EV and WC/FH rebuild inputs.
    DO NOT apply to the weekly TransferOptimizer — its roll-vs-make
    thresholds are tuned to the raw scale; calibrating its inputs
    without recalibrating the thresholds measured ~31 points WORSE.

Cross-season hygiene: player_predictions has no season column, so a
fresh season inheriting last season's rows would pollute the fit. Pass
`since` (ISO date, e.g. the season start) to restrict fitting to rows
created this season; the prior covers the gap until pairs accumulate.
"""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger('ron_clanker.calibration')

# Fringe (pred, actual) mass below this teaches nothing about the
# decision region.
MIN_PRED_FOR_FIT = 0.5
MIN_HISTORY_GWS = 3
MIN_PAIRS_PER_POSITION = 30

# Measured on the full 2025-26 season (DGW-normalized predictions vs
# actual GW totals). Used until the current season has enough pairs.
DEFAULT_PRIOR: Dict[int, Tuple[float, float]] = {
    1: (-0.21, 0.782),   # GK
    2: (0.10, 0.767),    # DEF
    3: (0.01, 0.846),    # MID
    4: (0.18, 0.728),    # FWD
}


def fit_linear_calibration(
    pairs: List[Tuple[int, float, float]],
    fallback: Optional[Dict[int, Tuple[float, float]]] = None,
) -> Dict[int, Tuple[float, float]]:
    """Fit (a, b) per element_type from (element_type, pred, actual)
    triples. Positions with too few pairs use the pooled fit; an empty
    input returns `fallback` (or identity)."""
    if not pairs:
        return dict(fallback) if fallback else {et: (0.0, 1.0) for et in (1, 2, 3, 4)}
    arr = np.asarray(pairs, dtype=float)
    pooled_b, pooled_a = np.polyfit(arr[:, 1], arr[:, 2], 1)
    params: Dict[int, Tuple[float, float]] = {}
    for et in (1, 2, 3, 4):
        sub = arr[arr[:, 0] == et]
        if len(sub) >= MIN_PAIRS_PER_POSITION and np.ptp(sub[:, 1]) > 0:
            b, a = np.polyfit(sub[:, 1], sub[:, 2], 1)
        else:
            a, b = pooled_a, pooled_b
        params[et] = (float(a), float(b))
    return params


class PredictionCalibrator:
    """Live calibrator over the project's Database wrapper."""

    def __init__(self, database, min_history_gws: int = MIN_HISTORY_GWS,
                 prior: Optional[Dict[int, Tuple[float, float]]] = None,
                 since: Optional[str] = None):
        self.db = database
        self.min_history_gws = min_history_gws
        self.prior = dict(DEFAULT_PRIOR if prior is None else prior)
        self.since = since
        self._etypes: Optional[Dict[int, int]] = None
        self._params_cache: Dict[int, Dict[int, Tuple[float, float]]] = {}

    # ------------------------------------------------------------------

    def _element_types(self) -> Dict[int, int]:
        if self._etypes is None:
            rows = self.db.execute_query(
                "SELECT id, element_type FROM players"
            )
            self._etypes = {r['id']: r['element_type'] for r in rows}
        return self._etypes

    def _load_pairs(self, before_gw: int) -> List[Tuple[int, float, float]]:
        since_clause = "AND pp.created_at >= ?" if self.since else ""
        args: tuple = (MIN_PRED_FOR_FIT, before_gw)
        if self.since:
            args = args + (self.since,)
        rows = self.db.execute_query(
            f"""
            SELECT p.element_type AS et,
                   pp.predicted_points AS pred,
                   COALESCE(a.pts, 0) AS actual
            FROM player_predictions pp
            JOIN players p ON p.id = pp.player_id
            LEFT JOIN (
                SELECT player_id, gameweek, SUM(total_points) AS pts
                FROM player_gameweek_history GROUP BY player_id, gameweek
            ) a ON a.player_id = pp.player_id AND a.gameweek = pp.gameweek
            WHERE pp.predicted_points >= ?
              AND pp.gameweek < ?
              {since_clause}
            """,
            args,
        )
        return [(r['et'], float(r['pred']), float(r['actual'])) for r in rows]

    def params_as_of(self, gameweek: int) -> Dict[int, Tuple[float, float]]:
        """Calibration params using only information available before the
        gameweek's deadline. Falls back to the prior while thin."""
        if gameweek in self._params_cache:
            return self._params_cache[gameweek]
        try:
            pairs = self._load_pairs(before_gw=gameweek)
        except Exception as exc:
            logger.warning("Calibration: pair load failed (%s) — using prior", exc)
            pairs = []
        try:
            rows = self.db.execute_query(
                "SELECT COUNT(DISTINCT gameweek) AS n FROM player_predictions "
                "WHERE gameweek < ?" + (" AND created_at >= ?" if self.since else ""),
                (gameweek, self.since) if self.since else (gameweek,),
            )
            gws_covered = rows[0]['n'] if rows else 0
        except Exception:
            gws_covered = 0
        if gws_covered < self.min_history_gws or not pairs:
            params = dict(self.prior)
            logger.info(
                "Calibration: %d GW(s) of pairs before GW%d — using prior",
                gws_covered, gameweek,
            )
        else:
            params = fit_linear_calibration(pairs, fallback=self.prior)
        self._params_cache[gameweek] = params
        return params

    # ------------------------------------------------------------------

    def calibrate(self, predictions: Dict[int, float],
                  as_of_gw: int) -> Dict[int, float]:
        """Apply calibration to a {player_id: xP} map. as_of_gw is the
        DECISION gameweek — never a future target gameweek, whose
        actuals don't exist yet at the deadline."""
        params = self.params_as_of(as_of_gw)
        etypes = self._element_types()
        out = {}
        for pid, xp in predictions.items():
            a, b = params.get(etypes.get(pid, 0), (0.0, 1.0))
            out[pid] = max(0.0, a + b * float(xp or 0.0))
        return out

    def calibrate_multi(self, multi: Dict[int, Dict[int, float]],
                        as_of_gw: int) -> Dict[int, Dict[int, float]]:
        """Calibrate a {player_id: {gameweek: xP}} map with one set of
        as-of params for every target gameweek."""
        params = self.params_as_of(as_of_gw)
        etypes = self._element_types()
        out: Dict[int, Dict[int, float]] = {}
        for pid, by_gw in multi.items():
            a, b = params.get(etypes.get(pid, 0), (0.0, 1.0))
            out[pid] = {
                gw: max(0.0, a + b * float(xp or 0.0))
                for gw, xp in by_gw.items()
            }
        return out
