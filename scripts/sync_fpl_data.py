#!/usr/bin/env python3
"""
Sync FPL data from API to local database.

Fetches latest player, team, fixture, and gameweek data and stores in SQLite.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.data_collector import DataCollector
from data.database import Database


async def sync_fpl_data():
    """Sync all FPL data to database."""
    print("=" * 80)
    print("RON CLANKER - FPL DATA SYNC")
    print("=" * 80)

    collector = DataCollector()
    db = Database()

    try:
        print("\n📡 Fetching latest FPL data...")
        fpl_data = await collector.update_all_data()

        # Sync players
        print(f"\n💾 Syncing {len(fpl_data['players'])} players...")
        for player in fpl_data['players']:
            db.upsert_player(player)
        print("✅ Players synced")

        # Sync teams
        print(f"\n💾 Syncing {len(fpl_data['teams'])} teams...")
        for team in fpl_data['teams']:
            team_data = {
                'id': team['id'],
                'code': team['code'],
                'name': team['name'],
                'short_name': team['short_name'],
                'strength': team.get('strength'),
                'strength_overall_home': team.get('strength_overall_home'),
                'strength_overall_away': team.get('strength_overall_away'),
                'strength_attack_home': team.get('strength_attack_home'),
                'strength_attack_away': team.get('strength_attack_away'),
                'strength_defence_home': team.get('strength_defence_home'),
                'strength_defence_away': team.get('strength_defence_away')
            }

            query = """
                INSERT INTO teams
                (id, code, name, short_name, strength, strength_overall_home,
                 strength_overall_away, strength_attack_home, strength_attack_away,
                 strength_defence_home, strength_defence_away, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    short_name = excluded.short_name,
                    strength = excluded.strength,
                    updated_at = CURRENT_TIMESTAMP
            """
            params = (
                team_data['id'], team_data['code'], team_data['name'],
                team_data['short_name'], team_data['strength'],
                team_data['strength_overall_home'], team_data['strength_overall_away'],
                team_data['strength_attack_home'], team_data['strength_attack_away'],
                team_data['strength_defence_home'], team_data['strength_defence_away']
            )
            db.execute_update(query, params)
        print("✅ Teams synced")

        # Sync fixtures
        print(f"\n💾 Syncing {len(fpl_data['fixtures'])} fixtures...")
        for fixture in fpl_data['fixtures']:
            db.upsert_fixture(fixture)
        print("✅ Fixtures synced")

        # Sync gameweeks
        print(f"\n💾 Syncing {len(fpl_data['gameweeks'])} gameweeks...")
        for gw in fpl_data['gameweeks']:
            query = """
                INSERT INTO gameweeks
                (id, name, deadline_time, finished, is_current, is_next)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    finished = excluded.finished,
                    is_current = excluded.is_current,
                    is_next = excluded.is_next
            """
            params = (
                gw['id'], gw['name'], gw.get('deadline_time'),
                gw.get('finished', False), gw.get('is_current', False),
                gw.get('is_next', False)
            )
            db.execute_update(query, params)
        print("✅ Gameweeks synced")

        # Summary
        print("\n" + "=" * 80)
        print("DATA SYNC COMPLETE")
        print("=" * 80)
        print(f"Database: {db.db_path}")
        print(f"Players: {len(fpl_data['players'])}")
        print(f"Teams: {len(fpl_data['teams'])}")
        print(f"Fixtures: {len(fpl_data['fixtures'])}")
        print(f"Gameweeks: {len(fpl_data['gameweeks'])}")

        current_gw = fpl_data.get('current_gameweek')
        if current_gw:
            print(f"\nCurrent Gameweek: {current_gw['id']} ({current_gw['name']})")
            print(f"Deadline: {current_gw.get('deadline_time', 'N/A')}")

        print("\n✅ Ron's database is up to date!")

    except Exception as e:
        print(f"\n❌ Error syncing data: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        await collector.close()

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(sync_fpl_data())
    sys.exit(exit_code)
