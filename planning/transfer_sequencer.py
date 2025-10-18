#!/usr/bin/env python3
"""
Transfer Sequencing for Multi-Gameweek Planning

Plans optimal transfer sequences over multiple gameweeks:
- When to use free transfers vs taking hits
- Multi-transfer strategies (banking, doubling up)
- Priority ordering for multiple targets
- Price change considerations in sequencing
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger('ron_clanker.planning')


class TransferSequencer:
    """
    Plans transfer sequences over multiple gameweeks.

    Helps Ron make smart transfer decisions by:
    - Planning ahead rather than reacting
    - Identifying when to bank transfers vs use them
    - Calculating expected value of taking hits
    - Coordinating with fixture swings and price changes
    """

    def __init__(self, database):
        """Initialize with database connection."""
        self.db = database
        logger.info("TransferSequencer: Initialized")

    def get_current_team_status(self, gameweek: int) -> Dict:
        """
        Get current team composition and transfer status.

        Args:
            gameweek: Current gameweek

        Returns:
            Dict with:
                - players: Current 15 players
                - team_value: Total team value
                - bank: Money in the bank
                - free_transfers: Number of free transfers available
        """
        # Get current team
        current_team = self.db.execute_query("""
            SELECT
                mt.player_id,
                p.web_name,
                p.element_type,
                p.team_id,
                mt.purchase_price,
                p.now_cost as current_price
            FROM my_team mt
            JOIN players p ON mt.player_id = p.id
            WHERE mt.gameweek = ?
            ORDER BY p.element_type, p.now_cost DESC
        """, (gameweek,))

        if not current_team:
            return {'error': 'No team found for this gameweek'}

        # Calculate team value
        team_value = sum(p['current_price'] for p in current_team)
        purchase_value = sum(p['purchase_price'] for p in current_team)

        # Get transfer history to determine free transfers
        transfer_history = self.db.execute_query("""
            SELECT COUNT(*) as transfer_count
            FROM transfers
            WHERE gameweek = ?
        """, (gameweek,))

        transfers_made = transfer_history[0]['transfer_count'] if transfer_history else 0

        # FPL rules: Start with 1 FT, can bank to max of 2
        # This is simplified - would need to track from previous GW
        free_transfers_remaining = max(0, 1 - transfers_made)

        return {
            'gameweek': gameweek,
            'players': current_team,
            'team_value': team_value,
            'purchase_value': purchase_value,
            'team_value_profit': team_value - purchase_value,
            'free_transfers': free_transfers_remaining,
            'transfers_made_this_gw': transfers_made
        }

    def plan_transfer_sequence(self, start_gw: int, targets: List[Dict],
                               planning_horizon: int = 4) -> Dict:
        """
        Plan optimal transfer sequence over multiple gameweeks.

        Args:
            start_gw: Starting gameweek
            targets: List of desired transfers, each dict with:
                - player_out_id: Player to remove
                - player_in_id: Player to bring in
                - priority: 1-5 (1=highest)
                - expected_gain: Expected points gain over period
                - latest_gw: Latest GW to complete by (optional)
            planning_horizon: Number of gameweeks to plan

        Returns:
            Dict with optimal transfer sequence:
                - sequence: Ordered list of transfers by GW
                - total_hits: Points deducted for hits
                - total_expected_gain: Expected points gained
                - net_gain: Total gain minus hits
                - reasoning: Explanation of sequence
        """
        logger.info(f"Planning transfer sequence for GW{start_gw}-{start_gw+planning_horizon-1}")

        if not targets:
            return {
                'sequence': [],
                'total_hits': 0,
                'total_expected_gain': 0,
                'net_gain': 0,
                'reasoning': 'No transfers needed'
            }

        # Sort targets by priority, then expected gain
        sorted_targets = sorted(
            targets,
            key=lambda x: (x.get('priority', 5), -x.get('expected_gain', 0))
        )

        # Track free transfers across gameweeks
        # Start with 1 FT, can bank to max of 2
        free_transfers = 1
        planned_sequence = []
        total_hits = 0
        total_gain = 0

        for gw_offset in range(planning_horizon):
            current_gw = start_gw + gw_offset

            # Determine how many transfers to make this GW
            urgent_transfers = [
                t for t in sorted_targets
                if t.get('latest_gw', 999) <= current_gw
            ]

            if urgent_transfers:
                # Must make urgent transfers even if it costs points
                num_transfers = len(urgent_transfers)
                targets_this_gw = urgent_transfers[:num_transfers]
            elif free_transfers >= 1:
                # Use available free transfers on highest priority
                num_transfers = min(free_transfers, len(sorted_targets))
                targets_this_gw = sorted_targets[:num_transfers]
            else:
                # No free transfers and nothing urgent - skip this GW
                targets_this_gw = []
                # Bank a transfer for next week (max 2)
                free_transfers = min(2, free_transfers + 1)
                continue

            # Execute transfers for this GW
            gw_transfers = []
            gw_hits = 0
            gw_gain = 0

            for i, transfer in enumerate(targets_this_gw):
                if i < free_transfers:
                    # Free transfer
                    cost = 0
                else:
                    # Hit (-4 points)
                    cost = 4
                    gw_hits += 4

                gw_transfers.append({
                    'player_out_id': transfer['player_out_id'],
                    'player_in_id': transfer['player_in_id'],
                    'expected_gain': transfer.get('expected_gain', 0),
                    'cost': cost,
                    'priority': transfer.get('priority', 3),
                    'reasoning': transfer.get('reasoning', 'Strategic transfer')
                })

                gw_gain += transfer.get('expected_gain', 0)

                # Remove from targets list
                sorted_targets.remove(transfer)

            if gw_transfers:
                planned_sequence.append({
                    'gameweek': current_gw,
                    'transfers': gw_transfers,
                    'free_transfers_used': min(len(gw_transfers), free_transfers),
                    'hits_taken': len(gw_transfers) - min(len(gw_transfers), free_transfers),
                    'points_cost': gw_hits,
                    'expected_gain': gw_gain,
                    'net_gain': gw_gain - gw_hits
                })

                total_hits += gw_hits
                total_gain += gw_gain

                # Reset free transfers for next GW
                free_transfers = 1
            else:
                # No transfers, bank for next week
                free_transfers = min(2, free_transfers + 1)

            # Stop if all targets completed
            if not sorted_targets:
                break

        # Generate reasoning
        num_transfers = sum(len(gw['transfers']) for gw in planned_sequence)
        num_gws = len(planned_sequence)

        reasoning = f"Planned {num_transfers} transfers over {num_gws} gameweeks. "
        if total_hits > 0:
            reasoning += f"Taking {total_hits // 4} hits for expected net gain of {total_gain - total_hits:.1f} points."
        else:
            reasoning += f"Using only free transfers for expected gain of {total_gain:.1f} points."

        return {
            'sequence': planned_sequence,
            'total_hits': total_hits,
            'total_expected_gain': total_gain,
            'net_gain': total_gain - total_hits,
            'reasoning': reasoning,
            'planning_period': f'GW{start_gw}-{start_gw+planning_horizon-1}'
        }

    def evaluate_hit_decision(self, transfer: Dict, horizon_gws: int = 3) -> Dict:
        """
        Evaluate whether a transfer is worth a -4 hit.

        Args:
            transfer: Dict with:
                - player_out_id: Player to remove
                - player_in_id: Player to bring in
                - player_out_xpts: Expected points for player out (over horizon)
                - player_in_xpts: Expected points for player in (over horizon)
            horizon_gws: Evaluate over this many gameweeks

        Returns:
            Dict with:
                - worth_hit: True if expected gain > 4 points
                - expected_gain: Points gained over horizon
                - net_gain: Gain minus -4 cost
                - recommendation: 'take_hit', 'wait_for_ft', or 'not_worth_it'
        """
        player_out_xpts = transfer.get('player_out_xpts', 0)
        player_in_xpts = transfer.get('player_in_xpts', 0)

        expected_gain = player_in_xpts - player_out_xpts
        net_gain = expected_gain - 4  # -4 point cost

        # Thresholds
        if expected_gain >= 8:
            # Gain >= 8 pts over 3 GWs = definitely worth it
            worth_hit = True
            recommendation = 'take_hit'
            reasoning = f"Strong transfer: +{expected_gain:.1f} xPts over {horizon_gws} GWs justifies -4 hit"
        elif expected_gain >= 5:
            # Gain 5-7 pts = probably worth it
            worth_hit = True
            recommendation = 'take_hit'
            reasoning = f"Good transfer: +{expected_gain:.1f} xPts likely worth -4 hit"
        elif expected_gain >= 4:
            # Marginal case
            worth_hit = False
            recommendation = 'wait_for_ft'
            reasoning = f"Marginal transfer: +{expected_gain:.1f} xPts barely justifies hit. Consider waiting for FT."
        else:
            # Not worth it
            worth_hit = False
            recommendation = 'not_worth_it'
            reasoning = f"Insufficient gain: +{expected_gain:.1f} xPts does not justify -4 hit. Wait for FT."

        return {
            'worth_hit': worth_hit,
            'expected_gain': expected_gain,
            'net_gain': net_gain,
            'recommendation': recommendation,
            'reasoning': reasoning,
            'horizon_gws': horizon_gws
        }

    def identify_transfer_priorities(self, current_gw: int, next_n_gws: int = 4) -> List[Dict]:
        """
        Identify transfer priorities based on:
        - Injured/suspended players (urgent)
        - Players with bad upcoming fixtures
        - Underperforming assets
        - Price falling players

        Args:
            current_gw: Current gameweek
            next_n_gws: Planning horizon

        Returns:
            List of players to consider transferring out, with priority levels
        """
        logger.info(f"Identifying transfer priorities for GW{current_gw}")

        # Get current team
        team_status = self.get_current_team_status(current_gw)

        if 'error' in team_status:
            return []

        priorities = []

        for player in team_status['players']:
            player_id = player['player_id']

            # Check injury status
            player_info = self.db.execute_query("""
                SELECT
                    web_name,
                    chance_of_playing_next_round,
                    news,
                    form
                FROM players
                WHERE id = ?
            """, (player_id,))

            if not player_info:
                continue

            player_info = player_info[0]

            priority_score = 0
            reasons = []

            # Injury/suspension (highest priority)
            chance_playing = player_info.get('chance_of_playing_next_round')
            if chance_playing is not None and chance_playing < 50:
                priority_score += 10
                reasons.append(f"Injury concern ({chance_playing}% to play)")

            # Poor form
            form = float(player_info.get('form', 0) or 0)
            if form < 2.0:
                priority_score += 3
                reasons.append(f"Poor form ({form:.1f})")

            # Price falling (use price change predictions if available)
            # This would integrate with price prediction system
            # For now, placeholder

            if priority_score > 0:
                priorities.append({
                    'player_id': player_id,
                    'player_name': player['web_name'],
                    'priority_score': priority_score,
                    'reasons': reasons,
                    'priority_level': 1 if priority_score >= 10 else (2 if priority_score >= 5 else 3)
                })

        # Sort by priority score
        priorities.sort(key=lambda x: x['priority_score'], reverse=True)

        logger.info(f"Identified {len(priorities)} transfer priorities")

        return priorities

    def recommend_transfer_strategy(self, current_gw: int,
                                   free_transfers_available: int,
                                   planning_horizon: int = 4) -> Dict:
        """
        Recommend overall transfer strategy for upcoming gameweeks.

        Args:
            current_gw: Current gameweek
            free_transfers_available: Number of FTs available
            planning_horizon: How many GWs to plan

        Returns:
            Dict with strategy recommendation:
                - action: 'make_transfers', 'bank_transfer', 'wildcard'
                - reasoning: Why this strategy
                - suggested_transfers: If make_transfers, which ones
        """
        logger.info(f"Recommending transfer strategy for GW{current_gw}")

        # Identify priorities
        priorities = self.identify_transfer_priorities(current_gw, planning_horizon)

        urgent_priorities = [p for p in priorities if p['priority_level'] == 1]
        high_priorities = [p for p in priorities if p['priority_level'] == 2]

        # Decision logic
        if len(urgent_priorities) >= 3:
            # Multiple urgent issues - consider wildcard
            return {
                'action': 'consider_wildcard',
                'reasoning': f"{len(urgent_priorities)} urgent transfer needs. Wildcard may be optimal.",
                'urgent_issues': urgent_priorities
            }

        elif urgent_priorities:
            # Must address urgent issues
            num_transfers = min(len(urgent_priorities), free_transfers_available + 1)
            return {
                'action': 'make_transfers',
                'reasoning': f"{len(urgent_priorities)} urgent issues require immediate transfers",
                'suggested_transfers': urgent_priorities[:num_transfers],
                'hits_required': max(0, num_transfers - free_transfers_available)
            }

        elif high_priorities and free_transfers_available >= 1:
            # Use free transfers on high priorities
            return {
                'action': 'make_transfers',
                'reasoning': f"{len(high_priorities)} high-priority transfers available, use FTs",
                'suggested_transfers': high_priorities[:free_transfers_available]
            }

        elif free_transfers_available < 2:
            # Bank transfer for more flexibility
            return {
                'action': 'bank_transfer',
                'reasoning': 'No urgent needs. Bank transfer for 2 FT next week.',
                'future_targets': high_priorities[:3] if high_priorities else []
            }

        else:
            # Have 2 FTs but nothing urgent - use them
            targets = priorities[:2] if len(priorities) >= 2 else priorities
            return {
                'action': 'make_transfers',
                'reasoning': 'Have 2 FTs available, optimize team even without urgent needs',
                'suggested_transfers': targets
            }
