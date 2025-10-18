#!/usr/bin/env python3
"""
Log Rotation Script

Rotates and compresses old log files to prevent disk space issues.
Runs weekly via cron (Sunday 04:00).
"""

import sys
import gzip
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import logging

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logger = logging.getLogger('ron_clanker.log_rotation')


def rotate_logs(logs_dir: Path, max_age_days: int = 30, compress: bool = True):
    """
    Rotate log files.

    - Compress logs older than 7 days
    - Delete compressed logs older than max_age_days
    """

    start_time = datetime.now()

    print("\n" + "=" * 80)
    print("LOG ROTATION")
    print("=" * 80)
    print(f"Timestamp: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Log directory: {logs_dir}")

    if not logs_dir.exists():
        print(f"\n⚠️  Log directory does not exist: {logs_dir}")
        return 0

    # Get all log files
    log_files = list(logs_dir.glob('*.log'))

    print(f"\nFound {len(log_files)} log files")

    # Stats
    compressed_count = 0
    deleted_count = 0
    bytes_saved = 0

    # Compress old logs
    if compress:
        print("\n" + "-" * 80)
        print("COMPRESSING OLD LOGS")
        print("-" * 80)

        compress_threshold = datetime.now() - timedelta(days=7)

        for log_file in log_files:
            # Skip if already compressed
            if log_file.suffix == '.gz':
                continue

            # Check modification time
            mtime = datetime.fromtimestamp(log_file.stat().st_mtime)

            if mtime < compress_threshold:
                try:
                    # Compress the file
                    gz_path = log_file.with_suffix(log_file.suffix + '.gz')

                    original_size = log_file.stat().st_size

                    with open(log_file, 'rb') as f_in:
                        with gzip.open(gz_path, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)

                    compressed_size = gz_path.stat().st_size
                    saved = original_size - compressed_size
                    bytes_saved += saved

                    # Remove original
                    log_file.unlink()

                    compressed_count += 1
                    print(f"  ✓ {log_file.name} → {gz_path.name} (saved {saved:,} bytes)")

                except Exception as e:
                    logger.error(f"LogRotation: Error compressing {log_file}: {e}")
                    print(f"  ✗ {log_file.name}: {e}")

    # Delete very old compressed logs
    print("\n" + "-" * 80)
    print("CLEANING UP OLD COMPRESSED LOGS")
    print("-" * 80)

    delete_threshold = datetime.now() - timedelta(days=max_age_days)

    gz_files = list(logs_dir.glob('*.gz'))

    for gz_file in gz_files:
        mtime = datetime.fromtimestamp(gz_file.stat().st_mtime)

        if mtime < delete_threshold:
            try:
                size = gz_file.stat().st_size
                gz_file.unlink()
                deleted_count += 1

                age_days = (datetime.now() - mtime).days
                print(f"  ✓ Deleted {gz_file.name} ({age_days} days old, {size:,} bytes)")

            except Exception as e:
                logger.error(f"LogRotation: Error deleting {gz_file}: {e}")
                print(f"  ✗ {gz_file.name}: {e}")

    if deleted_count == 0:
        print("  No old logs to delete")

    # Summary
    print("\n" + "-" * 80)
    print("SUMMARY")
    print("-" * 80)
    print(f"Compressed: {compressed_count} files")
    print(f"Deleted: {deleted_count} old files")
    print(f"Space saved by compression: {bytes_saved:,} bytes ({bytes_saved / 1024 / 1024:.2f} MB)")

    # Current disk usage
    total_size = sum(f.stat().st_size for f in logs_dir.glob('*') if f.is_file())
    print(f"\nCurrent log directory size: {total_size:,} bytes ({total_size / 1024 / 1024:.2f} MB)")

    duration = (datetime.now() - start_time).total_seconds()

    print("\n" + "=" * 80)
    print("LOG ROTATION COMPLETE")
    print("=" * 80)
    print(f"Duration: {duration:.1f} seconds")
    print(f"Status: SUCCESS")

    return 0


def main():
    """Main entry point."""

    logs_dir = project_root / 'logs'

    try:
        return rotate_logs(logs_dir, max_age_days=30, compress=True)
    except Exception as e:
        logger.error(f"LogRotation: Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        return 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nLog rotation cancelled.")
        sys.exit(1)
