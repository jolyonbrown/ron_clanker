"""Live prediction calibration (ml/prediction/calibration.py) and its
wiring into ChipStrategyService."""

import pytest

from ml.prediction.calibration import (
    DEFAULT_PRIOR,
    PredictionCalibrator,
    fit_linear_calibration,
)


class FakeDB:
    """Answers the three queries the calibrator makes."""

    def __init__(self, etypes, pred_rows, history_rows, n_gws):
        self.etypes = etypes              # pid -> element_type
        self.pred_rows = pred_rows        # (pid, gw, predicted)
        self.history_rows = history_rows  # (pid, gw, points)
        self.n_gws = n_gws

    def execute_query(self, query, params=()):
        if 'element_type FROM players' in query:
            return [{'id': pid, 'element_type': et}
                    for pid, et in self.etypes.items()]
        if 'COUNT(DISTINCT gameweek)' in query:
            return [{'n': self.n_gws}]
        if 'player_predictions pp' in query:
            min_pred, before_gw = params[0], params[1]
            actuals = {(p, g): pts for p, g, pts in self.history_rows}
            return [
                {'et': self.etypes[pid], 'pred': pred,
                 'actual': actuals.get((pid, gw), 0)}
                for pid, gw, pred in self.pred_rows
                if pred >= min_pred and gw < before_gw
            ]
        raise AssertionError(f'unexpected query: {query}')


def make_db(slope=0.8, gws=range(1, 7)):
    """Synthetic season where actual = slope * pred exactly."""
    etypes = {pid: (pid % 4) + 1 for pid in range(1, 41)}
    preds, hist = [], []
    for gw in gws:
        for pid in etypes:
            pred = 1.0 + (pid % 7) + 0.1 * gw
            preds.append((pid, gw, pred))
            hist.append((pid, gw, slope * pred))
    return FakeDB(etypes, preds, hist, n_gws=len(list(gws)))


class TestFit:
    def test_recovers_known_slope(self):
        pairs = [(et, x, 0.75 * x + 0.1)
                 for et in (1, 2, 3, 4) for x in [1, 2, 3, 4, 5, 6, 7, 8] * 5]
        params = fit_linear_calibration(pairs)
        for et, (a, b) in params.items():
            assert b == pytest.approx(0.75, abs=0.01)
            assert a == pytest.approx(0.1, abs=0.05)

    def test_empty_pairs_returns_fallback(self):
        assert fit_linear_calibration([], fallback=DEFAULT_PRIOR) == DEFAULT_PRIOR
        assert fit_linear_calibration([])[3] == (0.0, 1.0)

    def test_thin_position_uses_pooled(self):
        pairs = [(2, x, 0.5 * x) for x in range(1, 50)]  # only DEF has data
        params = fit_linear_calibration(pairs)
        assert params[4][1] == pytest.approx(params[2][1])


class TestCalibrator:
    def test_prior_used_when_history_thin(self):
        cal = PredictionCalibrator(make_db(gws=range(1, 3)))  # 2 GWs only
        assert cal.params_as_of(3) == DEFAULT_PRIOR

    def test_fits_from_pairs_when_history_sufficient(self):
        cal = PredictionCalibrator(make_db(slope=0.8))
        params = cal.params_as_of(7)
        for et, (a, b) in params.items():
            assert b == pytest.approx(0.8, abs=0.02)

    def test_calibrate_applies_per_position_and_floors_at_zero(self):
        cal = PredictionCalibrator(make_db(slope=0.5))
        out = cal.calibrate({1: 6.0, 2: 0.0}, as_of_gw=7)
        assert out[1] == pytest.approx(3.0, abs=0.15)
        assert out[2] >= 0.0

    def test_calibrate_multi_uses_single_as_of(self):
        cal = PredictionCalibrator(make_db(slope=0.5))
        multi = {1: {7: 4.0, 8: 6.0}}
        out = cal.calibrate_multi(multi, as_of_gw=7)
        # Both targets calibrated with the SAME as-of-GW7 params
        assert out[1][8] / out[1][7] == pytest.approx(6.0 / 4.0, abs=0.1)

    def test_db_failure_falls_back_to_prior(self):
        class BrokenDB:
            def execute_query(self, *a, **k):
                raise RuntimeError('boom')
        cal = PredictionCalibrator(BrokenDB())
        assert cal.params_as_of(20) == DEFAULT_PRIOR


class TestChipServiceWiring:
    def test_chip_service_calibrates_predictions(self):
        """A calibrator that halves everything must halve the EVs the
        service reads from player_predictions."""
        from services.chip_strategy import ChipStrategyService

        class HalvingCalibrator:
            def __init__(self):
                self.as_of_seen = []

            def calibrate(self, preds, as_of_gw):
                self.as_of_seen.append(as_of_gw)
                return {pid: xp / 2 for pid, xp in preds.items()}

            def calibrate_multi(self, multi, as_of_gw):
                self.as_of_seen.append(as_of_gw)
                return {pid: {gw: xp / 2 for gw, xp in m.items()}
                        for pid, m in multi.items()}

        class PredsDB:
            def execute_query(self, query, params=()):
                if 'player_predictions' in query:
                    return [{'player_id': 1, 'predicted_points': 8.0}]
                return []

        cal = HalvingCalibrator()
        svc = ChipStrategyService(database=PredsDB(), calibrator=cal)
        svc._calibration_as_of = 12
        preds = svc._predictions_for_gw(15, [1])
        assert preds[1] == 4.0
        assert cal.as_of_seen == [12]  # as-of decision GW, not target 15
