"""
Base agent class for event-driven agents.

All specialized agents (Manager, Data Collector, Valuation, etc.)
inherit from BaseAgent to get event-driven capabilities.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Set
from datetime import datetime

from .event_bus import EventBus, get_event_bus
from .events import Event, EventType, EventPriority, create_notification_event

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base class for all event-driven agents.

    Agents are autonomous workers that:
    1. Subscribe to specific event types
    2. Process events asynchronously
    3. Publish new events based on their work
    4. Maintain their own state
    5. Report health and status

    Each agent runs in its own asyncio task and communicates
    via the event bus.
    """

    def __init__(
        self,
        agent_name: str,
        event_bus: Optional[EventBus] = None,
        redis_url: str = "redis://localhost:6379"
    ):
        """
        Initialize the base agent.

        Args:
            agent_name: Unique identifier for this agent
            event_bus: Shared event bus (creates one if not provided)
            redis_url: Redis connection URL
        """
        self.agent_name = agent_name
        self.event_bus = event_bus or get_event_bus(redis_url)

        # Agent state
        self.is_running = False
        self.is_healthy = True
        self.started_at: Optional[datetime] = None
        self.events_processed = 0
        self.events_published = 0
        self.last_error: Optional[str] = None

        # Agent configuration
        self._subscribed_events: Set[EventType] = set()

        logger.info(f"Initialized agent: {self.agent_name}")

    @abstractmethod
    def get_subscribed_events(self) -> List[EventType]:
        """
        Return list of event types this agent subscribes to.

        Must be implemented by each concrete agent class.

        Returns:
            List of EventType enums this agent handles
        """
        pass

    @abstractmethod
    async def handle_event(self, event: Event) -> None:
        """
        Process an event.

        Must be implemented by each concrete agent class.

        Args:
            event: The event to process
        """
        pass

    async def start(self) -> None:
        """
        Start the agent.

        Connects to event bus, subscribes to events, begins processing.
        """
        if self.is_running:
            logger.warning(f"{self.agent_name} is already running")
            return

        try:
            # Connect to event bus if not already connected
            if not self.event_bus.redis_client:
                await self.event_bus.connect()

            # Subscribe to events
            subscribed_events = self.get_subscribed_events()
            for event_type in subscribed_events:
                await self.event_bus.subscribe(event_type, self._event_handler)
                self._subscribed_events.add(event_type)

            # Start listening
            if not self.event_bus._listening:
                await self.event_bus.start_listening()

            # Run initialization hook
            await self.on_start()

            self.is_running = True
            self.started_at = datetime.utcnow()

            logger.info(
                f"{self.agent_name} started. "
                f"Subscribed to {len(self._subscribed_events)} event types."
            )

            # Publish startup notification
            await self.publish_event(
                create_notification_event(
                    level='info',
                    message=f"{self.agent_name} started",
                    details={'subscriptions': [e.value for e in self._subscribed_events]}
                )
            )

        except Exception as e:
            logger.error(f"Failed to start {self.agent_name}: {e}", exc_info=True)
            self.is_healthy = False
            self.last_error = str(e)
            raise

    async def stop(self) -> None:
        """
        Stop the agent gracefully.

        Unsubscribes from events and cleans up resources.
        """
        if not self.is_running:
            return

        try:
            # Run cleanup hook
            await self.on_stop()

            # Unsubscribe from events
            for event_type in self._subscribed_events:
                await self.event_bus.unsubscribe(event_type, self._event_handler)

            self._subscribed_events.clear()
            self.is_running = False

            logger.info(
                f"{self.agent_name} stopped. "
                f"Processed {self.events_processed} events, "
                f"published {self.events_published} events."
            )

            # Publish shutdown notification
            await self.publish_event(
                create_notification_event(
                    level='info',
                    message=f"{self.agent_name} stopped",
                    details={
                        'events_processed': self.events_processed,
                        'events_published': self.events_published,
                        'uptime_seconds': (datetime.utcnow() - self.started_at).total_seconds()
                    }
                )
            )

        except Exception as e:
            logger.error(f"Error stopping {self.agent_name}: {e}", exc_info=True)

    async def _event_handler(self, event: Event) -> None:
        """
        Internal event handler wrapper.

        Adds error handling, metrics tracking, and logging.
        """
        try:
            logger.debug(f"{self.agent_name} received {event}")

            # Call the agent's event handler
            await self.handle_event(event)

            # Update metrics
            self.events_processed += 1

        except Exception as e:
            logger.error(
                f"{self.agent_name} error handling {event}: {e}",
                exc_info=True
            )
            self.last_error = str(e)

            # Publish error notification
            await self.publish_event(
                create_notification_event(
                    level='error',
                    message=f"{self.agent_name} failed to process event",
                    details={
                        'event_type': event.event_type.value,
                        'event_id': event.event_id,
                        'error': str(e)
                    }
                )
            )

            # Retry logic if event supports it
            if event.can_retry():
                event.increment_retry()
                logger.info(f"Retrying {event} (attempt {event.retry_count})")
                # Re-publish event for retry
                await self.event_bus.publish(event)

    async def publish_event(self, event: Event) -> None:
        """
        Publish an event to the event bus.

        Args:
            event: The event to publish
        """
        try:
            # Set source if not already set
            if not event.source:
                event.source = self.agent_name

            await self.event_bus.publish(event)
            self.events_published += 1

        except Exception as e:
            logger.error(f"{self.agent_name} failed to publish {event}: {e}")
            raise

    async def on_start(self) -> None:
        """
        Hook called when agent starts.

        Override in subclasses for custom initialization.
        """
        pass

    async def on_stop(self) -> None:
        """
        Hook called when agent stops.

        Override in subclasses for custom cleanup.
        """
        pass

    def get_status(self) -> Dict[str, any]:
        """
        Get current status of the agent.

        Returns:
            Dictionary with agent status information
        """
        status = {
            'agent_name': self.agent_name,
            'is_running': self.is_running,
            'is_healthy': self.is_healthy,
            'events_processed': self.events_processed,
            'events_published': self.events_published,
            'subscribed_events': [e.value for e in self._subscribed_events],
        }

        if self.started_at:
            status['uptime_seconds'] = (
                datetime.utcnow() - self.started_at
            ).total_seconds()

        if self.last_error:
            status['last_error'] = self.last_error

        return status

    async def health_check(self) -> Dict[str, any]:
        """
        Perform health check.

        Returns:
            Dictionary with health status
        """
        health = {
            'agent': self.agent_name,
            'healthy': self.is_healthy and self.is_running,
            'details': self.get_status()
        }

        return health

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"name={self.agent_name}, "
            f"running={self.is_running}, "
            f"healthy={self.is_healthy})"
        )


