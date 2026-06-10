"""Season rollover (scripts/season_rollover.py) — migrate-then-wipe,
plus the price-detection guard against ID renumbering."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / 'scripts'))

from collect_price_snapshots import detect_price_changes
from season_rollover import WIPE_TABLES, migrate_history, wipe_current_season
from data.database import Database


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / 'roll.db'))
    d.execute_update(
        "INSERT INTO teams (id, code, name, short_name) "
        "VALUES (1, 3, 'Arsenal', 'ARS'), (2, 14, 'Liverpool', 'LIV')")
    d.execute_update(
        "INSERT INTO players (id, code, first_name, second_name, web_name, "
        "team_id, element_type, now_cost) "
        "VALUES (10, 99999, 'Test', 'Fwd', 'TestFwd', 1, 4, 80)")
    d.execute_update(
        "INSERT INTO fixtures (id, code, event, team_h, team_a, "
        "team_h_difficulty, team_a_difficulty, kickoff_time) "
        "VALUES (500, 1, 7, 1, 2, 3, 4, '2025-10-18T14:00:00Z')")
    d.execute_update(
        "INSERT INTO player_gameweek_history "
        "(player_id, gameweek, fixture_id, minutes, total_points, goals_scored, value) "
        "VALUES (10, 7, 500, 90, 9, 1, 81)")
    return d


class TestMigrate:
    def test_history_keyed_by_code_with_fixture_context(self, db):
        n = migrate_history(db, '2025-26')
        assert n == 1
        row = db.execute_query(
            "SELECT * FROM historical_gameweek_data WHERE season_id='2025-26'")[0]
        assert row['player_code'] == 99999       # stable cross-season key
        assert row['opponent_team_code'] == 14   # away club's code
        assert row['was_home'] == 1
        assert row['fixture_difficulty'] == 3
        assert row['total_points'] == 9 and row['value'] == 81

    def test_idempotent(self, db):
        migrate_history(db, '2025-26')
        n = migrate_history(db, '2025-26')
        assert n == 1
        assert db.execute_query(
            "SELECT COUNT(*) AS n FROM historical_gameweek_data")[0]['n'] == 1

    def test_season_registered(self, db):
        migrate_history(db, '2025-26')
        row = db.execute_query("SELECT * FROM seasons WHERE id='2025-26'")[0]
        assert row['data_source'] == 'ron_clanker_live'


class TestWipe:
    def test_wipes_id_keyed_keeps_cross_season(self, db):
        migrate_history(db, '2025-26')
        counts = wipe_current_season(db)
        assert counts['players'] == 1
        assert counts['player_gameweek_history'] == 1
        for t in WIPE_TABLES:
            if isinstance(counts[t], int):
                left = db.execute_query(f"SELECT COUNT(*) AS n FROM {t}")[0]['n']
                assert left == 0, t
        # the migrated history survives
        assert db.execute_query(
            "SELECT COUNT(*) AS n FROM historical_gameweek_data")[0]['n'] == 1
        assert db.execute_query(
            "SELECT COUNT(*) AS n FROM seasons")[0]['n'] == 1


class TestRenumberingGuard:
    def test_mass_change_is_refused(self, tmp_path):
        """If most players 'changed price' overnight, the ids were
        renumbered (new season bootstrap) — detection must refuse."""
        d = Database(str(tmp_path / 'guard.db'))
        for pid in range(1, 21):
            d.execute_update(
                "INSERT INTO player_transfer_snapshots "
                "(player_id, snapshot_date, now_cost, gameweek) "
                "VALUES (?, '2026-07-01', ?, NULL)", (pid, 50 + pid))
            # next day: same ids, almost all different prices (renumbering)
            d.execute_update(
                "INSERT INTO player_transfer_snapshots "
                "(player_id, snapshot_date, now_cost, gameweek) "
                "VALUES (?, '2026-07-02', ?, NULL)", (pid, 90 + pid))
        n = detect_price_changes(d)
        assert n == 0
        assert d.execute_query(
            "SELECT COUNT(*) AS n FROM price_changes")[0]['n'] == 0

    def test_normal_night_still_detected(self, tmp_path):
        d = Database(str(tmp_path / 'ok.db'))
        for pid in range(1, 21):
            d.execute_update(
                "INSERT INTO player_transfer_snapshots "
                "(player_id, snapshot_date, now_cost, gameweek) "
                "VALUES (?, '2026-09-01', 50, 5)", (pid,))
            cost = 51 if pid <= 2 else 50   # 2/20 = 10% changed
            d.execute_update(
                "INSERT INTO player_transfer_snapshots "
                "(player_id, snapshot_date, now_cost, gameweek) "
                "VALUES (?, '2026-09-02', ?, 5)", (pid, cost))
        assert detect_price_changes(d) == 2
