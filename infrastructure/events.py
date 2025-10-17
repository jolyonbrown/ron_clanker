"""
Event definitions and schemas for the event-driven architecture.

Events are the primary communication mechanism between agents.
Each event has a type, priority, payload, and metadata.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
import json
import uuid


class EventPriority(Enum):
    """Event priority levels for queue ordering."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class EventType(Enum):
    """All possible event types in the system."""

    # System events
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_HEALTH_CHECK = "system.health_check"

    # Gameweek events
    GAMEWEEK_DEADLINE_APPROACHING = "gameweek.deadline_approaching"
    GAMEWEEK_PLANNING = "gameweek.planning"  # Triggered at 48h/24h/6h before deadline
    GAMEWEEK_STARTED = "gameweek.started"
    GAMEWEEK_COMPLETED = "gameweek.completed"

    # Data events
    DATA_REFRESH_REQUESTED = "data.refresh_requested"
    DATA_UPDATED = "data.updated"
    PLAYER_DATA_UPDATED = "data.player_updated"
    FIXTURE_DATA_UPDATED = "data.fixture_updated"

    # Price events
    PRICE_CHECK = "price.check"  # Daily price monitoring
    PRICE_CHANGE_DETECTED = "price.change_detected"
    PRICE_RISE_PREDICTED = "price.rise_predicted"
    PRICE_FALL_PREDICTED = "price.fall_predicted"

    # Team events
    TEAM_SELECTION_REQUESTED = "team.selection_requested"
    TEAM_SELECTED = "team.selected"
    TRANSFER_RECOMMENDED = "team.transfer_recommended"
    TRANSFER_EXECUTED = "team.transfer_executed"
    CAPTAIN_SELECTED = "team.captain_selected"
    CHIP_USED = "team.chip_used"

    # Player events
    PLAYER_INJURY = "player.injury"
    PLAYER_SUSPENDED = "player.suspended"
    PLAYER_PRICE_LOCKED = "player.price_locked"
    PLAYER_RETURNING = "player.returning"

    # Analysis events
    ANALYSIS_REQUESTED = "analysis.requested"
    ANALYSIS_COMPLETED = "analysis.completed"
    FIXTURE_ANALYSIS_COMPLETED = "analysis.fixture_completed"
    VALUATION_ANALYSIS_COMPLETED = "analysis.valuation_completed"
    DC_ANALYSIS_COMPLETED = "analysis.dc_completed"
    XG_ANALYSIS_COMPLETED = "analysis.xg_completed"
    VALUE_RANKINGS_COMPLETED = "analysis.value_rankings_completed"

    # Decision events
    DECISION_REQUIRED = "decision.required"
    DECISION_MADE = "decision.made"

    # Notification events
    NOTIFICATION_INFO = "notification.info"
    NOTIFICATION_WARNING = "notification.warning"
    NOTIFICATION_ERROR = "notification.error"

    # Intelligence events (Scout agent)
    INTELLIGENCE_DETECTED = "intelligence.detected"  # Generic intelligence event
    INJURY_INTELLIGENCE = "intelligence.injury"  # Injury detected from external source
    ROTATION_RISK = "intelligence.rotation_risk"  # Rotation warning
    SUSPENSION_INTELLIGENCE = "intelligence.suspension"  # Suspension detected
    LINEUP_LEAK = "intelligence.lineup_leak"  # Early team news
    PRESS_CONFERENCE_UPDATE = "intelligence.press_conference"  # Manager quotes

    # Chip events
    CHIP_RECOMMENDATION = "chip.recommendation"  # Terry's chip timing advice


