"""
Gameweek deadline calculation and monitoring.

Fetches real FPL gameweek deadlines and determines when to trigger
planning events (48h, 24h, 6h before deadline).
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import json
import asyncio

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.data_collector import DataCollector


class GameweekScheduler:
    """Manages gameweek deadline tracking and event scheduling."""

    def __init__(self):
        self.data_collector = DataCollector()
        self.cache_file = project_root / 'data' / 'gameweek_deadlines.json'
        self._loop = None

    def get_next_deadline(self):
        """
        Get the next gameweek deadline.

        Returns:
            dict: {
                'gameweek': int,
                'deadline': datetime,
                'hours_until': float
            } or None if no upcoming deadline
        """
        try:
            # Get bootstrap data (using asyncio)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                bootstrap = loop.run_until_complete(self.data_collector.fetch_bootstrap_data())
            finally:
                loop.run_until_complete(self.data_collector.close())
                loop.close()

            events = bootstrap.get('events', [])

            now = datetime.now()

            # Find next unfinished gameweek
            for event in events:
                if event['finished']:
                    continue

                deadline_str = event['deadline_time']
                # Parse FPL datetime format: "2025-10-19T11:00:00Z"
                deadline = datetime.fromisoformat(deadline_str.replace('Z', '+00:00'))

                # Convert to local time (assumes UK timezone)
                if deadline.tzinfo:
                    deadline = deadline.replace(tzinfo=None)

                hours_until = (deadline - now).total_seconds() / 3600

                return {
                    'gameweek': event['id'],
                    'deadline': deadline,
                    'deadline_str': deadline_str,
                    'hours_until': hours_until,
                    'is_finished': event['finished'],
                    'name': event['name']
                }

            return None

        except Exception as e:
            print(f"Error fetching next deadline: {e}")
            return None

    def should_trigger_planning(self, hours_before):
        """
        Check if we should trigger planning event.

        Args:
            hours_before: How many hours before deadline (48, 24, or 6)

        Returns:
            dict: Deadline info if we should trigger, None otherwise
        """
        deadline_info = self.get_next_deadline()

        if not deadline_info:
            return None

        hours_until = deadline_info['hours_until']

        # Check if we're within the trigger window
        # Trigger window is 1 hour (so we don't miss it between checks)
        lower_bound = hours_before - 1
        upper_bound = hours_before + 1

        if lower_bound <= hours_until <= upper_bound:
            return deadline_info

        return None

    def get_planning_status(self):
        """
        Get current planning status for all trigger points.

        Returns:
            dict: Status of each planning trigger point
        """
        deadline_info = self.get_next_deadline()

        if not deadline_info:
            return {
                'next_deadline': None,
                'triggers': {
                    '48h': False,
                    '24h': False,
                    '6h': False
                }
            }

        hours_until = deadline_info['hours_until']

        return {
            'next_deadline': deadline_info,
            'triggers': {
                '48h': 47 <= hours_until <= 49,
                '24h': 23 <= hours_until <= 25,
                '6h': 5 <= hours_until <= 7
            },
            'time_until_next_trigger': self._time_until_next_trigger(hours_until)
        }

    def _time_until_next_trigger(self, hours_until):
        """Calculate time until next trigger point."""
        if hours_until > 49:
            return hours_until - 48
        elif hours_until > 25:
            return hours_until - 24
        elif hours_until > 7:
            return hours_until - 6
        else:
            return 0

    def save_deadline_cache(self):
        """Cache deadline info to avoid excessive API calls."""
        deadline_info = self.get_next_deadline()

        if deadline_info:
            cache_data = {
                'cached_at': datetime.now().isoformat(),
                'deadline': deadline_info
            }

            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)

    def load_deadline_cache(self):
        """Load cached deadline info if fresh (< 6 hours old)."""
        try:
            if not self.cache_file.exists():
                return None

            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)

            cached_at = datetime.fromisoformat(cache_data['cached_at'])
            age = (datetime.now() - cached_at).total_seconds() / 3600

            # Cache valid for 6 hours
            if age < 6:
                return cache_data['deadline']

        except Exception as e:
            print(f"Error loading cache: {e}")

        return None


if __name__ == '__main__':
    # Test the scheduler
    scheduler = GameweekScheduler()

    print("Gameweek Deadline Monitor")
    print("=" * 60)

    status = scheduler.get_planning_status()

    if status['next_deadline']:
        deadline = status['next_deadline']
        print(f"\nNext Gameweek: {deadline['gameweek']}")
        print(f"Deadline: {deadline['deadline']}")
        print(f"Hours until deadline: {deadline['hours_until']:.1f}")
        print(f"\nPlanning Triggers:")
        print(f"  48h before: {'🔔 TRIGGER NOW' if status['triggers']['48h'] else '⏳ Not yet'}")
        print(f"  24h before: {'🔔 TRIGGER NOW' if status['triggers']['24h'] else '⏳ Not yet'}")
        print(f"  6h before:  {'🔔 TRIGGER NOW' if status['triggers']['6h'] else '⏳ Not yet'}")

        if status['time_until_next_trigger'] > 0:
            print(f"\nNext trigger in: {status['time_until_next_trigger']:.1f} hours")
    else:
        print("\nNo upcoming gameweek found")
