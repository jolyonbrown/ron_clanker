"""
Ron Clanker's FPL Management System - Agent Framework

This package contains all specialist agents that contribute to autonomous
FPL decision-making.
"""

from .base_agent import BaseAgent
from .dc_analyst import DCAnalyst
from .fixture_analyst import FixtureAnalyst
from .xg_analyst import XGAnalyst
from .value_analyst import ValueAnalyst
from .data_collector import DataCollector
from .player_valuation import PlayerValuationAgent
from .manager_agent_v2 import RonManager  # Event-driven manager
from .transfer_strategy import TransferStrategyAgent
from .chip_strategist import ChipStrategistAgent
from .learning_agent import LearningAgent
from .scout import ScoutAgent

__version__ = "0.2.0"  # Bumped for event-driven architecture

__all__ = [
    'BaseAgent',
    'DCAnalyst',
    'FixtureAnalyst',
    'XGAnalyst',
    'ValueAnalyst',
    'DataCollector',
    'PlayerValuationAgent',
    'RonManager',  # Preferred manager (event-driven)
    'TransferStrategyAgent',
    'ChipStrategistAgent',
    'LearningAgent',
    'ScoutAgent',
]
