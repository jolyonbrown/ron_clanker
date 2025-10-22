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
from intelligence.chip_strategy import ChipStrategyAnalyzer

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

    def __init__(self, database: Database, chip_strategy: Optional[ChipStrategyAnalyzer] = None):
        self.db = database
        self.chip_strategy = chip_strategy
        self.verbose = True  # Always show data for transparency
        logger.info("TransferOptimizer initialized")

    def optimize_transfers(
        self,
        current_team: List[Dict],
        ml_predictions: Dict[int, float],  # player_id -> xP for multiple GWs
        current_gw: int,
        free_transfers: int = 1,
        bank: float = 0.0,
        horizon: int = 4,  # Look ahead N gameweeks
        ron_entry_id: Optional[int] = None,
        league_id: Optional[int] = None
    ) -> Dict:
        """
        Main optimization method.

        Returns comprehensive transfer analysis including:
        - Best transfer option for each position
        - Overall best transfer
        - Roll vs make recommendation
        - Full reasoning with visible data
        """

        if self.verbose:
            print("\n" + "="*80)
            print("TRANSFER OPTIMIZER - COMPREHENSIVE ANALYSIS")
            print("="*80)
            print(f"Current GW: {current_gw}")
            print(f"Analyzing GW {current_gw} through GW {current_gw + horizon - 1}")
            print(f"Free transfers: {free_transfers}")
            print(f"Bank: £{bank:.1f}m")

        # Step 1: Get multi-gameweek predictions for all players
        multi_gw_predictions = self._get_multi_gw_predictions(
            current_gw,
            horizon
        )

        # Step 2: Evaluate transfer options for each position
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

        # Step 4: Get chip recommendations (if chip_strategy available)
        chip_recommendation = None
        if self.chip_strategy and ron_entry_id and league_id:
            chip_recommendation = self._evaluate_chip_vs_transfer(
                current_gw=current_gw,
                ron_entry_id=ron_entry_id,
                league_id=league_id,
                best_transfer_option=all_options[0] if all_options else None,
                current_team=current_team,
                horizon=horizon
            )

        # Step 5: Make roll vs make vs chip decision
        decision = self._decide_roll_vs_make_vs_chip(
            best_option=all_options[0] if all_options else None,
            free_transfers=free_transfers,
            current_gw=current_gw,
            chip_recommendation=chip_recommendation
        )

        # Step 6: Format output
        result = {
            'recommendation': decision['action'],  # 'MAKE', 'ROLL', or 'CHIP'
            'best_transfer': all_options[0] if all_options else None,
            'top_3_transfers': all_options[:3],
            'by_position': position_options,
            'reasoning': decision['reasoning'],
            'chip_recommendation': chip_recommendation,
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

        pos_players_with_value.sort(key=lambda x: x['value_score'])

        # Consider replacing bottom 2 players
        transfer_options = []

        for weak_player in pos_players_with_value[:2]:
            # Find replacements
            max_price = weak_player['now_cost'] / 10.0 + bank + 1.0  # Can upgrade by bank + £1m

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
                    player_out_price=weak_player['now_cost'] / 10.0,
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
        all_players = self.db.execute_query("""
            SELECT id, web_name, element_type, now_cost, selected_by_percent
            FROM players
            WHERE element_type = ?
            AND status != 'u'
            AND id NOT IN ({})
            AND now_cost <= ?
        """.format(','.join('?' * len(current_team_ids))),
            (position, *current_team_ids, int(max_price * 10))
        )

        # Calculate average xP for each over horizon
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

            replacements.append({
                'player_id': player['id'],
                'name': player['web_name'],
                'price': player['now_cost'] / 10.0,
                'avg_xp': avg_xp,
                'total_xp': total_xp,
                'ownership': float(player['selected_by_percent'] or 0)
            })

        # Sort by total xP over horizon
        replacements.sort(key=lambda x: x['total_xp'], reverse=True)

        return replacements

    def _evaluate_chip_vs_transfer(
        self,
        current_gw: int,
        ron_entry_id: int,
        league_id: int,
        best_transfer_option: Optional[TransferOption],
        current_team: List[Dict],
        horizon: int
    ) -> Optional[Dict]:
        """
        Evaluate chip usage vs transfer options.

        Returns chip recommendation with expected value comparison.
        """

        # Get all chip recommendations from ChipStrategyAnalyzer
        wc_recs = self.chip_strategy.recommend_wildcard_timing(current_gw, ron_entry_id)
        bb_recs = self.chip_strategy.recommend_bench_boost(current_gw, ron_entry_id)
        tc_recs = self.chip_strategy.recommend_triple_captain(current_gw, ron_entry_id)

        # Evaluate each chip type
        chip_options = []

        # Wildcard evaluation
        for wc_name, wc_rec in wc_recs.items():
            if wc_rec['recommendation'] in ['URGENT', 'CONSIDER', 'USE NOW']:
                # Estimate wildcard value
                # Rough heuristic: count weak players (< 3.0 xP/GW avg)
                weak_players = sum(1 for p in current_team if p.get('avg_xp', 5.0) < 3.0)

                # Wildcard value = weak_players * 3pts/GW * horizon
                wc_expected_value = weak_players * 3.0 * horizon

                chip_options.append({
                    'chip_type': 'wildcard',
                    'chip_number': 1 if '1' in wc_name else 2,
                    'chip_name': wc_name.replace('_', ' ').title(),
                    'expected_value': wc_expected_value,
                    'recommendation': wc_rec['recommendation'],
                    'reason': wc_rec['reason'],
                    'action_type': 'DEFER_TRANSFERS',
                    'urgency': wc_rec['recommendation']
                })

        # Bench Boost evaluation
        for bb_name, bb_rec in bb_recs.items():
            if bb_rec['status'] == 'AVAILABLE':
                # BB value: avg bench xP for this GW
                # For now, conservative estimate: 10 points from bench
                bb_expected_value = 10.0

                chip_options.append({
                    'chip_type': 'bench_boost',
                    'chip_number': 1 if '1' in bb_name else 2,
                    'chip_name': bb_name.replace('_', ' ').title(),
                    'expected_value': bb_expected_value,
                    'recommendation': bb_rec['recommendation'],
                    'reason': bb_rec.get('optimal_use', 'Use when bench is strong'),
                    'action_type': 'COORDINATE',
                    'urgency': 'LOW'
                })

        # Triple Captain evaluation
        for tc_name, tc_rec in tc_recs.items():
            if tc_rec['status'] == 'AVAILABLE':
                # TC value: double captain points
                # Conservative: 15 extra points from premium captain
                tc_expected_value = 15.0

                chip_options.append({
                    'chip_type': 'triple_captain',
                    'chip_number': 1 if '1' in tc_name else 2,
                    'chip_name': tc_name.replace('_', ' ').title(),
                    'expected_value': tc_expected_value,
                    'recommendation': tc_rec['recommendation'],
                    'reason': tc_rec.get('optimal_use', 'Use on premium player DGW'),
                    'action_type': 'COORDINATE',
                    'urgency': 'LOW'
                })

        if not chip_options:
            return None

        # Sort by expected value
        chip_options.sort(key=lambda x: x['expected_value'], reverse=True)

        best_chip = chip_options[0]

        # Compare with best transfer
        transfer_ev = best_transfer_option.total_gain if best_transfer_option else 0.0

        return {
            'best_chip': best_chip,
            'all_chip_options': chip_options,
            'chip_ev': best_chip['expected_value'],
            'transfer_ev': transfer_ev,
            'chip_wins': best_chip['expected_value'] > transfer_ev,
            'ev_difference': best_chip['expected_value'] - transfer_ev
        }

    def _decide_roll_vs_make_vs_chip(
        self,
        best_option: Optional[TransferOption],
        free_transfers: int,
        current_gw: int,
        chip_recommendation: Optional[Dict]
    ) -> Dict:
        """
        Decide whether to make a transfer, roll, or use a chip.

        Decision hierarchy:
        1. Check if chip recommended with higher EV than transfer
        2. If Wildcard/Free Hit urgent: DEFER transfers, use chip
        3. If BB/TC available: COORDINATE with transfers
        4. Otherwise: normal roll vs make logic
        """

        # Check chip recommendation first
        if chip_recommendation and chip_recommendation['chip_wins']:
            best_chip = chip_recommendation['best_chip']

            # Wildcard/Free Hit: DEFER all transfers
            if best_chip['action_type'] == 'DEFER_TRANSFERS':
                return {
                    'action': 'CHIP',
                    'chip_type': best_chip['chip_type'],
                    'chip_number': best_chip['chip_number'],
                    'chip_name': best_chip['chip_name'],
                    'reasoning': (
                        f"{best_chip['chip_name']} recommended: {best_chip['reason']}\n"
                        f"Expected value: {best_chip['expected_value']:.1f}pts "
                        f"vs {chip_recommendation['transfer_ev']:.1f}pts from transfer.\n"
                        f"DEFER transfers and rebuild team."
                    )
                }

            # BB/TC: Mention as alternative
            elif best_chip['action_type'] == 'COORDINATE':
                # Don't override transfer, but show chip as option
                pass

        # Normal roll vs make logic (from original method)
        if not best_option:
            return {
                'action': 'ROLL',
                'reasoning': 'No beneficial transfer options found'
            }

        avg_gain = best_option.avg_gain_per_gw

        # Not worth a free transfer
        if avg_gain < 2.0:
            return {
                'action': 'ROLL',
                'reasoning': (f'Best option only gains {avg_gain:.1f}pts/GW '
                             f'(threshold: 2.0pts/GW). Roll to build 2FT.')
            }

        # Worth a free transfer
        if free_transfers >= 1 and avg_gain >= 2.0:
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

        # Not worth a free transfer
        if avg_gain < 2.0:
            return {
                'action': 'ROLL',
                'reasoning': (f'Best option only gains {avg_gain:.1f}pts/GW '
                             f'(threshold: 2.0pts/GW). Roll to build 2FT.')
            }

        # Worth a free transfer
        if free_transfers >= 1 and avg_gain >= 2.0:
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

    def _print_analysis(self, result: Dict, current_gw: int, horizon: int):
        """Print comprehensive transfer analysis."""

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

        # Show chip analysis if available
        if result.get('chip_recommendation'):
            chip_rec = result['chip_recommendation']
            print("\n" + "="*80)
            print("CHIP VS TRANSFER ANALYSIS")
            print("="*80)

            best_chip = chip_rec['best_chip']
            print(f"\n🎯 Best Chip Option: {best_chip['chip_name']}")
            print(f"   Expected Value: {chip_rec['chip_ev']:.1f} points")
            print(f"   Reason: {best_chip['reason']}")
            print(f"   Action Type: {best_chip['action_type']}")

            print(f"\n📊 Best Transfer Option: ", end="")
            if result['best_transfer']:
                print(f"{result['best_transfer'].player_out_name} → {result['best_transfer'].player_in_name}")
                print(f"   Expected Value: {chip_rec['transfer_ev']:.1f} points")
            else:
                print("None available")
                print(f"   Expected Value: 0.0 points")

            print(f"\n⚖️  Comparison:")
            if chip_rec['chip_wins']:
                print(f"   CHIP WINS by {chip_rec['ev_difference']:+.1f} points")
            else:
                print(f"   TRANSFER WINS by {-chip_rec['ev_difference']:+.1f} points")

            # Show all chip options
            if len(chip_rec['all_chip_options']) > 1:
                print(f"\n   Other chip options:")
                for chip in chip_rec['all_chip_options'][1:]:
                    print(f"   - {chip['chip_name']}: {chip['expected_value']:.1f}pts ({chip['recommendation']})")

        print("\n" + "="*80)
        print("RECOMMENDATION")
        print("="*80)

        print(f"\nAction: {result['recommendation']}")
        print(f"Reasoning: {result['reasoning']}")

        if result['recommendation'] == 'CHIP':
            chip_rec = result.get('chip_recommendation')
            if chip_rec:
                best_chip = chip_rec['best_chip']
                print(f"\nExecute Chip:")
                print(f"  Chip: {best_chip['chip_name']}")
                print(f"  Type: {best_chip['chip_type']}")
                print(f"  Expected value: {best_chip['expected_value']:.1f} points")
                print(f"  Next steps: {best_chip.get('reason', 'Rebuild team')}")

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
