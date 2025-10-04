"""
Configuration settings for Ron Clanker's FPL system.
"""

import os
from pathlib import Path
from typing import Optional

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Database configuration
DATABASE_PATH = os.getenv('DATABASE_PATH', str(BASE_DIR / 'data' / 'ron_clanker.db'))

# MCP Configuration
MCP_SERVER_URL = os.getenv('MCP_SERVER_URL', 'http://localhost:8000')
MCP_ENABLED = os.getenv('MCP_ENABLED', 'false').lower() == 'true'

# FPL API Configuration (fallback if MCP not available)
FPL_API_BASE_URL = 'https://fantasy.premierleague.com/api'

# Logging configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_FILE = os.getenv('LOG_FILE', str(BASE_DIR / 'logs' / 'ron_clanker.log'))

# Agent configuration
AGENT_SETTINGS = {
    'data_collector': {
        'update_interval_hours': 6,
        'cache_enabled': True
    },
    'player_valuation': {
        'min_minutes_threshold': 180,  # Minimum minutes for consideration
        'defensive_contribution_weight': 0.5,  # Weight for DC boost
    },
    'manager': {
        'risk_tolerance': 'conservative',  # conservative, balanced, aggressive
        'max_hits_per_gameweek': 1,  # Max -4 hits to take
    }
}

# Budget constraints
INITIAL_BUDGET = 1000  # £100.0m in FPL units

# Feature flags
FEATURES = {
    'use_ml_predictions': False,  # ML models not yet implemented
    'automatic_price_tracking': True,
    'defensive_contribution_boost': True,  # Our competitive edge!
}

# Scheduled task configuration
TASKS = {
    'daily_data_update': {
        'enabled': True,
        'hour': 6,  # 6 AM
        'minute': 0
    },
    'price_change_check': {
        'enabled': True,
        'hour': 2,  # 2 AM (after price changes)
        'minute': 0
    },
    'gameweek_planning': {
        'enabled': True,
        'hours_before_deadline': 24
    }
}


def get_database_url() -> str:
    """Get database connection URL."""
    return f"sqlite:///{DATABASE_PATH}"


def ensure_directories():
    """Ensure all required directories exist."""
    directories = [
        BASE_DIR / 'data',
        BASE_DIR / 'logs',
        BASE_DIR / 'ml' / 'models',
        BASE_DIR / 'rules'
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


# Initialize on import
ensure_directories()
