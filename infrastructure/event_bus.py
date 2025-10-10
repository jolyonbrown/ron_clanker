"""
Redis-based event bus for pub/sub messaging between agents.

The event bus is the central nervous system of Ron Clanker's
event-driven architecture. It handles:
- Publishing events to channels
- Subscribing to event types
- Event routing and delivery
- Connection management and resilience
"""

import asyncio
import logging
from typing import Callable, Dict, List, Optional, Set
from contextlib import asynccontextmanager
import redis.asyncio as redis

from .events import Event, EventType

logger = logging.getLogger(__name__)


class EventBus:
    """
    Redis-based event bus for asynchronous pub/sub messaging.

    The event bus allows agents to:
    1. Publish events to specific channels
    2. Subscribe to events by type
    3. Receive events asynchronously
    4. Handle connection failures gracefully

    Events are serialized to JSON and sent via Redis pub/sub.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        channel_prefix: str = "ron_clanker"
    ):
        """
        Initialize the event bus.

        Args:
            redis_url: Redis connection URL
            channel_prefix: Prefix for all Redis channels (namespace)
        """
        self.redis_url = redis_url
        self.channel_prefix = channel_prefix
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None

        # Track subscriptions
        self._subscriptions: Dict[EventType, List[Callable]] = {}
        self._listening = False
        self._listen_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        """Establish connection to Redis."""
        try:
            self.redis_client = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            # Test connection
            await self.redis_client.ping()
            logger.info(f"Connected to Redis at {self.redis_url}")

            # Create pubsub instance
            self.pubsub = self.redis_client.pubsub()

        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._listening:
            await self.stop_listening()

        if self.pubsub:
            await self.pubsub.close()

        if self.redis_client:
            await self.redis_client.close()

        logger.info("Disconnected from Redis")

    def _get_channel_name(self, event_type: EventType) -> str:
        """Get Redis channel name for an event type."""
        return f"{self.channel_prefix}:{event_type.value}"

    async def publish(self, event: Event) -> int:
        """
        Publish an event to the appropriate channel.

        Args:
            event: The event to publish

        Returns:
            Number of subscribers that received the message
        """
        if not self.redis_client:
            raise RuntimeError("EventBus not connected. Call connect() first.")

        channel = self._get_channel_name(event.event_type)
        message = event.to_json()

        try:
            # Publish to Redis channel
            num_subscribers = await self.redis_client.publish(channel, message)

            logger.debug(
                f"Published {event} to channel '{channel}' "
                f"({num_subscribers} subscribers)"
            )

            # Also store event in a sorted set for audit/replay
            await self._store_event(event)

            return num_subscribers

        except Exception as e:
            logger.error(f"Failed to publish event {event}: {e}")
            raise

    async def _store_event(self, event: Event) -> None:
        """Store event in Redis sorted set for audit trail."""
        try:
            # Store in a sorted set with timestamp as score
            key = f"{self.channel_prefix}:events:history"
            score = event.timestamp.timestamp()
            await self.redis_client.zadd(
                key,
                {event.to_json(): score}
            )

            # Keep only last 10,000 events
            await self.redis_client.zremrangebyrank(key, 0, -10001)

        except Exception as e:
            logger.warning(f"Failed to store event in history: {e}")

    async def subscribe(
        self,
        event_type: EventType,
        handler: Callable[[Event], None]
    ) -> None:
        """
        Subscribe to events of a specific type.

        Args:
            event_type: The type of events to subscribe to
            handler: Async function to call when event is received
        """
        if not self.pubsub:
            raise RuntimeError("EventBus not connected. Call connect() first.")

        # Add handler to subscriptions
        if event_type not in self._subscriptions:
            self._subscriptions[event_type] = []
            # Subscribe to Redis channel
            channel = self._get_channel_name(event_type)
            await self.pubsub.subscribe(channel)
            logger.info(f"Subscribed to {event_type.value}")

        self._subscriptions[event_type].append(handler)

    async def unsubscribe(
        self,
        event_type: EventType,
        handler: Optional[Callable[[Event], None]] = None
    ) -> None:
        """
        Unsubscribe from events.

        Args:
            event_type: The event type to unsubscribe from
            handler: Specific handler to remove (if None, removes all)
        """
        if event_type not in self._subscriptions:
            return

        if handler:
            # Remove specific handler
            if handler in self._subscriptions[event_type]:
                self._subscriptions[event_type].remove(handler)
        else:
            # Remove all handlers for this event type
            self._subscriptions[event_type] = []

        # If no more handlers, unsubscribe from Redis channel
        if not self._subscriptions[event_type]:
            channel = self._get_channel_name(event_type)
            await self.pubsub.unsubscribe(channel)
            del self._subscriptions[event_type]
            logger.info(f"Unsubscribed from {event_type.value}")

    async def start_listening(self) -> None:
        """Start listening for events in the background."""
        if self._listening:
            logger.warning("Already listening for events")
            return

        self._listening = True
        self._listen_task = asyncio.create_task(self._listen_loop())
        logger.info("Started listening for events")

    async def stop_listening(self) -> None:
        """Stop listening for events."""
        if not self._listening:
            return

        self._listening = False

        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass

        logger.info("Stopped listening for events")

    async def _listen_loop(self) -> None:
        """Main event listening loop."""
        try:
            async for message in self.pubsub.listen():
                if not self._listening:
                    break

                if message['type'] != 'message':
                    continue

                try:
                    # Deserialize event
                    event = Event.from_json(message['data'])

                    # Call all registered handlers for this event type
                    handlers = self._subscriptions.get(event.event_type, [])
                    for handler in handlers:
                        try:
                            # Run handler (support both sync and async)
                            if asyncio.iscoroutinefunction(handler):
                                await handler(event)
                            else:
                                handler(event)
                        except Exception as e:
                            logger.error(
                                f"Error in handler for {event}: {e}",
                                exc_info=True
                            )

                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info("Listen loop cancelled")
        except Exception as e:
            logger.error(f"Fatal error in listen loop: {e}", exc_info=True)
            self._listening = False

    async def get_event_history(
        self,
        limit: int = 100,
        event_type: Optional[EventType] = None
    ) -> List[Event]:
        """
        Retrieve recent events from history.

        Args:
            limit: Maximum number of events to retrieve
            event_type: Filter by specific event type (optional)

        Returns:
            List of events in reverse chronological order
        """
        if not self.redis_client:
            raise RuntimeError("EventBus not connected")

        try:
            # Get events from sorted set
            key = f"{self.channel_prefix}:events:history"
            event_jsons = await self.redis_client.zrevrange(key, 0, limit - 1)

            # Deserialize events
            events = [Event.from_json(json_str) for json_str in event_jsons]

            # Filter by type if requested
            if event_type:
                events = [e for e in events if e.event_type == event_type]

            return events

        except Exception as e:
            logger.error(f"Failed to retrieve event history: {e}")
            return []

    @asynccontextmanager
    async def managed_connection(self):
        """Context manager for event bus lifecycle."""
        await self.connect()
        try:
            yield self
        finally:
            await self.disconnect()

    async def health_check(self) -> Dict[str, any]:
        """
        Check health of event bus.

        Returns:
            Dictionary with health status
        """
        status = {
            'connected': False,
            'subscriptions': 0,
            'listening': self._listening
        }

        try:
            if self.redis_client:
                await self.redis_client.ping()
                status['connected'] = True
                status['subscriptions'] = len(self._subscriptions)

        except Exception as e:
            status['error'] = str(e)

        return status


# Singleton instance for easy access
_event_bus: Optional[EventBus] = None


def get_event_bus(redis_url: str = "redis://localhost:6379") -> EventBus:
    """
    Get or create the global event bus instance.

    Args:
        redis_url: Redis connection URL

    Returns:
        EventBus singleton instance
    """
    global _event_bus

    if _event_bus is None:
        _event_bus = EventBus(redis_url=redis_url)

    return _event_bus