@dataclass
class Event:
    """
    Base event class for all system events.

    Events are immutable once created and should contain all
    necessary information for handlers to process them.
    """

    event_type: EventType
    payload: Dict[str, Any]

    # Metadata
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    priority: EventPriority = EventPriority.NORMAL
    source: Optional[str] = None
    correlation_id: Optional[str] = None  # For tracking related events

    # Retry logic
    retry_count: int = 0
    max_retries: int = 3

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization."""
        data = asdict(self)
        # Convert enums to strings
        data['event_type'] = self.event_type.value
        data['priority'] = self.priority.value
        # Convert datetime to ISO format
        data['timestamp'] = self.timestamp.isoformat()
        return data

    def to_json(self) -> str:
        """Serialize event to JSON."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Event':
        """Deserialize event from dictionary."""
        # Convert string back to enum
        data['event_type'] = EventType(data['event_type'])
        data['priority'] = EventPriority(data['priority'])
        # Convert ISO string back to datetime
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> 'Event':
        """Deserialize event from JSON."""
        return cls.from_dict(json.loads(json_str))

    def increment_retry(self) -> None:
        """Increment retry counter."""
        self.retry_count += 1

    def can_retry(self) -> bool:
        """Check if event can be retried."""
        return self.retry_count < self.max_retries

    def __str__(self) -> str:
        return f"Event({self.event_type.value}, source={self.source}, id={self.event_id[:8]})"


# Convenience functions for creating common events

def create_gameweek_deadline_event(
    gameweek: int,
    hours_until_deadline: int,
    deadline_time: datetime
) -> Event:
    """Create a gameweek deadline approaching event."""
    return Event(
        event_type=EventType.GAMEWEEK_DEADLINE_APPROACHING,
        priority=EventPriority.HIGH if hours_until_deadline <= 6 else EventPriority.NORMAL,
        payload={
            'gameweek': gameweek,
            'hours_until_deadline': hours_until_deadline,
            'deadline_time': deadline_time.isoformat()
        },
        source='scheduler'
    )


def create_price_change_event(
    player_id: int,
    player_name: str,
    old_price: float,
    new_price: float,
    change_type: str
) -> Event:
    """Create a price change detected event."""
    return Event(
        event_type=EventType.PRICE_CHANGE_DETECTED,
        priority=EventPriority.HIGH,
        payload={
            'player_id': player_id,
            'player_name': player_name,
            'old_price': old_price,
            'new_price': new_price,
            'change_type': change_type,  # 'rise' or 'fall'
            'change_amount': new_price - old_price
        },
        source='price_monitor'
    )


def create_analysis_request_event(
    analysis_type: str,
    gameweek: int,
    parameters: Dict[str, Any] = None
) -> Event:
    """Create an analysis request event."""
    return Event(
        event_type=EventType.ANALYSIS_REQUESTED,
        priority=EventPriority.NORMAL,
        payload={
            'analysis_type': analysis_type,
            'gameweek': gameweek,
            'parameters': parameters or {}
        },
        source='manager'
    )


def create_data_refresh_event(
    data_type: str = 'all',
    force: bool = False
) -> Event:
    """Create a data refresh request event."""
    return Event(
        event_type=EventType.DATA_REFRESH_REQUESTED,
        priority=EventPriority.HIGH if force else EventPriority.NORMAL,
        payload={
            'data_type': data_type,  # 'all', 'players', 'fixtures', 'teams'
            'force': force
        },
        source='scheduler'
    )


def create_notification_event(
    level: str,
    message: str,
    details: Dict[str, Any] = None
) -> Event:
    """Create a notification event."""
    event_type_map = {
        'info': EventType.NOTIFICATION_INFO,
        'warning': EventType.NOTIFICATION_WARNING,
        'error': EventType.NOTIFICATION_ERROR
    }

    priority_map = {
        'info': EventPriority.LOW,
        'warning': EventPriority.NORMAL,
        'error': EventPriority.HIGH
    }

    return Event(
        event_type=event_type_map.get(level, EventType.NOTIFICATION_INFO),
        priority=priority_map.get(level, EventPriority.LOW),
        payload={
            'level': level,
            'message': message,
            'details': details or {}
        },
        source='system'
    )
