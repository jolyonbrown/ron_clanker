#!/usr/bin/env python3
"""
Autonomous Gameweek Pipeline

THE single script for Ron Clanker's fully autonomous operation.
Runs the complete pre-deadline workflow end-to-end:

  1. Collect latest FPL data
  2. Run pre-deadline team selection (transfers, captain, formation)
  3. Submit team to FPL via authenticated API
  4. Verify submission
  5. Announce on Slack

Designed to be triggered by cron via the deadline scheduler.
Can also be run manually for testing.

Usage:
    python scripts/autonomous_gameweek.py                    # Auto-detect GW
    python scripts/autonomous_gameweek.py --gameweek 32      # Specific GW
    python scripts/autonomous_gameweek.py --dry-run          # Don't submit to FPL
    python scripts/autonomous_gameweek.py --skip-collect     # Skip data collection
    python scripts/autonomous_gameweek.py --skip-select      # Skip selection (submit existing draft)
"""

import argparse
import asyncio
import logging
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from utils.config import load_config

LOG_DIR = project_root / 'logs'
SCRIPTS_DIR = project_root / 'scripts'

logger = logging.getLogger('ron_clanker.autonomous')


def setup_logging(verbose: bool = False):
    """Configure logging to both file and console."""
    LOG_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = LOG_DIR / f'autonomous_gw_{timestamp}.log'

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout),
        ]
    )
    logger.info(f"Logging to {log_file}")


def get_python_path() -> str:
    """Get path to Python executable in venv."""
    venv_python = project_root / 'venv' / 'bin' / 'python'
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def run_script(script_name: str, args: list = None, timeout: int = None,
               deadline_dt=None) -> Tuple[bool, str]:
    """
    Run a subscript and return (success, output).

    No artificial timeout by default — selection/optimization runs to
    completion. If a caller explicitly passes `timeout`, it's honored
    (used for short, non-critical tasks like announcements). The
    `deadline_dt` parameter is accepted for back-compat but ignored:
    the pipeline is scheduled far in advance of the FPL deadline, so
    capping selection artificially just risks killing the work before
    it produces a decision (happened on GW33 2026-04-18).
    """
    del deadline_dt  # intentionally unused; see docstring

    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        return False, f"Script not found: {script_path}"

    cmd = [get_python_path(), str(script_path)]
    if args:
        cmd.extend(args)

    timeout_desc = f"timeout={timeout}s" if timeout else "no timeout"
    logger.info(f"Running: {' '.join(cmd)} ({timeout_desc})")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(project_root),
        )
        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"

        if result.returncode == 0:
            return True, output
        else:
            logger.error(f"{script_name} exited with code {result.returncode}")
            return False, output

    except subprocess.TimeoutExpired:
        return False, f"Script timed out after {timeout}s"
    except Exception as e:
        return False, f"Failed to run script: {e}"


def get_next_gameweek(db: Database) -> Optional[int]:
    """Get next unfinished gameweek from database."""
    rows = db.execute_query("""
        SELECT id FROM gameweeks
        WHERE finished = 0
        ORDER BY id ASC
        LIMIT 1
    """)
    return rows[0]['id'] if rows else None


def get_deadline_time(db: Database, gameweek: int) -> Optional[str]:
    """Get deadline time for a gameweek."""
    rows = db.execute_query(
        "SELECT deadline_time FROM gameweeks WHERE id = ?",
        (gameweek,)
    )
    return rows[0]['deadline_time'] if rows else None


def send_slack_notification(message: str, gameweek: int = 0):
    """Send a status notification to Slack."""
    try:
        from notifications.slack import SlackNotifier
        notifier = SlackNotifier()
        if notifier.enabled:
            notifier.send_message(f"[Ron Autonomous GW{gameweek}] {message}")
    except Exception as e:
        logger.warning(f"Could not send Slack notification: {e}")


