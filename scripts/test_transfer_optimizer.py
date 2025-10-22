#!/usr/bin/env python3
"""
Test Transfer Optimizer

Usage:
    python scripts/test_transfer_optimizer.py [start_gw] [horizon] [free_transfers] [bank]

Examples:
    python scripts/test_transfer_optimizer.py 10 4 1 5.0
    python scripts/test_transfer_optimizer.py 11 6 2 0.0
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.transfer_optimizer import TransferOptimizer
from intelligence.chip_strategy import ChipStrategyAnalyzer
from data.database import Database
from utils.config import load_config


def test_transfer_optimizer(
    start_gw: int = 10,
    horizon: int = 4,
    free_transfers: int = 1,
    bank: float = 5.0
):
    """
    Test the transfer optimizer with given parameters.

    Args:
        start_gw: Starting gameweek for analysis
        horizon: Number of gameweeks to look ahead
        free_transfers: Number of free transfers available
        bank: Money in the bank (£m)
    """

    db = Database()

    # Get current team from latest gameweek
    latest_gw = db.execute_query("""
        SELECT MAX(gameweek) as max_gw FROM my_team
    """)[0]['max_gw']

    current_team = db.execute_query('''
        SELECT mt.*, p.web_name, p.element_type, p.now_cost
        FROM my_team mt
        JOIN players p ON mt.player_id = p.id
        WHERE mt.gameweek = ?
    ''', (latest_gw,))

    print("="*80)
    print("TRANSFER OPTIMIZER TEST")
    print("="*80)
    print(f"Current team from GW{latest_gw}: {len(current_team)} players")
    print(f"Analysis period: GW{start_gw} to GW{start_gw + horizon - 1}")
    print(f"Free transfers: {free_transfers}")
    print(f"Bank: £{bank:.1f}m")
    print("="*80)

    # Get Ron's team and league IDs
    config = load_config()
    ron_entry_id = config.get('team_id')
    league_id = config.get('league_id')

    print(f"\nRon's Entry ID: {ron_entry_id}")
    print(f"League ID: {league_id}")

    # Initialize chip strategy analyzer
    chip_strategy = ChipStrategyAnalyzer(database=db, league_intel_service=None)

    # Initialize optimizer with chip strategy
    optimizer = TransferOptimizer(database=db, chip_strategy=chip_strategy)

    # Run optimization
    result = optimizer.optimize_transfers(
        current_team=current_team,
        ml_predictions={},  # Generated internally
        current_gw=start_gw,
        free_transfers=free_transfers,
        bank=bank,
        horizon=horizon,
        ron_entry_id=ron_entry_id,
        league_id=league_id
    )

    print("\n" + "="*80)
    print("FINAL DECISION")
    print("="*80)
    print(f"\nRecommendation: {result['recommendation']}")
    print(f"\nReasoning:\n{result['reasoning']}")

    if result['best_transfer']:
        best = result['best_transfer']
        print(f"\nBest Transfer:")
        print(f"  {best.player_out_name} ({best.position_name}) → {best.player_in_name}")
        print(f"  Total expected gain: {best.total_gain:+.1f} points over {horizon} gameweeks")
        print(f"  Average per GW: {best.avg_gain_per_gw:+.1f} pts/GW")

    return result


if __name__ == "__main__":
    # Parse command line arguments
    start_gw = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    horizon = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    free_transfers = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    bank = float(sys.argv[4]) if len(sys.argv) > 4 else 5.0

    test_transfer_optimizer(start_gw, horizon, free_transfers, bank)
