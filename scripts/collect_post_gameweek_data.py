#!/usr/bin/env python3
"""
Consolidated Post-Gameweek Data Collection

THE authoritative script for collecting all post-gameweek data.
Runs daily via cron (02:35), exits early if GW not finished yet.

Collects:
1. Player gameweek history (actual points, stats)
2. League standings (ranks, points)
3. Rival team picks (who picked what)

Features:
- Incremental: Only fetches new gameweek data
- Idempotent: Safe to run multiple times
- Fast: ~30-40 seconds (only players who played)
- Validated: Checks data quality, logs warnings

Usage:
    python scripts/collect_post_gameweek_data.py
    python scripts/collect_post_gameweek_data.py --force  # Ignore GW finished check
"""

import sys
import time
import argparse
import requests
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from utils.config import load_config

logger = logging.getLogger('ron_clanker.post_gw_collection')

FPL_API_BASE = "https://fantasy.premierleague.com/api"
REQUEST_DELAY = 0.1  # Seconds between API requests to avoid rate limits


class PostGameweekCollector:
    """Collects all post-gameweek data after a GW finishes."""

    def __init__(self, db: Database, config: Dict):
        self.db = db
        self.config = config
        self.team_id = config.get('team_id')
        self.league_id = config.get('league_id')
        self.stats = {
            'players_collected': 0,
            'players_failed': 0,
            'rivals_collected': 0,
            'rivals_failed': 0,
            'league_collected': False,
            'errors': []
        }

    def check_gameweek_status(self, force: bool = False) -> Optional[Dict]:
        """
        Check if current gameweek is finished and needs data collection.

        Returns:
            Dict with gameweek info if ready to collect, None otherwise
        """
        # Get current gameweek
        current_gw = self.db.execute_query("""
            SELECT id, finished, deadline_time
            FROM gameweeks
            WHERE is_current = 1
        """)

        if not current_gw:
            logger.error("PostGWCollection: No current gameweek found in database")
            return None

        gw = current_gw[0]
        gw_id = gw['id']
        finished = gw['finished']

        logger.info(f"PostGWCollection: Current GW{gw_id}, finished={finished}")

        if not finished and not force:
            logger.info("PostGWCollection: Gameweek not finished yet, exiting")
            return None

        # Check if we already have this gameweek's data
        max_gw_collected = self.db.execute_query("""
            SELECT MAX(gameweek) as max_gw
            FROM player_gameweek_history
        """)

        max_gw = max_gw_collected[0]['max_gw'] if max_gw_collected else 0

        if max_gw and max_gw >= gw_id and not force:
            logger.info(f"PostGWCollection: Already have GW{gw_id} data (max in DB: GW{max_gw}), exiting")
            return None

        logger.info(f"PostGWCollection: Ready to collect GW{gw_id} data (max in DB: GW{max_gw or 0})")
        return {'id': gw_id, 'finished': finished}

    def collect_player_gameweek_history(self, gameweek: int) -> int:
        """
        Collect player gameweek history data (INCREMENTAL).

        Only fetches players who played in this gameweek.
        Uses INSERT OR REPLACE for idempotency.

        Returns:
            Number of players successfully collected
        """
        logger.info(f"PostGWCollection: Collecting player GW history for GW{gameweek}")

        # Get players who played this gameweek (minutes > 0)
        # Note: players table updated by collect_fpl_data.py which runs at 02:30
        players = self.db.execute_query("""
            SELECT id, web_name
            FROM players
            WHERE minutes > 0
            ORDER BY id
        """)

        if not players:
            logger.warning("PostGWCollection: No players found with minutes > 0")
            # Fallback: get all players
            players = self.db.execute_query("SELECT id, web_name FROM players ORDER BY id")

        total_players = len(players)
        logger.info(f"PostGWCollection: Fetching history for {total_players} players who played")

        for i, player in enumerate(players, 1):
            player_id = player['id']
            player_name = player['web_name']

            try:
                # Fetch player history from FPL API
                url = f"{FPL_API_BASE}/element-summary/{player_id}/"
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()

                # Extract history array (contains all GWs this season)
                history = data.get('history', [])

                if not history:
                    logger.debug(f"PostGWCollection: No history for {player_name} (ID {player_id})")
                    continue

                # Store all history records (INSERT OR REPLACE handles deduplication)
                stored = self._store_player_history(player_id, history)

                self.stats['players_collected'] += 1

                # Progress logging
                if i % 50 == 0:
                    logger.info(f"PostGWCollection: Progress: {i}/{total_players} players processed")

                # Rate limiting
                time.sleep(REQUEST_DELAY)

            except requests.exceptions.RequestException as e:
                logger.warning(f"PostGWCollection: Failed to fetch history for {player_name}: {e}")
                self.stats['players_failed'] += 1
                self.stats['errors'].append(f"Player {player_id}: {str(e)}")
                continue
            except Exception as e:
                logger.error(f"PostGWCollection: Error processing {player_name}: {e}", exc_info=True)
                self.stats['players_failed'] += 1
                self.stats['errors'].append(f"Player {player_id}: {str(e)}")
                continue

        logger.info(f"PostGWCollection: Player history collection complete: {self.stats['players_collected']} succeeded, {self.stats['players_failed']} failed")
        return self.stats['players_collected']

    def _store_player_history(self, player_id: int, history: List[Dict]) -> int:
        """
        Store player gameweek history records.

        Uses INSERT OR REPLACE for idempotency.

        Returns:
            Number of records stored
        """
        stored = 0

        for gw in history:
            try:
                self.db.execute_update("""
                    INSERT OR REPLACE INTO player_gameweek_history (
                        player_id, gameweek, fixture_id, total_points,
                        minutes, goals_scored, assists, clean_sheets, goals_conceded,
                        own_goals, penalties_saved, penalties_missed, yellow_cards,
                        red_cards, saves, bonus, bps, influence, creativity,
                        threat, ict_index, value, selected, transfers_in,
                        transfers_out, tackles, interceptions, clearances_blocks_interceptions,
                        recoveries, defensive_contribution_points,
                        expected_goals, expected_assists, expected_goal_involvements,
                        expected_goals_conceded
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                """, (
                    player_id,
                    gw['round'],
                    gw.get('fixture'),
                    gw.get('total_points', 0),
                    gw.get('minutes', 0),
                    gw.get('goals_scored', 0),
                    gw.get('assists', 0),
                    gw.get('clean_sheets', 0),
                    gw.get('goals_conceded', 0),
                    gw.get('own_goals', 0),
                    gw.get('penalties_saved', 0),
                    gw.get('penalties_missed', 0),
                    gw.get('yellow_cards', 0),
                    gw.get('red_cards', 0),
                    gw.get('saves', 0),
                    gw.get('bonus', 0),
                    gw.get('bps', 0),
                    gw.get('influence'),
                    gw.get('creativity'),
                    gw.get('threat'),
                    gw.get('ict_index'),
                    gw.get('value'),
                    gw.get('selected'),
                    gw.get('transfers_in'),
                    gw.get('transfers_out'),
                    gw.get('tackles', 0),
                    gw.get('interceptions', 0),
                    gw.get('clearances_blocks_interceptions', 0),
                    gw.get('recoveries', 0),
                    gw.get('defensive_contribution', 0),
                    gw.get('expected_goals', 0),
                    gw.get('expected_assists', 0),
                    gw.get('expected_goal_involvements', 0),
                    gw.get('expected_goals_conceded', 0)
                ))
                stored += 1

            except Exception as e:
                logger.error(f"PostGWCollection: Failed to store GW{gw.get('round')} for player {player_id}: {e}")
                continue

        return stored

    def collect_league_standings(self, gameweek: int) -> bool:
        """
        Collect mini-league standings for this gameweek.

        Returns:
            True if successful
        """
        if not self.league_id:
            logger.warning("PostGWCollection: No league_id configured, skipping league standings")
            return False

        logger.info(f"PostGWCollection: Collecting league standings for GW{gameweek}")

        try:
            # Fetch league standings
            url = f"{FPL_API_BASE}/leagues-classic/{self.league_id}/standings/"
            params = {'page_standings': 1}
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            league_name = data.get('league', {}).get('name', f'League {self.league_id}')
            standings = data.get('standings', {}).get('results', [])

            if not standings:
                logger.warning(f"PostGWCollection: No standings found for league {self.league_id}")
                return False

            logger.info(f"PostGWCollection: Found {len(standings)} managers in '{league_name}'")

            # Store each manager's standing
            for entry in standings:
                try:
                    self.db.execute_update("""
                        INSERT OR REPLACE INTO league_standings_history (
                            league_id, entry_id, gameweek, rank, total_points, event_points
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        self.league_id,
                        entry['entry'],
                        gameweek,
                        entry['rank'],
                        entry['total'],
                        entry.get('event_total', 0)
                    ))
                except Exception as e:
                    logger.error(f"PostGWCollection: Failed to store standing for entry {entry.get('entry')}: {e}")
                    continue

            self.stats['league_collected'] = True
            logger.info(f"PostGWCollection: League standings collected successfully")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"PostGWCollection: Failed to fetch league standings: {e}")
            self.stats['errors'].append(f"League standings: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"PostGWCollection: Error processing league standings: {e}", exc_info=True)
            self.stats['errors'].append(f"League standings: {str(e)}")
            return False

    def collect_rival_team_picks(self, gameweek: int) -> int:
        """
        Collect rival team picks for this gameweek.
        EXCLUDES Ron's team (comes from my_team table instead).

        Returns:
            Number of rivals successfully collected
        """
        logger.info(f"PostGWCollection: Collecting rival team picks for GW{gameweek}")

        # Get list of rivals from league_rivals table, EXCLUDING Ron
        rivals = self.db.execute_query("""
            SELECT entry_id, player_name as entry_name
            FROM league_rivals
            WHERE league_id = ? AND entry_id != ?
        """, (self.league_id, self.team_id))

        if not rivals:
            logger.warning("PostGWCollection: No rivals found in league_rivals table")
            # Try to get from recent standings, EXCLUDING Ron
            rivals = self.db.execute_query("""
                SELECT DISTINCT entry_id, NULL as entry_name
                FROM league_standings_history
                WHERE league_id = ? AND gameweek = ? AND entry_id != ?
            """, (self.league_id, gameweek, self.team_id))

        if not rivals:
            logger.warning("PostGWCollection: No rivals to track")
            return 0

        logger.info(f"PostGWCollection: Fetching picks for {len(rivals)} rivals (excluding Ron)")

        for rival in rivals:
            entry_id = rival['entry_id']
            entry_name = rival.get('entry_name') or f'Entry {entry_id}'

            try:
                # Fetch team picks for this gameweek
                url = f"{FPL_API_BASE}/entry/{entry_id}/event/{gameweek}/picks/"
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()

                picks = data.get('picks', [])

                if not picks:
                    logger.debug(f"PostGWCollection: No picks found for {entry_name}")
                    continue

                # Store each pick
                for pick in picks:
                    try:
                        self.db.execute_update("""
                            INSERT OR REPLACE INTO rival_team_picks (
                                entry_id, gameweek, player_id, position,
                                is_captain, is_vice_captain, multiplier
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            entry_id,
                            gameweek,
                            pick['element'],
                            pick['position'],
                            pick['is_captain'],
                            pick['is_vice_captain'],
                            pick['multiplier']
                        ))
                    except Exception as e:
                        logger.error(f"PostGWCollection: Failed to store pick for {entry_name}: {e}")
                        continue

                self.stats['rivals_collected'] += 1

                # Rate limiting
                time.sleep(REQUEST_DELAY)

            except requests.exceptions.RequestException as e:
                logger.warning(f"PostGWCollection: Failed to fetch picks for {entry_name}: {e}")
                self.stats['rivals_failed'] += 1
                self.stats['errors'].append(f"Rival {entry_id}: {str(e)}")
                continue
            except Exception as e:
                logger.error(f"PostGWCollection: Error processing {entry_name}: {e}", exc_info=True)
                self.stats['rivals_failed'] += 1
                self.stats['errors'].append(f"Rival {entry_id}: {str(e)}")
                continue

        logger.info(f"PostGWCollection: Rival picks collection complete: {self.stats['rivals_collected']} succeeded, {self.stats['rivals_failed']} failed")
        return self.stats['rivals_collected']

    def validate_data(self, gameweek: int) -> Dict:
        """
        Validate collected data quality.

        Returns:
            Dict with validation results
        """
        logger.info(f"PostGWCollection: Validating GW{gameweek} data")

        validation = {
            'player_history_count': 0,
            'duplicates': 0,
            'league_standings_count': 0,
            'rival_picks_count': 0,
            'warnings': []
        }

        # Check player history
        result = self.db.execute_query("""
            SELECT COUNT(*) as cnt
            FROM player_gameweek_history
            WHERE gameweek = ?
        """, (gameweek,))
        validation['player_history_count'] = result[0]['cnt'] if result else 0

        if validation['player_history_count'] < 100:
            validation['warnings'].append(f"Only {validation['player_history_count']} players have GW{gameweek} history (expected ~200-300)")

        # Check for duplicates
        result = self.db.execute_query("""
            SELECT COUNT(*) as cnt
            FROM (
                SELECT player_id, gameweek, COUNT(*) as dup_cnt
                FROM player_gameweek_history
                WHERE gameweek = ?
                GROUP BY player_id, gameweek
                HAVING dup_cnt > 1
            )
        """, (gameweek,))
        validation['duplicates'] = result[0]['cnt'] if result else 0

        if validation['duplicates'] > 0:
            validation['warnings'].append(f"Found {validation['duplicates']} duplicate records")

        # Check league standings
        result = self.db.execute_query("""
            SELECT COUNT(*) as cnt
            FROM league_standings_history
            WHERE gameweek = ? AND league_id = ?
        """, (gameweek, self.league_id))
        validation['league_standings_count'] = result[0]['cnt'] if result else 0

        # Check rival picks
        result = self.db.execute_query("""
            SELECT COUNT(DISTINCT entry_id) as cnt
            FROM rival_team_picks
            WHERE gameweek = ?
        """, (gameweek,))
        validation['rival_picks_count'] = result[0]['cnt'] if result else 0

        return validation


