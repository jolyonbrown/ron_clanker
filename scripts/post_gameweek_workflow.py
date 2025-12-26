#!/usr/bin/env python3
"""
Post-Gameweek Workflow Orchestrator

THE single script to run after each gameweek completes.
Orchestrates all post-GW tasks in the correct order.

Tasks:
1. Refresh FPL data (players, teams, fixtures)
2. Collect post-GW data (player history, league standings, rival picks)
3. Sync Ron's actual team and score
4. Generate post-GW performance review
5. Update ML models with new data (optional)
6. Prepare for next gameweek

Usage:
    python scripts/post_gameweek_workflow.py           # Auto-detect completed GW
    python scripts/post_gameweek_workflow.py --gw 15   # Specific gameweek
    python scripts/post_gameweek_workflow.py --skip-ml # Skip ML update
    python scripts/post_gameweek_workflow.py --force   # Force even if GW not finished
"""

import sys
import subprocess
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from utils.config import load_config

logger = logging.getLogger('ron_clanker.post_gw_workflow')

# Script paths
SCRIPTS_DIR = project_root / 'scripts'


def get_python_path() -> str:
    """Get path to Python executable in venv."""
    venv_python = project_root / 'venv' / 'bin' / 'python'
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def run_script(script_name: str, args: list = None, description: str = None) -> Tuple[bool, str]:
    """
    Run a script and return success status and output.

    Returns:
        Tuple of (success: bool, output: str)
    """
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        return False, f"Script not found: {script_path}"

    cmd = [get_python_path(), str(script_path)]
    if args:
        cmd.extend(args)

    desc = description or script_name
    logger.info(f"PostGWWorkflow: Running {desc}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,  # 15 minute timeout
            cwd=str(project_root)
        )

        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"

        success = result.returncode == 0

        if not success:
            logger.warning(f"PostGWWorkflow: {desc} returned non-zero: {result.returncode}")

        return success, output

    except subprocess.TimeoutExpired:
        return False, f"Script timed out after 600 seconds"
    except Exception as e:
        return False, f"Error running script: {e}"


def get_completed_gameweek(db: Database, force: bool = False) -> Optional[int]:
    """
    Get the most recently completed gameweek.

    Returns:
        Gameweek number if one is finished, None otherwise
    """
    # Get current gameweek status
    result = db.execute_query("""
        SELECT id, finished, is_current
        FROM gameweeks
        WHERE finished = 1 OR is_current = 1
        ORDER BY id DESC
        LIMIT 2
    """)

    if not result:
        logger.error("PostGWWorkflow: No gameweeks found in database")
        return None

    # Find most recent finished GW
    for gw in result:
        if gw['finished']:
            return gw['id']

    # If force mode, return current even if not finished
    if force:
        current = next((gw for gw in result if gw['is_current']), None)
        if current:
            logger.warning(f"PostGWWorkflow: Force mode - using current GW{current['id']} (not finished)")
            return current['id']

    logger.info("PostGWWorkflow: No completed gameweek found")
    return None


def check_already_processed(db: Database, gameweek: int) -> bool:
    """Check if this gameweek has already been processed."""
    result = db.execute_query("""
        SELECT COUNT(*) as cnt
        FROM player_gameweek_history
        WHERE gameweek = ?
    """, (gameweek,))

    count = result[0]['cnt'] if result else 0

    # If we have >100 records, assume it's been processed
    return count > 100


