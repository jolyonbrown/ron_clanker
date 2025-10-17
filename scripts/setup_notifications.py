#!/usr/bin/env python3
"""
Setup Notification System

Interactive script to configure Discord/Slack notifications.
"""

import sys
import os
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_webhook(webhook_url: str) -> bool:
    """Test if webhook URL works."""
    try:
        import requests

        test_message = {
            "content": "✅ Ron Clanker notification test - webhook is working!",
            "embeds": [{
                "title": "Test Notification",
                "description": "If you see this, notifications are configured correctly.",
                "color": 2067276  # Green
            }]
        }

        response = requests.post(webhook_url, json=test_message, timeout=10)

        return response.status_code in [200, 204]

    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


def main():
    """Setup notifications."""

    print("\n" + "=" * 80)
    print("RON CLANKER - NOTIFICATION SETUP")
    print("=" * 80)

    print("\nThis script will help you configure notifications for:")
    print("  • Team selections (Ron's announcements)")
    print("  • Price changes")
    print("  • System alerts")
    print("  • Health check failures")

    # Check if .env exists
    env_file = project_root / ".env"
    env_example = project_root / "config" / "notifications.env.example"

    if not env_example.exists():
        print(f"\n❌ Example file not found: {env_example}")
        return 1

    # Read existing .env if it exists
    existing_webhook = None
    if env_file.exists():
        print(f"\n✓ Found existing .env file")
        with open(env_file, 'r') as f:
            for line in f:
                if line.startswith('WEBHOOK_URL='):
                    existing_webhook = line.split('=', 1)[1].strip()
                    if existing_webhook:
                        print(f"  Current webhook: {existing_webhook[:50]}...")

    # Prompt for service choice
    print("\n" + "-" * 80)
    print("CHOOSE NOTIFICATION SERVICE")
    print("-" * 80)
    print("\n1. Discord")
    print("2. Slack")
    print("3. Other webhook service")
    print("4. Skip setup (disable notifications)")

    choice = input("\nEnter choice (1-4): ").strip()

    webhook_url = None

    if choice == '1':
        print("\n📱 Discord Setup:")
        print("  1. Open Discord server settings")
        print("  2. Select 'Integrations' → 'Webhooks'")
        print("  3. Click 'New Webhook'")
        print("  4. Copy the webhook URL")
        print()
        webhook_url = input("Paste Discord webhook URL: ").strip()

    elif choice == '2':
        print("\n💬 Slack Setup:")
        print("  1. Go to https://api.slack.com/apps")
        print("  2. Create new app → 'Incoming Webhooks'")
        print("  3. Activate incoming webhooks")
        print("  4. Add new webhook to workspace")
        print("  5. Copy the webhook URL")
        print()
        webhook_url = input("Paste Slack webhook URL: ").strip()

    elif choice == '3':
        print("\n🔗 Other Webhook Service:")
        print("  Your webhook service should accept JSON payloads")
        print("  Compatible with Discord webhook format")
        print()
        webhook_url = input("Paste webhook URL: ").strip()

    elif choice == '4':
        print("\n⚠️  Notifications will be disabled")
        webhook_url = ""

    else:
        print("\n❌ Invalid choice")
        return 1

    # Test webhook if provided
    if webhook_url:
        print("\n" + "-" * 80)
        print("TESTING WEBHOOK")
        print("-" * 80)

        print("\nSending test message...")

        if test_webhook(webhook_url):
            print("✅ Test successful! Check your Discord/Slack channel.")
        else:
            print("❌ Test failed - webhook may not be configured correctly")
            confirm = input("\nContinue anyway? (yes/no): ").strip().lower()
            if confirm != 'yes':
                print("Setup cancelled")
                return 1

    # Write .env file
    print("\n" + "-" * 80)
    print("SAVING CONFIGURATION")
    print("-" * 80)

    # Read example and update
    with open(env_example, 'r') as f:
        env_content = f.read()

    # Replace WEBHOOK_URL
    lines = []
    for line in env_content.split('\n'):
        if line.startswith('WEBHOOK_URL='):
            lines.append(f'WEBHOOK_URL={webhook_url}')
        else:
            lines.append(line)

    # Write to .env
    with open(env_file, 'w') as f:
        f.write('\n'.join(lines))

    print(f"✓ Configuration saved to: {env_file}")

    # Add to shell profile
    print("\n" + "-" * 80)
    print("ENVIRONMENT SETUP")
    print("-" * 80)

    print("\nTo use notifications, ensure WEBHOOK_URL is exported:")
    print(f"  export WEBHOOK_URL='{webhook_url}'")
    print("\nOr add to your shell profile (~/.bashrc or ~/.zshrc):")
    print(f"  echo 'export WEBHOOK_URL=\"{webhook_url}\"' >> ~/.bashrc")

    # Summary
    print("\n" + "=" * 80)
    print("SETUP COMPLETE")
    print("=" * 80)

    if webhook_url:
        print("\n✅ Notifications enabled!")
        print("\nTest notifications:")
        print("  venv/bin/python -c \"")
        print("  from utils.notifications import NotificationService")
        print("  ns = NotificationService()")
        print("  ns.send_alert('Test', 'Ron Clanker is operational', 'info')")
        print("  \"")
    else:
        print("\n⚠️  Notifications disabled")
        print("Run this script again to enable notifications")

    print("\n" + "=" * 80)

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nSetup cancelled.")
        sys.exit(0)