def main():
    parser = argparse.ArgumentParser(description='Collect post-gameweek data')
    parser.add_argument('--force', action='store_true',
                       help='Force collection even if GW not finished')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose logging')

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    start_time = datetime.now()

    print("\n" + "=" * 80)
    print("POST-GAMEWEEK DATA COLLECTION")
    print("=" * 80)
    print(f"Timestamp: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    if args.force:
        print("⚠️  FORCE MODE: Ignoring gameweek finished check")

    logger.info("PostGWCollection: Starting")

    # Initialize
    db = Database()
    config = load_config()

    collector = PostGameweekCollector(db, config)

    # Check if we should collect
    gw_info = collector.check_gameweek_status(force=args.force)

    if not gw_info:
        print("\n✅ No collection needed (GW not finished or already collected)")
        print("=" * 80)
        return 0

    gameweek = gw_info['id']

    print(f"\n📊 Collecting data for Gameweek {gameweek}")
    print("=" * 80)

    # Collect player gameweek history
    print("\n1️⃣  Collecting player gameweek history...")
    players_collected = collector.collect_player_gameweek_history(gameweek)
    print(f"   ✅ Collected: {players_collected} players")
    if collector.stats['players_failed'] > 0:
        print(f"   ⚠️  Failed: {collector.stats['players_failed']} players")

    # Collect league standings
    print("\n2️⃣  Collecting league standings...")
    league_success = collector.collect_league_standings(gameweek)
    if league_success:
        print(f"   ✅ League standings collected")
    else:
        print(f"   ⚠️  Failed to collect league standings")

    # Collect rival team picks
    print("\n3️⃣  Collecting rival team picks...")
    rivals_collected = collector.collect_rival_team_picks(gameweek)
    print(f"   ✅ Collected: {rivals_collected} rivals")
    if collector.stats['rivals_failed'] > 0:
        print(f"   ⚠️  Failed: {collector.stats['rivals_failed']} rivals")

    # Validate data
    print("\n4️⃣  Validating data quality...")
    validation = collector.validate_data(gameweek)
    print(f"   Player history records: {validation['player_history_count']}")
    print(f"   League standings: {validation['league_standings_count']}")
    print(f"   Rival picks: {validation['rival_picks_count']}")
    print(f"   Duplicates: {validation['duplicates']}")

    if validation['warnings']:
        print(f"\n   ⚠️  Warnings:")
        for warning in validation['warnings']:
            print(f"      - {warning}")

    # Summary
    duration = (datetime.now() - start_time).total_seconds()

    print("\n" + "=" * 80)
    print("COLLECTION COMPLETE")
    print("=" * 80)
    print(f"Duration: {duration:.1f}s")
    print(f"Players: {collector.stats['players_collected']} ✅  {collector.stats['players_failed']} ❌")
    print(f"Rivals: {collector.stats['rivals_collected']} ✅  {collector.stats['rivals_failed']} ❌")
    print(f"League: {'✅' if collector.stats['league_collected'] else '❌'}")

    if collector.stats['errors']:
        print(f"\n⚠️  Errors: {len(collector.stats['errors'])}")
        if args.verbose:
            for error in collector.stats['errors'][:10]:  # Show first 10
                print(f"   - {error}")

    logger.info(f"PostGWCollection: Complete - Duration: {duration:.1f}s")

    return 0 if collector.stats['players_collected'] > 0 else 1


if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nCollection cancelled.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"PostGWCollection: Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