class AgentOrchestrator:
    """
    Orchestrator for managing multiple agents.

    Handles starting/stopping all agents and coordinating their lifecycle.
    """

    def __init__(self, event_bus: Optional[EventBus] = None):
        """
        Initialize the orchestrator.

        Args:
            event_bus: Shared event bus for all agents
        """
        self.event_bus = event_bus or get_event_bus()
        self.agents: Dict[str, BaseAgent] = {}
        self._tasks: Dict[str, asyncio.Task] = {}

    def register_agent(self, agent: BaseAgent) -> None:
        """
        Register an agent with the orchestrator.

        Args:
            agent: The agent to register
        """
        if agent.agent_name in self.agents:
            raise ValueError(f"Agent {agent.agent_name} already registered")

        self.agents[agent.agent_name] = agent
        logger.info(f"Registered agent: {agent.agent_name}")

    async def start_all(self) -> None:
        """Start all registered agents."""
        logger.info(f"Starting {len(self.agents)} agents...")

        for name, agent in self.agents.items():
            try:
                await agent.start()
            except Exception as e:
                logger.error(f"Failed to start {name}: {e}")

        logger.info("All agents started")

    async def stop_all(self) -> None:
        """Stop all registered agents."""
        logger.info(f"Stopping {len(self.agents)} agents...")

        for name, agent in self.agents.items():
            try:
                await agent.stop()
            except Exception as e:
                logger.error(f"Failed to stop {name}: {e}")

        logger.info("All agents stopped")

    async def get_system_status(self) -> Dict[str, any]:
        """
        Get status of all agents.

        Returns:
            Dictionary with system-wide status
        """
        agent_statuses = {}
        for name, agent in self.agents.items():
            agent_statuses[name] = agent.get_status()

        event_bus_health = await self.event_bus.health_check()

        return {
            'agents': agent_statuses,
            'event_bus': event_bus_health,
            'total_agents': len(self.agents),
            'running_agents': sum(1 for a in self.agents.values() if a.is_running),
            'healthy_agents': sum(1 for a in self.agents.values() if a.is_healthy)
        }
