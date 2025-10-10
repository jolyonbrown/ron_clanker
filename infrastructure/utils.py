"""
Utility functions and decorators for event-driven infrastructure.

Provides convenience functions for common operations like:
- Event handler decorators
- Async context managers
- Event filtering utilities
- Debugging helpers
"""

import asyncio
import logging
from functools import wraps
from typing import Callable, List, Optional
from contextlib import asynccontextmanager

from .event_bus import EventBus, get_event_bus
from .events import Event, EventType, EventPriority

logger = logging.getLogger(__name__)


def event_handler(*event_types: EventType):
    """
    Decorator for marking methods as event handlers.

    Usage:
        @event_handler(EventType.PLAYER_DATA_UPDATED, EventType.FIXTURE_DATA_UPDATED)
        async def handle_data_update(self, event: Event):
            # Process the event
            pass
    """
    def decorator(func: Callable):
        func._handles_events = list(event_types)
        return func
    return decorator


def get_event_handlers(obj) -> dict:
    """
    Extract all event handler methods from an object.

    Returns:
        Dictionary mapping EventType to handler methods
    """
    handlers = {}
    for attr_name in dir(obj):
        attr = getattr(obj, attr_name)
        if hasattr(attr, '_handles_events'):
            for event_type in attr._handles_events:
                if event_type not in handlers:
                    handlers[event_type] = []
                handlers[event_type].append(attr)
    return handlers


