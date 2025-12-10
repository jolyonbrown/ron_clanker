#!/usr/bin/env python3
"""
Chip Strategy Analyzer

Helps Ron maximize chip value by:
- Tracking rival chip usage
- Identifying optimal chip timing windows
- Comparing Ron's chip arsenal vs rivals
- Recommending chip usage based on fixtures and competition

Uses ChipAvailabilityService for API-driven chip definitions that adapt
to any season's chip configuration automatically.
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime

from services.chip_availability import ChipAvailabilityService

logger = logging.getLogger('ron_clanker.chip_strategy')


class ChipStrategyAnalyzer:
    """
    Analyzes chip strategy for competitive advantage.

    Chip configuration is read from the FPL API via ChipAvailabilityService,
    so this adapts automatically to any season's chip rules (e.g., split
    windows, different chip types, etc.)
    """

    def __init__(self, database, league_intel_service, team_id: Optional[int] = None):
        """Initialize with database and league intelligence."""
        self.db = database
        self.league_intel = league_intel_service
        self.chip_service = ChipAvailabilityService()
        self._team_id = team_id
        logger.info("ChipStrategyAnalyzer: Initialized with API-driven chip tracking")

    def get_ron_chip_status(self, team_id: int, current_gw: Optional[int] = None) -> Dict:
        """
        Get Ron's chip status directly from FPL API.

        This is the authoritative source for Ron's chip availability,
        using the ChipAvailabilityService which reads from the API.
        """
        summary = self.chip_service.get_chip_summary(team_id, current_gw)
        return summary

    def get_chip_usage_timeline(self, league_id: int) -> List[Dict]:
        """Get timeline of chip usage across the league."""

        chip_events = self.db.execute_query("""
            SELECT
                rcu.gameweek,
                rcu.chip_name,
                rcu.chip_number,
                lr.player_name,
                lr.entry_id,
                rcu.detected_at
            FROM rival_chip_usage rcu
            JOIN league_rivals lr ON rcu.entry_id = lr.entry_id
            WHERE lr.league_id = ?
            ORDER BY rcu.gameweek, rcu.detected_at
        """, (league_id,))

        logger.info(f"ChipStrategy: Found {len(chip_events)} chip events for league {league_id}")
        return chip_events or []

    def analyze_chip_trends(self, league_id: int, current_gw: int) -> Dict:
        """Analyze chip usage trends in the league."""

        timeline = self.get_chip_usage_timeline(league_id)

        analysis = {
            'total_chips_used': len(timeline),
            'by_chip_type': {},
            'by_gameweek': {},
            'early_wildcards': [],
            'bench_boost_timing': [],
            'triple_captain_timing': [],
            'free_hit_timing': []
        }

        # Count by chip type
        for event in timeline:
            chip_type = event['chip_name']
            analysis['by_chip_type'][chip_type] = analysis['by_chip_type'].get(chip_type, 0) + 1

            # Count by gameweek
            gw = event['gameweek']
            if gw not in analysis['by_gameweek']:
                analysis['by_gameweek'][gw] = []
            analysis['by_gameweek'][gw].append(event)

            # Categorize timing
            if chip_type == 'wildcard':
                if gw < 10:
                    analysis['early_wildcards'].append(event)
            elif chip_type == 'bboost':
                analysis['bench_boost_timing'].append(event)
            elif chip_type == '3xc':
                analysis['triple_captain_timing'].append(event)
            elif chip_type == 'freehit':
                analysis['free_hit_timing'].append(event)

        logger.info(f"ChipStrategy: Analyzed trends - {analysis['total_chips_used']} chips used")
        return analysis

    def get_ron_chip_advantage(self, ron_entry_id: int, league_id: int, current_gw: Optional[int] = None) -> Dict:
        """Calculate Ron's chip advantage vs league.

        Uses the ChipAvailabilityService for Ron's actual chip status from API.
        """

        # Get Ron's chips from API (authoritative source)
        try:
            ron_status = self.chip_service.get_chip_summary(ron_entry_id, current_gw)
            ron_remaining = len(ron_status['available'])
            total_chips = ron_status['total_chips']
        except Exception as e:
            logger.warning(f"ChipStrategy: Could not fetch Ron's chips from API: {e}")
            # Fall back to database
            ron_chips = self.db.execute_query("""
                SELECT * FROM rival_chip_status
                WHERE entry_id = ?
            """, (ron_entry_id,))

            if not ron_chips:
                ron_remaining = 8
                total_chips = 8
                logger.warning(f"ChipStrategy: Ron's chip status not found, assuming all chips available")
            else:
                ron_data = ron_chips[0]
                ron_remaining = (
                    ron_data['wildcards_remaining'] +
                    ron_data['bench_boosts_remaining'] +
                    ron_data['triple_captains_remaining'] +
                    ron_data['free_hits_remaining']
                )
                total_chips = 8

        # Get league average from tracked rivals
        all_chips = self.db.execute_query("""
            SELECT * FROM rival_chip_status
        """)

        if all_chips:
            avg_remaining = sum(
                c['wildcards_remaining'] +
                c['bench_boosts_remaining'] +
                c['triple_captains_remaining'] +
                c['free_hits_remaining']
                for c in all_chips
            ) / len(all_chips)
        else:
            avg_remaining = total_chips

        advantage = {
            'ron_chips_remaining': ron_remaining,
            'league_avg_remaining': round(avg_remaining, 1),
            'chip_advantage': ron_remaining - avg_remaining,
            'advantage_percentage': ((ron_remaining - avg_remaining) / total_chips) * 100 if avg_remaining < total_chips else 0
        }

        logger.info(f"ChipStrategy: Ron has {ron_remaining} chips, league avg: {avg_remaining:.1f}")
        return advantage

    def recommend_chip_usage(self, current_gw: int, ron_entry_id: int) -> Dict:
        """
        Get chip recommendations using API-driven chip definitions.

        This is the new generic method that adapts to any season's chip
        configuration automatically.
        """
        recommendations = {}

        # Get chip status from API
        all_chips = self.chip_service.get_available_chips(ron_entry_id, current_gw)

        for chip in all_chips:
            chip_key = f"{chip.definition.name}_{chip.definition.number}"

            if chip.used:
                recommendations[chip_key] = {
                    'status': 'USED',
                    'display_name': chip.definition.display_name,
                    'used_gw': chip.used_in_gw,
                    'recommendation': 'N/A'
                }
            elif not chip.available_now:
                # Not in current window
                if current_gw < chip.definition.start_event:
                    recommendations[chip_key] = {
                        'status': 'LOCKED',
                        'display_name': chip.definition.display_name,
                        'available_from': f'GW{chip.definition.start_event}',
                        'window': f'GW{chip.definition.start_event}-{chip.definition.stop_event}',
                        'recommendation': 'WAIT',
                        'reason': f'Available from GW{chip.definition.start_event}'
                    }
                else:
                    recommendations[chip_key] = {
                        'status': 'EXPIRED',
                        'display_name': chip.definition.display_name,
                        'window': f'GW{chip.definition.start_event}-{chip.definition.stop_event}',
                        'recommendation': 'LOST',
                        'reason': f'Window closed at GW{chip.definition.stop_event}'
                    }
            else:
                # Available now - assess urgency
                if chip.expires_soon:
                    recommendations[chip_key] = {
                        'status': 'AVAILABLE',
                        'display_name': chip.definition.display_name,
                        'window': f'GW{chip.definition.start_event}-{chip.definition.stop_event}',
                        'gws_until_expiry': chip.gws_until_expiry,
                        'recommendation': 'URGENT',
                        'reason': f'Expires in {chip.gws_until_expiry} GWs! Use or lose it.',
                        'urgency': 'HIGH'
                    }
                elif chip.gws_until_expiry <= 6:
                    recommendations[chip_key] = {
                        'status': 'AVAILABLE',
                        'display_name': chip.definition.display_name,
                        'window': f'GW{chip.definition.start_event}-{chip.definition.stop_event}',
                        'gws_until_expiry': chip.gws_until_expiry,
                        'recommendation': 'CONSIDER',
                        'reason': f'{chip.gws_until_expiry} GWs remaining in window. Plan usage.',
                        'urgency': 'MEDIUM'
                    }
                else:
                    recommendations[chip_key] = {
                        'status': 'AVAILABLE',
                        'display_name': chip.definition.display_name,
                        'window': f'GW{chip.definition.start_event}-{chip.definition.stop_event}',
                        'gws_until_expiry': chip.gws_until_expiry,
                        'recommendation': 'HOLD',
                        'reason': f'Plenty of time ({chip.gws_until_expiry} GWs). Wait for optimal moment.',
                        'urgency': 'LOW'
                    }

        return recommendations

    def recommend_wildcard_timing(self, current_gw: int, ron_entry_id: int) -> Dict:
        """Recommend optimal wildcard timing.

        Now uses API-driven chip definitions via recommend_chip_usage().
        Kept for backwards compatibility.
        """
        all_recs = self.recommend_chip_usage(current_gw, ron_entry_id)

        recommendations = {
            'wildcard_1': all_recs.get('wildcard_1', {'status': 'NOT_FOUND'}),
            'wildcard_2': all_recs.get('wildcard_2', {'status': 'NOT_FOUND'})
        }

        return recommendations

    def recommend_bench_boost(self, current_gw: int, ron_entry_id: int) -> Dict:
        """Recommend bench boost timing.

        Now uses API-driven chip definitions via recommend_chip_usage().
        Kept for backwards compatibility.
        """
        all_recs = self.recommend_chip_usage(current_gw, ron_entry_id)

        recommendations = {
            'bench_boost_1': all_recs.get('bboost_1', {'status': 'NOT_FOUND'}),
            'bench_boost_2': all_recs.get('bboost_2', {'status': 'NOT_FOUND'})
        }

        # Add strategic context for bench boost
        for key in recommendations:
            if recommendations[key].get('status') == 'AVAILABLE':
                recommendations[key]['optimal_use'] = 'Double Gameweek with strong bench'

        return recommendations

    def recommend_triple_captain(self, current_gw: int, ron_entry_id: int) -> Dict:
        """Recommend triple captain timing.

        Now uses API-driven chip definitions via recommend_chip_usage().
        Kept for backwards compatibility.
        """
        all_recs = self.recommend_chip_usage(current_gw, ron_entry_id)

        recommendations = {
            'triple_captain_1': all_recs.get('3xc_1', {'status': 'NOT_FOUND'}),
            'triple_captain_2': all_recs.get('3xc_2', {'status': 'NOT_FOUND'})
        }

        # Add strategic context for triple captain
        for key in recommendations:
            if recommendations[key].get('status') == 'AVAILABLE':
                recommendations[key]['optimal_use'] = 'Premium player in Double Gameweek'
                recommendations[key]['high_value_targets'] = ['Haaland (MCI)', 'Salah (LIV)', 'Palmer (CHE)']

        return recommendations

    def recommend_free_hit(self, current_gw: int, ron_entry_id: int) -> Dict:
        """Recommend free hit timing.

        Uses API-driven chip definitions via recommend_chip_usage().
        """
        all_recs = self.recommend_chip_usage(current_gw, ron_entry_id)

        recommendations = {
            'free_hit_1': all_recs.get('freehit_1', {'status': 'NOT_FOUND'}),
            'free_hit_2': all_recs.get('freehit_2', {'status': 'NOT_FOUND'})
        }

        # Add strategic context for free hit
        for key in recommendations:
            if recommendations[key].get('status') == 'AVAILABLE':
                recommendations[key]['optimal_use'] = 'Blank Gameweek or fixture swing'

        return recommendations

    def generate_chip_report(self, ron_entry_id: int, league_id: int, current_gw: int) -> str:
        """Generate comprehensive chip strategy report.

        Uses API-driven chip definitions so adapts to any season's configuration.
        """

        logger.info(f"ChipStrategy: Generating report for entry {ron_entry_id}, GW{current_gw}")

        report = []
        report.append("\n" + "=" * 80)
        report.append("CHIP STRATEGY REPORT")
        report.append("=" * 80)
        report.append(f"Gameweek: {current_gw}")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Chip status from API (authoritative)
        try:
            ron_status = self.chip_service.get_chip_summary(ron_entry_id, current_gw)
            report.append(f"\n📦 CHIP STATUS (from API):")
            report.append(f"   Total chips this season: {ron_status['total_chips']}")
            report.append(f"   Available: {len(ron_status['available'])}")
            report.append(f"   Used: {len(ron_status['used'])}")

            if ron_status['expiring_soon']:
                report.append(f"\n   ⚠️  EXPIRING SOON:")
                for chip in ron_status['expiring_soon']:
                    report.append(f"      - {chip['display_name']}: {chip['gws_until_expiry']} GWs left!")
        except Exception as e:
            logger.warning(f"ChipStrategy: Could not fetch chip status from API: {e}")
            report.append(f"\n⚠️  Could not fetch chip status from API")

        # Chip advantage
        advantage = self.get_ron_chip_advantage(ron_entry_id, league_id, current_gw)
        report.append(f"\n🎯 RON'S CHIP ADVANTAGE:")
        report.append(f"   Ron has {advantage['ron_chips_remaining']} chips remaining")
        report.append(f"   League average: {advantage['league_avg_remaining']} chips")
        report.append(f"   Advantage: +{advantage['chip_advantage']:.1f} chips ({advantage['advantage_percentage']:.0f}%)")

        # League trends
        trends = self.analyze_chip_trends(league_id, current_gw)
        report.append(f"\n📊 LEAGUE CHIP TRENDS:")
        report.append(f"   Total chips used: {trends['total_chips_used']}")
        for chip_type, count in trends['by_chip_type'].items():
            report.append(f"   {chip_type}: {count} used")

        # All chip recommendations using generic method
        all_recs = self.recommend_chip_usage(current_gw, ron_entry_id)

        # Group by chip type for display
        chip_groups = {
            'wildcard': ('🃏', 'WILDCARD'),
            'bboost': ('💪', 'BENCH BOOST'),
            '3xc': ('⭐', 'TRIPLE CAPTAIN'),
            'freehit': ('🔄', 'FREE HIT')
        }

        for chip_name, (emoji, display) in chip_groups.items():
            report.append(f"\n{emoji} {display} STRATEGY:")

            matching = {k: v for k, v in all_recs.items() if k.startswith(chip_name)}
            if not matching:
                report.append(f"   No {display.lower()} chips defined this season")
                continue

            for key, rec in sorted(matching.items()):
                report.append(f"\n   {rec.get('display_name', key.upper())}:")
                report.append(f"      Status: {rec['status']}")
                if rec.get('window'):
                    report.append(f"      Window: {rec['window']}")
                if rec.get('recommendation'):
                    report.append(f"      Recommendation: {rec['recommendation']}")
                if rec.get('reason'):
                    report.append(f"      Reason: {rec['reason']}")
                if rec.get('gws_until_expiry'):
                    report.append(f"      GWs until expiry: {rec['gws_until_expiry']}")
                if rec.get('used_gw'):
                    report.append(f"      Used in: GW{rec['used_gw']}")
                if rec.get('optimal_use'):
                    report.append(f"      Best use: {rec['optimal_use']}")
                if rec.get('high_value_targets'):
                    report.append(f"      Target players: {', '.join(rec['high_value_targets'])}")

        return "\n".join(report)
