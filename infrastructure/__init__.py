"""
Infrastructure components for Ron Clanker's event-driven architecture.

This package provides the foundational components for the event-driven
multi-agent system:
- Event bus (Redis-based pub/sub)
- Event schemas and base classes
- Base agent implementation
- Publisher/subscriber utilities
"""

from .event_bus import EventBus
from .events import Event, EventType, EventPriority
from .base_agent import BaseAgent

__all__ = [
    'EventBus',
    'Event',
    'EventType',
    'EventPriority',
    'BaseAgent'
]
