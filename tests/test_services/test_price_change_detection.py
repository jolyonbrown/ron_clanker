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