def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    """
    Decorator to retry async functions on failure.

    Args:
        max_retries: Maximum number of retry attempts
        delay: Delay between retries in seconds
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries} failed for "
                            f"{func.__name__}: {e}. Retrying..."
                        )
                        await asyncio.sleep(delay * (attempt + 1))
                    else:
                        logger.error(
                            f"All {max_retries} attempts failed for {func.__name__}"
                        )
            raise last_exception
        return wrapper
    return decorator


async def wait_for_event(
    event_bus: EventBus,
    event_type: EventType,
    timeout: float = 30.0,
    filter_func: Optional[Callable[[Event], bool]] = None
) -> Optional[Event]:
    """
    Wait for a specific event to be published.

    Useful for testing and synchronization.

    Args:
        event_bus: The event bus to listen on
        event_type: The type of event to wait for
        timeout: Maximum time to wait in seconds
        filter_func: Optional function to filter events

    Returns:
        The event if received, None if timeout
    """
    received_event = None
    event_received = asyncio.Event()

    async def handler(event: Event):
        nonlocal received_event
        if filter_func is None or filter_func(event):
            received_event = event
            event_received.set()

    # Subscribe to event
    await event_bus.subscribe(event_type, handler)

    try:
        # Wait for event or timeout
        await asyncio.wait_for(event_received.wait(), timeout=timeout)
        return received_event
    except asyncio.TimeoutError:
        logger.warning(f"Timeout waiting for {event_type.value}")
        return None
    finally:
        # Cleanup subscription
        await event_bus.unsubscribe(event_type, handler)


async def publish_and_wait(
    event_bus: EventBus,
    publish_event: Event,
    wait_for_type: EventType,
    timeout: float = 30.0,
    filter_func: Optional[Callable[[Event], bool]] = None
) -> Optional[Event]:
    """
    Publish an event and wait for a response event.

    Useful for request-response patterns.

    Args:
        event_bus: The event bus
        publish_event: Event to publish
        wait_for_type: Type of response event to wait for
        timeout: Maximum time to wait
        filter_func: Optional function to filter response events

    Returns:
        The response event or None if timeout
    """
    # Set up listener first
    wait_task = asyncio.create_task(
        wait_for_event(event_bus, wait_for_type, timeout, filter_func)
    )

    # Small delay to ensure subscription is ready
    await asyncio.sleep(0.1)

    # Publish the event
    await event_bus.publish(publish_event)

    # Wait for response
    return await wait_task


@asynccontextmanager
async def event_listener(
    event_type: EventType,
    handler: Callable[[Event], None],
    event_bus: Optional[EventBus] = None
):
    """
    Context manager for temporary event listening.

    Usage:
        async with event_listener(EventType.PLAYER_DATA_UPDATED, my_handler):
            # Handler is active within this block
            await do_something()
        # Handler automatically unsubscribed
    """
    bus = event_bus or get_event_bus()

    # Ensure connected
    if not bus.redis_client:
        await bus.connect()

    # Subscribe
    await bus.subscribe(event_type, handler)

    # Start listening if not already
    was_listening = bus._listening
    if not was_listening:
        await bus.start_listening()

    try:
        yield bus
    finally:
        # Cleanup
        await bus.unsubscribe(event_type, handler)
        if not was_listening:
            await bus.stop_listening()


class EventCollector:
    """
    Helper class to collect events for testing/debugging.

    Usage:
        collector = EventCollector()
        await event_bus.subscribe(EventType.PLAYER_DATA_UPDATED, collector)

        # Do something that generates events
        await some_operation()

        # Check collected events
        assert len(collector.events) > 0
        assert collector.events[0].event_type == EventType.PLAYER_DATA_UPDATED
    """

    def __init__(self, max_events: int = 100):
        """
        Initialize event collector.

        Args:
            max_events: Maximum number of events to store
        """
        self.events: List[Event] = []
        self.max_events = max_events

    async def __call__(self, event: Event):
        """Handle incoming event."""
        self.events.append(event)
        # Keep only last N events
        if len(self.events) > self.max_events:
            self.events.pop(0)

    def clear(self):
        """Clear collected events."""
        self.events.clear()

    def get_events_by_type(self, event_type: EventType) -> List[Event]:
        """Get all events of a specific type."""
        return [e for e in self.events if e.event_type == event_type]

    def get_events_by_source(self, source: str) -> List[Event]:
        """Get all events from a specific source."""
        return [e for e in self.events if e.source == source]

    def __len__(self) -> int:
        return len(self.events)

    def __repr__(self) -> str:
        return f"EventCollector({len(self.events)} events)"


async def broadcast_system_event(
    event_type: EventType,
    payload: dict,
    priority: EventPriority = EventPriority.NORMAL,
    event_bus: Optional[EventBus] = None
) -> None:
    """
    Convenience function to broadcast a system event.

    Args:
        event_type: Type of event
        payload: Event payload
        priority: Event priority
        event_bus: Event bus to use (creates one if not provided)
    """
    bus = event_bus or get_event_bus()

    event = Event(
        event_type=event_type,
        payload=payload,
        priority=priority,
        source='system'
    )

    await bus.publish(event)


class EventMetrics:
    """
    Track metrics about event processing.

    Useful for monitoring and debugging.
    """

    def __init__(self):
        self.total_events = 0
        self.events_by_type = {}
        self.events_by_source = {}
        self.events_by_priority = {}

    async def __call__(self, event: Event):
        """Process event for metrics."""
        self.total_events += 1

        # Count by type
        event_type = event.event_type.value
        self.events_by_type[event_type] = self.events_by_type.get(event_type, 0) + 1

        # Count by source
        if event.source:
            self.events_by_source[event.source] = (
                self.events_by_source.get(event.source, 0) + 1
            )

        # Count by priority
        priority = event.priority.name
        self.events_by_priority[priority] = (
            self.events_by_priority.get(priority, 0) + 1
        )

    def get_summary(self) -> dict:
        """Get metrics summary."""
        return {
            'total_events': self.total_events,
            'by_type': self.events_by_type,
            'by_source': self.events_by_source,
            'by_priority': self.events_by_priority
        }

    def reset(self):
        """Reset all metrics."""
        self.total_events = 0
        self.events_by_type.clear()
        self.events_by_source.clear()
        self.events_by_priority.clear()
