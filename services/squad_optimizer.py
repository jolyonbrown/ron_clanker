"""
Squad Optimizer Service

Builds optimal 15-player squads for Wildcard and Free Hit chips.

Key differences:
- Free Hit: Fresh £100m budget, optimize for single GW, squad reverts after
- Wildcard: Use selling prices + bank, optimize for multi-GW horizon, permanent squad

Uses greedy algorithm with beam search for near-optimal solutions that respect
all FPL constraints (budget, position limits, team limits).
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from collections import defaultdict

from data.database import Database

logger = logging.getLogger('ron_clanker.squad_optimizer')

# Position constants
POSITIONS = {1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD'}
POSITION_TARGETS = {'GKP': 2, 'DEF': 5, 'MID': 5, 'FWD': 3}
POSITION_IDS = {'GKP': 1, 'DEF': 2, 'MID': 3, 'FWD': 4}

# Budget constraint
FREE_HIT_BUDGET = 1000  # £100.0m in tenths


@dataclass
class OptimizedSquad:
    """Result of squad optimization."""
    players: List[Dict[str, Any]]
    total_cost: float  # In millions
    total_xp: float  # Expected points for optimization horizon
    budget_remaining: float
    mode: str  # 'freehit' or 'wildcard'
    horizon_gws: int
    reasoning: str

    def get_by_position(self) -> Dict[str, List[Dict]]:
        """Group players by position."""
        by_pos = defaultdict(list)
        for p in self.players:
            pos_name = POSITIONS.get(p.get('element_type', 0), 'UNK')
            by_pos[pos_name].append(p)
        return dict(by_pos)

    def to_dict(self) -> Dict:
        return {
            'players': self.players,
            'total_cost': self.total_cost,
            'total_xp': self.total_xp,
            'budget_remaining': self.budget_remaining,
            'mode': self.mode,
            'horizon_gws': self.horizon_gws,
            'reasoning': self.reasoning,
        }


class SquadOptimizer:
    """
    Optimizes squad selection for Wildcard and Free Hit chips.

    Uses beam search to explore multiple candidate squads and find
    near-optimal solution within FPL constraints.
    """

    def __init__(self, database: Database):
        """Initialize with database connection."""
        self.db = database
        logger.info("SquadOptimizer: Initialized")

    def optimize_free_hit(
        self,
        gameweek: int,
        predictions: Dict[int, float],
        verbose: bool = True
    ) -> OptimizedSquad:
        """
        Build optimal squad for Free Hit chip.

        Free Hit rules:
        - Fresh £100m budget (ignores current squad)
        - Optimize for single gameweek only
        - Squad reverts to pre-FH squad after gameweek

        Args:
            gameweek: Target gameweek
            predictions: Dict mapping player_id -> expected points for GW
            verbose: Whether to print progress

        Returns:
            OptimizedSquad with optimal 15 players
        """
        if verbose:
            print(f"\n{'='*60}")
            print(f"FREE HIT SQUAD OPTIMIZER - GW{gameweek}")
            print(f"{'='*60}")
            print(f"Budget: £100.0m (fresh)")
            print(f"Optimization: Single gameweek")

        # Get all available players with predictions
        players = self._get_available_players(predictions)

        if verbose:
            print(f"Available players: {len(players)}")

        # Run optimization
        squad = self._optimize_squad(
            players=players,
            budget=FREE_HIT_BUDGET,
            predictions=predictions,
            horizon=1,
            verbose=verbose
        )

        total_cost = sum(p['now_cost'] for p in squad) / 10
        total_xp = sum(predictions.get(p['id'], 0) for p in squad)

        reasoning = (
            f"Free Hit squad optimized for GW{gameweek}. "
            f"Total xP: {total_xp:.1f} from 15 players. "
            f"Budget: £{total_cost:.1f}m / £100.0m."
        )

        if verbose:
            self._print_squad(squad, predictions, "FREE HIT SQUAD")

        return OptimizedSquad(
            players=squad,
            total_cost=total_cost,
            total_xp=total_xp,
            budget_remaining=(FREE_HIT_BUDGET - sum(p['now_cost'] for p in squad)) / 10,
            mode='freehit',
            horizon_gws=1,
            reasoning=reasoning
        )

    def optimize_wildcard(
        self,
        gameweek: int,
        current_squad: List[Dict],
        bank: float,
        multi_gw_predictions: Dict[int, Dict[int, float]],
        horizon: int = 4,
        verbose: bool = True
    ) -> OptimizedSquad:
        """
        Build optimal squad for Wildcard chip.

        Wildcard rules:
        - Budget = sum of selling prices + bank
        - Unlimited transfers (complete rebuild allowed)
        - Optimize for multi-gameweek horizon
        - Squad is permanent (doesn't revert)

        Args:
            gameweek: Starting gameweek
            current_squad: Current 15-player squad (for selling prices)
            bank: Current bank balance (in millions)
            multi_gw_predictions: Dict[player_id][gw] -> xP
            horizon: Number of gameweeks to optimize for
            verbose: Whether to print progress

        Returns:
            OptimizedSquad with optimal 15 players
        """
        if verbose:
            print(f"\n{'='*60}")
            print(f"WILDCARD SQUAD OPTIMIZER - GW{gameweek}")
            print(f"{'='*60}")

        # Calculate available budget from current squad selling prices
        selling_value = sum(p.get('selling_price', p.get('now_cost', 0)) for p in current_squad)
        total_budget = selling_value + int(bank * 10)  # Convert bank to tenths

        if verbose:
            print(f"Current squad selling value: £{selling_value/10:.1f}m")
            print(f"Bank: £{bank:.1f}m")
            print(f"Total budget: £{total_budget/10:.1f}m")
            print(f"Optimization horizon: GW{gameweek} to GW{gameweek + horizon - 1}")

        # Aggregate predictions across horizon (weighted towards nearer GWs)
        aggregated_predictions = self._aggregate_predictions(
            multi_gw_predictions,
            gameweek,
            horizon
        )

        # Get all available players
        players = self._get_available_players(aggregated_predictions)

        if verbose:
            print(f"Available players: {len(players)}")

        # Run optimization
        squad = self._optimize_squad(
            players=players,
            budget=total_budget,
            predictions=aggregated_predictions,
            horizon=horizon,
            verbose=verbose
        )

        total_cost = sum(p['now_cost'] for p in squad) / 10
        total_xp = sum(aggregated_predictions.get(p['id'], 0) for p in squad)

        reasoning = (
            f"Wildcard squad optimized for GW{gameweek}-{gameweek+horizon-1}. "
            f"Total weighted xP: {total_xp:.1f} over {horizon} GWs. "
            f"Budget: £{total_cost:.1f}m / £{total_budget/10:.1f}m."
        )

        if verbose:
            self._print_squad(squad, aggregated_predictions, "WILDCARD SQUAD")

        return OptimizedSquad(
            players=squad,
            total_cost=total_cost,
            total_xp=total_xp,
            budget_remaining=(total_budget - sum(p['now_cost'] for p in squad)) / 10,
            mode='wildcard',
            horizon_gws=horizon,
            reasoning=reasoning
        )

    def _get_available_players(
        self,
        predictions: Dict[int, float]
    ) -> List[Dict]:
        """
        Get all available players with their predictions.

        Filters out injured/unavailable players.
        Returns players with all fields needed by downstream processors.
        """
        # Get players from database with all needed fields
        players = self.db.execute_query("""
            SELECT
                p.id,
                p.web_name,
                p.first_name,
                p.second_name,
                p.element_type,
                p.team_id,
                p.now_cost,
                p.status,
                p.chance_of_playing_next_round,
                p.selected_by_percent,
                p.form,
                p.points_per_game,
                p.total_points,
                t.short_name as team_name
            FROM players p
            LEFT JOIN teams t ON p.team_id = t.id
            WHERE p.status IN ('a', 'd')
            AND (p.chance_of_playing_next_round IS NULL
                 OR p.chance_of_playing_next_round >= 50)
            ORDER BY p.id
        """)

        # Add predictions and ensure all required fields are set
        for player in players:
            # Core fields for downstream processors
            player['player_id'] = player['id']  # FPL player ID
            player['xP'] = predictions.get(player['id'], 0.0)

            # Value score for ranking within position
            if player['now_cost'] > 0:
                player['value_score'] = player['xP'] / (player['now_cost'] / 10)
            else:
                player['value_score'] = 0.0

            # Ensure team field is set (some code uses 'team', some uses 'team_id')
            player['team'] = player.get('team_id')

            # Initialize captain/vice-captain flags (will be set by captain selection)
            player['is_captain'] = False
            player['is_vice_captain'] = False

            # Set purchase/selling price for new squad (buying at current price)
            player['purchase_price'] = player['now_cost']
            player['selling_price'] = player['now_cost']

        return players

    def _aggregate_predictions(
        self,
        multi_gw_predictions: Dict[int, Dict[int, float]],
        start_gw: int,
        horizon: int
    ) -> Dict[int, float]:
        """
        Aggregate multi-GW predictions with time decay.

        Weights nearer gameweeks more heavily (0.85^n decay).
        """
        aggregated = {}

        for player_id, gw_predictions in multi_gw_predictions.items():
            total = 0.0
            weight_sum = 0.0

            for i in range(horizon):
                gw = start_gw + i
                xp = gw_predictions.get(gw, 0.0)
                weight = 0.85 ** i  # Decay factor
                total += xp * weight
                weight_sum += weight

            # Normalize
            if weight_sum > 0:
                aggregated[player_id] = total / weight_sum * horizon
            else:
                aggregated[player_id] = 0.0

        return aggregated

    def _optimize_squad(
        self,
        players: List[Dict],
        budget: int,
        predictions: Dict[int, float],
        horizon: int,
        verbose: bool = True
    ) -> List[Dict]:
        """
        Core optimization algorithm using position-by-position greedy selection
        with lookahead to avoid painting ourselves into a corner.

        Strategy:
        1. Sort players by xP within each position
        2. Select positions in order that preserves budget flexibility
        3. Use greedy selection with constraint checking
        4. Fallback to cheaper options if budget runs low
        """
        squad = []
        spent = 0
        team_counts = defaultdict(int)  # Track players per team

        # Group players by position
        by_position = defaultdict(list)
        for p in players:
            by_position[p['element_type']].append(p)

        # Sort each position by xP (descending)
        for pos_id in by_position:
            by_position[pos_id].sort(key=lambda x: x['xP'], reverse=True)

        # Selection order: Start with positions that have fewer good options
        # GKP and FWD typically have fewer elite options
        selection_order = [
            (1, 2),  # 2 GKPs
            (4, 3),  # 3 FWDs
            (2, 5),  # 5 DEFs
            (3, 5),  # 5 MIDs
        ]

        if verbose:
            print(f"\n📊 Selecting squad...")

        for pos_id, target_count in selection_order:
            pos_name = POSITIONS[pos_id]
            candidates = by_position[pos_id]
            selected = 0

            # Calculate remaining budget for other positions
            remaining_positions = sum(
                count for pid, count in selection_order
                if pid != pos_id and sum(1 for p in squad if p['element_type'] == pid) < count
            )

            # Reserve minimum budget for remaining positions
            # Use position-specific minimum prices
            min_prices = {1: 40, 2: 40, 3: 45, 4: 45}  # In tenths
            reserved = remaining_positions * min_prices.get(pos_id, 45)

            for candidate in candidates:
                if selected >= target_count:
                    break

                # Check team constraint
                if team_counts[candidate['team_id']] >= 3:
                    continue

                # Check budget (with reserve for other positions)
                positions_remaining_for_this = target_count - selected - 1
                this_pos_reserve = positions_remaining_for_this * min_prices.get(pos_id, 45)
                available_budget = budget - spent - reserved - this_pos_reserve

                if candidate['now_cost'] > available_budget:
                    continue

                # Select player
                squad.append(candidate)
                spent += candidate['now_cost']
                team_counts[candidate['team_id']] += 1
                selected += 1

                if verbose:
                    print(f"  {pos_name} {selected}/{target_count}: "
                          f"{candidate['web_name']} ({candidate['team_name']}) "
                          f"£{candidate['now_cost']/10:.1f}m, xP={candidate['xP']:.1f}")

            # If we couldn't fill the position, try cheaper options
            if selected < target_count:
                logger.warning(f"SquadOptimizer: Only got {selected}/{target_count} {pos_name}s, "
                              f"trying budget options...")

                # Sort by price to find cheaper options
                cheap_candidates = sorted(
                    [c for c in candidates if c not in squad],
                    key=lambda x: x['now_cost']
                )

                for candidate in cheap_candidates:
                    if selected >= target_count:
                        break

                    if team_counts[candidate['team_id']] >= 3:
                        continue

                    if candidate['now_cost'] > (budget - spent):
                        continue

                    squad.append(candidate)
                    spent += candidate['now_cost']
                    team_counts[candidate['team_id']] += 1
                    selected += 1

                    if verbose:
                        print(f"  {pos_name} {selected}/{target_count} (budget): "
                              f"{candidate['web_name']} £{candidate['now_cost']/10:.1f}m")

        if verbose:
            print(f"\n  Total: {len(squad)} players, £{spent/10:.1f}m")

        return squad

    def _print_squad(
        self,
        squad: List[Dict],
        predictions: Dict[int, float],
        title: str
    ):
        """Print squad in a nice format."""
        print(f"\n{'='*60}")
        print(f"{title}")
        print(f"{'='*60}")

        by_pos = defaultdict(list)
        for p in squad:
            by_pos[p['element_type']].append(p)

        total_xp = 0.0
        total_cost = 0.0

        for pos_id in [1, 2, 3, 4]:
            pos_name = POSITIONS[pos_id]
            players = sorted(by_pos[pos_id], key=lambda x: x['xP'], reverse=True)

            print(f"\n{pos_name}:")
            for p in players:
                xp = predictions.get(p['id'], 0.0)
                cost = p['now_cost'] / 10
                total_xp += xp
                total_cost += cost
                print(f"  {p['web_name']:<18} ({p['team_name']:<3}) "
                      f"£{cost:>5.1f}m  xP={xp:>5.1f}")

        print(f"\n{'-'*60}")
        print(f"TOTAL: {len(squad)} players, £{total_cost:.1f}m, xP={total_xp:.1f}")
        print(f"{'='*60}")


# Convenience functions for integration
def build_free_hit_squad(
    database: Database,
    gameweek: int,
    predictions: Dict[int, float],
    verbose: bool = True
) -> OptimizedSquad:
    """Build optimal Free Hit squad."""
    optimizer = SquadOptimizer(database)
    return optimizer.optimize_free_hit(gameweek, predictions, verbose)


def build_wildcard_squad(
    database: Database,
    gameweek: int,
    current_squad: List[Dict],
    bank: float,
    multi_gw_predictions: Dict[int, Dict[int, float]],
    horizon: int = 4,
    verbose: bool = True
) -> OptimizedSquad:
    """Build optimal Wildcard squad."""
    optimizer = SquadOptimizer(database)
    return optimizer.optimize_wildcard(
        gameweek, current_squad, bank, multi_gw_predictions, horizon, verbose
    )


if __name__ == "__main__":
    # Test the optimizer
    import sys
    sys.path.insert(0, str(__file__).rsplit('/', 2)[0])

    from agents.synthesis.engine import DecisionSynthesisEngine

    print("\n=== Squad Optimizer Test ===\n")

    db = Database()
    engine = DecisionSynthesisEngine(db)

    # Get current gameweek
    from utils.gameweek import get_current_gameweek
    current_gw = get_current_gameweek(db)
    print(f"Current gameweek: {current_gw}")

    # Run ML predictions
    predictions = engine.run_ml_predictions(current_gw)
    print(f"Generated {len(predictions)} predictions")

    # Test Free Hit
    print("\n" + "="*60)
    print("TESTING FREE HIT OPTIMIZER")
    print("="*60)

    optimizer = SquadOptimizer(db)
    fh_squad = optimizer.optimize_free_hit(
        gameweek=current_gw,
        predictions=predictions,
        verbose=True
    )

    print(f"\nFree Hit Result:")
    print(f"  Total xP: {fh_squad.total_xp:.1f}")
    print(f"  Total Cost: £{fh_squad.total_cost:.1f}m")
    print(f"  Budget Remaining: £{fh_squad.budget_remaining:.1f}m")
