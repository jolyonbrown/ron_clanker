"""
Configuration Loader

Loads configuration from .env file and ron_config.json.
.env contains sensitive data (team IDs, tokens, passwords)
ron_config.json contains non-sensitive settings (safe to commit to git)
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional

# Try to import python-dotenv, but don't fail if not installed
try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False

# Project root
PROJECT_ROOT = Path(__file__).parent.parent


def load_config() -> Dict[str, Any]:
    """
    Load complete configuration from .env and ron_config.json.

    Returns:
        Combined configuration dict with all settings
    """
    config = {}

    # Load .env file if available
    if DOTENV_AVAILABLE:
        env_path = PROJECT_ROOT / '.env'
        if env_path.exists():
            load_dotenv(env_path)

    # Load from environment variables (populated by .env or system)
    config['team_id'] = int(os.getenv('FPL_TEAM_ID', 0)) or None
    config['team_name'] = os.getenv('FPL_TEAM_NAME', '')
    config['league_id'] = int(os.getenv('FPL_LEAGUE_ID', 0)) or None

    # Telegram
    config['telegram_bot_token'] = os.getenv('TELEGRAM_BOT_TOKEN', '')
    config['telegram_chat_id'] = os.getenv('TELEGRAM_CHAT_ID', '')

    # Database
    config['db_password'] = os.getenv('DB_PASSWORD', '')
    config['postgres_url'] = os.getenv('POSTGRES_URL', '')
    config['redis_url'] = os.getenv('REDIS_URL', 'redis://localhost:6379')

    # FPL API
    config['fpl_api_url'] = os.getenv('FPL_API_URL', 'https://fantasy.premierleague.com/api')
    config['fpl_email'] = os.getenv('FPL_EMAIL', '')
    config['fpl_password'] = os.getenv('FPL_PASSWORD', '')

    # System
    config['log_level'] = os.getenv('LOG_LEVEL', 'INFO')
    config['mcp_enabled'] = os.getenv('MCP_ENABLED', 'false').lower() == 'true'

    # Load ron_config.json (non-sensitive settings)
    config_file = PROJECT_ROOT / 'config' / 'ron_config.json'
    if config_file.exists():
        with open(config_file) as f:
            json_config = json.load(f)

            # Merge non-sensitive settings
            config['manager_name'] = json_config.get('manager_name', 'Ron Clanker')
            config['season'] = json_config.get('season', '2025/26')
            config['entry_gameweek'] = json_config.get('entry_gameweek', 8)

            # ML config
            config['ml_config'] = json_config.get('ml_config', {})

            # Decision config
            config['decision_config'] = json_config.get('decision_config', {})

            # Notification config
            config['notification_config'] = json_config.get('notification_config', {})

    return config


def get_team_id() -> Optional[int]:
    """Get FPL team ID from environment."""
    team_id = os.getenv('FPL_TEAM_ID')
    return int(team_id) if team_id else None


def get_league_id() -> Optional[int]:
    """Get league ID from environment."""
    league_id = os.getenv('FPL_LEAGUE_ID')
    return int(league_id) if league_id else None


def get_telegram_token() -> str:
    """Get Telegram bot token from environment."""
    return os.getenv('TELEGRAM_BOT_TOKEN', '')


def get_telegram_chat_id() -> str:
    """Get Telegram chat ID from environment."""
    return os.getenv('TELEGRAM_CHAT_ID', '')


def check_config() -> Dict[str, bool]:
    """
    Check which configuration items are set.

    Returns:
        Dict with boolean status for each config item
    """
    if DOTENV_AVAILABLE:
        load_dotenv(PROJECT_ROOT / '.env')

    return {
        'team_id': bool(os.getenv('FPL_TEAM_ID')),
        'league_id': bool(os.getenv('FPL_LEAGUE_ID')),
        'telegram_bot_token': bool(os.getenv('TELEGRAM_BOT_TOKEN')),
        'telegram_chat_id': bool(os.getenv('TELEGRAM_CHAT_ID')),
        'db_password': bool(os.getenv('DB_PASSWORD')),
    }


def print_config_status():
    """Print configuration status (for debugging)."""
    status = check_config()

    print("Configuration Status:")
    print("=" * 50)

    for key, is_set in status.items():
        symbol = "✅" if is_set else "❌"
        print(f"{symbol} {key:25s}: {'SET' if is_set else 'NOT SET'}")

    print("=" * 50)

    if not DOTENV_AVAILABLE:
        print("\n⚠️  python-dotenv not installed")
        print("   Install with: pip install python-dotenv")

    if not all(status.values()):
        print("\n⚠️  Some configuration missing!")
        print("   Copy .env.example to .env and fill in values")


if __name__ == '__main__':
    # Test configuration loading
    print_config_status()
    print("\nFull config:")
    import pprint
    config = load_config()
    # Don't print sensitive data!
    safe_config = {k: v for k, v in config.items()
                   if not any(secret in k.lower() for secret in ['token', 'password', 'key'])}
    pprint.pprint(safe_config)
