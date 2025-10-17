#!/usr/bin/env python3
"""
System Health Check

Verifies that Ron Clanker's core systems are operational.
Runs every 6 hours to catch issues early.
"""

import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.database import Database
import logging

logger = logging.getLogger('ron_clanker.health_check')


def check_database():
    """Check database connectivity and health."""
    try:
        db = Database()

        # Check if we can query
        result = db.execute_query("SELECT 1 as test")
        if result and result[0]['test'] == 1:
            return True, "Database OK"

        return False, "Database query failed"

    except Exception as e:
        return False, f"Database error: {e}"


def check_bootstrap_data():
    """Check if we have recent FPL data."""
    try:
        db = Database()

        age = db.execute_query("""
            SELECT (julianday('now') - julianday(MAX(fetched_at))) * 24 as hours_old
            FROM bootstrap_data
        """)

        if not age or age[0]['hours_old'] is None:
            return False, "No bootstrap data found"

        hours_old = age[0]['hours_old']

        if hours_old > 48:
            return False, f"Bootstrap data is {hours_old:.1f} hours old (stale)"

        return True, f"Bootstrap data is {hours_old:.1f} hours old"

    except Exception as e:
        return False, f"Bootstrap check error: {e}"


def check_intelligence_cache():
    """Check if Scout is gathering intelligence."""
    try:
        db = Database()

        recent = db.execute_query("""
            SELECT COUNT(*) as count
            FROM intelligence_cache
            WHERE timestamp > datetime('now', '-2 days')
        """)

        if not recent or recent[0]['count'] == 0:
            return False, "No recent intelligence (48h)"

        count = recent[0]['count']
        return True, f"{count} intelligence items in last 48h"

    except Exception as e:
        return False, f"Intelligence check error: {e}"


def check_disk_space():
    """Check available disk space."""
    try:
        import shutil
        stats = shutil.disk_usage(project_root)

        free_gb = stats.free / (1024 ** 3)
        percent_free = (stats.free / stats.total) * 100

        if percent_free < 10:
            return False, f"Low disk space: {free_gb:.1f} GB free ({percent_free:.1f}%)"

        return True, f"Disk space OK: {free_gb:.1f} GB free"

    except Exception as e:
        return False, f"Disk space check error: {e}"


def check_log_files():
    """Check if log files are growing too large."""
    try:
        logs_dir = project_root / "logs"

        if not logs_dir.exists():
            return False, "Logs directory not found"

        total_size = 0
        large_files = []

        for log_file in logs_dir.glob("*.log"):
            size_mb = log_file.stat().st_size / (1024 ** 2)
            total_size += size_mb

            if size_mb > 100:  # More than 100 MB
                large_files.append(f"{log_file.name} ({size_mb:.1f} MB)")

        if large_files:
            return False, f"Large log files: {', '.join(large_files)}"

        return True, f"Logs OK: {total_size:.1f} MB total"

    except Exception as e:
        return False, f"Log file check error: {e}"


def main():
    """Run health checks."""

    print("\n" + "=" * 80)
    print("RON CLANKER - SYSTEM HEALTH CHECK")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    checks = [
        ("Database", check_database),
        ("Bootstrap Data", check_bootstrap_data),
        ("Intelligence Cache", check_intelligence_cache),
        ("Disk Space", check_disk_space),
        ("Log Files", check_log_files),
    ]

    results = []
    all_passed = True

    print("\n" + "-" * 80)
    print("RUNNING CHECKS")
    print("-" * 80)

    for name, check_func in checks:
        try:
            passed, message = check_func()
            results.append((name, passed, message))

            status = "✓" if passed else "✗"
            print(f"{status} {name}: {message}")

            if not passed:
                all_passed = False

        except Exception as e:
            logger.error(f"HealthCheck: Error in {name}: {e}", exc_info=True)
            results.append((name, False, f"Check failed: {e}"))
            print(f"✗ {name}: Check failed: {e}")
            all_passed = False

    # Summary
    print("\n" + "=" * 80)
    print("HEALTH CHECK SUMMARY")
    print("=" * 80)

    passed_count = sum(1 for _, passed, _ in results if passed)
    total_count = len(results)

    print(f"\nPassed: {passed_count}/{total_count}")

    if all_passed:
        print("Status: ✓ ALL SYSTEMS OPERATIONAL")
        return 0
    else:
        print("Status: ✗ ISSUES DETECTED")
        print("\nFailed checks:")
        for name, passed, message in results:
            if not passed:
                print(f"  • {name}: {message}")

        return 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nHealth check cancelled.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"HealthCheck: Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
