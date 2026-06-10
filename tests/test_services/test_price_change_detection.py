"""Nightly price-change detection derived from transfer snapshots
(scripts/collect_price_snapshots.py::detect_price_changes)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / 'scripts'))

from collect_price_snapshots import detect_price_changes
from data.database import Database


@pytest.fixture
def db(tmp_path):
    database = Database(str(tmp_path / 'test.db'))

    def snap(pid, day, cost):
        database.execute_update(
            "INSERT INTO player_transfer_snapshots "
            "(player_id, snapshot_date, now_cost, gameweek) "
            "VALUES (?, ?, ?, 10)", (pid, day, cost))
    # player 1 rises overnight, player 2 falls, players 3-10 static
    # (enough static players that 2 changes stay under the mass-change
    # guard's 30% renumbering threshold)
    snap(1, '2026-09-01', 100); snap(1, '2026-09-02', 101)
    snap(2, '2026-09-01', 55);  snap(2, '2026-09-02', 54)
    for pid in range(3, 11):
        snap(pid, '2026-09-01', 45); snap(pid, '2026-09-02', 45)
    return database


def changes(db):
    return db.execute_query(
        "SELECT player_id, old_price, new_price, change_amount "
        "FROM price_changes ORDER BY player_id")


def test_detects_rises_and_falls_not_static(db):
    n = detect_price_changes(db)
    assert n == 2
    rows = changes(db)
    assert [(r['player_id'], r['change_amount']) for r in rows] == \
        [(1, 1), (2, -1)]
    assert rows[0]['old_price'] == 100 and rows[0]['new_price'] == 101


def test_idempotent_rerun(db):
    detect_price_changes(db)
    assert detect_price_changes(db) >= 0
    assert len(changes(db)) == 2   # no duplicates


def test_large_gap_is_not_a_nightly_move(db):
    # six-month gap (season boundary / outage) must not be recorded
    db.execute_update(
        "INSERT INTO player_transfer_snapshots "
        "(player_id, snapshot_date, now_cost, gameweek) "
        "VALUES (1, '2027-03-01', 130, 28)")
    detect_price_changes(db)
    rows = [r for r in changes(db) if r['new_price'] == 130]
    assert rows == []


def test_backfill_processes_all_pairs(db):
    db.execute_update(
        "INSERT INTO player_transfer_snapshots "
        "(player_id, snapshot_date, now_cost, gameweek) "
        "VALUES (1, '2026-09-03', 102, 10)")
    for pid in range(3, 11):   # statics present on day 3 too, else the
        db.execute_update(     # 1-player pair trips the renumbering guard
            "INSERT INTO player_transfer_snapshots "
            "(player_id, snapshot_date, now_cost, gameweek) "
            "VALUES (?, '2026-09-03', 45, 10)", (pid,))
    n = detect_price_changes(db, backfill=True)
    assert n == 3   # two changes on 09-02 + one on 09-03
    player1 = [r for r in changes(db) if r['player_id'] == 1]
    assert [(r['old_price'], r['new_price']) for r in player1] == \
        [(100, 101), (101, 102)]


class TestPredictionVerification:
    def _seed(self, tmp_path):
        from collect_price_snapshots import verify_price_predictions
        d = Database(str(tmp_path / 'verify.db'))
        # two snapshot days, one detected rise for player 1
        for pid in range(1, 11):
            for day, cost in (('2026-09-01', 50), ('2026-09-02', 50)):
                d.execute_update(
                    "INSERT INTO player_transfer_snapshots "
                    "(player_id, snapshot_date, now_cost, gameweek) "
                    "VALUES (?, ?, ?, 5)",
                    (pid, day, cost + (1 if pid == 1 and day.endswith('02') else 0)))
        detect_price_changes(d)
        return d, verify_price_predictions

    def test_outcomes_settled_correct_incorrect_and_hold(self, tmp_path):
        d, verify = self._seed(tmp_path)
        preds = [
            (1, '2026-09-02', 1),    # predicted rise, player 1 rose: correct
            (2, '2026-09-02', 1),    # predicted rise, no change: wrong
            (3, '2026-09-02', -1),   # predicted fall, no change: wrong
        ]
        for pid, day, change in preds:
            d.execute_update(
                "INSERT INTO price_predictions "
                "(player_id, prediction_for_date, predicted_change, confidence) "
                "VALUES (?, ?, ?, 0.8)", (pid, day, change))
        assert verify(d) == 3
        rows = d.execute_query(
            "SELECT player_id, actual_change, prediction_correct "
            "FROM price_predictions ORDER BY player_id")
        assert [(r['actual_change'], r['prediction_correct']) for r in rows] == \
            [(1, 1), (0, 0), (0, 0)]

    def test_uncovered_dates_stay_null(self, tmp_path):
        d, verify = self._seed(tmp_path)
        # prediction for a date with no snapshot coverage (outage)
        d.execute_update(
            "INSERT INTO price_predictions "
            "(player_id, prediction_for_date, predicted_change, confidence) "
            "VALUES (1, '2026-09-10', 1, 0.9)")
        assert verify(d) == 0
        row = d.execute_query("SELECT actual_change FROM price_predictions")[0]
        assert row['actual_change'] is None
