#!/usr/bin/env python3
"""
Fixture-Based Chip Optimizer

Analyzes fixtures to recommend optimal chip timing:
- Double gameweeks (best for Bench Boost, Triple Captain)
- Blank gameweeks (best for Free Hit)
- Fixture swings (best for Wildcard)
- Easy opponent runs (best for Triple Captain on form players)
"""

import logging
from typing import Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger('ron_clanker.fixture_optimizer')


class FixtureOptimizer:
    """
    Analyzes fixture schedules to optimize chip timing.
    """

    def __init__(self, database):
        """Initialize with database connection."""
        self.db = database
        logger.info("FixtureOptimizer: Initialized")

    def identify_double_gameweeks(self) -> List[Dict]:
        """
        Identify gameweeks where teams play twice.

        Double gameweeks are gold for:
        - Bench Boost (all 15 players get 2x games)
        - Triple Captain (captain gets 6x points instead of 3x)
        """

        # Count fixtures per team per gameweek
        fixtures_per_gw = self.db.execute_query("""
            SELECT
                event as gameweek,
                team_h as team_id,
                COUNT(*) as fixture_count
            FROM fixtures
            WHERE event IS NOT NULL
            GROUP BY event, team_h
            HAVING COUNT(*) > 1

            UNION ALL

            SELECT
                event as gameweek,
                team_a as team_id,
                COUNT(*) as fixture_count
            FROM fixtures
            WHERE event IS NOT NULL
            GROUP BY event, team_a
            HAVING COUNT(*) > 1

            ORDER BY gameweek, team_id
        """)

        if not fixtures_per_gw:
            logger.info("FixtureOptimizer: No double gameweeks found in fixture data")
            return []

        # Group by gameweek
        dgws = defaultdict(list)
        for row in fixtures_per_gw:
            dgws[row['gameweek']].append({
                'team_id': row['team_id'],
                'fixture_count': row['fixture_count']
            })

        double_gameweeks = [
            {
                'gameweek': gw,
                'teams_with_doubles': len(teams),
                'teams': teams
            }
            for gw, teams in sorted(dgws.items())
        ]

        logger.info(f"FixtureOptimizer: Found {len(double_gameweeks)} double gameweeks")
        return double_gameweeks

    def identify_blank_gameweeks(self) -> List[int]:
        """
        Identify gameweeks where many teams don't play.

        Blank gameweeks are best for Free Hit.
        """

        # Get all gameweeks
        all_gws = self.db.execute_query("""
            SELECT DISTINCT event FROM fixtures
            WHERE event IS NOT NULL
            ORDER BY event
        """)

        if not all_gws:
            return []

        blank_gws = []

        for gw_row in all_gws:
            gw = gw_row['event']

            # Count how many teams play this gameweek
            teams_playing = self.db.execute_query("""
                SELECT COUNT(DISTINCT team_h) + COUNT(DISTINCT team_a) as teams
                FROM fixtures
                WHERE event = ?
            """, (gw,))

            teams_count = teams_playing[0]['teams'] if teams_playing else 0

            # If fewer than 30 teams playing (out of 20 teams = 40 team-slots), it's a blank
            if teams_count < 30:
                blank_gws.append({
                    'gameweek': gw,
                    'teams_playing': teams_count,
                    'severity': 'SEVERE' if teams_count < 20 else 'MODERATE'
                })

        logger.info(f"FixtureOptimizer: Found {len(blank_gws)} blank gameweeks")
        return blank_gws

    def analyze_fixture_difficulty(self, team_id: int, gameweeks: int = 6) -> Dict:
        """
        Analyze upcoming fixture difficulty for a team.

        Returns difficulty rating for next N gameweeks.
        Lower = easier fixtures = better for assets.
        """

        fixtures = self.db.execute_query("""
            SELECT
                f.event as gameweek,
                f.team_h,
                f.team_a,
                f.team_h_difficulty,
                f.team_a_difficulty,
                t_opp.name as opponent
            FROM fixtures f
            LEFT JOIN teams t_opp ON (
                CASE
                    WHEN f.team_h = ? THEN f.team_a
                    ELSE f.team_h
                END
            ) = t_opp.id
            WHERE (f.team_h = ? OR f.team_a = ?)
            AND f.event IS NOT NULL
            AND f.finished = 0
            ORDER BY f.event
            LIMIT ?
        """, (team_id, team_id, team_id, gameweeks))

        if not fixtures:
            return {'team_id': team_id, 'fixtures': [], 'avg_difficulty': 0}

        total_difficulty = 0
        fixture_list = []

        for fix in fixtures:
            # Get difficulty based on whether home or away
            if fix['team_h'] == team_id:
                difficulty = fix['team_h_difficulty'] or 3
                venue = 'H'
            else:
                difficulty = fix['team_a_difficulty'] or 3
                venue = 'A'

            total_difficulty += difficulty
            fixture_list.append({
                'gameweek': fix['gameweek'],
                'opponent': fix['opponent'],
                'venue': venue,
                'difficulty': difficulty
            })

        avg_difficulty = total_difficulty / len(fixtures) if fixtures else 0

        return {
            'team_id': team_id,
            'fixtures': fixture_list,
            'avg_difficulty': round(avg_difficulty, 2),
            'total_difficulty': total_difficulty
        }

    def find_fixture_swings(self, min_swing: float = 1.5) -> List[Dict]:
        """
        Find teams with major fixture swings (hard run → easy run).

        Perfect timing for wildcards to bring in players.
        """

        # Get all teams
        teams = self.db.execute_query("SELECT id, name, short_name FROM teams")

        if not teams:
            return []

        swings = []

        for team in teams:
            team_id = team['id']

            # Compare current 3 GWs vs next 3 GWs
            current_run = self.analyze_fixture_difficulty(team_id, gameweeks=3)
            next_run = self.db.execute_query("""
                SELECT
                    f.event as gameweek,
                    CASE
                        WHEN f.team_h = ? THEN f.team_h_difficulty
                        ELSE f.team_a_difficulty
                    END as difficulty
                FROM fixtures f
                WHERE (f.team_h = ? OR f.team_a = ?)
                AND f.event IS NOT NULL
                AND f.finished = 0
                ORDER BY f.event
                LIMIT 3 OFFSET 3
            """, (team_id, team_id, team_id))

            if not next_run or not current_run['fixtures']:
                continue

            next_avg = sum(f['difficulty'] or 3 for f in next_run) / len(next_run) if next_run else 3

            swing = current_run['avg_difficulty'] - next_avg

            if abs(swing) >= min_swing:
                swings.append({
                    'team_name': team['short_name'],
                    'team_id': team_id,
                    'current_difficulty': current_run['avg_difficulty'],
                    'next_difficulty': round(next_avg, 2),
                    'swing': round(swing, 2),
                    'direction': 'EASIER' if swing > 0 else 'HARDER',
                    'current_fixtures': [f['opponent'] for f in current_run['fixtures']],
                    'next_fixtures': [f.get('opponent', 'TBD') for f in next_run]
                })

        # Sort by swing magnitude
        swings.sort(key=lambda x: abs(x['swing']), reverse=True)

        logger.info(f"FixtureOptimizer: Found {len(swings)} significant fixture swings")
        return swings

    def recommend_wildcard_window(self, current_gw: int, wc_number: int = 1) -> Dict:
        """
        Recommend optimal wildcard timing based on fixtures.

        WC1: Before GW20
        WC2: After GW20
        """

        if wc_number == 1 and current_gw >= 19:
            return {
                'recommendation': 'URGENT',
                'reason': 'WC1 expires after GW19!',
                'suggested_gw': current_gw + 1
            }

        if wc_number == 2 and current_gw < 20:
            return {
                'recommendation': 'WAIT',
                'reason': 'WC2 not available until GW20',
                'suggested_gw': 25  # Typical good WC2 timing
            }

        # Find fixture swings
        swings = self.find_fixture_swings()

        # Look for teams turning easier
        easy_swings = [s for s in swings if s['direction'] == 'EASIER']

        if easy_swings:
            best_swing = easy_swings[0]
            suggested_gw = current_gw + 3  # Use wildcard before easy run

            return {
                'recommendation': 'CONSIDER',
                'reason': f"{best_swing['team_name']} fixtures turn easier (difficulty {best_swing['current_difficulty']} → {best_swing['next_difficulty']})",
                'suggested_gw': suggested_gw,
                'target_teams': [s['team_name'] for s in easy_swings[:5]],
                'swing_magnitude': best_swing['swing']
            }

        return {
            'recommendation': 'HOLD',
            'reason': 'No significant fixture swings detected',
            'suggested_gw': None
        }

    def recommend_bench_boost_window(self, current_gw: int) -> Dict:
        """
        Recommend bench boost timing.

        Best used in double gameweeks with strong bench.
        """

        dgws = self.identify_double_gameweeks()

        # Filter for future DGWs
        future_dgws = [d for d in dgws if d['gameweek'] > current_gw]

        if not future_dgws:
            return {
                'recommendation': 'NO DGW FOUND',
                'reason': 'No upcoming double gameweeks detected in fixture data',
                'suggested_gw': None
            }

        # Find DGW with most teams doubling
        best_dgw = max(future_dgws, key=lambda d: d['teams_with_doubles'])

        return {
            'recommendation': 'WAIT FOR DGW',
            'reason': f"GW{best_dgw['gameweek']} has {best_dgw['teams_with_doubles']} teams with double fixtures",
            'suggested_gw': best_dgw['gameweek'],
            'teams_doubling': best_dgw['teams_with_doubles']
        }

    def recommend_triple_captain_window(self, current_gw: int) -> Dict:
        """
        Recommend triple captain timing.

        Best for premium captain in double gameweek.
        """

        dgws = self.identify_double_gameweeks()
        future_dgws = [d for d in dgws if d['gameweek'] > current_gw]

        if not future_dgws:
            # No DGW - look for easy fixtures for premiums
            # TODO: Check which premium players have easiest upcoming fixtures
            return {
                'recommendation': 'WAIT FOR DGW',
                'reason': 'Best value in double gameweeks',
                'suggested_gw': None,
                'alternative': 'Or use on Haaland vs weak opponent at home'
            }

        best_dgw = max(future_dgws, key=lambda d: d['teams_with_doubles'])

        return {
            'recommendation': 'SAVE FOR DGW',
            'reason': f"GW{best_dgw['gameweek']} double gameweek - captain gets 6x points",
            'suggested_gw': best_dgw['gameweek'],
            'best_targets': ['Haaland (if MCI doubles)', 'Salah (if LIV doubles)', 'Palmer (if CHE doubles)']
        }

    def recommend_free_hit_window(self, current_gw: int) -> Dict:
        """
        Recommend free hit timing.

        Best for blank gameweeks.
        """

        blank_gws = self.identify_blank_gameweeks()
        future_blanks = [b for b in blank_gws if b['gameweek'] > current_gw]

        if not future_blanks:
            return {
                'recommendation': 'NO BLANKS DETECTED',
                'reason': 'No blank gameweeks found in schedule',
                'suggested_gw': None,
                'alternative': 'Can use in DGW to field 15 DGW players'
            }

        # Get most severe blank
        worst_blank = min(future_blanks, key=lambda b: b['teams_playing'])

        return {
            'recommendation': 'SAVE FOR BLANK',
            'reason': f"GW{worst_blank['gameweek']} is a {worst_blank['severity']} blank ({worst_blank['teams_playing']} teams playing)",
            'suggested_gw': worst_blank['gameweek'],
            'severity': worst_blank['severity']
        }

    def generate_optimization_report(self, current_gw: int) -> str:
        """Generate comprehensive fixture-based chip optimization report."""

        logger.info(f"FixtureOptimizer: Generating report for GW{current_gw}")

        report = []
        report.append("\n" + "=" * 80)
        report.append("FIXTURE-BASED CHIP OPTIMIZATION")
        report.append("=" * 80)

        # Double gameweeks
        dgws = self.identify_double_gameweeks()
        future_dgws = [d for d in dgws if d['gameweek'] > current_gw]

        if future_dgws:
            report.append(f"\n📅 UPCOMING DOUBLE GAMEWEEKS:")
            for dgw in future_dgws[:3]:  # Next 3 DGWs
                report.append(f"   GW{dgw['gameweek']}: {dgw['teams_with_doubles']} teams with double fixtures")
        else:
            report.append(f"\n📅 No double gameweeks detected in fixture data")

        # Blank gameweeks
        blank_gws = self.identify_blank_gameweeks()
        future_blanks = [b for b in blank_gws if b['gameweek'] > current_gw]

        if future_blanks:
            report.append(f"\n🚫 UPCOMING BLANK GAMEWEEKS:")
            for blank in future_blanks[:3]:
                report.append(f"   GW{blank['gameweek']}: {blank['severity']} blank ({blank['teams_playing']} teams playing)")

        # Fixture swings
        swings = self.find_fixture_swings(min_swing=1.0)

        if swings:
            report.append(f"\n📊 FIXTURE SWINGS (Top 5):")
            for swing in swings[:5]:
                arrow = "🟢" if swing['direction'] == 'EASIER' else "🔴"
                report.append(f"   {arrow} {swing['team_name']}: {swing['current_difficulty']} → {swing['next_difficulty']} ({swing['swing']:+.1f})")

        # Recommendations
        report.append(f"\n💡 FIXTURE-BASED RECOMMENDATIONS:")

        wc1_rec = self.recommend_wildcard_window(current_gw, 1)
        report.append(f"\n   Wildcard 1: {wc1_rec['recommendation']}")
        report.append(f"      {wc1_rec['reason']}")

        bb_rec = self.recommend_bench_boost_window(current_gw)
        report.append(f"\n   Bench Boost: {bb_rec['recommendation']}")
        report.append(f"      {bb_rec['reason']}")

        tc_rec = self.recommend_triple_captain_window(current_gw)
        report.append(f"\n   Triple Captain: {tc_rec['recommendation']}")
        report.append(f"      {tc_rec['reason']}")

        fh_rec = self.recommend_free_hit_window(current_gw)
        report.append(f"\n   Free Hit: {fh_rec['recommendation']}")
        report.append(f"      {fh_rec['reason']}")

        return "\n".join(report)
