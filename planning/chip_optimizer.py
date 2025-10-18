#!/usr/bin/env python3
"""
Chip Timing Optimization for Multi-Gameweek Planning

Optimizes when to use FPL chips:
- Wildcard (rebuild entire team) - 2 available: GW1-19, GW20-38
- Bench Boost (all 15 players score) - 2 available
- Triple Captain (3x points instead of 2x) - 2 available
- Free Hit (one-week team, reverts after) - 2 available

NEW 2025/26 Rules:
- TWO of each chip (first/second half)
- First half chips must be used by GW19 deadline
- Second half chips available from GW20 onwards
- Cannot carry chips over between halves
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger('ron_clanker.planning')


class ChipOptimizer:
    """
    Optimizes chip timing across the season.

    Identifies optimal windows for each chip type based on:
    - Fixture schedules (double/blank gameweeks)
    - Team performance trends
    - Fixture difficulty runs
    - Competitive position
    """

    def __init__(self, database):
        """Initialize with database connection."""
        self.db = database
        logger.info("ChipOptimizer: Initialized")

        # Chip availability rules (2025/26 season)
        self.chip_rules = {
            'wildcard': {
                'first_half': {'min_gw': 1, 'max_gw': 19},
                'second_half': {'min_gw': 20, 'max_gw': 38}
            },
            'bench_boost': {
                'first_half': {'min_gw': 1, 'max_gw': 19},
                'second_half': {'min_gw': 20, 'max_gw': 38}
            },
            'triple_captain': {
                'first_half': {'min_gw': 1, 'max_gw': 19},
                'second_half': {'min_gw': 20, 'max_gw': 38}
            },
            'free_hit': {
                'first_half': {'min_gw': 1, 'max_gw': 19},
                'second_half': {'min_gw': 20, 'max_gw': 38}
            }
        }

    def get_chips_used(self) -> Dict:
        """
        Check which chips have been used.

        Returns:
            Dict mapping chip_type -> list of gameweeks used
        """
        chips_used = self.db.execute_query("""
            SELECT chip_name as chip_type, gameweek
            FROM chips_used
            ORDER BY gameweek
        """)

        chip_history = {
            'wildcard': [],
            'bench_boost': [],
            'triple_captain': [],
            'free_hit': []
        }

        if chips_used:
            for chip in chips_used:
                chip_type = chip['chip_type']
                if chip_type in chip_history:
                    chip_history[chip_type].append(chip['gameweek'])

        return chip_history

    def get_available_chips(self, current_gw: int) -> Dict:
        """
        Determine which chips are still available.

        Args:
            current_gw: Current gameweek

        Returns:
            Dict with available chips and windows:
                - chip_type: {available: bool, window: 'first_half'/'second_half', deadline_gw: int}
        """
        chips_used = self.get_chips_used()

        available = {}

        for chip_type, rules in self.chip_rules.items():
            # Determine which half we're in
            if current_gw <= 19:
                half = 'first_half'
            else:
                half = 'second_half'

            window = rules[half]

            # Check if already used in this half
            used_in_half = [
                gw for gw in chips_used.get(chip_type, [])
                if window['min_gw'] <= gw <= window['max_gw']
            ]

            available[chip_type] = {
                'available': len(used_in_half) == 0,
                'window': half,
                'min_gw': window['min_gw'],
                'max_gw': window['max_gw'],
                'deadline_gw': window['max_gw'],
                'used_in_half': used_in_half
            }

        return available

    def identify_double_gameweeks(self, start_gw: int = 1, end_gw: int = 38) -> List[Dict]:
        """
        Identify double gameweeks where teams play twice.

        These are optimal for Bench Boost and Triple Captain.

        Args:
            start_gw: Start of search window
            end_gw: End of search window

        Returns:
            List of double gameweeks with team counts
        """
        # Count fixtures per team per gameweek
        fixture_counts = self.db.execute_query("""
            SELECT
                gameweek,
                team_id,
                COUNT(*) as fixture_count
            FROM (
                SELECT event as gameweek, team_h as team_id FROM fixtures WHERE event >= ? AND event <= ?
                UNION ALL
                SELECT event as gameweek, team_a as team_id FROM fixtures WHERE event >= ? AND event <= ?
            )
            GROUP BY gameweek, team_id
            HAVING fixture_count > 1
        """, (start_gw, end_gw, start_gw, end_gw))

        # Group by gameweek
        double_gws = {}
        for row in fixture_counts:
            gw = row['gameweek']
            if gw not in double_gws:
                double_gws[gw] = []
            double_gws[gw].append({
                'team_id': row['team_id'],
                'fixture_count': row['fixture_count']
            })

        # Convert to list
        result = []
        for gw, teams in double_gws.items():
            result.append({
                'gameweek': gw,
                'teams_with_dgw': len(teams),
                'teams': teams
            })

        result.sort(key=lambda x: x['gameweek'])

        logger.info(f"Found {len(result)} double gameweeks between GW{start_gw}-{end_gw}")

        return result

    def identify_blank_gameweeks(self, start_gw: int = 1, end_gw: int = 38) -> List[Dict]:
        """
        Identify blank gameweeks where some teams don't play.

        These are optimal for Free Hit.

        Args:
            start_gw: Start of search window
            end_gw: End of search window

        Returns:
            List of blank gameweeks with affected teams
        """
        # This would check fixture data for missing teams
        # For now, return empty list - would need actual fixture data
        # to implement properly

        blank_gws = []

        logger.info(f"Found {len(blank_gws)} blank gameweeks between GW{start_gw}-{end_gw}")

        return blank_gws

    def recommend_wildcard_timing(self, current_gw: int) -> Dict:
        """
        Recommend optimal timing for Wildcard chip.

        Good times to wildcard:
        - When team needs major overhaul (4+ transfers needed)
        - Before favorable fixture runs
        - After international breaks (injury news)
        - Mid-season (GW10-15) or before DGWs

        Args:
            current_gw: Current gameweek

        Returns:
            Dict with wildcard recommendation
        """
        logger.info(f"Analyzing Wildcard timing for GW{current_gw}")

        available_chips = self.get_available_chips(current_gw)
        wc_info = available_chips['wildcard']

        if not wc_info['available']:
            return {
                'recommendation': 'not_available',
                'reasoning': f"Wildcard already used in {wc_info['window']}",
                'used_gw': wc_info['used_in_half'][0] if wc_info['used_in_half'] else None
            }

        # Determine which half we're in
        if current_gw <= 19:
            # First half wildcard
            # Optimal windows: GW3-5 (early template break), GW10-15 (mid-season pivot)
            if current_gw <= 5:
                urgency = 'low'
                timing = 'early_wildcard'
                reasoning = "Early wildcard (GW3-5) useful if poor start or want to break template"
            elif 10 <= current_gw <= 15:
                urgency = 'medium'
                timing = 'mid_season'
                reasoning = "Mid-season wildcard optimal: enough data, can pivot to favorable fixtures"
            elif current_gw >= 17:
                urgency = 'high'
                timing = 'use_or_lose'
                reasoning = f"Must use first half wildcard by GW19 (deadline approaching)"
            else:
                urgency = 'low'
                timing = 'wait'
                reasoning = "No urgent need. Consider GW10-15 for mid-season pivot"

        else:
            # Second half wildcard
            # Optimal: Before DGWs or before final run-in (GW32-34)
            dgws = self.identify_double_gameweeks(current_gw, 38)

            if dgws:
                next_dgw = dgws[0]['gameweek']
                urgency = 'medium'
                timing = 'before_dgw'
                reasoning = f"Wildcard before GW{next_dgw} DGW to maximize double fixtures"
            elif current_gw >= 35:
                urgency = 'high'
                timing = 'use_or_lose'
                reasoning = "Must use second half wildcard before season ends"
            else:
                urgency = 'low'
                timing = 'wait_for_dgw'
                reasoning = "Wait for double gameweek announcement or final run-in (GW32-34)"

        return {
            'recommendation': timing,
            'urgency': urgency,
            'reasoning': reasoning,
            'optimal_window': f"GW{current_gw}-{wc_info['deadline_gw']}",
            'deadline_gw': wc_info['deadline_gw']
        }

    def recommend_bench_boost_timing(self, current_gw: int) -> Dict:
        """
        Recommend optimal timing for Bench Boost chip.

        Best used:
        - During double gameweeks (all 15 players play 2x)
        - When bench has strong players
        - When multiple good fixtures align

        Args:
            current_gw: Current gameweek

        Returns:
            Dict with bench boost recommendation
        """
        logger.info(f"Analyzing Bench Boost timing for GW{current_gw}")

        available_chips = self.get_available_chips(current_gw)
        bb_info = available_chips['bench_boost']

        if not bb_info['available']:
            return {
                'recommendation': 'not_available',
                'reasoning': f"Bench Boost already used in {bb_info['window']}",
                'used_gw': bb_info['used_in_half'][0] if bb_info['used_in_half'] else None
            }

        # Find double gameweeks
        dgws = self.identify_double_gameweeks(current_gw, bb_info['deadline_gw'])

        if dgws:
            best_dgw = max(dgws, key=lambda x: x['teams_with_dgw'])

            return {
                'recommendation': 'wait_for_dgw',
                'optimal_gw': best_dgw['gameweek'],
                'reasoning': f"GW{best_dgw['gameweek']} has {best_dgw['teams_with_dgw']} teams with DGW - optimal for BB",
                'urgency': 'low',
                'deadline_gw': bb_info['deadline_gw']
            }
        else:
            # No DGWs found - check if deadline approaching
            if current_gw >= bb_info['deadline_gw'] - 2:
                return {
                    'recommendation': 'use_soon',
                    'reasoning': f"No DGW found, but deadline GW{bb_info['deadline_gw']} approaching. Use in good fixture week.",
                    'urgency': 'high',
                    'deadline_gw': bb_info['deadline_gw']
                }
            else:
                return {
                    'recommendation': 'wait',
                    'reasoning': "Wait for double gameweek announcement or high-scoring week",
                    'urgency': 'low',
                    'deadline_gw': bb_info['deadline_gw']
                }

    def recommend_triple_captain_timing(self, current_gw: int) -> Dict:
        """
        Recommend optimal timing for Triple Captain chip.

        Best used:
        - On premium player in double gameweek (2 games, 3x points)
        - On player with best fixture (Haaland vs bottom team at home)
        - When captain pick has high ceiling

        Args:
            current_gw: Current gameweek

        Returns:
            Dict with triple captain recommendation
        """
        logger.info(f"Analyzing Triple Captain timing for GW{current_gw}")

        available_chips = self.get_available_chips(current_gw)
        tc_info = available_chips['triple_captain']

        if not tc_info['available']:
            return {
                'recommendation': 'not_available',
                'reasoning': f"Triple Captain already used in {tc_info['window']}",
                'used_gw': tc_info['used_in_half'][0] if tc_info['used_in_half'] else None
            }

        # Find double gameweeks
        dgws = self.identify_double_gameweeks(current_gw, tc_info['deadline_gw'])

        if dgws:
            best_dgw = dgws[0]  # Closest DGW

            return {
                'recommendation': 'wait_for_dgw',
                'optimal_gw': best_dgw['gameweek'],
                'reasoning': f"GW{best_dgw['gameweek']} DGW - triple captain on premium (Haaland/Salah) in DGW",
                'urgency': 'low',
                'deadline_gw': tc_info['deadline_gw']
            }
        else:
            # No DGWs - look for premium fixtures
            if current_gw >= tc_info['deadline_gw'] - 2:
                return {
                    'recommendation': 'use_on_premium_fixture',
                    'reasoning': f"No DGW found, deadline approaching. Use on Haaland/Salah in best fixture.",
                    'urgency': 'high',
                    'deadline_gw': tc_info['deadline_gw']
                }
            else:
                return {
                    'recommendation': 'wait',
                    'reasoning': "Wait for DGW or exceptional fixture (e.g., Haaland vs worst team at home)",
                    'urgency': 'low',
                    'deadline_gw': tc_info['deadline_gw']
                }

    def recommend_free_hit_timing(self, current_gw: int) -> Dict:
        """
        Recommend optimal timing for Free Hit chip.

        Best used:
        - During blank gameweeks (many teams not playing)
        - When team has bad fixtures but improves next week
        - Strategic one-week punt

        Args:
            current_gw: Current gameweek

        Returns:
            Dict with free hit recommendation
        """
        logger.info(f"Analyzing Free Hit timing for GW{current_gw}")

        available_chips = self.get_available_chips(current_gw)
        fh_info = available_chips['free_hit']

        if not fh_info['available']:
            return {
                'recommendation': 'not_available',
                'reasoning': f"Free Hit already used in {fh_info['window']}",
                'used_gw': fh_info['used_in_half'][0] if fh_info['used_in_half'] else None
            }

        # Find blank gameweeks
        bgws = self.identify_blank_gameweeks(current_gw, fh_info['deadline_gw'])

        if bgws:
            next_bgw = bgws[0]

            return {
                'recommendation': 'wait_for_bgw',
                'optimal_gw': next_bgw['gameweek'],
                'reasoning': f"GW{next_bgw['gameweek']} is blank gameweek - optimal for Free Hit",
                'urgency': 'low',
                'deadline_gw': fh_info['deadline_gw']
            }
        else:
            # No BGWs - FH less valuable
            if current_gw >= fh_info['deadline_gw'] - 2:
                return {
                    'recommendation': 'use_or_lose',
                    'reasoning': f"Deadline approaching (GW{fh_info['deadline_gw']}). Use strategically or lose.",
                    'urgency': 'medium',
                    'deadline_gw': fh_info['deadline_gw']
                }
            else:
                return {
                    'recommendation': 'save',
                    'reasoning': "Free Hit best for blank gameweeks. Save for now.",
                    'urgency': 'low',
                    'deadline_gw': fh_info['deadline_gw']
                }

    def generate_chip_strategy(self, current_gw: int) -> Dict:
        """
        Generate overall chip strategy for remainder of season.

        Args:
            current_gw: Current gameweek

        Returns:
            Dict with complete chip strategy:
                - available_chips: Which chips can still be used
                - recommendations: Strategy for each chip
                - priority: Which chip to use next
        """
        logger.info(f"Generating chip strategy for GW{current_gw}")

        available = self.get_available_chips(current_gw)

        recommendations = {
            'wildcard': self.recommend_wildcard_timing(current_gw),
            'bench_boost': self.recommend_bench_boost_timing(current_gw),
            'triple_captain': self.recommend_triple_captain_timing(current_gw),
            'free_hit': self.recommend_free_hit_timing(current_gw)
        }

        # Determine priority
        urgency_scores = {
            'wildcard': 0,
            'bench_boost': 0,
            'triple_captain': 0,
            'free_hit': 0
        }

        for chip, rec in recommendations.items():
            if available[chip]['available']:
                if rec.get('urgency') == 'high':
                    urgency_scores[chip] = 3
                elif rec.get('urgency') == 'medium':
                    urgency_scores[chip] = 2
                else:
                    urgency_scores[chip] = 1

        # Priority chip
        if max(urgency_scores.values()) > 0:
            priority_chip = max(urgency_scores, key=urgency_scores.get)
        else:
            priority_chip = None

        return {
            'current_gameweek': current_gw,
            'available_chips': available,
            'recommendations': recommendations,
            'priority_chip': priority_chip,
            'urgency_scores': urgency_scores
        }
