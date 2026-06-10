#!/usr/bin/env python3
"""
Dynamic Deadline Scheduler

Checks the FPL API for the next gameweek deadline and schedules
the autonomous pipeline to run at the right time.

Uses `at` (one-shot scheduler) to create a job that fires
6 hours before deadline. Designed to run hourly from cron.

Idempotent: if a job is already scheduled for the correct time,
it won't create a duplicate.

Usage:
    python scripts/schedule_next_deadline.py           # Schedule next deadline
    python scripts/schedule_next_deadline.py --check   # Just show next deadline
    python scripts/schedule_next_deadline.py --hours 4 # Run 4h before (default: 6)
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict

import requests

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
from utils.config import load_config
from utils.gameweek import season_complete_from_events, is_season_complete

logger = logging.getLogger('ron_clanker.deadline_scheduler')

FPL_API_URL = "https://fantasy.premierleague.com/api"
STATE_FILE = project_root / 'data' / '.deadline_scheduler_state.json'
PIPELINE_SCRIPT = project_root / 'scripts' / 'autonomous_gameweek.py'
PYTHON_PATH = project_root / 'venv' / 'bin' / 'python'


def get_next_deadline_from_api() -> Optional[Dict]:
    """
    Fetch next gameweek deadline directly from FPL API.

    Returns dict with: gameweek, deadline_time (ISO string), name
    """
    try:
        resp = requests.get(f"{FPL_API_URL}/bootstrap-static/", timeout=15)
        resp.raise_for_status()
        data = resp.json()

        now = datetime.now(timezone.utc)

        for event in data.get('events', []):
            if event.get('finished'):
                continue

            deadline_str = event.get('deadline_time', '')
            if not deadline_str:
                continue

            deadline_dt = datetime.fromisoformat(deadline_str.replace('Z', '+00:00'))
            if deadline_dt > now:
                return {
                    'gameweek': event['id'],
                    'deadline_time': deadline_str,
                    'deadline_dt': deadline_dt,
                    'name': event.get('name', f"Gameweek {event['id']}"),
                }

        return None

    except Exception as e:
        logger.error(f"Failed to fetch deadline from FPL API: {e}")
        return None


def is_season_complete_from_api() -> Optional[bool]:
    """
    Check the FPL API directly for season completion.

    Returns:
        True/False per season_complete_from_events, or None if the API
        could not be reached (so the caller can fall back to the DB rather
        than mistaking a network failure for the season ending).
    """
    try:
        resp = requests.get(f"{FPL_API_URL}/bootstrap-static/", timeout=15)
        resp.raise_for_status()
        return season_complete_from_events(resp.json().get('events', []))
    except Exception as e:
        logger.warning(f"Could not check season status from FPL API: {e}")
        return None


def get_next_deadline_from_db() -> Optional[Dict]:
    """Fallback: get deadline from local database."""
    try:
        db = Database()
        rows = db.execute_query("""
            SELECT id, deadline_time, name
            FROM gameweeks
            WHERE finished = 0
            ORDER BY id ASC
            LIMIT 1
        """)
        if rows:
            from dateutil.parser import parse as parse_dt
            deadline_dt = parse_dt(rows[0]['deadline_time'])
            return {
                'gameweek': rows[0]['id'],
                'deadline_time': rows[0]['deadline_time'],
                'deadline_dt': deadline_dt,
                'name': rows[0]['name'],
            }
    except Exception as e:
        logger.warning(f"Could not read deadline from DB: {e}")

    return None


def load_scheduler_state() -> Dict:
    """Load the scheduler's state (what's already scheduled)."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_scheduler_state(state: Dict):
    """Persist scheduler state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def schedule_with_systemd(run_time_utc: datetime, gameweek: int) -> bool:
    """
    Schedule the autonomous pipeline using a systemd transient timer.

    Creates a one-shot user timer that fires at the specified time.
    Preferred method on Arch Linux (no cron/at needed).

    Args:
        run_time_utc: When to run (UTC)
        gameweek: Target gameweek (for logging)

    Returns:
        True if scheduled successfully
    """
    run_time_local = run_time_utc.astimezone()
    time_str = run_time_local.strftime('%Y-%m-%d %H:%M:%S')
    unit_name = f"ron-gw{gameweek}-pipeline"

    log_file = project_root / 'logs' / f'autonomous_gw{gameweek}_{run_time_local.strftime("%Y%m%d_%H%M")}.log'
    (project_root / 'logs').mkdir(exist_ok=True)

    # Stop any existing timer for this gameweek
    subprocess.run(
        ['systemctl', '--user', 'stop', f'{unit_name}.timer'],
        capture_output=True, text=True,
    )

    # Create the transient timer using systemd-run
    # --on-calendar schedules it, --unit names it, --user runs as user
    cmd = [
        'systemd-run', '--user',
        '--unit', unit_name,
        f'--on-calendar={run_time_local.strftime("%Y-%m-%d %H:%M:%S")}',
        '--description', f'Ron Clanker autonomous pipeline GW{gameweek}',
        '/bin/bash', '-c',
        (
            f'cd {project_root} && '
            f'{PYTHON_PATH} {PIPELINE_SCRIPT} --gameweek {gameweek} '
            f'>> {log_file} 2>&1'
        ),
    ]

    logger.info(f"Scheduling systemd transient timer: {unit_name} at {time_str}")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if proc.returncode == 0:
            logger.info(f"systemd timer scheduled for {time_str}")
            return True
        else:
            # systemd-run may output on stderr even on success
            if 'Timer' in proc.stderr or proc.returncode == 0:
                logger.info(f"systemd timer scheduled for {time_str}")
                return True
            logger.error(f"systemd-run failed: {proc.stderr}")
            return False

    except Exception as e:
        logger.error(f"Failed to schedule systemd timer: {e}")
        return False


def schedule_deadline(hours_before: float = 6.0, check_only: bool = False) -> int:
    """
    Main scheduling logic.

    1. Fetch next deadline from FPL API (or DB fallback)
    2. Calculate when to run pipeline (hours_before deadline)
    3. Schedule using `at` (preferred) or one-shot cron (fallback)

    Args:
        hours_before: Hours before deadline to trigger pipeline
        check_only: Just display info, don't schedule

    Returns:
        0 on success, 1 on error
    """
    # Get next deadline
    deadline_info = get_next_deadline_from_api()
    if not deadline_info:
        deadline_info = get_next_deadline_from_db()

    if not deadline_info:
        # No upcoming deadline. Distinguish "season is over" (expected, no
        # action needed) from a transient data problem (genuine error).
        season_over = is_season_complete_from_api()
        if season_over is None:  # API unreachable - fall back to local DB
            season_over = is_season_complete(Database())

        if season_over:
            logger.info("Season complete - no further gameweeks. Nothing to schedule.")
            print("\n🏁 Season complete. No upcoming gameweek - nothing to schedule.")
            print("   Disable ron-deadline-check.timer over the break, or leave it;")
            print("   it will pick up GW1 automatically when next season's fixtures load.")
            return 0

        logger.error("Cannot determine next gameweek deadline")
        print("Cannot determine next deadline. Run collect_fpl_data.py first.")
        return 1

    gw = deadline_info['gameweek']
    deadline_dt = deadline_info['deadline_dt']
    now = datetime.now(timezone.utc)
    hours_until = (deadline_dt - now).total_seconds() / 3600

    print(f"\nNext deadline: {deadline_info['name']}")
    print(f"  Gameweek: {gw}")
    print(f"  Deadline: {deadline_dt.strftime('%Y-%m-%d %H:%M %Z')}")
    print(f"  Hours until: {hours_until:.1f}")

    # Calculate run time
    run_time_utc = deadline_dt - timedelta(hours=hours_before)
    # Convert to local time for scheduling
    run_time_local = run_time_utc.astimezone()

    print(f"  Pipeline trigger: {run_time_local.strftime('%Y-%m-%d %H:%M %Z')} ({hours_before}h before)")

    if check_only:
        return 0

    # Check if already scheduled
    state = load_scheduler_state()
    if (state.get('gameweek') == gw and
            state.get('scheduled') and
            state.get('run_time') == run_time_utc.isoformat()):
        print(f"\nAlready scheduled for GW{gw}")
        logger.info(f"GW{gw} pipeline already scheduled for {run_time_local}")
        return 0

    # Check if run time is in the past
    if run_time_utc < now:
        if deadline_dt > now:
            # Deadline hasn't passed but trigger time has - run NOW
            print(f"\nTrigger time already passed but deadline is in {hours_until:.1f}h")
            print("Running pipeline immediately...")

            log_file = project_root / 'logs' / f'autonomous_gw{gw}_immediate.log'
            cmd = [
                str(PYTHON_PATH), str(PIPELINE_SCRIPT),
                '--gameweek', str(gw),
            ]
            # Run in background
            subprocess.Popen(
                cmd,
                stdout=open(log_file, 'w'),
                stderr=subprocess.STDOUT,
                cwd=str(project_root),
            )

            save_scheduler_state({
                'gameweek': gw,
                'scheduled': True,
                'run_time': now.isoformat(),
                'method': 'immediate',
                'timestamp': now.isoformat(),
            })

            print(f"Pipeline started in background. Logs: {log_file}")
            return 0
        else:
            print(f"\nDeadline has already passed ({-hours_until:.1f}h ago). Nothing to schedule.")
            return 0

    # Schedule it
    print(f"\nScheduling pipeline for {run_time_local.strftime('%Y-%m-%d %H:%M')}...")

    scheduled = schedule_with_systemd(run_time_utc, gw)
    method = 'systemd'

    if scheduled:
        save_scheduler_state({
            'gameweek': gw,
            'scheduled': True,
            'run_time': run_time_utc.isoformat(),
            'method': method,
            'timestamp': now.isoformat(),
        })
        print(f"Scheduled (via {method}) for GW{gw}")
        logger.info(f"GW{gw} pipeline scheduled via {method} at {run_time_local}")
        return 0
    else:
        logger.error(f"Failed to schedule GW{gw} pipeline")
        print("Failed to schedule. Check logs.")
        return 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Schedule the autonomous pipeline for next FPL deadline'
    )
    parser.add_argument('--check', action='store_true',
                        help='Just display next deadline (don\'t schedule)')
    parser.add_argument('--hours', type=float, default=6.0,
                        help='Hours before deadline to trigger pipeline (default: 6)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Verbose logging')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
    )

    sys.exit(schedule_deadline(
        hours_before=args.hours,
        check_only=args.check,
    ))
