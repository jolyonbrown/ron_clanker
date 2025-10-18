#!/usr/bin/env python3
"""
League Intelligence Service

Fetches and stores mini-league data for competitive analysis.
Tracks rivals' teams, chip usage, transfers, and differentials.
"""

import requests
import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger('ron_clanker.league_intel')

FPL_BASE_URL = "https://fantasy.premierleague.com/api"


class LeagueIntelligenceService:
    """
    Tracks mini-league rivals for competitive intelligence.

    Monitors:
    - League standings and point gaps
    - Rival chip usage
    - Rival team picks and captain choices
    - Rival transfers and hits taken
    - Differential opportunities
    """

    def __init__(self, database):
        """Initialize with database connection."""
        self.db = database
        logger.info("LeagueIntelligenceService: Initialized")

    def fetch_league_standings(self, league_id: int, page: int = 1) -> Dict:
        """Fetch mini-league standings from FPL API."""
        try:
            url = f"{FPL_BASE_URL}/leagues-classic/{league_id}/standings/?page_standings={page}"
            logger.info(f"LeagueIntel: Fetching league {league_id} page {page}")

            response = requests.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()
            logger.info(f"LeagueIntel: Fetched {len(data['standings']['results'])} teams from league {league_id}")

            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"LeagueIntel: Failed to fetch league {league_id}: {e}")
            raise

    def fetch_team_entry(self, entry_id: int) -> Dict:
        """Fetch team entry data from FPL API."""
        try:
            url = f"{FPL_BASE_URL}/entry/{entry_id}/"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"LeagueIntel: Failed to fetch entry {entry_id}: {e}")
            raise

    def fetch_team_transfers(self, entry_id: int) -> List[Dict]:
        """Fetch team transfer history from FPL API."""
        try:
            url = f"{FPL_BASE_URL}/entry/{entry_id}/transfers/"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.warning(f"LeagueIntel: Could not fetch transfers for {entry_id}: {e}")
            return []

    def fetch_team_picks(self, entry_id: int, gameweek: int) -> Optional[Dict]:
        """Fetch team picks for a specific gameweek."""
        try:
            url = f"{FPL_BASE_URL}/entry/{entry_id}/event/{gameweek}/picks/"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.warning(f"LeagueIntel: Could not fetch picks for entry {entry_id} GW{gameweek}: {e}")
            return None

    def fetch_team_history(self, entry_id: int) -> Dict:
        """Fetch team history including chip usage."""
        try:
            url = f"{FPL_BASE_URL}/entry/{entry_id}/history/"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"LeagueIntel: Failed to fetch history for entry {entry_id}: {e}")
            raise

    def store_rival(self, entry_id: int, player_name: str, team_name: str, league_id: int, gameweek: int):
        """Store or update a rival team in the database."""
        try:
            self.db.execute_update("""
                INSERT INTO league_rivals (entry_id, player_name, team_name, league_id, first_seen_gw, last_updated)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(entry_id, league_id) DO UPDATE SET
                    player_name = excluded.player_name,
                    team_name = excluded.team_name,
                    last_updated = CURRENT_TIMESTAMP
            """, (entry_id, player_name, team_name, league_id, gameweek))

            logger.debug(f"LeagueIntel: Stored rival {player_name} ({entry_id})")

        except Exception as e:
            logger.error(f"LeagueIntel: Failed to store rival {entry_id}: {e}")
            raise

    def store_standings(self, league_id: int, standings: List[Dict], gameweek: int):
        """Store league standings snapshot with bank and value data."""
        stored_count = 0

        for team in standings:
            try:
                entry_id = team['entry']
                player_name = team['player_name']
                team_name = team['entry_name']

                # First, ensure rival exists
                self.store_rival(entry_id, player_name, team_name, league_id, gameweek)

                # Fetch entry details to get bank and value
                try:
                    entry_data = self.fetch_team_entry(entry_id)
                    bank = entry_data.get('last_deadline_bank', 0)
                    value = entry_data.get('last_deadline_value', 0)
                except Exception:
                    bank = None
                    value = None

                # Store standings data with bank/value
                self.db.execute_update("""
                    INSERT INTO league_standings_history
                    (league_id, entry_id, gameweek, rank, last_rank, total_points, event_points,
                     bank_value, value, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(league_id, entry_id, gameweek) DO UPDATE SET
                        rank = excluded.rank,
                        last_rank = excluded.last_rank,
                        total_points = excluded.total_points,
                        event_points = excluded.event_points,
                        bank_value = excluded.bank_value,
                        value = excluded.value,
                        recorded_at = CURRENT_TIMESTAMP
                """, (
                    league_id,
                    entry_id,
                    gameweek,
                    team['rank'],
                    team.get('last_rank'),
                    team['total'],
                    team.get('event_total'),
                    bank,
                    value
                ))

                stored_count += 1

            except Exception as e:
                logger.error(f"LeagueIntel: Failed to store standings for {entry_id}: {e}")
                continue

        logger.info(f"LeagueIntel: Stored {stored_count} standings for league {league_id} GW{gameweek}")
        return stored_count

    def store_chip_usage(self, entry_id: int, chips: List[Dict]):
        """Store rival chip usage."""
        stored_count = 0

        for chip in chips:
            try:
                gameweek = chip['event']
                chip_name = chip['name']

                # Determine chip number (1st or 2nd half)
                chip_number = 1 if gameweek < 20 else 2

                self.db.execute_update("""
                    INSERT OR IGNORE INTO rival_chip_usage
                    (entry_id, gameweek, chip_name, chip_number, detected_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (entry_id, gameweek, chip_name, chip_number))

                stored_count += 1
                logger.debug(f"LeagueIntel: Stored chip {chip_name} for entry {entry_id} GW{gameweek}")

            except Exception as e:
                logger.error(f"LeagueIntel: Failed to store chip for {entry_id}: {e}")
                continue

        return stored_count

    def store_team_picks(self, entry_id: int, gameweek: int, picks: List[Dict]):
        """Store rival team picks for a gameweek."""
        stored_count = 0

        for pick in picks:
            try:
                self.db.execute_update("""
                    INSERT INTO rival_team_picks
                    (entry_id, gameweek, player_id, position, is_captain, is_vice_captain, multiplier, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(entry_id, gameweek, player_id) DO UPDATE SET
                        position = excluded.position,
                        is_captain = excluded.is_captain,
                        is_vice_captain = excluded.is_vice_captain,
                        multiplier = excluded.multiplier,
                        recorded_at = CURRENT_TIMESTAMP
                """, (
                    entry_id,
                    gameweek,
                    pick['element'],
                    pick['position'],
                    pick['is_captain'],
                    pick['is_vice_captain'],
                    pick['multiplier']
                ))

                stored_count += 1

            except Exception as e:
                logger.error(f"LeagueIntel: Failed to store pick for {entry_id}: {e}")
                continue

        logger.debug(f"LeagueIntel: Stored {stored_count} picks for entry {entry_id} GW{gameweek}")
        return stored_count

    def store_transfers(self, entry_id: int, gameweek: int) -> int:
        """Store rival transfers for a gameweek."""
        try:
            all_transfers = self.fetch_team_transfers(entry_id)

            # Filter for this gameweek
            gw_transfers = [t for t in all_transfers if t.get('event') == gameweek]

            stored = 0
            for transfer in gw_transfers:
                try:
                    self.db.execute_update("""
                        INSERT OR IGNORE INTO rival_transfers
                        (entry_id, gameweek, player_in, player_out, transfer_cost, recorded_at)
                        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (
                        entry_id,
                        gameweek,
                        transfer['element_in'],
                        transfer['element_out'],
                        transfer['element_in_cost'] - transfer['element_out_cost']
                    ))
                    stored += 1
                except Exception as e:
                    logger.warning(f"LeagueIntel: Could not store transfer for {entry_id}: {e}")

            return stored

        except Exception as e:
            logger.warning(f"LeagueIntel: Could not fetch transfers for {entry_id}: {e}")
            return 0

    def track_league(self, league_id: int, gameweek: int, detailed: bool = True) -> Dict:
        """
        Track a mini-league comprehensively.

        Args:
            league_id: FPL league ID
            gameweek: Current gameweek
            detailed: If True, fetch team picks, chips, and transfers for all rivals

        Returns:
            Summary dictionary with tracking stats
        """
        logger.info(f"LeagueIntel: Starting tracking for league {league_id} GW{gameweek}")

        stats = {
            'league_id': league_id,
            'gameweek': gameweek,
            'rivals_tracked': 0,
            'standings_stored': 0,
            'chips_stored': 0,
            'picks_stored': 0,
            'transfers_stored': 0
        }

        try:
            # Fetch league standings
            league_data = self.fetch_league_standings(league_id)
            standings = league_data['standings']['results']

            # Store standings (includes bank and value now)
            stats['standings_stored'] = self.store_standings(league_id, standings, gameweek)
            stats['rivals_tracked'] = len(standings)

            # Detailed tracking (chips, picks, and transfers)
            if detailed:
                logger.info(f"LeagueIntel: Fetching detailed data for {len(standings)} rivals")

                for team in standings:
                    entry_id = team['entry']

                    try:
                        # Fetch and store chip usage
                        history = self.fetch_team_history(entry_id)
                        chips = history.get('chips', [])
                        stats['chips_stored'] += self.store_chip_usage(entry_id, chips)

                        # Fetch and store team picks
                        picks_data = self.fetch_team_picks(entry_id, gameweek)
                        if picks_data:
                            picks = picks_data.get('picks', [])
                            stats['picks_stored'] += self.store_team_picks(entry_id, gameweek, picks)

                        # Fetch and store transfers
                        stats['transfers_stored'] += self.store_transfers(entry_id, gameweek)

                    except Exception as e:
                        logger.warning(f"LeagueIntel: Could not fetch detailed data for {entry_id}: {e}")
                        continue

            logger.info(f"LeagueIntel: Tracking complete - {stats}")
            return stats

        except Exception as e:
            logger.error(f"LeagueIntel: Failed to track league {league_id}: {e}", exc_info=True)
            raise

    def get_current_standings(self, league_id: int) -> List[Dict]:
        """Get current league standings from database."""
        results = self.db.execute_query("""
            SELECT
                entry_id,
                player_name,
                team_name,
                rank,
                total_points,
                event_points,
                rank - last_rank as rank_change
            FROM current_league_standings
            WHERE league_id = ?
            ORDER BY rank
        """, (league_id,))

        return results or []

    def get_rival_chip_status(self, entry_id: Optional[int] = None) -> List[Dict]:
        """Get chip usage status for rivals."""
        if entry_id:
            query = "SELECT * FROM rival_chip_status WHERE entry_id = ?"
            params = (entry_id,)
        else:
            query = "SELECT * FROM rival_chip_status ORDER BY wildcards_remaining DESC, bench_boosts_remaining DESC"
            params = ()

        results = self.db.execute_query(query, params)
        return results or []

    def get_league_ownership(self, gameweek: int, min_ownership: float = 20.0) -> List[Dict]:
        """Get player ownership within the league."""
        results = self.db.execute_query("""
            SELECT
                player_id,
                web_name,
                rival_count,
                league_ownership_pct,
                captain_count
            FROM league_player_ownership
            WHERE gameweek = ?
            AND league_ownership_pct >= ?
            ORDER BY league_ownership_pct DESC
        """, (gameweek, min_ownership))

        return results or []

    def get_differentials(self, ron_entry_id: int, gameweek: int, rival_limit: int = 5) -> Dict:
        """
        Find differentials between Ron and top rivals.

        Returns dict with:
        - ron_exclusives: Players Ron has that rivals don't
        - template_missing: Popular players Ron doesn't have
        """
        # Get Ron's picks
        ron_picks = self.db.execute_query("""
            SELECT player_id FROM rival_team_picks
            WHERE entry_id = ? AND gameweek = ?
        """, (ron_entry_id, gameweek))

        if not ron_picks:
            logger.warning(f"LeagueIntel: No picks found for Ron's team ({ron_entry_id}) in GW{gameweek}")
            return {'ron_exclusives': [], 'template_missing': []}

        ron_player_ids = {row['player_id'] for row in ron_picks}

        # Find template players (owned by 3+ of top rivals) that Ron doesn't have
        template_missing = self.db.execute_query("""
            SELECT
                lpo.player_id,
                lpo.web_name,
                lpo.rival_count,
                lpo.league_ownership_pct,
                p.now_cost / 10.0 as price
            FROM league_player_ownership lpo
            JOIN players p ON lpo.player_id = p.id
            WHERE lpo.gameweek = ?
            AND lpo.rival_count >= 3
            AND lpo.player_id NOT IN ({})
            ORDER BY lpo.league_ownership_pct DESC
        """.format(','.join('?' * len(ron_player_ids))),
            (gameweek, *ron_player_ids))

        # Find Ron's exclusives (players he has that top rivals don't)
        ron_exclusives = self.db.execute_query("""
            SELECT
                rtp.player_id,
                p.web_name,
                p.now_cost / 10.0 as price,
                p.selected_by_percent as global_ownership,
                rtp.is_captain
            FROM rival_team_picks rtp
            JOIN players p ON rtp.player_id = p.id
            WHERE rtp.entry_id = ?
            AND rtp.gameweek = ?
            AND rtp.player_id NOT IN (
                SELECT DISTINCT player_id
                FROM rival_team_picks
                WHERE gameweek = ?
                AND entry_id != ?
                AND entry_id IN (
                    SELECT entry_id FROM league_standings_history
                    WHERE gameweek = ? AND rank <= ?
                )
            )
            ORDER BY p.now_cost DESC
        """, (ron_entry_id, gameweek, gameweek, ron_entry_id, gameweek, rival_limit))

        return {
            'ron_exclusives': ron_exclusives or [],
            'template_missing': template_missing or []
        }
