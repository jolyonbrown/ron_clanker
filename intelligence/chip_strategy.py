#!/usr/bin/env python3
"""
Chip Strategy Analyzer

Helps Ron maximize chip value by:
- Tracking rival chip usage
- Identifying optimal chip timing windows
- Comparing Ron's chip arsenal vs rivals
- Recommending chip usage based on fixtures and competition
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger('ron_clanker.chip_strategy')


class ChipStrategyAnalyzer:
    """
    Analyzes chip strategy for competitive advantage.

    Ron has 8 chips to use optimally:
    - 2 Wildcards (1 before GW20, 1 after GW20)
    - 2 Bench Boosts
    - 2 Triple Captains
    - 2 Free Hits
    """

    def __init__(self, database, league_intel_service):
        """Initialize with database and league intelligence."""
        self.db = database
        self.league_intel = league_intel_service
        logger.info("ChipStrategyAnalyzer: Initialized")

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

    def get_ron_chip_advantage(self, ron_entry_id: int, league_id: int) -> Dict:
        """Calculate Ron's chip advantage vs league."""

        # Get Ron's chips
        ron_chips = self.db.execute_query("""
            SELECT * FROM rival_chip_status
            WHERE entry_id = ?
        """, (ron_entry_id,))

        if not ron_chips:
            # Ron not tracked yet - assume all chips available
            ron_remaining = 8
            logger.warning(f"ChipStrategy: Ron's chip status not found, assuming all chips available")
        else:
            ron_data = ron_chips[0]
            ron_remaining = (
                ron_data['wildcards_remaining'] +
                ron_data['bench_boosts_remaining'] +
                ron_data['triple_captains_remaining'] +
                ron_data['free_hits_remaining']
            )

        # Get league average
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
            avg_remaining = 8

        advantage = {
            'ron_chips_remaining': ron_remaining,
            'league_avg_remaining': round(avg_remaining, 1),
            'chip_advantage': ron_remaining - avg_remaining,
            'advantage_percentage': ((ron_remaining - avg_remaining) / 8) * 100 if avg_remaining < 8 else 0
        }

        logger.info(f"ChipStrategy: Ron has {ron_remaining} chips, league avg: {avg_remaining:.1f}")
        return advantage

    def recommend_wildcard_timing(self, current_gw: int, ron_entry_id: int) -> Dict:
        """Recommend optimal wildcard timing."""

        recommendations = {
            'wildcard_1': {},
            'wildcard_2': {}
        }

        # Check if Ron has used WC1
        used_chips = self.db.execute_query("""
            SELECT chip_name, gameweek, chip_number
            FROM rival_chip_usage
            WHERE entry_id = ? AND chip_name = 'wildcard'
            ORDER BY gameweek
        """, (ron_entry_id,))

        wc1_used = any(c['chip_number'] == 1 for c in (used_chips or []))
        wc2_used = any(c['chip_number'] == 2 for c in (used_chips or []))

        # Wildcard 1 recommendations (must use before GW20)
        if not wc1_used:
            if current_gw < 10:
                recommendations['wildcard_1'] = {
                    'status': 'AVAILABLE',
                    'deadline': 'GW19',
                    'recommendation': 'HOLD',
                    'reason': 'Still early. Wait for fixture swings or injury crisis.',
                    'optimal_windows': ['GW12-14 (pre-Christmas fixtures)', 'GW16-18 (injury crisis period)']
                }
            elif current_gw < 15:
                recommendations['wildcard_1'] = {
                    'status': 'AVAILABLE',
                    'deadline': 'GW19',
                    'recommendation': 'CONSIDER',
                    'reason': 'Approaching Christmas fixture congestion. Good time for major overhaul.',
                    'optimal_windows': ['GW15-17 (fixture swing opportunities)']
                }
            elif current_gw < 19:
                recommendations['wildcard_1'] = {
                    'status': 'AVAILABLE',
                    'deadline': 'GW19',
                    'recommendation': 'URGENT',
                    'reason': 'Must use before GW20! Don\'t waste it.',
                    'optimal_windows': [f'GW{current_gw + 1} (IMMEDIATE)']
                }
            else:
                recommendations['wildcard_1'] = {
                    'status': 'EXPIRED',
                    'deadline': 'GW19',
                    'recommendation': 'LOST',
                    'reason': 'Wildcard 1 expired unused.'
                }
        else:
            wc1_gw = next(c['gameweek'] for c in used_chips if c['chip_number'] == 1)
            recommendations['wildcard_1'] = {
                'status': 'USED',
                'used_gw': wc1_gw,
                'recommendation': 'N/A'
            }

        # Wildcard 2 recommendations (must use after GW20)
        if not wc2_used:
            if current_gw <= 20:
                recommendations['wildcard_2'] = {
                    'status': 'LOCKED',
                    'available_from': 'GW20',
                    'recommendation': 'WAIT',
                    'reason': 'Not yet available. Can use from GW20 onwards.',
                    'optimal_windows': ['GW25-27 (fixture swings)', 'GW33-35 (final push)']
                }
            elif current_gw < 35:
                recommendations['wildcard_2'] = {
                    'status': 'AVAILABLE',
                    'recommendation': 'PLAN',
                    'reason': 'Available for second half. Use for final run-in fixtures.',
                    'optimal_windows': [f'GW{current_gw + 3}-{current_gw + 5} (fixture analysis needed)']
                }
            else:
                recommendations['wildcard_2'] = {
                    'status': 'AVAILABLE',
                    'recommendation': 'USE NOW',
                    'reason': 'Season ending! Use for final gameweeks.',
                    'optimal_windows': [f'GW{current_gw} (IMMEDIATE)']
                }
        else:
            wc2_gw = next(c['gameweek'] for c in used_chips if c['chip_number'] == 2)
            recommendations['wildcard_2'] = {
                'status': 'USED',
                'used_gw': wc2_gw,
                'recommendation': 'N/A'
            }

        return recommendations

    def recommend_bench_boost(self, current_gw: int, ron_entry_id: int) -> Dict:
        """Recommend bench boost timing."""

        # Check usage
        used = self.db.execute_query("""
            SELECT chip_number, gameweek
            FROM rival_chip_usage
            WHERE entry_id = ? AND chip_name = 'bboost'
        """, (ron_entry_id,))

        bb1_used = any(c['chip_number'] == 1 for c in (used or []))
        bb2_used = any(c['chip_number'] == 2 for c in (used or []))

        recommendations = {
            'bench_boost_1': {
                'status': 'USED' if bb1_used else 'AVAILABLE',
                'optimal_use': 'Double Gameweek with strong bench',
                'recommendation': 'Wait for DGW with 15 strong players' if not bb1_used else 'Used',
                'used_gw': next((c['gameweek'] for c in (used or []) if c['chip_number'] == 1), None)
            },
            'bench_boost_2': {
                'status': 'USED' if bb2_used else 'AVAILABLE',
                'optimal_use': 'Double Gameweek with strong bench',
                'recommendation': 'Wait for DGW with 15 strong players' if not bb2_used else 'Used',
                'used_gw': next((c['gameweek'] for c in (used or []) if c['chip_number'] == 2), None)
            }
        }

        return recommendations

    def recommend_triple_captain(self, current_gw: int, ron_entry_id: int) -> Dict:
        """Recommend triple captain timing."""

        # Check usage
        used = self.db.execute_query("""
            SELECT chip_number, gameweek
            FROM rival_chip_usage
            WHERE entry_id = ? AND chip_name = '3xc'
        """, (ron_entry_id,))

        tc1_used = any(c['chip_number'] == 1 for c in (used or []))
        tc2_used = any(c['chip_number'] == 2 for c in (used or []))

        recommendations = {
            'triple_captain_1': {
                'status': 'USED' if tc1_used else 'AVAILABLE',
                'optimal_use': 'Premium player in Double Gameweek',
                'recommendation': 'Save for Haaland/Salah DGW' if not tc1_used else 'Used',
                'used_gw': next((c['gameweek'] for c in (used or []) if c['chip_number'] == 1), None),
                'high_value_targets': ['Haaland (MCI)', 'Salah (LIV)', 'Palmer (CHE)']
            },
            'triple_captain_2': {
                'status': 'USED' if tc2_used else 'AVAILABLE',
                'optimal_use': 'Premium player in Double Gameweek',
                'recommendation': 'Save for Haaland/Salah DGW' if not tc2_used else 'Used',
                'used_gw': next((c['gameweek'] for c in (used or []) if c['chip_number'] == 2), None),
                'high_value_targets': ['Haaland (MCI)', 'Salah (LIV)', 'Palmer (CHE)']
            }
        }

        return recommendations

    def generate_chip_report(self, ron_entry_id: int, league_id: int, current_gw: int) -> str:
        """Generate comprehensive chip strategy report."""

        logger.info(f"ChipStrategy: Generating report for entry {ron_entry_id}, GW{current_gw}")

        report = []
        report.append("\n" + "=" * 80)
        report.append("CHIP STRATEGY REPORT")
        report.append("=" * 80)
        report.append(f"Gameweek: {current_gw}")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Chip advantage
        advantage = self.get_ron_chip_advantage(ron_entry_id, league_id)
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

        # Wildcard recommendations
        wc_recs = self.recommend_wildcard_timing(current_gw, ron_entry_id)
        report.append(f"\n🃏 WILDCARD STRATEGY:")

        for wc_name, rec in wc_recs.items():
            report.append(f"\n   {wc_name.upper().replace('_', ' ')}:")
            report.append(f"      Status: {rec['status']}")
            if rec.get('recommendation'):
                report.append(f"      Recommendation: {rec['recommendation']}")
            if rec.get('reason'):
                report.append(f"      Reason: {rec['reason']}")
            if rec.get('optimal_windows'):
                report.append(f"      Optimal windows: {', '.join(rec['optimal_windows'])}")

        # Bench Boost
        bb_recs = self.recommend_bench_boost(current_gw, ron_entry_id)
        report.append(f"\n💪 BENCH BOOST STRATEGY:")
        for bb_name, rec in bb_recs.items():
            report.append(f"\n   {bb_name.upper().replace('_', ' ')}:")
            report.append(f"      Status: {rec['status']}")
            report.append(f"      Recommendation: {rec['recommendation']}")

        # Triple Captain
        tc_recs = self.recommend_triple_captain(current_gw, ron_entry_id)
        report.append(f"\n⭐ TRIPLE CAPTAIN STRATEGY:")
        for tc_name, rec in tc_recs.items():
            report.append(f"\n   {tc_name.upper().replace('_', ' ')}:")
            report.append(f"      Status: {rec['status']}")
            report.append(f"      Recommendation: {rec['recommendation']}")
            if rec.get('high_value_targets'):
                report.append(f"      Best targets: {', '.join(rec['high_value_targets'])}")

        return "\n".join(report)
