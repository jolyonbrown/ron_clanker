"""
Integration tests for event-driven infrastructure.

Tests the core components:
- EventBus (Redis pub/sub)
- Event creation and serialization
- BaseAgent lifecycle
- Event flow between agents
"""

import asyncio
import logging
from typing import List

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from infrastructure.event_bus import EventBus, get_event_bus
from infrastructure.events import (
    Event,
    EventType,
    EventPriority,
    create_data_refresh_event,
    create_notification_event
)
from infrastructure.base_agent import BaseAgent, AgentOrchestrator
from infrastructure.utils import EventCollector, wait_for_event

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# TEST AGENTS
# ============================================================================

class TestPublisherAgent(BaseAgent):
    """Simple agent that publishes test events."""

    def __init__(self, **kwargs):
        super().__init__(agent_name="test_publisher", **kwargs)
        self.published_count = 0

    def get_subscribed_events(self) -> List[EventType]:
        # This agent doesn't subscribe to anything
        return []

    async def handle_event(self, event: Event) -> None:
        # No events to handle
        pass

    async def publish_test_event(self):
        """Publish a test data refresh event."""
        event = create_data_refresh_event(data_type='test', force=True)
        await self.publish_event(event)
        self.published_count += 1


class TestConsumerAgent(BaseAgent):
    """Simple agent that consumes test events."""

    def __init__(self, **kwargs):
        super().__init__(agent_name="test_consumer", **kwargs)
        self.received_events: List[Event] = []

    def get_subscribed_events(self) -> List[EventType]:
        return [
            EventType.DATA_REFRESH_REQUESTED,
            EventType.DATA_UPDATED
        ]

    async def handle_event(self, event: Event) -> None:
        """Handle received events."""
        self.received_events.append(event)
        logger.info(f"Consumer received: {event}")

        # If we receive a refresh request, publish an update
        if event.event_type == EventType.DATA_REFRESH_REQUESTED:
            response = Event(
                event_type=EventType.DATA_UPDATED,
                payload={
                    'data_type': event.payload.get('data_type'),
                    'status': 'success'
                },
                correlation_id=event.event_id
            )
            await self.publish_event(response)


# ============================================================================
# TESTS
# ============================================================================

async def test_event_serialization():
    """Test event serialization and deserialization."""
    # Create an event
    original = create_data_refresh_event(data_type='players', force=True)

    # Serialize to JSON
    json_str = original.to_json()
    assert isinstance(json_str, str)
    assert 'players' in json_str

    # Deserialize back
    restored = Event.from_json(json_str)

    # Verify equality
    assert restored.event_type == original.event_type
    assert restored.payload == original.payload
    assert restored.event_id == original.event_id
    assert restored.priority == original.priority


async def test_event_bus_connection():
    """Test EventBus can connect to Redis."""
    bus = EventBus(redis_url="redis://localhost:6379")

    try:
        await bus.connect()
        assert bus.redis_client is not None

        # Test ping
        health = await bus.health_check()
        assert health['connected'] is True

    finally:
        await bus.disconnect()


async def test_event_publishing():
    """Test publishing events to the bus."""
    bus = EventBus(redis_url="redis://localhost:6379")

    try:
        await bus.connect()

        # Create and publish event
        event = create_data_refresh_event(data_type='test')
        subscribers = await bus.publish(event)

        # Event should be published even with 0 subscribers
        assert subscribers >= 0

        logger.info(f"Event published to {subscribers} subscribers")

    finally:
        await bus.disconnect()


async def test_event_subscription():
    """Test subscribing to and receiving events."""
    bus = EventBus(redis_url="redis://localhost:6379")
    collector = EventCollector()

    try:
        await bus.connect()

        # Subscribe to events
        await bus.subscribe(EventType.DATA_REFRESH_REQUESTED, collector)
        await bus.start_listening()

        # Give subscription time to register
        await asyncio.sleep(0.5)

        # Publish an event
        event = create_data_refresh_event(data_type='test')
        await bus.publish(event)

        # Wait for event to be received
        await asyncio.sleep(1)

        # Verify event was received
        assert len(collector) > 0
        received = collector.events[0]
        assert received.event_type == EventType.DATA_REFRESH_REQUESTED
        assert received.payload['data_type'] == 'test'

        logger.info(f"Successfully received event: {received}")

    finally:
        await bus.stop_listening()
        await bus.disconnect()


async def test_agent_lifecycle():
    """Test agent start/stop lifecycle."""
    bus = EventBus(redis_url="redis://localhost:6379")

    try:
        await bus.connect()

        # Create agent
        agent = TestPublisherAgent(event_bus=bus)

        # Start agent
        await agent.start()
        assert agent.is_running is True
        assert agent.is_healthy is True

        # Check status
        status = agent.get_status()
        assert status['agent_name'] == 'test_publisher'
        assert status['is_running'] is True

        # Stop agent
        await agent.stop()
        assert agent.is_running is False

    finally:
        await bus.disconnect()


