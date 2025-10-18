#!/usr/bin/env python3
"""
Multi-Gameweek Strategic Planner

Main orchestrator for Ron's strategic planning.

Coordinates:
- Fixture analysis (best/worst upcoming runs)
- Transfer sequencing (multi-week planning)
- Chip timing (optimal windows)
- Budget management (team value growth)

Produces comprehensive strategic plan for next 4-6 gameweeks.
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime

from planning.fixture_analyzer import FixtureAnalyzer
from planning.transfer_sequencer import TransferSequencer
from planning.chip_optimizer import ChipOptimizer
from planning.budget_tracker import BudgetTracker

logger = logging.getLogger('ron_clanker.planning')


class MultiGWPlanner:
    """
    Main strategic planner for multiple gameweeks.

    Ron's "tactical board" for planning 4-6 gameweeks ahead.
    """

    def __init__(self, database):
        """Initialize with database and all planning modules."""
        self.db = database

        # Initialize all planning modules
        self.fixture_analyzer = FixtureAnalyzer(database)
        self.transfer_sequencer = TransferSequencer(database)
        self.chip_optimizer = ChipOptimizer(database)
        self.budget_tracker = BudgetTracker(database)

        logger.info("MultiGWPlanner: Initialized with all planning modules")

    def generate_strategic_plan(self, current_gw: int, planning_horizon: int = 6) -> Dict:
        """
        Generate comprehensive strategic plan for next N gameweeks.

        This is the main entry point for Ron's multi-GW planning.

        Args:
            current_gw: Current gameweek
            planning_horizon: How many gameweeks to plan ahead (default 6)

        Returns:
            Dict with complete strategic plan:
                - fixture_analysis: Best/worst runs, swings
                - transfer_plan: Recommended sequence
                - chip_strategy: When to use chips
                - budget_plan: Value growth targets
                - key_recommendations: Top priorities
        """
        logger.info(f"Generating strategic plan: GW{current_gw}-{current_gw+planning_horizon-1}")

        plan = {
            'current_gameweek': current_gw,
            'planning_period': f'GW{current_gw}-{current_gw+planning_horizon-1}',
            'generated_at': datetime.now().isoformat(),
        }

        # 1. FIXTURE ANALYSIS
        logger.info("Analyzing fixtures...")
        plan['fixtures'] = self._analyze_fixtures(current_gw, planning_horizon)

        # 2. TRANSFER PLANNING
        logger.info("Planning transfers...")
        plan['transfers'] = self._plan_transfers(current_gw, planning_horizon, plan['fixtures'])

        # 3. CHIP STRATEGY
        logger.info("Optimizing chip timing...")
        plan['chips'] = self._optimize_chips(current_gw)

        # 4. BUDGET MANAGEMENT
        logger.info("Analyzing budget...")
        plan['budget'] = self._analyze_budget(current_gw, planning_horizon)

        # 5. KEY RECOMMENDATIONS
        logger.info("Generating recommendations...")
        plan['recommendations'] = self._generate_recommendations(plan)

        logger.info("Strategic plan complete")

        return plan

    def _analyze_fixtures(self, current_gw: int, horizon: int) -> Dict:
        """
        Analyze fixtures for planning period.

        Returns:
            Dict with fixture insights
        """
        # Best fixture runs
        best_runs = self.fixture_analyzer.find_best_fixture_runs(
            current_gw,
            horizon,
            top_n=10
        )

        # Fixture swings
        swings = self.fixture_analyzer.identify_fixture_swings(
            current_gw,
            horizon
        )

        # Categorize swings
        favorable_swings = [s for s in swings if s['swing_type'] == 'favorable']
        unfavorable_swings = [s for s in swings if s['swing_type'] == 'unfavorable']

        return {
            'best_fixture_runs': best_runs[:5],  # Top 5 teams
            'favorable_swings': favorable_swings[:3],  # Top 3 improving
            'unfavorable_swings': unfavorable_swings[:3],  # Top 3 worsening
            'summary': {
                'teams_to_target': [r['team_name'] for r in best_runs[:3]],
                'teams_to_avoid': [s['team_name'] for s in unfavorable_swings[:3]]
            }
        }

    def _plan_transfers(self, current_gw: int, horizon: int, fixtures: Dict) -> Dict:
        """
        Plan transfer sequence based on fixtures.

        Returns:
            Dict with transfer plan
        """
        # Get transfer priorities
        priorities = self.transfer_sequencer.identify_transfer_priorities(
            current_gw,
            horizon
        )

        # Get transfer strategy recommendation
        strategy = self.transfer_sequencer.recommend_transfer_strategy(
            current_gw,
            free_transfers_available=1,  # Would get from team state
            planning_horizon=horizon
        )

        # Build transfer targets from fixture analysis
        targets = []

        # Players from teams with good fixtures to bring in
        for team_info in fixtures['best_fixture_runs'][:3]:
            # Would query for best players from this team
            # Placeholder for now
            pass

        # Players from teams with bad fixtures to move out
        for team_info in fixtures['unfavorable_swings'][:2]:
            # Would check if we own players from this team
            # Placeholder for now
            pass

        return {
            'strategy': strategy,
            'priorities': priorities[:5],  # Top 5 priorities
            'targets_in': [],  # Would populate from fixture analysis
            'targets_out': priorities[:3] if priorities else [],
            'summary': strategy.get('reasoning', 'No urgent transfers needed')
        }

    def _optimize_chips(self, current_gw: int) -> Dict:
        """
        Determine optimal chip timing.

        Returns:
            Dict with chip strategy
        """
        chip_strategy = self.chip_optimizer.generate_chip_strategy(current_gw)

        # Extract key info
        available = [
            chip for chip, info in chip_strategy['available_chips'].items()
            if info['available']
        ]

        priority_chip = chip_strategy.get('priority_chip')

        summary = []
        for chip in available:
            rec = chip_strategy['recommendations'][chip]
            if rec.get('recommendation') != 'not_available':
                summary.append({
                    'chip': chip,
                    'recommendation': rec.get('recommendation', 'wait'),
                    'optimal_gw': rec.get('optimal_gw'),
                    'urgency': rec.get('urgency', 'low'),
                    'reasoning': rec.get('reasoning', '')
                })

        return {
            'available_chips': available,
            'priority_chip': priority_chip,
            'recommendations': summary,
            'full_strategy': chip_strategy
        }

    def _analyze_budget(self, current_gw: int, horizon: int) -> Dict:
        """
        Analyze budget and value growth.

        Returns:
            Dict with budget insights
        """
        # Current budget status
        budget_status = self.budget_tracker.get_current_budget_status(current_gw)

        # Price rise targets
        rise_targets = self.budget_tracker.identify_price_rise_targets(current_gw)

        # Price fall risks
        fall_risks = self.budget_tracker.identify_price_fall_risks(current_gw)

        # Budget strategy
        strategy = self.budget_tracker.recommend_budget_strategy(current_gw)

        # Value growth projection
        value_growth = self.budget_tracker.calculate_value_growth_opportunity(
            current_gw,
            current_gw + horizon - 1
        )

        return {
            'current_status': {
                'team_value': budget_status.get('team_value', 0),
                'total_budget': budget_status.get('total_budget', 0),
                'profit': budget_status.get('unrealized_profit', 0)
            },
            'price_targets': {
                'rise_soon': len(rise_targets),
                'fall_risks': len(fall_risks),
                'top_targets': rise_targets[:3] if rise_targets else []
            },
            'value_growth': value_growth,
            'strategy': strategy.get('recommendations', [])
        }

    def _generate_recommendations(self, plan: Dict) -> List[Dict]:
        """
        Generate prioritized recommendations from full plan.

        Returns:
            List of actionable recommendations, sorted by priority
        """
        recommendations = []

        # Transfer recommendations
        transfer_strategy = plan['transfers']['strategy']
        if transfer_strategy.get('action') == 'consider_wildcard':
            recommendations.append({
                'priority': 1,
                'category': 'chip',
                'action': 'Consider Wildcard',
                'reasoning': transfer_strategy.get('reasoning', ''),
                'gameweek': plan['current_gameweek']
            })
        elif transfer_strategy.get('action') == 'make_transfers':
            num_transfers = len(transfer_strategy.get('suggested_transfers', []))
            recommendations.append({
                'priority': 2,
                'category': 'transfer',
                'action': f'Make {num_transfers} transfer(s)',
                'reasoning': transfer_strategy.get('reasoning', ''),
                'gameweek': plan['current_gameweek']
            })

        # Chip recommendations
        chip_priority = plan['chips'].get('priority_chip')
        if chip_priority:
            chip_rec = next(
                (r for r in plan['chips']['recommendations'] if r['chip'] == chip_priority),
                None
            )
            if chip_rec and chip_rec.get('urgency') in ['high', 'medium']:
                recommendations.append({
                    'priority': 2 if chip_rec['urgency'] == 'high' else 3,
                    'category': 'chip',
                    'action': f"Plan {chip_priority.replace('_', ' ').title()}",
                    'reasoning': chip_rec.get('reasoning', ''),
                    'optimal_gw': chip_rec.get('optimal_gw')
                })

        # Budget recommendations
        budget_recs = plan['budget'].get('strategy', [])
        for rec in budget_recs:
            if rec.get('priority') == 'high':
                recommendations.append({
                    'priority': 2,
                    'category': 'budget',
                    'action': rec.get('action', '').replace('_', ' ').title(),
                    'reasoning': rec.get('reasoning', ''),
                    'gameweek': plan['current_gameweek']
                })

        # Fixture-based recommendations
        target_teams = plan['fixtures']['summary']['teams_to_target']
        if target_teams:
            recommendations.append({
                'priority': 3,
                'category': 'fixture',
                'action': f"Target players from: {', '.join(target_teams)}",
                'reasoning': 'These teams have best upcoming fixtures',
                'gameweek_range': plan['planning_period']
            })

        avoid_teams = plan['fixtures']['summary']['teams_to_avoid']
        if avoid_teams:
            recommendations.append({
                'priority': 3,
                'category': 'fixture',
                'action': f"Avoid players from: {', '.join(avoid_teams)}",
                'reasoning': 'These teams have difficult upcoming fixtures',
                'gameweek_range': plan['planning_period']
            })

        # Sort by priority
        recommendations.sort(key=lambda x: x['priority'])

        return recommendations

    def get_quick_summary(self, current_gw: int) -> Dict:
        """
        Get quick strategic summary (lighter version).

        Useful for daily updates without full planning.

        Args:
            current_gw: Current gameweek

        Returns:
            Dict with quick insights
        """
        logger.info(f"Generating quick summary for GW{current_gw}")

        # Fixtures next 3 GWs
        best_runs = self.fixture_analyzer.find_best_fixture_runs(
            current_gw,
            num_gameweeks=3,
            top_n=5
        )

        # Transfer strategy
        transfer_strategy = self.transfer_sequencer.recommend_transfer_strategy(
            current_gw,
            free_transfers_available=1
        )

        # Chip urgency
        chip_strategy = self.chip_optimizer.generate_chip_strategy(current_gw)
        urgent_chips = [
            chip for chip, score in chip_strategy['urgency_scores'].items()
            if score >= 2
        ]

        # Budget alerts
        fall_risks = self.budget_tracker.identify_price_fall_risks(current_gw)

        return {
            'gameweek': current_gw,
            'best_fixtures_next_3_gw': [r['team_name'] for r in best_runs[:3]],
            'transfer_action': transfer_strategy.get('action', 'bank_transfer'),
            'urgent_chips': urgent_chips,
            'price_fall_alerts': len(fall_risks),
            'key_message': self._generate_key_message(
                transfer_strategy,
                urgent_chips,
                fall_risks
            )
        }

    def _generate_key_message(self, transfer_strategy: Dict,
                             urgent_chips: List[str],
                             fall_risks: List) -> str:
        """
        Generate Ron's key message for the day.

        Returns:
            String with key message
        """
        messages = []

        if urgent_chips:
            messages.append(f"Chip deadline approaching: {', '.join(urgent_chips)}")

        if fall_risks:
            messages.append(f"{len(fall_risks)} player(s) at risk of price fall")

        action = transfer_strategy.get('action', 'hold')
        if action == 'make_transfers':
            messages.append("Transfers recommended this week")
        elif action == 'bank_transfer':
            messages.append("Bank transfer for 2 FT next week")

        if not messages:
            messages.append("All quiet. Team looking solid.")

        return " | ".join(messages)
