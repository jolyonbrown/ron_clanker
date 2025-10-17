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
from .manager import ManagerAgent
from .transfer_strategy import TransferStrategyAgent

__version__ = "0.1.0"

__all__ = [
    'BaseAgent',
    'DCAnalyst',
    'FixtureAnalyst',
    'XGAnalyst',
    'ValueAnalyst',
    'DataCollector',
    'PlayerValuationAgent',
    'ManagerAgent',
    'TransferStrategyAgent',
]
