#!/usr/bin/env python3
"""
Budget Planning and Team Value Tracking

Monitors and optimizes:
- Current team value
- Potential team value growth
- Price change targets (buy before rises, sell before falls)
- Budget allocation strategy
- Selling value calculations (50% profit rule)
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger('ron_clanker.planning')


class BudgetTracker:
    """
    Tracks team budget and plans value growth.

    Helps Ron maximize team value by:
    - Identifying players about to rise in price
    - Timing transfers to capture price rises
    - Avoiding price falls
    - Planning budget for future targets
    """

    def __init__(self, database):
        """Initialize with database connection."""
        self.db = database
        self.INITIAL_BUDGET = 1000  # £100.0m in tenths
        logger.info("BudgetTracker: Initialized")

    def get_current_budget_status(self, gameweek: int) -> Dict:
        """
        Calculate current budget situation.

        Args:
            gameweek: Current gameweek

        Returns:
            Dict with:
                - team_value: Current market value (what team is worth)
                - selling_value: What you'd get if you sold all players
                - purchase_cost: What was originally spent
                - profit: Unrealized profit
                - budget_remaining: Money in the bank
                - total_budget: Selling value + bank
        """
        # Get current team
        team = self.db.execute_query("""
            SELECT
                mt.player_id,
                p.web_name,
                mt.purchase_price,
                p.now_cost as current_price
            FROM my_team mt
            JOIN players p ON mt.player_id = p.id
            WHERE mt.gameweek = ?
        """, (gameweek,))

        if not team:
            return {
                'error': 'No team found',
                'team_value': 0,
                'selling_value': 0,
                'budget_remaining': self.INITIAL_BUDGET
            }

        team_value = 0
        selling_value = 0
        purchase_cost = 0

        player_details = []

        for player in team:
            current_price = player['current_price']
            purchase_price = player['purchase_price']

            # Team value = sum of current prices
            team_value += current_price

            # Purchase cost = sum of purchase prices
            purchase_cost += purchase_price

            # Selling price = purchase + (profit / 2), rounded down
            profit = current_price - purchase_price
            if profit > 0:
                # Keep 50% of profit
                selling_price = purchase_price + (profit // 2)
            else:
                # Full loss
                selling_price = current_price

            selling_value += selling_price

            player_details.append({
                'player_id': player['player_id'],
                'name': player['web_name'],
                'purchase_price': purchase_price,
                'current_price': current_price,
                'selling_price': selling_price,
                'profit': profit,
                'profit_kept': selling_price - purchase_price
            })

        # Budget remaining (simplified - would need actual bank balance from team state)
        budget_remaining = self.INITIAL_BUDGET - purchase_cost

        return {
            'gameweek': gameweek,
            'team_value': team_value,
            'selling_value': selling_value,
            'purchase_cost': purchase_cost,
            'unrealized_profit': team_value - purchase_cost,
            'realized_profit': selling_value - purchase_cost,
            'profit_locked': selling_value - purchase_cost,
            'budget_remaining': budget_remaining,
            'total_budget': selling_value + budget_remaining,
            'players': player_details
        }

    def identify_price_rise_targets(self, gameweek: int, max_price: int = None) -> List[Dict]:
        """
        Identify players likely to rise in price soon.

        These are good targets to bring in before price rises.

        Args:
            gameweek: Current gameweek
            max_price: Maximum price to consider (optional)

        Returns:
            List of players likely to rise, sorted by probability
        """
        # Get price predictions (recent predictions, since table is date-based not GW-based)
        predictions = self.db.execute_query("""
            SELECT
                pp.player_id,
                p.web_name,
                p.now_cost,
                p.selected_by_percent,
                pp.predicted_change,
                pp.confidence,
                pp.predicted_at
            FROM price_predictions pp
            JOIN players p ON pp.player_id = p.id
            WHERE pp.predicted_change = 'rise'
            AND DATE(pp.predicted_at) >= DATE('now', '-2 days')
            ORDER BY pp.confidence DESC
        """)

        if max_price:
            predictions = [p for p in predictions if p['now_cost'] <= max_price]

        targets = []
        for pred in predictions:
            targets.append({
                'player_id': pred['player_id'],
                'name': pred['web_name'],
                'current_price': pred['now_cost'],
                'expected_price': pred['now_cost'] + 1,  # +0.1m
                'ownership': pred['selected_by_percent'],
                'confidence': pred['confidence'],
                'potential_profit': 1,  # 0.1m if brought in before rise
                'recommendation': 'bring_in_before_rise'
            })

        logger.info(f"Found {len(targets)} players likely to rise")

        return targets

    def identify_price_fall_risks(self, gameweek: int) -> List[Dict]:
        """
        Identify owned players likely to fall in price.

        These should be prioritized for transfer out.

        Args:
            gameweek: Current gameweek

        Returns:
            List of owned players at risk of falling
        """
        # Get current team
        team = self.db.execute_query("""
            SELECT player_id
            FROM my_team
            WHERE gameweek = ?
        """, (gameweek,))

        if not team:
            return []

        owned_ids = [p['player_id'] for p in team]

        # Get price predictions for owned players (recent predictions)
        owned_ids_str = ','.join('?' * len(owned_ids))
        predictions = self.db.execute_query(f"""
            SELECT
                pp.player_id,
                p.web_name,
                p.now_cost,
                mt.purchase_price,
                pp.predicted_change,
                pp.confidence
            FROM price_predictions pp
            JOIN players p ON pp.player_id = p.id
            JOIN my_team mt ON p.id = mt.player_id AND mt.gameweek = ?
            WHERE pp.predicted_change = 'fall'
            AND DATE(pp.predicted_at) >= DATE('now', '-2 days')
            AND pp.player_id IN ({owned_ids_str})
            ORDER BY pp.confidence DESC
        """, (gameweek, *owned_ids))

        risks = []
        for pred in predictions:
            purchase = pred['purchase_price']
            current = pred['now_cost']
            fall_to = current - 1  # -0.1m

            # Calculate selling value before/after fall
            profit_now = current - purchase
            selling_now = purchase + (profit_now // 2) if profit_now > 0 else current

            profit_after = fall_to - purchase
            selling_after = purchase + (profit_after // 2) if profit_after > 0 else fall_to

            value_loss = selling_now - selling_after

            risks.append({
                'player_id': pred['player_id'],
                'name': pred['web_name'],
                'current_price': current,
                'expected_price': fall_to,
                'purchase_price': purchase,
                'selling_value_now': selling_now,
                'selling_value_after_fall': selling_after,
                'value_loss': value_loss,
                'confidence': pred['confidence'],
                'recommendation': 'transfer_out_soon' if value_loss > 0 else 'monitor'
            })

        logger.info(f"Found {len(risks)} owned players at risk of falling")

        return risks

    def plan_budget_for_targets(self, gameweek: int, targets: List[Dict]) -> Dict:
        """
        Plan budget to afford future transfer targets.

        Args:
            gameweek: Current gameweek
            targets: List of target players with their prices

        Returns:
            Dict with budget feasibility analysis
        """
        budget_status = self.get_current_budget_status(gameweek)
        available_budget = budget_status['total_budget']

        target_cost = sum(t.get('price', 0) for t in targets)

        # Need to sell players equal to targets
        num_transfers = len(targets)

        # Estimate selling value from cheapest players
        current_team = budget_status['players']
        cheapest_players = sorted(current_team, key=lambda x: x['selling_price'])[:num_transfers]
        selling_value = sum(p['selling_price'] for p in cheapest_players)

        budget_after_sales = available_budget + selling_value
        surplus_deficit = budget_after_sales - target_cost

        feasible = surplus_deficit >= 0

        return {
            'targets': targets,
            'target_cost': target_cost,
            'available_budget': available_budget,
            'selling_value': selling_value,
            'budget_after_sales': budget_after_sales,
            'surplus_deficit': surplus_deficit,
            'feasible': feasible,
            'recommendation': 'affordable' if feasible else 'need_cheaper_targets'
        }

    def calculate_value_growth_opportunity(self, start_gw: int, end_gw: int) -> Dict:
        """
        Calculate potential team value growth over period.

        Based on price change predictions.

        Args:
            start_gw: Start of period
            end_gw: End of period

        Returns:
            Dict with value growth projections
        """
        # This would analyze price predictions over the period
        # For now, simplified version

        current_budget = self.get_current_budget_status(start_gw)

        # Estimate: Good managers gain 0.5-1.0m per 10 gameweeks
        gameweeks = end_gw - start_gw + 1
        expected_growth = (gameweeks / 10) * 7  # 0.7m per 10 GWs (conservative)

        projected_value = current_budget['team_value'] + expected_growth

        return {
            'current_value': current_budget['team_value'],
            'projected_value': projected_value,
            'expected_growth': expected_growth,
            'growth_rate': f"+{expected_growth / gameweeks:.2f}m per GW",
            'period': f"GW{start_gw}-{end_gw}"
        }

    def recommend_budget_strategy(self, gameweek: int) -> Dict:
        """
        Recommend overall budget management strategy.

        Args:
            gameweek: Current gameweek

        Returns:
            Dict with strategy recommendations
        """
        logger.info(f"Recommending budget strategy for GW{gameweek}")

        budget_status = self.get_current_budget_status(gameweek)
        price_rises = self.identify_price_rise_targets(gameweek)
        price_falls = self.identify_price_fall_risks(gameweek)

        recommendations = []

        # Check for fall risks
        if price_falls:
            high_risk = [p for p in price_falls if p['confidence'] > 0.7]
            if high_risk:
                recommendations.append({
                    'priority': 'high',
                    'action': 'transfer_out',
                    'targets': high_risk,
                    'reasoning': f"{len(high_risk)} players at high risk of falling - transfer out to preserve value"
                })

        # Check for rise opportunities
        if price_rises:
            high_prob = [p for p in price_rises if p['confidence'] > 0.7]
            if high_prob:
                recommendations.append({
                    'priority': 'medium',
                    'action': 'transfer_in',
                    'targets': high_prob[:3],
                    'reasoning': f"Bring in before price rises to gain {len(high_prob[:3])} × 0.1m value"
                })

        # Budget health check
        total_budget = budget_status['total_budget']
        if total_budget < 995:  # Below 99.5m
            recommendations.append({
                'priority': 'medium',
                'action': 'rebuild_value',
                'reasoning': f"Team value {total_budget/10:.1f}m is below target. Focus on value picks."
            })

        if not recommendations:
            recommendations.append({
                'priority': 'low',
                'action': 'maintain',
                'reasoning': 'Budget healthy, no urgent actions needed'
            })

        return {
            'gameweek': gameweek,
            'budget_status': budget_status,
            'recommendations': recommendations,
            'price_rise_targets': len(price_rises),
            'price_fall_risks': len(price_falls)
        }
