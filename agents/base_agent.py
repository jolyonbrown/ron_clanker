"""
Base Agent Class

All specialist agents inherit from BaseAgent to get event-driven capabilities.
This provides:
- Event bus integration
- Subscription management
- Standard lifecycle methods
- Logging and error handling
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Callable
from datetime import datetime

from infrastructure.event_bus import EventBus, get_event_bus
from infrastructure.events import Event, EventType, EventPriority

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Base class for all specialist agents in Ron Clanker's system.

    Provides:
    - Event bus connection management
    - Event subscription helpers
    - Standard lifecycle (start, stop, health check)
    - Error handling and logging
    - Agent state management

    Subclasses must implement:
    - setup_subscriptions(): Define which events to listen for
    - handle_event(): Process received events
    """

    def __init__(
        self,
        agent_name: str,
        event_bus: Optional[EventBus] = None
    ):
        """
        Initialize the base agent.

        Args:
            agent_name: Unique identifier for this agent (e.g., "dc_analyst")
            event_bus: Optional event bus instance (creates one if not provided)
        """
        self.agent_name = agent_name
        self.event_bus = event_bus or get_event_bus()

        self._running = False
        self._subscriptions: List[EventType] = []
        self._handlers: dict[EventType, Callable] = {}

        logger.info(f"{self.agent_name} initialized")

    async def start(self) -> None:
        """
        Start the agent.

        - Connects to event bus
        - Sets up subscriptions
        - Begins listening for events
        - Runs any initialization logic
        """
        if self._running:
            logger.warning(f"{self.agent_name} already running")
            return

        try:
            # Connect to event bus if not already connected
            if not self.event_bus.redis_client:
                await self.event_bus.connect()

            # Set up subscriptions (defined by subclass)
            await self.setup_subscriptions()

            # Start listening
            if not self.event_bus._listening:
                await self.event_bus.start_listening()

            self._running = True
            logger.info(f"{self.agent_name} started successfully")

            # Announce agent startup
            await self.publish_event(
                EventType.NOTIFICATION_INFO,
                {
                    'message': f'{self.agent_name} agent started',
                    'subscriptions': [et.value for et in self._subscriptions]
                }
            )

        except Exception as e:
            logger.error(f"Failed to start {self.agent_name}: {e}", exc_info=True)
            raise

    async def stop(self) -> None:
        """
        Stop the agent gracefully.

        - Unsubscribes from events
        - Cleans up resources
        - Disconnects from event bus (if singleton allows)
        """
        if not self._running:
            return

        try:
            # Unsubscribe from all events
            for event_type in self._subscriptions:
                handler = self._handlers.get(event_type)
                if handler:
                    await self.event_bus.unsubscribe(event_type, handler)

            self._subscriptions.clear()
            self._handlers.clear()
            self._running = False

            logger.info(f"{self.agent_name} stopped")

            # Announce shutdown
            await self.publish_event(
                EventType.NOTIFICATION_INFO,
                {'message': f'{self.agent_name} agent stopped'}
            )

        except Exception as e:
            logger.error(f"Error stopping {self.agent_name}: {e}", exc_info=True)

    async def subscribe_to(self, event_type: EventType) -> None:
        """
        Subscribe to an event type.

        Args:
            event_type: The type of event to subscribe to
        """
        # Create handler wrapper that calls handle_event
        async def handler_wrapper(event: Event):
            try:
                await self.handle_event(event)
            except Exception as e:
                logger.error(
                    f"{self.agent_name} error handling {event}: {e}",
                    exc_info=True
                )
                # Publish error notification
                await self.publish_event(
                    EventType.NOTIFICATION_ERROR,
                    {
                        'message': f'{self.agent_name} error handling event',
                        'event_type': event.event_type.value,
                        'error': str(e)
                    }
                )

        # Subscribe to event bus
        await self.event_bus.subscribe(event_type, handler_wrapper)
        self._subscriptions.append(event_type)
        self._handlers[event_type] = handler_wrapper

        logger.debug(f"{self.agent_name} subscribed to {event_type.value}")

    async def publish_event(
        self,
        event_type: EventType,
        payload: dict,
        priority: EventPriority = EventPriority.NORMAL,
        correlation_id: Optional[str] = None
    ) -> int:
        """
        Publish an event to the event bus.

        Args:
            event_type: Type of event to publish
            payload: Event data
            priority: Event priority level
            correlation_id: Optional ID to correlate related events

        Returns:
            Number of subscribers that received the event
        """
        event = Event(
            event_type=event_type,
            payload=payload,
            source=self.agent_name,
            priority=priority,
            correlation_id=correlation_id
        )

        try:
            num_subscribers = await self.event_bus.publish(event)
            logger.debug(
                f"{self.agent_name} published {event_type.value} "
                f"to {num_subscribers} subscribers"
            )
            return num_subscribers

        except Exception as e:
            logger.error(f"{self.agent_name} failed to publish event: {e}")
            raise

    @abstractmethod
    async def setup_subscriptions(self) -> None:
        """
        Set up event subscriptions for this agent.

        Subclasses must implement this to define which events they listen for.

        Example:
            await self.subscribe_to(EventType.DATA_UPDATED)
            await self.subscribe_to(EventType.ANALYSIS_REQUESTED)
        """
        pass

    @abstractmethod
    async def handle_event(self, event: Event) -> None:
        """
        Handle an incoming event.

        Subclasses must implement this to define their event handling logic.

        Args:
            event: The event to handle

        Example:
            if event.event_type == EventType.DATA_UPDATED:
                await self.perform_analysis(event.payload)
        """
        pass

    async def health_check(self) -> dict:
        """
        Check agent health status.

        Returns:
            Dictionary with health information
        """
        return {
            'agent_name': self.agent_name,
            'running': self._running,
            'subscriptions': [et.value for et in self._subscriptions],
            'event_bus_connected': self.event_bus.redis_client is not None,
            'timestamp': datetime.utcnow().isoformat()
        }

    def is_running(self) -> bool:
        """Check if agent is currently running."""
        return self._running

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.agent_name}, running={self._running})"