async def run_pipeline(args):
    """Run the full autonomous pipeline."""
    start_time = datetime.now(timezone.utc)
    db = Database()

    # Determine gameweek
    if args.gameweek:
        gameweek = args.gameweek
    else:
        gameweek = get_next_gameweek(db)
        if not gameweek:
            logger.error("Cannot determine next gameweek. Run collect_fpl_data.py first.")
            return 1

    deadline = get_deadline_time(db, gameweek)

    print("\n" + "=" * 70)
    print("RON CLANKER - AUTONOMOUS GAMEWEEK PIPELINE")
    print("=" * 70)
    print(f"Gameweek: {gameweek}")
    print(f"Deadline: {deadline or 'Unknown'}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("=" * 70)

    deadline_dt = None
    if deadline:
        from dateutil.parser import parse as parse_dt
        deadline_dt = parse_dt(deadline)
        hours_until = (deadline_dt - start_time).total_seconds() / 3600
        print(f"Time to deadline: {hours_until:.1f} hours")

        if hours_until < 0:
            logger.warning(f"Deadline has PASSED ({-hours_until:.1f}h ago)")
            if not args.force:
                print("\nDeadline passed. Use --force to run anyway.")
                return 1
        elif hours_until < 0.5:
            logger.warning("Less than 30 minutes to deadline!")

    # ===== STEP 1: Collect FPL Data =====
    print("\n" + "-" * 70)
    print("STEP 1: COLLECT FPL DATA")
    print("-" * 70)

    if args.skip_collect:
        print("Skipped (--skip-collect)")
    else:
        success, output = run_script('collect_fpl_data.py', deadline_dt=deadline_dt)
        if success:
            print("Data collection complete")
            logger.info("Step 1 complete: FPL data collected")
        else:
            logger.warning(f"Data collection had issues (continuing): {output[-200:]}")
            print("Data collection had issues - continuing with existing data")

    # ===== STEP 2: Team Selection =====
    print("\n" + "-" * 70)
    print("STEP 2: TEAM SELECTION")
    print("-" * 70)

    if args.skip_select:
        print("Skipped (--skip-select)")
        # Verify draft exists
        draft = db.get_draft_team(gameweek)
        if not draft:
            logger.error(f"No existing draft for GW{gameweek}")
            print(f"No existing draft for GW{gameweek}. Cannot skip selection.")
            return 1
        print(f"Using existing draft: {len(draft)} players")
    else:
        selection_args = ['--gameweek', str(gameweek), '--no-notify']
        success, output = run_script('pre_deadline_selection.py', selection_args,
                                     deadline_dt=deadline_dt)
        if success:
            print("Team selection complete")
            logger.info("Step 2 complete: team selected")
        else:
            logger.error(f"Team selection FAILED:\n{output[-500:]}")
            print("Team selection FAILED")
            send_slack_notification(
                f"ALERT: Pre-deadline selection FAILED for GW{gameweek}. "
                f"Manual intervention needed!",
                gameweek
            )
            return 1

    # Show draft summary
    draft = db.get_draft_team(gameweek)
    if draft:
        captain = next((p for p in draft if p['is_captain']), None)
        starters = [p for p in draft if p['position'] <= 11]
        bench = [p for p in draft if p['position'] > 11]

        print(f"\nDraft summary:")
        print(f"  Starters: {', '.join(p['web_name'] for p in sorted(starters, key=lambda x: x['position']))}")
        print(f"  Bench: {', '.join(p['web_name'] for p in sorted(bench, key=lambda x: x['position']))}")
        print(f"  Captain: {captain['web_name'] if captain else '???'}")

    draft_transfers = db.get_draft_transfers(gameweek)
    if draft_transfers:
        print(f"  Transfers: {len(draft_transfers)}")
        for t in draft_transfers:
            print(f"    OUT: {t['player_out_name']} -> IN: {t['player_in_name']}")

    # ===== STEP 3: Submit to FPL =====
    print("\n" + "-" * 70)
    print("STEP 3: SUBMIT TO FPL")
    print("-" * 70)

    from services.fpl_submission import FPLSubmissionClient, SubmissionResult

    client = FPLSubmissionClient(dry_run=args.dry_run)

    if not await asyncio.to_thread(client.login):
        logger.error("FPL login failed")
        print("FPL login FAILED")
        send_slack_notification(
            f"ALERT: FPL login failed for GW{gameweek}. Check credentials!",
            gameweek
        )
        return 1

    print("Logged in to FPL")

    result = client.submit_gameweek_from_draft(gameweek)

    if result.success:
        print(f"Submission: {result.message}")
        logger.info(f"Step 3 complete: {result.message}")
    else:
        logger.error(f"FPL submission FAILED: {result.message}")
        print(f"Submission FAILED: {result.message}")
        send_slack_notification(
            f"ALERT: FPL submission FAILED for GW{gameweek}: {result.message}",
            gameweek
        )
        return 1

    # ===== STEP 4: Verify Submission =====
    print("\n" + "-" * 70)
    print("STEP 4: VERIFY SUBMISSION")
    print("-" * 70)

    if args.dry_run:
        print("Skipped (dry run)")
    else:
        import time
        time.sleep(3)  # Brief pause before verification
        verification = client.verify_submission(gameweek)
        if verification['verified']:
            print("VERIFIED: FPL team matches draft")
            logger.info("Step 4 complete: submission verified")
        else:
            logger.warning(f"Verification MISMATCH: {verification}")
            print(f"WARNING: Verification mismatch - {verification}")
            send_slack_notification(
                f"WARNING: GW{gameweek} submission verification mismatch. "
                f"Check FPL website!",
                gameweek
            )

    # ===== STEP 5: Announce on Slack =====
    print("\n" + "-" * 70)
    print("STEP 5: SLACK ANNOUNCEMENT")
    print("-" * 70)

    if args.dry_run:
        print("Skipped (dry run)")
    else:
        announce_args = ['--gameweek', str(gameweek), '--from-database']
        if args.dry_run:
            announce_args.append('--dry-run')
        success, output = run_script('send_team_announcement.py', announce_args, timeout=120)
        if success:
            print("Slack announcement sent")
            logger.info("Step 5 complete: Slack announcement sent")
        else:
            logger.warning(f"Slack announcement failed (non-fatal): {output[-200:]}")
            print("Slack announcement had issues (non-fatal)")

    # ===== COMPLETE =====
    duration = (datetime.now(timezone.utc) - start_time).total_seconds()

    print("\n" + "=" * 70)
    print("AUTONOMOUS PIPELINE COMPLETE")
    print("=" * 70)
    print(f"Gameweek: {gameweek}")
    print(f"Duration: {duration:.1f}s")
    print(f"Result: {result.message}")
    print("=" * 70)

    logger.info(f"Autonomous pipeline complete for GW{gameweek} in {duration:.1f}s")
    return 0


def parse_args():
    parser = argparse.ArgumentParser(
        description="Ron Clanker's Autonomous Gameweek Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This script runs the entire pre-deadline workflow:
  collect data -> select team -> submit to FPL -> verify -> announce

Designed to be triggered automatically by the deadline scheduler.
        """
    )
    parser.add_argument('-g', '--gameweek', type=int,
                        help='Target gameweek (default: auto-detect)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Run selection but don\'t submit to FPL')
    parser.add_argument('--skip-collect', action='store_true',
                        help='Skip FPL data collection (use existing data)')
    parser.add_argument('--skip-select', action='store_true',
                        help='Skip team selection (submit existing draft)')
    parser.add_argument('--force', action='store_true',
                        help='Run even if deadline has passed')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Verbose logging')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    setup_logging(args.verbose)

    try:
        exit_code = asyncio.run(run_pipeline(args))
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nPipeline cancelled.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error in autonomous pipeline: {e}", exc_info=True)
        print(f"\nFATAL ERROR: {e}")
        traceback.print_exc()

        # Try to alert on Slack even if everything else failed
        try:
            send_slack_notification(f"FATAL: Autonomous pipeline crashed: {e}")
        except Exception:
            pass

        sys.exit(1)