async def test_agent_communication():
    """Test two agents communicating via events."""
    bus = EventBus(redis_url="redis://localhost:6379")

    try:
        await bus.connect()

        # Create agents
        publisher = TestPublisherAgent(event_bus=bus)
        consumer = TestConsumerAgent(event_bus=bus)

        # Start agents
        await consumer.start()  # Start consumer first to register subscriptions
        await publisher.start()

        # Wait for subscriptions to register
        await asyncio.sleep(0.5)

        # Publisher publishes an event
        await publisher.publish_test_event()

        # Wait for consumer to receive
        await asyncio.sleep(1)

        # Verify consumer received the event
        assert len(consumer.received_events) > 0
        received = consumer.received_events[0]
        assert received.event_type == EventType.DATA_REFRESH_REQUESTED
        assert received.source == 'test_publisher'

        logger.info(
            f"✓ Publisher sent {publisher.published_count} events, "
            f"Consumer received {len(consumer.received_events)} events"
        )

        # Stop agents
        await publisher.stop()
        await consumer.stop()

    finally:
        await bus.disconnect()


async def test_request_response_pattern():
    """Test request-response event pattern."""
    bus = EventBus(redis_url="redis://localhost:6379")

    try:
        await bus.connect()

        # Create agents
        publisher = TestPublisherAgent(event_bus=bus)
        consumer = TestConsumerAgent(event_bus=bus)  # Responds to refresh requests

        # Start both agents
        await consumer.start()
        await publisher.start()
        await asyncio.sleep(0.5)

        # Publisher sends request
        request_event = create_data_refresh_event(data_type='players', force=True)
        await publisher.publish_event(request_event)

        # Wait for response
        await asyncio.sleep(1)

        # Check consumer received request and sent response
        assert len(consumer.received_events) >= 1
        assert consumer.received_events[0].event_type == EventType.DATA_REFRESH_REQUESTED

        # Consumer should have published DATA_UPDATED response
        assert consumer.events_published >= 1

        logger.info("✓ Request-response pattern working")

        # Cleanup
        await publisher.stop()
        await consumer.stop()

    finally:
        await bus.disconnect()


async def test_orchestrator():
    """Test AgentOrchestrator managing multiple agents."""
    bus = EventBus(redis_url="redis://localhost:6379")

    try:
        await bus.connect()

        # Create orchestrator
        orchestrator = AgentOrchestrator(event_bus=bus)

        # Register agents
        publisher = TestPublisherAgent(event_bus=bus)
        consumer = TestConsumerAgent(event_bus=bus)

        orchestrator.register_agent(publisher)
        orchestrator.register_agent(consumer)

        # Start all agents
        await orchestrator.start_all()

        # Verify all running
        assert publisher.is_running
        assert consumer.is_running

        # Get system status
        status = await orchestrator.get_system_status()
        assert status['total_agents'] == 2
        assert status['running_agents'] == 2

        logger.info(f"System status: {status}")

        # Stop all agents
        await orchestrator.stop_all()

        # Verify all stopped
        assert not publisher.is_running
        assert not consumer.is_running

        logger.info("✓ Orchestrator managing agents successfully")

    finally:
        await bus.disconnect()


# ============================================================================
# MAIN - Run all tests manually
# ============================================================================

async def run_all_tests():
    """Run all tests sequentially."""
    logger.info("=" * 60)
    logger.info("TESTING EVENT-DRIVEN INFRASTRUCTURE")
    logger.info("=" * 60)

    tests = [
        ("Event Serialization", test_event_serialization),
        ("Event Bus Connection", test_event_bus_connection),
        ("Event Publishing", test_event_publishing),
        ("Event Subscription", test_event_subscription),
        ("Agent Lifecycle", test_agent_lifecycle),
        ("Agent Communication", test_agent_communication),
        ("Request-Response Pattern", test_request_response_pattern),
        ("Agent Orchestrator", test_orchestrator),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        logger.info(f"\n{'─' * 60}")
        logger.info(f"Running: {name}")
        logger.info(f"{'─' * 60}")

        try:
            await test_func()
            logger.info(f"✓ {name} PASSED")
            passed += 1
        except Exception as e:
            logger.error(f"✗ {name} FAILED: {e}", exc_info=True)
            failed += 1

    logger.info(f"\n{'=' * 60}")
    logger.info(f"TEST RESULTS: {passed} passed, {failed} failed")
    logger.info(f"{'=' * 60}")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)
