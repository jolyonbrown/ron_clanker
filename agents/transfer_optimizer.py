#!/usr/bin/env python3
"""
Transfer Optimizer - Intelligent Transfer Decision Engine

Makes smart transfer decisions by:
1. Evaluating ALL positions independently
2. Calculating multi-gameweek value (not just next GW)
3. Comparing options across positions
4. Deciding roll vs make vs chip usage
5. Surfacing all data transparently

This replaces the narrow single-transfer logic in ManagerAgent.
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from data.database import Database

logger = logging.getLogger('ron_clanker.transfer_optimizer')

POSITIONS = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}


@dataclass
class TransferOption:
    """A single transfer option with full context"""
    position: int
    position_name: str
    player_out_id: int
    player_out_name: str
    player_out_price: float
    player_in_id: int
    player_in_name: str
    player_in_price: float
    gw_predictions: List[Tuple[int, float, float]]  # [(gw, xp_out, xp_in), ...]
    total_gain: float
    avg_gain_per_gw: float
    fixtures_out: List[Dict]
    fixtures_in: List[Dict]
    price_change_urgency: str  # 'HIGH', 'MEDIUM', 'LOW'
    alternatives_count: int

    def __repr__(self):
        return (f"Transfer({self.player_out_name} → {self.player_in_name}, "
                f"+{self.total_gain:.1f}pts over {len(self.gw_predictions)}GWs)")


class TransferOptimizer:
    """
    Intelligent transfer decision engine.

    Philosophy:
    - Look ahead 4 gameweeks (balance between planning and uncertainty)
    - Evaluate ALL positions, not just weakest overall
    - Compare opportunity cost across positions
    - Factor in fixtures, price changes, urgency
    - Decide roll vs make based on expected value
    """

    def __init__(self, database: Database, chip_strategy=None):
        """
        Initialize transfer optimizer.

        Args:
            database: Database instance
            chip_strategy: Deprecated, chip decisions now handled by manager
        """
        self.db = database
        self.verbose = True  # Always show data for transparency

        # Load learned thresholds (or use defaults)
        self.thresholds = self._load_learned_thresholds()
        logger.info(f"TransferOptimizer initialized with thresholds: {self.thresholds}")

    def _load_learned_thresholds(self) -> Dict[int, float]:
        """
        Load position-specific transfer thresholds from database.

        Returns:
            Dict mapping position_id -> min_gain_per_gw threshold
            Defaults to 2.0 if no learned thresholds
        """
        defaults = {0: 2.0, 1: 2.0, 2: 2.0, 3: 2.0, 4: 2.0}

        try:
            thresholds = self.db.execute_query("""
                SELECT position, threshold_value
                FROM learned_thresholds
                WHERE threshold_type = 'min_gain_per_gw'
            """)

            if thresholds:
                for row in thresholds:
                    defaults[row['position']] = row['threshold_value']
                logger.info(f"Loaded learned thresholds: {defaults}")
            else:
                logger.debug("No learned thresholds found, using defaults")

        except Exception as e:
            logger.debug(f"Could not load learned thresholds: {e}")

        return defaults

    def get_threshold_for_position(self, position: int) -> float:
        """Get the minimum gain per GW threshold for a specific position."""
        return self.thresholds.get(position, self.thresholds.get(0, 2.0))

    def identify_unavailable_players(self, current_team: List[Dict]) -> List[Dict]:
        """
        Identify players in squad who are unavailable and MUST be transferred out.

        A player is considered unavailable if:
        - status is 'n' (not available) or 'u' (unknown/left club)
        - chance_of_playing_next_round is 0

        These are "forced transfers" - any available replacement is better than 0 points.

        Returns:
            List of unavailable player dicts with their details
        """
        unavailable = []

        for player in current_team:
            player_id = player.get('player_id')

            # Get current status from database
            player_info = self.db.execute_query("""
                SELECT id, web_name, element_type, now_cost, status,
                       chance_of_playing_next_round, news
                FROM players
                WHERE id = ?
            """, (player_id,))

            if not player_info:
                continue

            p = player_info[0]
            status = p.get('status', 'a')
            cop = p.get('chance_of_playing_next_round')

            # Check if unavailable
            is_unavailable = False
            reason = None

            if status in ('n', 'u'):
                is_unavailable = True
                reason = f"Status: {status}"
                if p.get('news'):
                    reason += f" - {p['news'][:50]}..."
            elif cop is not None and cop == 0:
                is_unavailable = True
                reason = f"0% chance of playing"
                if p.get('news'):
                    reason += f" - {p['news'][:50]}..."

            if is_unavailable:
                unavailable.append({
                    'player_id': player_id,
                    'web_name': p['web_name'],
                    'element_type': p['element_type'],
                    'now_cost': p['now_cost'],
                    'status': status,
                    'chance_of_playing': cop,
                    'reason': reason,
                    'position_in_team': player.get('position', 0)
                })

        return unavailable

    def get_forced_transfer_replacements(
        self,
        unavailable_player: Dict,
        current_team_ids: set,
        multi_gw_predictions: Dict[int, Dict[int, float]],
        current_gw: int,
        horizon: int,
        bank: float
    ) -> List[TransferOption]:
        """
        Find replacement options for an unavailable player.

        Unlike normal transfers, we don't apply strict xP thresholds here -
        ANY available player is better than someone who won't play.

        Returns:
            List of TransferOption objects, sorted by predicted points
        """
        position = unavailable_player['element_type']
        # Use actual selling_price if available (from current_team sync), else now_cost
        selling_price = unavailable_player.get('selling_price', unavailable_player['now_cost']) / 10.0
        max_price = selling_price + bank

        # Find available replacements
        replacements = self._find_replacements(
            position=position,
            current_team_ids=current_team_ids,
            max_price=max_price,
            multi_gw_predictions=multi_gw_predictions,
            current_gw=current_gw,
            horizon=horizon
        )

        if not replacements:
            return []

        # Create TransferOption objects
        transfer_options = []
        for replacement in replacements[:10]:  # Top 10 options
            gw_gains = []
            for gw in range(current_gw, current_gw + horizon):
                xp_out = 0.0  # Unavailable player = 0 points guaranteed
                xp_in = multi_gw_predictions.get(replacement['player_id'], {}).get(gw, 0.0)
                gw_gains.append((gw, xp_out, xp_in))

            total_gain = sum(xp_in for _, _, xp_in in gw_gains)  # All gain since out = 0
            avg_gain = total_gain / len(gw_gains) if gw_gains else 0

            option = TransferOption(
                position=position,
                position_name=POSITIONS[position],
                player_out_id=unavailable_player['player_id'],
                player_out_name=unavailable_player['web_name'],
                player_out_price=selling_price,
                player_in_id=replacement['player_id'],
                player_in_name=replacement['name'],
                player_in_price=replacement['price'],
                gw_predictions=gw_gains,
                total_gain=total_gain,
                avg_gain_per_gw=avg_gain,
                fixtures_out=[],
                fixtures_in=[],
                price_change_urgency='HIGH',  # Forced transfers are urgent
                alternatives_count=len(replacements)
            )
            transfer_options.append(option)

        # Sort by total expected points (not gain, since out player = 0)
        transfer_options.sort(key=lambda x: x.total_gain, reverse=True)

        return transfer_options

    def optimize_transfers(
        self,
        current_team: List[Dict],
        ml_predictions: Dict[int, float],  # player_id -> xP for multiple GWs
        current_gw: int,
        free_transfers: int = 1,
        bank: float = 0.0,
        horizon: int = 4,  # Look ahead N gameweeks
        ron_entry_id: Optional[int] = None,
        league_id: Optional[int] = None,
        strategy_context: Optional[Dict] = None  # Strategy from synthesis engine
    ) -> Dict:
        """
        Main optimization method.

        Returns comprehensive transfer analysis including:
        - Best transfer option for each position
        - Overall best transfer
        - Roll vs make recommendation
        - Full reasoning with visible data
        """

        # Store strategy context for ownership-based scoring
        self.strategy_context = strategy_context or {}
        risk_level = self.strategy_context.get('risk_level', 'MODERATE')

        if self.verbose:
            print("\n" + "="*80)
            print("TRANSFER OPTIMIZER - COMPREHENSIVE ANALYSIS")
            print("="*80)
            print(f"Current GW: {current_gw}")
            print(f"Analyzing GW {current_gw} through GW {current_gw + horizon - 1}")
            print(f"Free transfers: {free_transfers}")
            print(f"Bank: £{bank:.1f}m")
            if strategy_context:
                print(f"Strategy: {risk_level} ({strategy_context.get('approach', 'balanced')})")
                if risk_level == 'LOW':
                    print("  → Prioritizing template players (high ownership)")
                elif risk_level == 'BOLD':
                    print("  → Prioritizing differentials (low ownership)")

        # Step 1: Get multi-gameweek predictions for all players
        multi_gw_predictions = self._get_multi_gw_predictions(
            current_gw,
            horizon
        )

        # Step 1b: Check for unavailable players (FORCED transfers)
        unavailable_players = self.identify_unavailable_players(current_team)
        forced_transfers = []
        remaining_fts = free_transfers

        if unavailable_players and free_transfers > 0:
            if self.verbose:
                print(f"\n⚠️  FORCED TRANSFERS NEEDED: {len(unavailable_players)} unavailable player(s)")
                for up in unavailable_players:
                    print(f"   🚫 {up['web_name']} - {up['reason']}")

            current_team_ids = {p['player_id'] for p in current_team}

            for unavailable in unavailable_players:
                if remaining_fts <= 0:
                    if self.verbose:
                        print(f"\n   ⚠️  No FTs left for {unavailable['web_name']} - will remain in squad")
                    break

                # Find best replacement
                replacement_options = self.get_forced_transfer_replacements(
                    unavailable_player=unavailable,
                    current_team_ids=current_team_ids,
                    multi_gw_predictions=multi_gw_predictions,
                    current_gw=current_gw,
                    horizon=horizon,
                    bank=bank
                )

                if replacement_options:
                    best = replacement_options[0]
                    forced_transfers.append(best)
                    remaining_fts -= 1

                    # Update tracking for next iteration
                    current_team_ids.discard(unavailable['player_id'])
                    current_team_ids.add(best.player_in_id)
                    bank -= (best.player_in_price - best.player_out_price)

                    if self.verbose:
                        print(f"\n   ✓ FORCED: {best.player_out_name} → {best.player_in_name}")
                        print(f"     Reason: {unavailable['reason']}")
                        print(f"     Expected gain: +{best.total_gain:.1f}pts over {horizon} GWs")
                        print(f"     Remaining FTs: {remaining_fts}")
                else:
                    if self.verbose:
                        print(f"\n   ❌ No affordable replacement found for {unavailable['web_name']}")

        # Step 2: Evaluate transfer options for each position (with remaining FTs)
        position_options = {}

        for pos_id in [1, 2, 3, 4]:
            options = self._evaluate_position_transfers(
                current_team=current_team,
                position=pos_id,
                multi_gw_predictions=multi_gw_predictions,
                current_gw=current_gw,
                horizon=horizon,
                bank=bank
            )

            if options:
                position_options[pos_id] = options

        # Step 3: Rank all options across positions
        all_options = []
        for pos_id, options in position_options.items():
            all_options.extend(options[:3])  # Top 3 from each position

        all_options.sort(key=lambda x: x.total_gain, reverse=True)

        # Step 4: Chip decisions now handled by manager separately
        # TransferOptimizer focuses purely on transfer recommendations
        chip_recommendation = None

        # Step 5: Multi-transfer optimization with REMAINING FTs (after forced transfers)
        optional_transfers = []
        if remaining_fts > 1 and all_options:
            if self.verbose:
                print(f"\n📋 Optional Transfer Optimization ({remaining_fts} FTs remaining)...")

            optional_transfers = self.optimize_multi_transfers(
                all_options=all_options,
                free_transfers=remaining_fts,
                current_team=current_team,
                bank=bank,
                min_gain_threshold=1.5,  # Lower threshold when multiple FTs
                horizon=horizon
            )

            if self.verbose and optional_transfers:
                total_gain = sum(t.total_gain for t in optional_transfers)
                print(f"\n  📊 Optional transfer summary: {len(optional_transfers)} transfers "
                      f"for +{total_gain:.1f}pts total over {horizon} GWs")
        elif remaining_fts == 1 and all_options:
            # Single optional transfer - use position-specific threshold
            pos = all_options[0].position
            threshold = self.get_threshold_for_position(pos)
            if all_options[0].avg_gain_per_gw >= threshold:
                optional_transfers = [all_options[0]]

        # Combine forced + optional transfers
        recommended_transfers = forced_transfers + optional_transfers

        # Step 6: Make roll vs make decision
        if forced_transfers:
            # Forced transfers always happen
            if optional_transfers:
                total_gain = sum(t.total_gain for t in recommended_transfers)
                decision = {
                    'action': 'MAKE_MULTI',
                    'reasoning': (f'{len(forced_transfers)} forced + {len(optional_transfers)} optional transfers. '
                                 f'Total gain: +{total_gain:.1f}pts over {horizon} GWs.')
                }
            else:
                total_gain = sum(t.total_gain for t in forced_transfers)
                decision = {
                    'action': 'MAKE_MULTI' if len(forced_transfers) > 1 else 'MAKE',
                    'reasoning': (f'{len(forced_transfers)} forced transfer(s) for unavailable players. '
                                 f'Expected gain: +{total_gain:.1f}pts over {horizon} GWs.')
                }
        elif len(optional_transfers) > 1:
            total_gain = sum(t.total_gain for t in optional_transfers)
            decision = {
                'action': 'MAKE_MULTI',
                'reasoning': (f'{len(optional_transfers)} transfers recommended using '
                             f'{remaining_fts} FTs. Total gain: +{total_gain:.1f}pts over '
                             f'{horizon} GWs.')
            }
        elif optional_transfers:
            decision = {
                'action': 'MAKE',
                'reasoning': f'Transfer gains +{optional_transfers[0].total_gain:.1f}pts over {horizon} GWs.'
            }
        elif remaining_fts < 2:
            decision = {
                'action': 'ROLL',
                'reasoning': 'No transfers meet minimum threshold. Rolling FT.'
            }
        else:
            decision = {
                'action': 'ROLL',
                'reasoning': f'Have {remaining_fts} FTs but no transfers meet threshold.'
            }

        # Step 7: Format output
        result = {
            'recommendation': decision['action'],  # 'MAKE', 'MAKE_MULTI', 'ROLL', or 'CHIP'
            'best_transfer': all_options[0] if all_options else None,
            'recommended_transfers': recommended_transfers,  # Forced + optional transfers
            'forced_transfers': forced_transfers,  # Just the forced ones
            'optional_transfers': optional_transfers,  # Just the optional ones
            'top_3_transfers': all_options[:3],
            'by_position': position_options,
            'reasoning': decision['reasoning'],
            'chip_recommendation': chip_recommendation,
            'free_transfers': free_transfers,
            'remaining_fts_after_forced': remaining_fts,
            'transfers_to_make': len(recommended_transfers),
            'unavailable_players': unavailable_players,
            'data_visible': True
        }

        if self.verbose:
            self._print_analysis(result, current_gw, horizon)

        return result

    def _get_multi_gw_predictions(
        self,
        start_gw: int,
        horizon: int
    ) -> Dict[int, Dict[int, float]]:
        """
        Get ML predictions for multiple gameweeks.

        Returns:
            Dict[player_id, Dict[gw, xp]]

        For now, we'll run predictions for each GW separately.
        In production, this should be cached/pre-computed.
        """

        from agents.synthesis.engine import DecisionSynthesisEngine

        engine = DecisionSynthesisEngine(self.db)

        predictions_by_gw = {}

        if self.verbose:
            print(f"\n📊 Generating ML predictions for GW{start_gw} to GW{start_gw + horizon - 1}...")

        for gw in range(start_gw, start_gw + horizon):
            # Run ML predictions for this GW
            recs = engine.synthesize_recommendations(gameweek=gw)

            # Extract predictions
            gw_preds = {}
            for player in recs['top_players']:
                gw_preds[player['player_id']] = player['xp']

            predictions_by_gw[gw] = gw_preds

            if self.verbose:
                print(f"  GW{gw}: {len(gw_preds)} player predictions")

        # Restructure to player_id -> {gw -> xp}
        multi_gw = {}
        all_player_ids = set()
        for gw_preds in predictions_by_gw.values():
            all_player_ids.update(gw_preds.keys())

        for player_id in all_player_ids:
            multi_gw[player_id] = {}
            for gw, gw_preds in predictions_by_gw.items():
                multi_gw[player_id][gw] = gw_preds.get(player_id, 0.0)

        return multi_gw

    def _evaluate_position_transfers(
        self,
        current_team: List[Dict],
        position: int,
        multi_gw_predictions: Dict[int, Dict[int, float]],
        current_gw: int,
        horizon: int,
        bank: float
    ) -> List[TransferOption]:
        """
        Evaluate all transfer options for a specific position.

        Returns top N transfer options ranked by total gain.
        """

        pos_name = POSITIONS[position]

        # Get current players in this position
        pos_players = [p for p in current_team if p['element_type'] == position]

        if not pos_players:
            return []

        # Find weakest players in this position
        pos_players_with_value = []
        for p in pos_players:
            # Calculate average xP over horizon
            avg_xp = sum(
                multi_gw_predictions.get(p['player_id'], {}).get(gw, 0.0)
                for gw in range(current_gw, current_gw + horizon)
            ) / horizon

            pos_players_with_value.append({
                **p,
                'avg_xp': avg_xp,
                'value_score': avg_xp / (p['now_cost'] / 10.0) if p['now_cost'] > 0 else 0
            })

        # Sort by value_score BUT exclude high-performing premiums
        # Don't treat premiums with xP > 5.0 as "weak" regardless of value_score
        # They serve different purpose (captain options, consistent high scores)
        weak_candidates = [
            p for p in pos_players_with_value
            if p['avg_xp'] < 5.0  # Only consider truly underperforming players
        ]
        weak_candidates.sort(key=lambda x: x['value_score'])

        # If no truly weak players, consider lowest value_score players anyway
        if not weak_candidates:
            weak_candidates = sorted(pos_players_with_value, key=lambda x: x['value_score'])

        # Consider replacing bottom 2 weak players
        transfer_options = []

        for weak_player in weak_candidates[:2]:
            # Find replacements - use selling_price for budget calculation
            weak_selling_price = weak_player.get('selling_price', weak_player['now_cost']) / 10.0
            max_price = weak_selling_price + bank + 1.0  # Can upgrade by bank + £1m

            replacements = self._find_replacements(
                position=position,
                current_team_ids={p['player_id'] for p in current_team},
                max_price=max_price,
                multi_gw_predictions=multi_gw_predictions,
                current_gw=current_gw,
                horizon=horizon
            )

            # Create TransferOption objects
            for replacement in replacements[:10]:  # Top 10 per weak player
                # Calculate gain per gameweek
                gw_gains = []
                for gw in range(current_gw, current_gw + horizon):
                    xp_out = multi_gw_predictions.get(weak_player['player_id'], {}).get(gw, 0.0)
                    xp_in = multi_gw_predictions.get(replacement['player_id'], {}).get(gw, 0.0)
                    gw_gains.append((gw, xp_out, xp_in))

                total_gain = sum(xp_in - xp_out for _, xp_out, xp_in in gw_gains)
                avg_gain = total_gain / len(gw_gains)

                # Get fixtures (stub for now - would query fixtures table)
                fixtures_out = []
                fixtures_in = []

                # Price change urgency (stub for now - would query price predictions)
                urgency = 'LOW'

                option = TransferOption(
                    position=position,
                    position_name=pos_name,
                    player_out_id=weak_player['player_id'],
                    player_out_name=weak_player['web_name'],
                    player_out_price=weak_selling_price,
                    player_in_id=replacement['player_id'],
                    player_in_name=replacement['name'],
                    player_in_price=replacement['price'],
                    gw_predictions=gw_gains,
                    total_gain=total_gain,
                    avg_gain_per_gw=avg_gain,
                    fixtures_out=fixtures_out,
                    fixtures_in=fixtures_in,
                    price_change_urgency=urgency,
                    alternatives_count=len(replacements)
                )

                transfer_options.append(option)

        # Sort by total gain
        transfer_options.sort(key=lambda x: x.total_gain, reverse=True)

        return transfer_options

    def _find_replacements(
        self,
        position: int,
        current_team_ids: set,
        max_price: float,
        multi_gw_predictions: Dict[int, Dict[int, float]],
        current_gw: int,
        horizon: int
    ) -> List[Dict]:
        """Find replacement players for a position within budget."""

        # Get all available players in this position
        # CRITICAL: Filter out injured ('i'), suspended ('s'), and unavailable ('u')
        # Only include available ('a') or doubtful ('d') with reasonable chance
        all_players = self.db.execute_query("""
            SELECT id, web_name, element_type, now_cost, selected_by_percent,
                   status, chance_of_playing_next_round
            FROM players
            WHERE element_type = ?
            AND status IN ('a', 'd')
            AND (chance_of_playing_next_round IS NULL OR chance_of_playing_next_round >= 50)
            AND id NOT IN ({})
            AND now_cost <= ?
        """.format(','.join('?' * len(current_team_ids))),
            (position, *current_team_ids, int(max_price * 10))
        )

        # Calculate average xP for each over horizon
        # Apply ownership-based strategy multiplier
        risk_level = getattr(self, 'strategy_context', {}).get('risk_level', 'MODERATE')

        replacements = []
        for player in all_players:
            avg_xp = sum(
                multi_gw_predictions.get(player['id'], {}).get(gw, 0.0)
                for gw in range(current_gw, current_gw + horizon)
            ) / horizon

            total_xp = sum(
                multi_gw_predictions.get(player['id'], {}).get(gw, 0.0)
                for gw in range(current_gw, current_gw + horizon)
            )

            ownership = float(player['selected_by_percent'] or 0)

            # Apply ownership-based strategy multiplier to scoring
            # This affects ranking, not the actual xP predictions
            strategy_multiplier = 1.0
            if risk_level == 'LOW':
                # Leading: boost template players (>50% ownership)
                if ownership >= 50:
                    strategy_multiplier = 1.15  # 15% boost for safe template picks
                elif ownership < 20:
                    strategy_multiplier = 0.9   # 10% penalty for risky differentials
            elif risk_level == 'BOLD':
                # Chasing: boost differentials (<20% ownership)
                if ownership < 20:
                    strategy_multiplier = 1.20  # 20% boost for differentials
                elif ownership >= 50:
                    strategy_multiplier = 0.95  # 5% penalty for boring template
            # MODERATE/MODERATE-HIGH: no ownership adjustment (balanced)

            adjusted_xp = total_xp * strategy_multiplier

            replacements.append({
                'player_id': player['id'],
                'name': player['web_name'],
                'price': player['now_cost'] / 10.0,
                'avg_xp': avg_xp,
                'total_xp': total_xp,
                'adjusted_xp': adjusted_xp,  # Strategy-adjusted score
                'ownership': ownership,
                'strategy_multiplier': strategy_multiplier
            })

        # Sort by strategy-adjusted xP (considers ownership based on strategy)
        replacements.sort(key=lambda x: x['adjusted_xp'], reverse=True)

        return replacements

    def _decide_roll_vs_make(
        self,
        best_option: Optional[TransferOption],
        free_transfers: int,
        current_gw: int
    ) -> Dict:
        """
        Decide whether to make a transfer or roll.

        Decision logic:
        - If no good options: ROLL
        - If best option avg < 2pts/GW: ROLL (not worth it)
        - If best option avg >= 2pts/GW and free transfer: MAKE
        - If best option avg >= 4pts/GW: MAKE (even for -4 hit)
        - Consider chip timing
        """

        if not best_option:
            return {
                'action': 'ROLL',
                'reasoning': 'No beneficial transfer options found'
            }

        avg_gain = best_option.avg_gain_per_gw
        threshold = self.get_threshold_for_position(best_option.position)

        # Not worth a free transfer
        if avg_gain < threshold:
            return {
                'action': 'ROLL',
                'reasoning': (f'Best option only gains {avg_gain:.1f}pts/GW '
                             f'(threshold: {threshold:.1f}pts/GW). Roll to build 2FT.')
            }

        # Worth a free transfer
        if free_transfers >= 1 and avg_gain >= threshold:
            return {
                'action': 'MAKE',
                'reasoning': (f'Best option gains {avg_gain:.1f}pts/GW '
                             f'({best_option.total_gain:.1f}pts total). '
                             f'Good value for free transfer.')
            }

        # Worth a hit (-4 points)
        if free_transfers == 0 and avg_gain >= 4.0:
            return {
                'action': 'MAKE',
                'reasoning': (f'Best option gains {avg_gain:.1f}pts/GW '
                             f'({best_option.total_gain:.1f}pts total). '
                             f'Worth taking -4 hit.')
            }

        # Default: roll
        return {
            'action': 'ROLL',
            'reasoning': (f'Best option gains {avg_gain:.1f}pts/GW but have '
                         f'{free_transfers} free transfers. Not urgent enough.')
        }

    def optimize_multi_transfers(
        self,
        all_options: List[TransferOption],
        free_transfers: int,
        current_team: List[Dict],
        bank: float,
        min_gain_threshold: float = 1.5,  # Minimum pts/GW to be worth a transfer
        horizon: int = 4
    ) -> List[TransferOption]:
        """
        Greedy multi-transfer optimization when FT > 1.

        Strategy:
        1. Start with best single transfer
        2. Remove conflicting options (same player out)
        3. Update budget after each transfer
        4. Repeat until FTs exhausted or no good options remain

        Args:
            all_options: All ranked transfer options
            free_transfers: Number of free transfers available
            current_team: Current squad
            bank: Current budget
            min_gain_threshold: Minimum avg gain per GW to make transfer
            horizon: Planning horizon (GWs)

        Returns:
            List of recommended transfers (up to free_transfers count)
        """
        if not all_options or free_transfers < 1:
            return []

        recommended = []
        remaining_budget = bank
        used_player_out_ids = set()  # Track players already transferred out
        used_player_in_ids = set()   # Track players already transferred in

        # Get current squad player IDs
        current_player_ids = {p['player_id'] for p in current_team}

        for _ in range(free_transfers):
            # Find best valid option
            best_option = None

            for opt in all_options:
                # Skip if player already being transferred out
                if opt.player_out_id in used_player_out_ids:
                    continue

                # Skip if player already being transferred in
                if opt.player_in_id in used_player_in_ids:
                    continue

                # Skip if player in already in squad (and not being transferred out)
                if opt.player_in_id in current_player_ids and opt.player_in_id not in used_player_out_ids:
                    continue

                # Check budget (player out sale price - player in cost)
                net_cost = opt.player_in_price - opt.player_out_price
                if net_cost > remaining_budget:
                    continue

                # Check if gain meets threshold
                if opt.avg_gain_per_gw < min_gain_threshold:
                    continue

                best_option = opt
                break

            if best_option is None:
                # No more valid options
                break

            # Add to recommended list
            recommended.append(best_option)

            # Update state
            used_player_out_ids.add(best_option.player_out_id)
            used_player_in_ids.add(best_option.player_in_id)
            remaining_budget -= (best_option.player_in_price - best_option.player_out_price)

            if self.verbose:
                print(f"  ✓ Transfer {len(recommended)}/{free_transfers}: "
                      f"{best_option.player_out_name} → {best_option.player_in_name} "
                      f"(+{best_option.total_gain:.1f}pts, remaining budget: £{remaining_budget:.1f}m)")

        return recommended

    def _print_analysis(self, result: Dict, current_gw: int, horizon: int):
        """Print comprehensive transfer analysis."""

        # Print forced transfers first if any
        forced = result.get('forced_transfers', [])
        if forced:
            print("\n" + "="*80)
            print("⚠️  FORCED TRANSFERS (Unavailable Players)")
            print("="*80)
            for i, ft in enumerate(forced, 1):
                print(f"\n{i}. {ft.position_name}: {ft.player_out_name} → {ft.player_in_name}")
                print(f"   Reason: Player unavailable (0 points guaranteed)")
                print(f"   Price: £{ft.player_out_price:.1f}m → £{ft.player_in_price:.1f}m")
                print(f"   Expected points from replacement: +{ft.total_gain:.1f} over {horizon} GWs")

        print("\n" + "="*80)
        print(f"TRANSFER OPTIONS BY POSITION (GW{current_gw}-{current_gw+horizon-1})")
        print("="*80)

        by_position = result['by_position']

        for pos_id in [1, 2, 3, 4]:
            if pos_id not in by_position:
                continue

            options = by_position[pos_id]
            print(f"\n{POSITIONS[pos_id]} - Top 5 Transfer Options:")
            print(f"{'#':<3} {'OUT':<18} {'→'} {'IN':<18} {'Total':>8} {'Avg/GW':>8} {'GW Detail'}")
            print("-"*80)

            for i, opt in enumerate(options[:5], 1):
                gw_detail = ', '.join([f"GW{gw}:{xp_in-xp_out:+.1f}"
                                      for gw, xp_out, xp_in in opt.gw_predictions])
                print(f"{i:<3} {opt.player_out_name:<18} → {opt.player_in_name:<18} "
                      f"{opt.total_gain:>+7.1f}pt {opt.avg_gain_per_gw:>+7.1f}pt")
                print(f"    {gw_detail}")

        print("\n" + "="*80)
        print("TOP 3 TRANSFERS (ALL POSITIONS)")
        print("="*80)

        for i, opt in enumerate(result['top_3_transfers'], 1):
            print(f"\n{i}. {opt.position_name}: {opt.player_out_name} → {opt.player_in_name}")
            print(f"   Price: £{opt.player_out_price:.1f}m → £{opt.player_in_price:.1f}m")
            print(f"   Total gain: {opt.total_gain:+.1f} points over {len(opt.gw_predictions)} GWs")
            print(f"   Average: {opt.avg_gain_per_gw:+.1f} pts/GW")
            print(f"   Gameweek breakdown:")
            for gw, xp_out, xp_in in opt.gw_predictions:
                print(f"     GW{gw}: {xp_out:.1f} → {xp_in:.1f} ({xp_in-xp_out:+.1f})")
            print(f"   Alternatives: {opt.alternatives_count} other options in position")

        # Note: Chip decisions are now handled separately by ChipStrategyService
        # via the manager agent, not by the transfer optimizer

        print("\n" + "="*80)
        print("RECOMMENDATION")
        print("="*80)

        print(f"\nAction: {result['recommendation']}")
        print(f"Reasoning: {result['reasoning']}")

        if result['recommendation'] == 'MAKE_MULTI' and result.get('recommended_transfers'):
            transfers = result['recommended_transfers']
            total_gain = sum(t.total_gain for t in transfers)
            print(f"\nExecute {len(transfers)} Transfers (using {result.get('free_transfers', len(transfers))} FTs):")
            for i, t in enumerate(transfers, 1):
                print(f"\n  Transfer {i}:")
                print(f"    OUT: {t.player_out_name} (£{t.player_out_price:.1f}m)")
                print(f"    IN:  {t.player_in_name} (£{t.player_in_price:.1f}m)")
                print(f"    Gain: {t.total_gain:+.1f}pts over {len(t.gw_predictions)} GWs ({t.avg_gain_per_gw:+.1f}/GW)")
            print(f"\n  Total Expected Gain: {total_gain:+.1f} points")

        elif result['recommendation'] == 'MAKE' and result['best_transfer']:
            best = result['best_transfer']
            print(f"\nExecute Transfer:")
            print(f"  OUT: {best.player_out_name} ({best.position_name})")
            print(f"  IN:  {best.player_in_name} ({best.position_name})")
            print(f"  Expected value: {best.total_gain:+.1f} points over {len(best.gw_predictions)} gameweeks")

            # Show chip alternative if available
            if result.get('chip_recommendation'):
                chip_rec = result['chip_recommendation']
                if chip_rec['all_chip_options']:
                    print(f"\n  Alternative: Could use {chip_rec['best_chip']['chip_name']} "
                          f"for {chip_rec['chip_ev']:.1f}pts instead")