def main():
    parser = argparse.ArgumentParser(
        description='Post-gameweek workflow orchestrator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/post_gameweek_workflow.py           # Auto-detect completed GW
  python scripts/post_gameweek_workflow.py --gw 15   # Process specific gameweek
  python scripts/post_gameweek_workflow.py --skip-ml # Skip ML model update
  python scripts/post_gameweek_workflow.py --force   # Process even if not finished
        """
    )
    parser.add_argument('--gw', type=int, help='Specific gameweek to process')
    parser.add_argument('--force', action='store_true',
                       help='Force processing even if GW not finished')
    parser.add_argument('--skip-ml', action='store_true',
                       help='Skip ML model update step')
    parser.add_argument('--skip-review', action='store_true',
                       help='Skip performance review step')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Verbose output')

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    start_time = datetime.now()

    print("\n" + "=" * 80)
    print("POST-GAMEWEEK WORKFLOW")
    print("=" * 80)
    print(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Initialize
    db = Database()
    config = load_config()
    team_id = config.get('team_id')

    # Track results
    results = {
        'fpl_data_refresh': None,
        'post_gw_collection': None,
        'ron_team_sync': None,
        'performance_review': None,
        'threshold_learning': None,
        'ml_update': None
    }

    # Determine which gameweek to process
    if args.gw:
        gameweek = args.gw
        print(f"\n📋 Processing specified gameweek: GW{gameweek}")
    else:
        gameweek = get_completed_gameweek(db, force=args.force)
        if not gameweek:
            print("\n✅ No completed gameweek needs processing")
            print("   Use --gw N to specify a gameweek, or --force to process current")
            return 0
        print(f"\n📋 Auto-detected completed gameweek: GW{gameweek}")

    # Check if already processed (unless force)
    if not args.force and check_already_processed(db, gameweek):
        print(f"\n✅ GW{gameweek} already processed (found existing data)")
        print("   Use --force to reprocess")
        return 0

    print(f"\n🔄 Starting post-GW{gameweek} workflow...")

    # =========================================================================
    # STEP 1: Refresh FPL Data
    # =========================================================================
    print("\n" + "-" * 80)
    print("STEP 1: REFRESH FPL DATA")
    print("-" * 80)

    success, output = run_script(
        'collect_fpl_data.py',
        description='FPL data refresh'
    )
    results['fpl_data_refresh'] = success

    if success:
        print("✅ FPL data refreshed successfully")
        if args.verbose:
            print(output[-500:] if len(output) > 500 else output)
    else:
        print("❌ FPL data refresh failed")
        print(output[-500:] if len(output) > 500 else output)

    # =========================================================================
    # STEP 2: Collect Post-GW Data
    # =========================================================================
    print("\n" + "-" * 80)
    print("STEP 2: COLLECT POST-GAMEWEEK DATA")
    print("-" * 80)

    script_args = ['--force'] if args.force else []
    if args.verbose:
        script_args.append('--verbose')

    success, output = run_script(
        'collect_post_gameweek_data.py',
        args=script_args,
        description='Post-GW data collection'
    )
    results['post_gw_collection'] = success

    if success:
        print("✅ Post-GW data collected successfully")
        # Show key stats from output
        for line in output.split('\n'):
            if any(x in line for x in ['Collected:', 'Player history', 'League', 'Rival']):
                print(f"   {line.strip()}")
    else:
        print("❌ Post-GW data collection failed")
        print(output[-500:] if len(output) > 500 else output)

    # =========================================================================
    # STEP 3: Sync Ron's Team
    # =========================================================================
    print("\n" + "-" * 80)
    print("STEP 3: SYNC RON'S TEAM")
    print("-" * 80)

    if not team_id:
        print("⚠️  No team_id configured - skipping Ron's team sync")
        results['ron_team_sync'] = None
    else:
        success, output = run_script(
            'track_ron_team.py',
            args=['--sync'],
            description="Ron's team sync"
        )
        results['ron_team_sync'] = success

        if success:
            print("✅ Ron's team synced successfully")
            # Show Ron's GW score if available
            for line in output.split('\n'):
                if any(x in line for x in ['GW Points:', 'Total Points:', 'Overall Rank:']):
                    print(f"   {line.strip()}")
        else:
            print("❌ Ron's team sync failed")
            if args.verbose:
                print(output[-500:] if len(output) > 500 else output)

    # =========================================================================
    # STEP 4: Performance Review
    # =========================================================================
    if not args.skip_review:
        print("\n" + "-" * 80)
        print("STEP 4: PERFORMANCE REVIEW")
        print("-" * 80)

        success, output = run_script(
            'post_gameweek_review.py',
            args=['--gw', str(gameweek)],
            description='Performance review'
        )
        results['performance_review'] = success

        if success:
            print("✅ Performance review completed")
            # Show key metrics
            for line in output.split('\n'):
                if any(x in line for x in ['RMSE:', 'MAE:', 'Captain:', 'Bias:']):
                    print(f"   {line.strip()}")
        else:
            print("⚠️  Performance review had issues")
            if args.verbose:
                print(output[-500:] if len(output) > 500 else output)
    else:
        print("\n⏭️  Skipping performance review (--skip-review)")

    # =========================================================================
    # STEP 5: Update Transfer Thresholds (Learning)
    # =========================================================================
    print("\n" + "-" * 80)
    print("STEP 5: UPDATE TRANSFER THRESHOLDS (LEARNING)")
    print("-" * 80)

    try:
        from learning.performance_tracker import PerformanceTracker
        tracker = PerformanceTracker(db)

        learning_result = tracker.run_threshold_learning(min_sample_size=3)

        if 'error' in learning_result:
            print(f"⏭️  Threshold learning skipped: {learning_result['error']}")
            results['threshold_learning'] = None
        elif learning_result.get('adjustments_made', 0) > 0:
            print("✅ Transfer thresholds updated")
            print(f"   Adjustments made: {learning_result['adjustments_made']}")
            for pos_id, threshold in learning_result['new_thresholds'].items():
                pos_name = {0: 'ALL', 1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}.get(pos_id, str(pos_id))
                old_val = learning_result['previous_thresholds'].get(pos_id, 2.0)
                if old_val != threshold:
                    print(f"     {pos_name}: {old_val:.2f} → {threshold:.2f}")
            results['threshold_learning'] = True
        else:
            print("✅ Thresholds analyzed - no adjustments needed")
            results['threshold_learning'] = True
    except Exception as e:
        print(f"⚠️  Threshold learning failed: {e}")
        results['threshold_learning'] = False
        if args.verbose:
            import traceback
            traceback.print_exc()

    # =========================================================================
    # STEP 6: Update ML Models (Optional)
    # =========================================================================
    if not args.skip_ml:
        print("\n" + "-" * 80)
        print("STEP 6: UPDATE ML MODELS")
        print("-" * 80)

        # Check if update script exists
        update_script = SCRIPTS_DIR / 'update_ml_models.py'
        if update_script.exists():
            success, output = run_script(
                'update_ml_models.py',
                description='ML model update'
            )
            results['ml_update'] = success

            if success:
                print("✅ ML models updated successfully")
            else:
                print("⚠️  ML model update had issues")
                if args.verbose:
                    print(output[-500:] if len(output) > 500 else output)
        else:
            print("⏭️  ML update script not found - skipping")
            results['ml_update'] = None
    else:
        print("\n⏭️  Skipping ML update (--skip-ml)")

    # =========================================================================
    # STEP 7: TRANSFORMER TRAINING (Optional - GPU required)
    # =========================================================================
    results['transformer_training'] = None

    if not args.skip_ml:
        print("\n" + "=" * 80)
        print("STEP 7: TRANSFORMER TRAINING")
        print("=" * 80)

        transformer_script = scripts_dir / 'train_transformer.py'
        if transformer_script.exists():
            print("🤖 Training transformer model with latest data...")
            print("   (This improves predictions with learned player embeddings)")

            success, output = run_script(transformer_script, ['--epochs', '30'])
            results['transformer_training'] = success

            if success:
                print("✅ Transformer trained successfully")
            else:
                print("⚠️  Transformer training had issues (predictions still work without it)")
                if args.verbose:
                    print(output[-500:] if len(output) > 500 else output)
        else:
            print("⏭️  Transformer training script not found - skipping")
            results['transformer_training'] = None

    # =========================================================================
    # SUMMARY
    # =========================================================================
    duration = (datetime.now() - start_time).total_seconds()

    print("\n" + "=" * 80)
    print("WORKFLOW COMPLETE")
    print("=" * 80)
    print(f"Gameweek: {gameweek}")
    print(f"Duration: {duration:.1f}s")
    print()

    # Results summary
    success_count = sum(1 for v in results.values() if v is True)
    fail_count = sum(1 for v in results.values() if v is False)
    skip_count = sum(1 for v in results.values() if v is None)

    status_map = {True: '✅', False: '❌', None: '⏭️'}

    print("Results:")
    print(f"  FPL Data Refresh:     {status_map[results['fpl_data_refresh']]}")
    print(f"  Post-GW Collection:   {status_map[results['post_gw_collection']]}")
    print(f"  Ron's Team Sync:      {status_map[results['ron_team_sync']]}")
    print(f"  Performance Review:   {status_map[results['performance_review']]}")
    print(f"  Threshold Learning:   {status_map[results['threshold_learning']]}")
    print(f"  ML Model Update:      {status_map[results['ml_update']]}")
    print(f"  Transformer Training: {status_map[results['transformer_training']]}")
    print()
    print(f"Summary: {success_count} succeeded, {fail_count} failed, {skip_count} skipped")

    # Next steps
    print("\n" + "-" * 80)
    print("NEXT STEPS")
    print("-" * 80)

    # Get next gameweek
    next_gw_result = db.execute_query("""
        SELECT id, deadline_time
        FROM gameweeks
        WHERE finished = 0
        ORDER BY id ASC
        LIMIT 1
    """)

    if next_gw_result:
        next_gw = next_gw_result[0]
        print(f"Next gameweek: GW{next_gw['id']}")
        print(f"Deadline: {next_gw['deadline_time']}")
        print()
        print("Before deadline, run:")
        print(f"  python scripts/pre_deadline_selection.py --gameweek {next_gw['id']}")

    logger.info(f"PostGWWorkflow: Complete - GW{gameweek}, Duration: {duration:.1f}s")

    # Return non-zero if any critical steps failed
    if results['fpl_data_refresh'] is False or results['post_gw_collection'] is False:
        return 1
    return 0


if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nWorkflow cancelled.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"PostGWWorkflow: Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
