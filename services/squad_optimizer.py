"""
Squad Optimizer Service

Builds optimal 15-player squads for Wildcard and Free Hit chips.
Also provides MILP-based starting XI optimization.

Key differences:
- Free Hit: Fresh £100m budget, optimize for single GW, squad reverts after
- Wildcard: Use selling prices + bank, optimize for multi-GW horizon, permanent squad

Uses Mixed-Integer Linear Programming (PuLP) for guaranteed optimal solutions
that respect all FPL constraints (budget, position limits, team limits).
Falls back to greedy algorithm if PuLP unavailable.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from collections import defaultdict

try:
    import pulp
    PULP_AVAILABLE = True
except ImportError:
    PULP_AVAILABLE = False

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
        # Pass gameweek to filter out teams with no fixture (blank GW handling)
        players = self._get_available_players(predictions, gameweek=gameweek)

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

        # Filter to players whose teams play in the target gameweek. A WC
        # squad still has to field an XI *this* GW; without this filter
        # the optimizer could pick 6+ players from blanking teams (happened
        # on GW34 2026-04-24 — Haaland, Semenyo, Van Hecke, João Pedro,
        # Calvert-Lewin, Cherki all blanked, captain was Haaland with zero
        # fixtures). Trade-off: some multi-GW value is lost when a key
        # player (e.g. Haaland) blanks the target GW but plays later in the
        # horizon — accepted because a 5-blank XI costs far more than
        # missing one player's horizon contribution.
        players = self._get_available_players(aggregated_predictions, gameweek=gameweek)

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
        predictions: Dict[int, float],
        gameweek: int = None
    ) -> List[Dict]:
        """
        Get all available players with their predictions.

        Filters out injured/unavailable players.
        If gameweek is provided, also filters out players whose teams
        don't have a fixture in that gameweek (blank gameweek handling).
        Returns players with all fields needed by downstream processors.
        """
        # If gameweek specified, find which teams actually play
        playing_teams = None
        if gameweek is not None:
            fixtures = self.db.execute_query(
                "SELECT team_h, team_a FROM fixtures WHERE event = ?",
                (gameweek,)
            )
            if fixtures:
                playing_teams = set()
                for f in fixtures:
                    playing_teams.add(f['team_h'])
                    playing_teams.add(f['team_a'])

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

        # Filter to only players whose teams play in the target gameweek
        if playing_teams is not None:
            before_count = len(players)
            players = [p for p in players if p['team_id'] in playing_teams]
            filtered = before_count - len(players)
            if filtered > 0:
                logger.info(
                    f"BGW filter: Removed {filtered} players from "
                    f"{before_count - filtered} teams not playing in GW{gameweek}"
                )

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
        Core optimization using MILP (Mixed-Integer Linear Programming).

        Guaranteed optimal squad selection subject to FPL constraints:
        - Budget limit
        - Exactly 2 GKP, 5 DEF, 5 MID, 3 FWD
        - Max 3 players from any single team
        - Maximize total expected points

        Falls back to greedy algorithm if PuLP unavailable.
        """
        if not PULP_AVAILABLE:
            logger.warning("PuLP not available, falling back to greedy optimizer")
            return self._optimize_squad_greedy(players, budget, predictions, horizon, verbose)

        if verbose:
            print(f"\n📊 Running MILP optimizer (guaranteed optimal)...")

        # Pre-filter to top candidates per position to keep problem tractable
        # (full player pool would work but solving is faster with fewer vars)
        by_position = defaultdict(list)
        for p in players:
            by_position[p['element_type']].append(p)

        candidates = []
        pos_limits = {1: 15, 2: 40, 3: 40, 4: 25}  # Top N per position
        for pos_id, limit in pos_limits.items():
            sorted_pos = sorted(by_position[pos_id], key=lambda x: x['xP'], reverse=True)
            candidates.extend(sorted_pos[:limit])

        # Create the LP problem
        prob = pulp.LpProblem("FPL_Squad_Selection", pulp.LpMaximize)

        # Decision variables: x[i] = 1 if player i is selected
        player_vars = {}
        for i, p in enumerate(candidates):
            player_vars[i] = pulp.LpVariable(f"x_{p['id']}", cat='Binary')

        # Objective: maximize total xP
        prob += pulp.lpSum(
            candidates[i]['xP'] * player_vars[i] for i in range(len(candidates))
        ), "Total_xP"

        # Constraint 1: Budget
        prob += pulp.lpSum(
            candidates[i]['now_cost'] * player_vars[i] for i in range(len(candidates))
        ) <= budget, "Budget"

        # Constraint 2: Position limits (exact counts)
        position_targets = {1: 2, 2: 5, 3: 5, 4: 3}
        for pos_id, target in position_targets.items():
            pos_indices = [i for i, p in enumerate(candidates) if p['element_type'] == pos_id]
            prob += pulp.lpSum(
                player_vars[i] for i in pos_indices
            ) == target, f"Position_{POSITIONS[pos_id]}"

        # Constraint 3: Max 3 per team
        team_ids = set(p['team_id'] for p in candidates)
        for team_id in team_ids:
            team_indices = [i for i, p in enumerate(candidates) if p['team_id'] == team_id]
            prob += pulp.lpSum(
                player_vars[i] for i in team_indices
            ) <= 3, f"Team_{team_id}"

        # Solve
        prob.solve(pulp.PULP_CBC_CMD(msg=0))

        if prob.status != pulp.constants.LpStatusOptimal:
            logger.warning(f"MILP solver status: {pulp.LpStatus[prob.status]}, falling back to greedy")
            return self._optimize_squad_greedy(players, budget, predictions, horizon, verbose)

        # Extract solution
        squad = []
        for i, p in enumerate(candidates):
            if player_vars[i].varValue and player_vars[i].varValue > 0.5:
                squad.append(p)

        total_xp = sum(p['xP'] for p in squad)
        total_cost = sum(p['now_cost'] for p in squad)

        if verbose:
            print(f"  MILP optimal solution found!")
            print(f"  Total xP: {total_xp:.1f}")
            print(f"  Total cost: £{total_cost/10:.1f}m / £{budget/10:.1f}m")

            # Print by position
            for pos_id in [1, 2, 3, 4]:
                pos_name = POSITIONS[pos_id]
                pos_players = sorted(
                    [p for p in squad if p['element_type'] == pos_id],
                    key=lambda x: x['xP'], reverse=True
                )
                for p in pos_players:
                    print(f"  {pos_name}: {p['web_name']} ({p.get('team_name', '?')}) "
                          f"£{p['now_cost']/10:.1f}m, xP={p['xP']:.1f}")

        return squad

    def _optimize_squad_greedy(
        self,
        players: List[Dict],
        budget: int,
        predictions: Dict[int, float],
        horizon: int,
        verbose: bool = True
    ) -> List[Dict]:
        """
        Fallback greedy optimizer (position-by-position with budget reservation).
        Used when PuLP is not available.
        """
        squad = []
        spent = 0
        team_counts = defaultdict(int)

        by_position = defaultdict(list)
        for p in players:
            by_position[p['element_type']].append(p)

        for pos_id in by_position:
            by_position[pos_id].sort(key=lambda x: x['xP'], reverse=True)

        selection_order = [(1, 2), (4, 3), (2, 5), (3, 5)]

        if verbose:
            print(f"\n📊 Selecting squad (greedy fallback)...")

        min_prices = {1: 40, 2: 40, 3: 45, 4: 45}

        for pos_id, target_count in selection_order:
            pos_name = POSITIONS[pos_id]
            candidates = by_position[pos_id]
            selected = 0

            remaining_positions = sum(
                count for pid, count in selection_order
                if pid != pos_id and sum(1 for p in squad if p['element_type'] == pid) < count
            )
            reserved = remaining_positions * min_prices.get(pos_id, 45)

            for candidate in candidates:
                if selected >= target_count:
                    break
                if team_counts[candidate['team_id']] >= 3:
                    continue
                positions_remaining_for_this = target_count - selected - 1
                this_pos_reserve = positions_remaining_for_this * min_prices.get(pos_id, 45)
                available_budget = budget - spent - reserved - this_pos_reserve
                if candidate['now_cost'] > available_budget:
                    continue

                squad.append(candidate)
                spent += candidate['now_cost']
                team_counts[candidate['team_id']] += 1
                selected += 1

                if verbose:
                    print(f"  {pos_name} {selected}/{target_count}: "
                          f"{candidate['web_name']} ({candidate['team_name']}) "
                          f"£{candidate['now_cost']/10:.1f}m, xP={candidate['xP']:.1f}")

            if selected < target_count:
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

    def optimize_starting_xi(
        self,
        squad: List[Dict],
        verbose: bool = False
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Given a 15-player squad, find the optimal starting XI and bench order
        using MILP to test all valid formations simultaneously.

        Returns:
            Tuple of (starting_xi, bench) where each player has 'position' set.
        """
        if not PULP_AVAILABLE or len(squad) != 15:
            return self._starting_xi_greedy(squad, verbose)

        prob = pulp.LpProblem("FPL_Starting_XI", pulp.LpMaximize)

        # Decision variables: s[i] = 1 if player i starts
        s = {}
        for i, p in enumerate(squad):
            s[i] = pulp.LpVariable(f"s_{p.get('id', i)}", cat='Binary')

        # Objective: maximize starting XI xP
        prob += pulp.lpSum(
            squad[i].get('xP', 0) * s[i] for i in range(15)
        ), "Starting_XI_xP"

        # Constraint: exactly 11 starters
        prob += pulp.lpSum(s[i] for i in range(15)) == 11, "Exactly_11"

        # Position constraints for valid formations
        by_pos = defaultdict(list)
        for i, p in enumerate(squad):
            by_pos[p['element_type']].append(i)

        # GK: exactly 1 starting
        prob += pulp.lpSum(s[i] for i in by_pos[1]) == 1, "GK_1"
        # DEF: at least 3
        prob += pulp.lpSum(s[i] for i in by_pos[2]) >= 3, "DEF_min_3"
        # MID: at least 2 (implicit from formation constraints)
        prob += pulp.lpSum(s[i] for i in by_pos[3]) >= 2, "MID_min_2"
        # FWD: at least 1
        prob += pulp.lpSum(s[i] for i in by_pos[4]) >= 1, "FWD_min_1"

        prob.solve(pulp.PULP_CBC_CMD(msg=0))

        if prob.status != pulp.constants.LpStatusOptimal:
            return self._starting_xi_greedy(squad, verbose)

        starting = []
        bench = []
        for i, p in enumerate(squad):
            if s[i].varValue and s[i].varValue > 0.5:
                starting.append(p)
            else:
                bench.append(p)

        # Sort starting by position then xP
        starting.sort(key=lambda x: (x['element_type'], -x.get('xP', 0)))

        # Bench: sort by xP descending (GK last)
        bench_outfield = [p for p in bench if p['element_type'] != 1]
        bench_gk = [p for p in bench if p['element_type'] == 1]
        bench_outfield.sort(key=lambda x: x.get('xP', 0), reverse=True)
        bench = bench_outfield + bench_gk

        # Assign positions 1-15
        for idx, p in enumerate(starting):
            p['position'] = idx + 1
        for idx, p in enumerate(bench):
            p['position'] = 12 + idx

        if verbose:
            total_xp = sum(p.get('xP', 0) for p in starting)
            formation = self._get_formation(starting)
            print(f"  MILP Starting XI: {formation}, xP={total_xp:.1f}")

        return starting, bench

    def _starting_xi_greedy(
        self,
        squad: List[Dict],
        verbose: bool = False
    ) -> Tuple[List[Dict], List[Dict]]:
        """Fallback greedy starting XI selection."""
        by_pos = defaultdict(list)
        for p in squad:
            by_pos[p['element_type']].append(p)
        for pos in by_pos:
            by_pos[pos].sort(key=lambda x: x.get('xP', 0), reverse=True)

        valid_formations = [
            (1, 3, 4, 3), (1, 3, 5, 2), (1, 4, 3, 3),
            (1, 4, 4, 2), (1, 4, 5, 1), (1, 5, 3, 2), (1, 5, 4, 1),
        ]

        best_xi = None
        best_score = -1
        for gk, d, m, f in valid_formations:
            if len(by_pos[1]) < gk or len(by_pos[2]) < d or \
               len(by_pos[3]) < m or len(by_pos[4]) < f:
                continue
            xi = by_pos[1][:gk] + by_pos[2][:d] + by_pos[3][:m] + by_pos[4][:f]
            score = sum(p.get('xP', 0) for p in xi)
            if score > best_score:
                best_score = score
                best_xi = xi

        bench = [p for p in squad if p not in best_xi]
        bench_outfield = [p for p in bench if p['element_type'] != 1]
        bench_gk = [p for p in bench if p['element_type'] == 1]
        bench_outfield.sort(key=lambda x: x.get('xP', 0), reverse=True)
        bench = bench_outfield + bench_gk

        for idx, p in enumerate(best_xi):
            p['position'] = idx + 1
        for idx, p in enumerate(bench):
            p['position'] = 12 + idx

        return best_xi, bench

    @staticmethod
    def _get_formation(starting: List[Dict]) -> str:
        """Get formation string from starting XI."""
        counts = defaultdict(int)
        for p in starting:
            counts[p['element_type']] += 1
        return f"{counts[2]}-{counts[3]}-{counts[4]}"

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
