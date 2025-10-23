"""
Manager Agent - Ron Clanker

The central decision-maker. Coordinates all specialist agents and makes
final autonomous decisions on team selection, transfers, and chip usage.
"""

from typing import Dict, List, Any, Optional, Tuple
import logging
from datetime import datetime

from rules.rules_engine import RulesEngine
from agents.data_collector import DataCollector
from agents.player_valuation import PlayerValuationAgent
from agents.synthesis.engine import DecisionSynthesisEngine
from agents.transfer_optimizer import TransferOptimizer
from intelligence.chip_strategy import ChipStrategyAnalyzer
from ron_clanker.persona import RonClanker
from data.database import Database
from utils.gameweek import get_current_gameweek

logger = logging.getLogger(__name__)


class ManagerAgent:
    """
    Ron Clanker - The Gaffer

    Central orchestrator for all FPL decisions. Coordinates specialist agents
    and makes final autonomous choices.

    Phase 1 Capabilities:
    - Select valid team within budget
    - Make weekly transfers based on value analysis
    - Choose captain based on expected points
    - Validate all decisions against FPL rules
    - Communicate in Ron Clanker's persona
    """

    def __init__(
        self,
        database: Optional[Database] = None,
        data_collector: Optional[DataCollector] = None,
        use_ml: bool = True
    ):
        """Initialize the Manager Agent."""
        self.db = database or Database()
        self.data_collector = data_collector or DataCollector()
        self.rules_engine = RulesEngine()
        self.valuation_agent = PlayerValuationAgent()
        self.ron = RonClanker()

        # ML-powered Decision Synthesis Engine (NEW!)
        self.use_ml = use_ml
        if use_ml:
            try:
                self.synthesis_engine = DecisionSynthesisEngine(database=self.db)

                # Initialize chip strategy analyzer
                # Note: We need league_intel_service, but for now we'll pass None
                # and handle it gracefully in the optimizer
                self.chip_strategy = ChipStrategyAnalyzer(
                    database=self.db,
                    league_intel_service=None  # Will be set when available
                )

                self.transfer_optimizer = TransferOptimizer(
                    database=self.db,
                    chip_strategy=self.chip_strategy
                )
                logger.info("Decision Synthesis Engine loaded - ML predictions ENABLED")
                logger.info("Transfer Optimizer loaded - Multi-GW transfer analysis ENABLED")
                logger.info("Chip Strategy Analyzer loaded - Chip vs transfer comparison ENABLED")
            except Exception as e:
                logger.warning(f"Could not load synthesis engine: {e}. Falling back to basic valuation.")
                self.synthesis_engine = None
                self.transfer_optimizer = None
                self.chip_strategy = None
                self.use_ml = False
        else:
            self.synthesis_engine = None
            self.transfer_optimizer = None
            self.chip_strategy = None

        self.current_team = None
        self.available_budget = 0
        self.free_transfers = 1
        self.chips_used = []

        logger.info("Ron Clanker initialized. Ready to manage.")

    # ========================================================================
    # TEAM SELECTION
    # ========================================================================

    async def select_initial_team(
        self,
        budget: int = 1000  # £100m
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Select initial 15-player squad at start of season.

        Phase 1 Strategy:
        - Build balanced team with mix of premium and budget players
        - Prioritize value (points per million)
        - Exploit defensive contribution potential
        - Ensure valid formation and budget compliance

        Returns:
            (team, announcement)
        """
        logger.info("Ron Clanker is selecting the squad...")

        # Get all player data
        fpl_data = await self.data_collector.update_all_data()
        all_players = fpl_data['players']

        # Rank all players by value
        ranked_players = self.valuation_agent.rank_players_by_value(
            all_players,
            include_dc_boost=True
        )

        # Build squad using budget optimization
        team = self._build_optimal_squad(ranked_players, budget)

        # Validate team
        is_valid, message = self.rules_engine.validate_team(team)
        if not is_valid:
            logger.error(f"Team validation failed: {message}")
            raise ValueError(f"Invalid team: {message}")

        # Set captain (highest expected points in starting XI)
        team = self._assign_captain(team)

        # Save to database
        self.current_team = team
        self.db.set_team(1, team)  # GW1

        # Generate announcement
        reasoning = {
            'strategy': "Balanced approach. Mix of premium attackers and value defenders.",
            'defensive_contribution_focus': (
                "Prioritizing defenders and midfielders who'll earn defensive contribution points. "
                "Most managers will miss this - that's our edge."
            )
        }

        announcement = self.ron.announce_team_selection(team, 1, reasoning)

        logger.info(f"Team selected. Total cost: {sum(p['now_cost'] for p in team)/10:.1f}m")

        return team, announcement

    def _build_optimal_squad(
        self,
        ranked_players: List[Dict[str, Any]],
        budget: int
    ) -> List[Dict[str, Any]]:
        """
        Build optimal 15-player squad within budget.

        Phase 1 approach: Greedy algorithm with position constraints.
        """
        team = []
        spent = 0

        # Target allocation (total 15 players)
        position_targets = {
            1: 2,  # 2 GK
            2: 5,  # 5 DEF
            3: 5,  # 5 MID
            4: 3   # 3 FWD
        }

        position_filled = {1: 0, 2: 0, 3: 0, 4: 0}

        # Reserve budget for each position
        position_budget = {
            1: 90,   # £9.0m for 2 GKs (avg 4.5m each)
            2: 250,  # £25.0m for 5 DEFs (avg 5.0m each)
            3: 400,  # £40.0m for 5 MIDs (avg 8.0m each)
            4: 260   # £26.0m for 3 FWDs (avg 8.7m each)
        }

        # Fill each position
        for position in [4, 3, 2, 1]:  # Fill forwards first (most expensive)
            target = position_targets[position]
            pos_budget = position_budget[position]

            # Get best players for this position within budget
            position_players = [
                p for p in ranked_players
                if p['element_type'] == position and
                p['now_cost'] <= pos_budget and
                p['id'] not in [t['id'] for t in team]
            ]

            # Select top players for this position
            selected = []
            pos_spent = 0

            for player in position_players:
                if len(selected) >= target:
                    break

                player_cost = player['now_cost']

                # Check team constraint (max 3 from same team)
                team_count = sum(1 for p in team if p.get('team_id') == player.get('team_id'))
                if team_count >= 3:
                    continue

                if pos_spent + player_cost <= pos_budget:
                    selected.append(player)
                    pos_spent += player_cost

            team.extend(selected)
            spent += pos_spent
            position_filled[position] = len(selected)

        # Assign positions (1-11 starting, 12-15 bench)
        team = self._assign_positions(team)

        # Add purchase and selling prices
        for player in team:
            player['purchase_price'] = player['now_cost']
            player['selling_price'] = player['now_cost']

        return team

    def _assign_positions(self, team: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Assign positions 1-15 (1-11 starting, 12-15 bench).

        Strategy: Test all valid formations and select the one that maximizes
        total expected points (using total_value_score as proxy).
        """
        # Separate by position
        by_position = {1: [], 2: [], 3: [], 4: []}
        for player in team:
            by_position[player['element_type']].append(player)

        # Sort each position by value score (best first)
        for pos in by_position:
            by_position[pos].sort(
                key=lambda x: x.get('total_value_score', 0),
                reverse=True
            )

        # Valid formations: (GK, DEF, MID, FWD) - all sum to 11
        valid_formations = [
            (1, 3, 4, 3),
            (1, 3, 5, 2),
            (1, 4, 3, 3),
            (1, 4, 4, 2),
            (1, 4, 5, 1),
            (1, 5, 3, 2),
            (1, 5, 4, 1)
        ]

        # Find formation that maximizes total value score
        best_formation = None
        best_total_score = 0

        for gk_count, def_count, mid_count, fwd_count in valid_formations:
            # Check if we have enough players for this formation
            if (len(by_position[1]) < gk_count or
                len(by_position[2]) < def_count or
                len(by_position[3]) < mid_count or
                len(by_position[4]) < fwd_count):
                continue

            # Calculate total score for this formation
            total_score = (
                sum(p.get('total_value_score', 0) for p in by_position[1][:gk_count]) +
                sum(p.get('total_value_score', 0) for p in by_position[2][:def_count]) +
                sum(p.get('total_value_score', 0) for p in by_position[3][:mid_count]) +
                sum(p.get('total_value_score', 0) for p in by_position[4][:fwd_count])
            )

            if total_score > best_total_score:
                best_total_score = total_score
                best_formation = (gk_count, def_count, mid_count, fwd_count)

        if not best_formation:
            logger.warning("No valid formation found! Falling back to 3-5-2")
            best_formation = (1, 3, 5, 2)

        gk_count, def_count, mid_count, fwd_count = best_formation
        formation_str = f"{def_count}-{mid_count}-{fwd_count}"
        logger.info(f"Optimal formation: {formation_str} (total score: {best_total_score:.2f})")

        # Assign positions based on best formation
        position_number = 1

        # Starting XI (positions 1-11)
        for i in range(gk_count):
            by_position[1][i]['position'] = position_number
            position_number += 1

        for i in range(def_count):
            by_position[2][i]['position'] = position_number
            position_number += 1

        for i in range(mid_count):
            by_position[3][i]['position'] = position_number
            position_number += 1

        for i in range(fwd_count):
            by_position[4][i]['position'] = position_number
            position_number += 1

        # Bench (positions 12-15)
        for i in range(gk_count, len(by_position[1])):
            by_position[1][i]['position'] = position_number
            position_number += 1

        for i in range(def_count, len(by_position[2])):
            by_position[2][i]['position'] = position_number
            position_number += 1

        for i in range(mid_count, len(by_position[3])):
            by_position[3][i]['position'] = position_number
            position_number += 1

        for i in range(fwd_count, len(by_position[4])):
            by_position[4][i]['position'] = position_number
            position_number += 1

        return team

    def _assign_captain(self, team: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Assign captain and vice-captain based on expected points."""
        starting_xi = [p for p in team if p.get('position', 16) <= 11]

        # Calculate expected points for each
        expected_points = []
        for player in starting_xi:
            exp_pts = self.valuation_agent.calculate_expected_points(player, 3)
            expected_points.append((player, exp_pts))

        # Sort by expected points
        expected_points.sort(key=lambda x: x[1], reverse=True)

        # Assign captain and vice
        if expected_points:
            expected_points[0][0]['is_captain'] = True
            expected_points[0][0]['is_vice_captain'] = False
            expected_points[0][0]['multiplier'] = 2

        if len(expected_points) > 1:
            expected_points[1][0]['is_captain'] = False
            expected_points[1][0]['is_vice_captain'] = True
            expected_points[1][0]['multiplier'] = 1

        # Ensure all others are set to False
        for player in team:
            if 'is_captain' not in player:
                player['is_captain'] = False
            if 'is_vice_captain' not in player:
                player['is_vice_captain'] = False
            if 'multiplier' not in player:
                player['multiplier'] = 1

        return team

    # ========================================================================
    # TRANSFER DECISIONS
    # ========================================================================

    async def make_weekly_decision(
        self,
        gameweek: int
    ) -> Tuple[List[Dict[str, Any]], Optional[str], str]:
        """
        Make weekly team decisions.

        Decides:
        - Whether to make transfers
        - Which players to transfer
        - Captain selection
        - Chip usage

        Returns:
            (transfers, chip_used, announcement)
        """
        logger.info(f"Ron Clanker is planning for GW{gameweek}...")

        # Get current team and latest data
        current_team = self.db.get_current_team(gameweek - 1) or self.current_team
        fpl_data = await self.data_collector.update_all_data()
        all_players = fpl_data['players']

        # ===== NEW: ML-POWERED DECISION MAKING =====
        recommendations = None
        if self.use_ml and self.synthesis_engine:
            try:
                logger.info("Running Decision Synthesis Engine...")
                recommendations = self.synthesis_engine.synthesize_recommendations(gameweek)
                logger.info(f"Synthesis complete: {len(recommendations.get('top_players', []))} players ranked")
            except Exception as e:
                logger.error(f"Synthesis engine failed: {e}. Falling back to basic valuation.", exc_info=True)
                recommendations = None

        # Decide on transfers (ML-powered if available)
        if recommendations:
            transfers = self._decide_transfers_ml(
                current_team,
                recommendations,
                gameweek
            )
        else:
            # Fallback to basic valuation
            transfer_opportunities = self.valuation_agent.identify_transfer_targets(
                current_team,
                all_players
            )
            transfers = self._decide_transfers(
                transfer_opportunities,
                gameweek
            )

        # Execute transfers
        new_team = self._execute_transfers(current_team, transfers)

        # Update captain for new gameweek (ML-powered if available)
        if recommendations and recommendations.get('captain_recommendation'):
            new_team = self._assign_captain_ml(new_team, recommendations['captain_recommendation'], recommendations)
            captain_rec = recommendations['captain_recommendation']
        else:
            new_team = self._assign_captain(new_team)
            captain_rec = None

        # Optimize starting XI based on expected points (ML-powered if available)
        if recommendations:
            new_team = self._optimize_starting_xi(new_team, recommendations)

        # Log captain decision
        captain = next((p for p in new_team if p.get('is_captain')), None)
        if captain:
            captain_reasoning = f"ML recommendation: {captain_rec.get('primary', {}).get('name', 'N/A')}" if captain_rec else "Form-based selection"
            expected_points = captain_rec.get('primary', {}).get('xp', 0) * 2 if captain_rec else 0
            self.db.log_decision(
                gameweek=gameweek,
                decision_type='captain',
                decision_data={'player_id': captain.get('player_id', captain.get('id')), 'player_name': captain.get('web_name', 'Unknown')},
                reasoning=captain_reasoning,
                expected_value=expected_points,
                agent_source='ML' if captain_rec else 'Basic',
                confidence=captain_rec.get('primary', {}).get('confidence', 0.5) if captain_rec else 0.5
            )

        # Decide on chip usage (ML-powered if available)
        if recommendations and recommendations.get('chip_recommendation'):
            chip_used = self._decide_chip_usage_ml(gameweek, new_team, recommendations['chip_recommendation'])
        else:
            chip_used = self._decide_chip_usage(gameweek, new_team)

        # Log chip usage decision
        chip_reasoning = f"Using {chip_used}" if chip_used else "No chip used - saving for better opportunity"
        self.db.log_decision(
            gameweek=gameweek,
            decision_type='chip_usage',
            decision_data={'chip': chip_used or 'none'},
            reasoning=chip_reasoning,
            expected_value=0,  # Hard to quantify chip value
            agent_source='ML' if recommendations else 'Basic',
            confidence=0.6
        )

        # Log transfer strategy decision
        if transfers:
            total_expected_gain = sum(t.get('expected_gain', 0) for t in transfers)
            transfer_reasoning = f"Made {len(transfers)} transfer(s). " + '; '.join([t.get('reasoning', 'N/A') for t in transfers])
        else:
            total_expected_gain = 0
            transfer_reasoning = recommendations.get('strategy', {}).get('reasoning', 'Team unchanged - no beneficial transfers identified') if recommendations else 'No transfers needed'

        self.db.log_decision(
            gameweek=gameweek,
            decision_type='transfer_strategy',
            decision_data={'num_transfers': len(transfers), 'transfers': [{'out': t['player_out'].get('web_name'), 'in': t['player_in'].get('web_name')} for t in transfers]},
            reasoning=transfer_reasoning,
            expected_value=total_expected_gain,
            agent_source='ML' if recommendations else 'Basic',
            confidence=0.7 if transfers else 0.8  # Higher confidence when holding
        )

        # Save decisions
        self.db.set_team(gameweek, new_team)
        for transfer in transfers:
            self.db.log_transfer(
                gameweek,
                transfer['player_out']['id'],
                transfer['player_in']['id'],
                transfer.get('cost', 0),
                transfer.get('is_free', True),
                transfer.get('reasoning', '')
            )

        # Generate announcement (with ML insights if available)
        if transfers:
            reasoning = self._generate_transfer_reasoning(transfers, recommendations)
            announcement = self.ron.announce_transfers(transfers, gameweek, reasoning)
        else:
            reasoning = {
                'strategy': recommendations.get('strategy', {}).get('reasoning', f"Team looks solid for GW{gameweek}. No changes needed.") if recommendations else f"Team looks solid for GW{gameweek}. No changes needed.",
                'chip_used': chip_used,
                'ml_insights': recommendations.get('strategy') if recommendations else None
            }
            announcement = self.ron.announce_team_selection(new_team, gameweek, reasoning)

        return transfers, chip_used, announcement

    def _decide_transfers_optimized(
        self,
        current_team: List[Dict[str, Any]],
        gameweek: int,
        free_transfers: int = 1,
        bank: float = 5.0,
        horizon: int = 4
    ) -> Dict[str, Any]:
        """
        OPTIMIZED TRANSFER DECISION ENGINE (NEW!)

        Uses TransferOptimizer for intelligent multi-gameweek transfer analysis.

        Features:
        - Evaluates ALL positions independently
        - Multi-gameweek value calculation (default 4 GW horizon)
        - Compares options across positions
        - Roll vs make decision logic
        - Full data transparency

        Args:
            current_team: Current 15-player squad
            gameweek: Current gameweek
            free_transfers: Available free transfers (default 1)
            bank: Money in the bank in £m (default 5.0)
            horizon: Gameweeks to look ahead (default 4)

        Returns:
            Dict with:
                - 'recommendation': 'MAKE', 'ROLL', or 'CHIP'
                - 'best_transfer': TransferOption object
                - 'top_3_transfers': List of top 3 options
                - 'by_position': Options grouped by position
                - 'reasoning': Text explanation
        """

        logger.info(f"Running optimized transfer analysis for GW{gameweek}")

        if not self.transfer_optimizer:
            logger.warning("TransferOptimizer not available, falling back to old method")
            return None

        # Get Ron's team and league IDs from config
        from utils.config import load_config
        config = load_config()
        ron_entry_id = config.get('team_id')
        league_id = config.get('league_id')

        # Run the optimizer
        result = self.transfer_optimizer.optimize_transfers(
            current_team=current_team,
            ml_predictions={},  # Generated internally
            current_gw=gameweek,
            free_transfers=free_transfers,
            bank=bank,
            horizon=horizon,
            ron_entry_id=ron_entry_id,
            league_id=league_id
        )

        return result

    def _decide_transfers_ml(
        self,
        current_team: List[Dict[str, Any]],
        recommendations: Dict[str, Any],
        gameweek: int
    ) -> List[Dict[str, Any]]:
        """
        ML-POWERED: Decide transfers using synthesis recommendations.

        Considers:
        - Top value players from ML predictions
        - Template risks to cover
        - League position and competitive context
        - Multi-gameweek value
        """
        transfers = []

        # Get top recommended players by position
        all_ranked_players = recommendations.get('top_players', [])  # Full list (~50 players)
        top_players = all_ranked_players[:20]  # Top 20 for consideration
        template_risks = recommendations.get('risks_to_cover', [])
        strategy = recommendations.get('strategy', {})

        print(f"\n🔍 TransferML: ML ranked {len(all_ranked_players)} players total")
        print(f"🔍 TransferML: Considering top {len(top_players)} for transfers")
        print(f"🔍 TransferML: Current team size: {len(current_team)} players")
        if top_players:
            print(f"🔍 TransferML: Top 3 ML recommendations:")
            for i, p in enumerate(top_players[:3]):
                print(f"  {i+1}. {p.get('name', 'Unknown')} - xP: {p.get('xp', 0):.1f}, value: {p.get('value_score', 0):.2f}, pos: {p.get('position', '?')}")

        # Identify weakest player in current team
        # Use player_id (FPL player ID), not id (my_team row ID)
        current_team_ids = {p.get('player_id', p.get('id')) for p in current_team}

        # Find players in current team - search in FULL ranked list, not just top 20
        current_team_with_predictions = []
        for player in current_team:
            player_fpl_id = player.get('player_id', player.get('id'))
            player_pred = next((p for p in all_ranked_players if p.get('player_id') == player_fpl_id), None)
            if player_pred:
                current_team_with_predictions.append({
                    **player,
                    'xp': player_pred['xp'],
                    'value_score': player_pred['value_score']
                })
            else:
                # Player not in top recommendations - likely weak
                current_team_with_predictions.append({
                    **player,
                    'xp': 0.0,
                    'value_score': 0.0
                })

        # Group by position and find weakest in each position
        print(f"\n📊 TransferML: Analyzing weakest players BY POSITION:")

        positions = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}
        weakest_by_position = {}

        for pos_id, pos_name in positions.items():
            pos_players = [p for p in current_team_with_predictions if p.get('element_type') == pos_id]
            if pos_players:
                pos_players.sort(key=lambda x: x['value_score'])
                weakest_by_position[pos_id] = pos_players[0]
                print(f"  {pos_name}: {pos_players[0].get('web_name', 'Unknown')} - xP: {pos_players[0].get('xp', 0):.1f}, value: {pos_players[0].get('value_score', 0):.2f}")

        # Find overall weakest (for logging)
        current_team_with_predictions.sort(key=lambda x: x['value_score'])
        weakest = current_team_with_predictions[0] if current_team_with_predictions else None

        print(f"\n📊 TransferML: Overall weakest: {weakest.get('web_name', 'Unknown')} ({positions.get(weakest.get('element_type'), '?')})")

        if weakest and weakest['value_score'] < 0.5:
            print(f"✅ TransferML: Weakest player {weakest.get('web_name')} has value_score {weakest['value_score']:.2f} < 0.5 - considering transfer")
            # Find best replacement in same position - search ALL players, not just top 20
            position = weakest['element_type']
            position_name = positions.get(position, '?')

            print(f"🔍 TransferML: Searching ALL {len(all_ranked_players)} players for {position_name} replacements (up to £{weakest['now_cost'] / 10 + 1.0:.1f}m)...")

            replacements = [p for p in all_ranked_players  # Search ALL players, not just top_players
                           if p['position'] == position
                           and p['player_id'] not in current_team_ids
                           and p['price'] <= weakest['now_cost'] / 10 + 1.0]  # Allow 1m upgrade

            # Sort by value_score to get best options first
            replacements.sort(key=lambda x: x.get('value_score', 0), reverse=True)

            print(f"📊 TransferML: Found {len(replacements)} potential {position_name} replacements")
            if replacements:
                print(f"📊 TransferML: Top 3 replacements:")
                for i, r in enumerate(replacements[:3]):
                    print(f"  {i+1}. {r.get('name', 'Unknown')} - xP: {r.get('xp', 0):.1f}, value: {r.get('value_score', 0):.2f}, £{r.get('price', 0):.1f}m")

            if replacements:
                best_replacement = replacements[0]
                expected_gain = best_replacement['xp'] - weakest.get('xp', 0.0)

                if expected_gain >= 2.0:  # Worth a free transfer
                    transfers.append({
                        'player_out': weakest,
                        'player_in': self._get_player_details(best_replacement['player_id']),
                        'expected_gain': expected_gain,
                        'is_free': True,
                        'cost': 0,
                        'reasoning': (
                            f"ML predicts {best_replacement['name']} will score "
                            f"{best_replacement['xp']:.1f} xP vs {weakest.get('xp', 0):.1f} for "
                            f"{weakest['web_name']}. {strategy.get('approach', 'Value upgrade')}."
                        )
                    })
                else:
                    print(f"⚠️  TransferML: Best replacement xP gain {expected_gain:.1f} < 2.0 - not worth free transfer")
            else:
                print(f"⚠️  TransferML: No suitable replacements found for {weakest.get('web_name')} in position {position}")
        else:
            if weakest:
                print(f"✅ TransferML: Weakest player {weakest.get('web_name')} has value_score {weakest['value_score']:.2f} >= 0.5 - no transfer needed")
            else:
                print(f"⚠️  TransferML: No players in current team to evaluate")

        return transfers

    def _assign_captain_ml(
        self,
        team: List[Dict[str, Any]],
        captain_rec: Dict[str, Any],
        recommendations: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        ML-POWERED: Assign captain using synthesis recommendation.

        Considers:
        - ML predicted points
        - Ownership (template vs differential)
        - League position context
        """
        primary = captain_rec.get('primary', {})
        differential = captain_rec.get('differential_option', {})

        captain_id = primary.get('player_id') if primary else None
        vice_captain_id = differential.get('player_id') if differential else None

        # Find captain and vice in team
        for player in team:
            player_fpl_id = player.get('player_id', player.get('id'))
            if player_fpl_id == captain_id:
                player['is_captain'] = True
                player['is_vice_captain'] = False
                player['multiplier'] = 2
                logger.info(f"Captain (ML): {player['web_name']} ({primary.get('xp', 0):.2f} xP)")
            elif player_fpl_id == vice_captain_id:
                player['is_captain'] = False
                player['is_vice_captain'] = True
                player['multiplier'] = 1
            else:
                player['is_captain'] = False
                player['is_vice_captain'] = False
                player['multiplier'] = 1

        # If no captain set (player not in team), fallback to basic method
        if not any(p.get('is_captain') for p in team):
            logger.warning("ML captain not in team, using fallback")
            return self._assign_captain(team)

        # If captain is set but vice captain is not (differential not in team),
        # set vice captain to second-best player in the actual team
        if not any(p.get('is_vice_captain') for p in team):
            logger.warning(f"ML vice captain {differential.get('name', 'N/A')} not in team, assigning to second-best player")
            starting_xi = [p for p in team if p.get('position', 16) <= 11 and not p.get('is_captain')]

            # Get ML xP for each player from recommendations
            all_players_xp = {}
            if recommendations and recommendations.get('top_players'):
                for player_pred in recommendations['top_players']:
                    all_players_xp[player_pred['player_id']] = player_pred.get('xp', 0)

            # Calculate expected points for each using ML predictions
            expected_points = []
            for player in starting_xi:
                player_fpl_id = player.get('player_id', player.get('id'))
                exp_pts = all_players_xp.get(player_fpl_id, 0)
                expected_points.append((player, exp_pts))

            # Sort by expected points and assign vice to top player
            expected_points.sort(key=lambda x: x[1], reverse=True)
            if expected_points:
                expected_points[0][0]['is_vice_captain'] = True
                expected_points[0][0]['multiplier'] = 1
                logger.info(f"Vice Captain (fallback): {expected_points[0][0]['web_name']} ({expected_points[0][1]:.2f} xP)")

        return team

    def _optimize_starting_xi(
        self,
        team: List[Dict[str, Any]],
        recommendations: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Optimize starting XI selection based on ML expected points.

        Tries all valid FPL formations (3-5-2, 4-4-2, 4-5-1, etc.) and
        selects the combination that maximizes total expected points.

        Args:
            team: Current team (15 players)
            recommendations: ML recommendations with xP for all players

        Returns:
            Team with optimized positions (1-11 starters, 12-15 bench)
        """
        # Get ML xP predictions
        all_players_xp = {}
        if recommendations and recommendations.get('top_players'):
            for player_pred in recommendations['top_players']:
                all_players_xp[player_pred['player_id']] = player_pred.get('xp', 0)

        # Add xP to each team player
        for player in team:
            player_id = player.get('player_id', player.get('id'))
            player['ml_xp'] = all_players_xp.get(player_id, 0)

        # Group players by position
        by_position = {1: [], 2: [], 3: [], 4: []}  # GK, DEF, MID, FWD
        for player in team:
            pos = player.get('element_type')
            if pos in by_position:
                by_position[pos].append(player)

        # Sort each position by xP (highest first)
        for pos in by_position:
            by_position[pos].sort(key=lambda x: x.get('ml_xp', 0), reverse=True)

        # Try all valid formations
        formations = [
            ('3-5-2', 1, 3, 5, 2),
            ('4-5-1', 1, 4, 5, 1),
            ('4-4-2', 1, 4, 4, 2),
            ('3-4-3', 1, 3, 4, 3),
            ('5-4-1', 1, 5, 4, 1),
            ('5-3-2', 1, 5, 3, 2),
        ]

        best_formation = None
        best_total_xp = 0
        best_starters = {}

        for name, num_gk, num_def, num_mid, num_fwd in formations:
            # Check if we have enough players for this formation
            if (num_gk > len(by_position[1]) or
                num_def > len(by_position[2]) or
                num_mid > len(by_position[3]) or
                num_fwd > len(by_position[4])):
                continue

            # Calculate total xP for this formation
            total_xp = 0
            total_xp += sum(p.get('ml_xp', 0) for p in by_position[1][:num_gk])
            total_xp += sum(p.get('ml_xp', 0) for p in by_position[2][:num_def])
            total_xp += sum(p.get('ml_xp', 0) for p in by_position[3][:num_mid])
            total_xp += sum(p.get('ml_xp', 0) for p in by_position[4][:num_fwd])

            if total_xp > best_total_xp:
                best_total_xp = total_xp
                best_formation = name
                best_starters = {
                    1: by_position[1][:num_gk],
                    2: by_position[2][:num_def],
                    3: by_position[3][:num_mid],
                    4: by_position[4][:num_fwd]
                }

        if not best_formation:
            logger.warning("No valid formation found, keeping current positions")
            return team

        logger.info(f"Optimal formation: {best_formation} ({best_total_xp:.2f} xP)")

        # Clear all existing positions first
        for player in team:
            if 'position' in player:
                del player['position']

        # Assign positions: 1-11 for starters, 12-15 for bench
        position_number = 1

        # Assign starting XI in order: GK, DEF, MID, FWD
        for pos_type in [1, 2, 3, 4]:
            for player in best_starters.get(pos_type, []):
                player['position'] = position_number
                position_number += 1

        # Assign bench (remaining players that haven't been assigned yet)
        for pos_type in [1, 2, 3, 4]:
            for player in by_position[pos_type]:
                if 'position' not in player:
                    player['position'] = position_number
                    position_number += 1

        return team

    def _decide_chip_usage_ml(
        self,
        gameweek: int,
        team: List[Dict[str, Any]],
        chip_rec: Dict[str, Any]
    ) -> Optional[str]:
        """
        ML-POWERED: Decide chip usage using synthesis recommendation.

        Considers:
        - Optimal timing from chip analyzer
        - League position and competitive context
        - Expected gain vs alternatives
        """
        recommended_chip = chip_rec.get('recommended_chip')
        reasoning = chip_rec.get('reasoning', '')

        if recommended_chip and recommended_chip != 'none':
            logger.info(f"Chip recommendation: {recommended_chip} - {reasoning}")
            # For now, be conservative - still don't use chips in early phase
            # TODO: Enable chip usage when confidence is high
            return None

        return None

    def _get_player_details(self, player_id: int) -> Dict[str, Any]:
        """Fetch full player details from database."""
        player_data = self.db.execute_query(
            "SELECT * FROM players WHERE id = ?",
            (player_id,)
        )
        return player_data[0] if player_data else None

    def _decide_transfers(
        self,
        opportunities: List[Tuple[Dict, Dict, float]],
        gameweek: int
    ) -> List[Dict[str, Any]]:
        """
        Decide which transfers to make this week.

        Phase 1 logic: Conservative approach
        - Use free transfer if significant upgrade available (2+ points)
        - Only take hits for 4+ point expected gain
        """
        if not opportunities:
            return []

        transfers = []
        best_opportunity = opportunities[0]
        player_out, player_in, expected_gain = best_opportunity

        # Check if worth using free transfer
        if expected_gain >= 2.0:
            transfers.append({
                'player_out': player_out,
                'player_in': player_in,
                'expected_gain': expected_gain,
                'is_free': True,
                'cost': 0,
                'reasoning': f"Upgrading {player_out['web_name']} to {player_in['web_name']} - expect {expected_gain} extra points"
            })

        return transfers

    def _execute_transfers(
        self,
        current_team: List[Dict[str, Any]],
        transfers: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Execute transfers and return new team."""
        new_team = current_team.copy()

        for transfer in transfers:
            player_out = transfer['player_out']
            player_in = transfer['player_in']

            # Remove player out (compare player_id, not my_team row id)
            new_team = [p for p in new_team if p.get('player_id', p.get('id')) != player_out['id']]

            # Add player in with same position
            # Make a copy to avoid mutating the original player dict
            player_in_copy = player_in.copy()
            player_in_copy['position'] = player_out.get('position', 1)
            player_in_copy['purchase_price'] = player_in['now_cost']
            player_in_copy['selling_price'] = player_in['now_cost']
            # Ensure we use 'id' for the player, not 'player_id'
            if 'player_id' not in player_in_copy:
                player_in_copy['player_id'] = player_in_copy['id']
            new_team.append(player_in_copy)

        return new_team

    def _decide_chip_usage(
        self,
        gameweek: int,
        team: List[Dict[str, Any]]
    ) -> Optional[str]:
        """
        Decide whether to use a chip this gameweek.

        Phase 1: Conservative - don't use chips yet
        """
        # Phase 1: No chip usage - save for later phases
        return None

    def _generate_transfer_reasoning(
        self,
        transfers: List[Dict[str, Any]],
        recommendations: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate Ron's reasoning for transfers."""
        reasoning_parts = []

        for transfer in transfers:
            player_out = transfer['player_out']['web_name']
            player_in = transfer['player_in']['web_name']
            gain = transfer['expected_gain']

            base_reasoning = (
                f"{player_out} hasn't delivered. {player_in} is the better option. "
                f"Expect {gain:.1f} extra points per week."
            )

            # Add ML context if available
            if recommendations and recommendations.get('strategy'):
                strategy = recommendations['strategy']
                base_reasoning += f" {strategy.get('reasoning', '')}"

            reasoning_parts.append(base_reasoning)

        return " ".join(reasoning_parts)

    # ========================================================================
    # POST-GAMEWEEK ANALYSIS
    # ========================================================================

    def review_gameweek(
        self,
        gameweek: int,
        points_scored: int,
        average_score: int
    ) -> str:
        """
        Review gameweek performance and generate Ron's analysis.

        Returns:
            Review text
        """
        highlights = []
        lowlights = []

        # Analyze performance
        if points_scored > average_score + 10:
            highlights.append("Well above average - tactics worked")
        elif points_scored < average_score - 10:
            lowlights.append("Below average - need to improve")

        # Generate review
        review = self.ron.post_gameweek_review(
            gameweek,
            points_scored,
            average_score,
            highlights,
            lowlights
        )

        return review
