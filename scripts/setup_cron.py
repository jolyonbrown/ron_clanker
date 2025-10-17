#!/usr/bin/env python3
"""
Setup Cron Jobs for Ron Clanker

Interactive script to configure and install cron jobs for autonomous operation.
"""

import sys
import subprocess
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def get_current_crontab():
    """Get current crontab entries."""
    try:
        result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout
        return ""
    except Exception as e:
        print(f"⚠️  Could not read current crontab: {e}")
        return ""


def main():
    """Setup cron jobs for automated operation."""

    print("\n" + "=" * 80)
    print("RON CLANKER - CRON JOB SETUP")
    print("=" * 80)

    print("\nThis script will help you set up automated scheduling for Ron Clanker.")
    print("The system will run autonomously without manual intervention.")

    # Check if cron is available
    try:
        subprocess.run(['which', 'crontab'], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        print("\n❌ ERROR: crontab command not found")
        print("Cron may not be installed on this system.")
        print("Install with: sudo apt-get install cron")
        return 1

    # Check project path
    print(f"\nProject directory: {project_root}")

    # Check for example crontab
    example_crontab = project_root / "config" / "crontab.example"
    if not example_crontab.exists():
        print(f"\n❌ ERROR: {example_crontab} not found")
        return 1

    # Read example
    with open(example_crontab, 'r') as f:
        example_content = f.read()

    # Replace PROJECT_PATH
    configured_content = example_content.replace(
        'PROJECT_PATH=/home/jolyon/ron_clanker',
        f'PROJECT_PATH={project_root}'
    )

    # Create configured version
    configured_crontab = project_root / "config" / "crontab"
    with open(configured_crontab, 'w') as f:
        f.write(configured_content)

    print(f"\n✓ Created configured crontab: {configured_crontab}")

    # Show current crontab
    current = get_current_crontab()
    if current:
        print("\n" + "-" * 80)
        print("CURRENT CRONTAB")
        print("-" * 80)
        print(current)
        print("-" * 80)

        # Check if Ron Clanker jobs already exist
        if 'ron_clanker' in current or 'daily_scout.py' in current:
            print("\n⚠️  WARNING: Ron Clanker jobs may already be installed")
            print("Installing again will create duplicates.")

    # Show what will be installed
    print("\n" + "-" * 80)
    print("JOBS TO BE INSTALLED")
    print("-" * 80)

    # Extract just the job lines
    jobs = [line for line in configured_content.split('\n')
            if line and not line.startswith('#') and not line.startswith('\n')]

    if jobs:
        for i, job in enumerate(jobs, 1):
            if job.strip():
                print(f"{i}. {job[:80]}...")
    else:
        print("No jobs found (crontab contains only comments)")

    # Ask for confirmation
    print("\n" + "=" * 80)
    print("INSTALLATION OPTIONS")
    print("=" * 80)
    print("\n1. Install cron jobs (replaces current crontab)")
    print("2. Append to existing crontab (keeps current jobs)")
    print("3. Show configured crontab (don't install)")
    print("4. Cancel")

    choice = input("\nEnter choice (1-4): ").strip()

    if choice == '1':
        # Replace current crontab
        print("\n⚠️  This will REPLACE your current crontab!")
        confirm = input("Are you sure? (yes/no): ").strip().lower()

        if confirm == 'yes':
            try:
                subprocess.run(['crontab', str(configured_crontab)], check=True)
                print("\n✓ Cron jobs installed successfully!")
            except subprocess.CalledProcessError as e:
                print(f"\n❌ Error installing crontab: {e}")
                return 1

    elif choice == '2':
        # Append to existing
        print("\nAppending Ron Clanker jobs to existing crontab...")

        merged = current + "\n\n" + configured_content

        # Write to temp file
        temp_crontab = project_root / "config" / "crontab.merged"
        with open(temp_crontab, 'w') as f:
            f.write(merged)

        try:
            subprocess.run(['crontab', str(temp_crontab)], check=True)
            print("✓ Jobs appended successfully!")
        except subprocess.CalledProcessError as e:
            print(f"❌ Error installing crontab: {e}")
            return 1

    elif choice == '3':
        # Just show
        print("\n" + "-" * 80)
        print("CONFIGURED CRONTAB")
        print("-" * 80)
        print(configured_content)
        print("-" * 80)
        print(f"\nSaved to: {configured_crontab}")
        print("To install manually: crontab config/crontab")

    else:
        print("\nCancelled.")
        return 0

    # Verify installation
    print("\n" + "-" * 80)
    print("VERIFICATION")
    print("-" * 80)

    new_crontab = get_current_crontab()
    if 'daily_scout.py' in new_crontab:
        print("✓ Ron Clanker jobs are installed")
    else:
        print("⚠️  Could not verify installation")

    print("\nTo view installed jobs: crontab -l")
    print("To remove all jobs: crontab -r")
    print("To edit jobs: crontab -e")

    # Show next steps
    print("\n" + "=" * 80)
    print("NEXT STEPS")
    print("=" * 80)
    print("""
1. Monitor Logs:
   tail -f logs/cron_scout.log
   tail -f logs/cron_deadline.log

2. Test Jobs Manually:
   venv/bin/python scripts/daily_scout.py
   venv/bin/python scripts/pre_deadline_selection.py

3. Configure Notifications:
   Set WEBHOOK_URL environment variable for Discord/Slack alerts
   export WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK"

4. Verify Schedule:
   Check FPL deadline times and adjust cron schedule if needed
   Typical: Friday 18:30 or Saturday 11:00 UK time

5. Database Backups:
   Ensure backups run weekly (Sunday 03:00)
   Check: ls -lh backups/

Ron Clanker is now autonomous!
    """)

    print("=" * 80)

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nSetup cancelled.")
        sys.exit(0)
