# Ron Clanker: True Agentic Architecture
## Building a Real-World Autonomous Multi-Agent FPL System

---

## Executive Summary

This document outlines the transformation of Ron Clanker from a scripted automation system into a **truly agentic multi-agent system** where specialized agents operate autonomously, communicate asynchronously, and make decisions without human intervention. The system will run 24/7 on dedicated hardware (Raspberry Pi 3 with UPS backup), responding to real-world events in the FPL ecosystem.

**Last Updated**: October 6, 2025
**Target Deployment**: Raspberry Pi 3 with UPS backup
**Architecture Pattern**: Event-Driven Hierarchical Multi-Agent System

---

## Table of Contents

1. [Critical Research Findings](#critical-research-findings)
2. [What Makes a System "Agentic"?](#what-makes-a-system-agentic)
3. [Architecture Overview](#architecture-overview)
4. [Agent Communication Protocol](#agent-communication-protocol)
5. [LLM Integration Strategy](#llm-integration-strategy)
6. [Infrastructure Components](#infrastructure-components)
7. [Raspberry Pi Deployment](#raspberry-pi-deployment)
8. [Roadmap & Phases](#roadmap--phases)
9. [Open Questions & Challenges](#open-questions--challenges)

---

## Critical Research Findings

### 1. FPL API - Can We Make Transfers Programmatically?

**Short Answer**: Yes, but with caveats.

**Details**:
- The FPL API supports **authentication** via POST to `https://users.premierleague.com/accounts/login/`
- Authentication returns session cookies that enable authenticated endpoints
- **Read-Only Endpoints** (well documented):
  - Bootstrap data (players, teams, events)
  - Player statistics and history
  - Fixtures and results
  - Public team data
  - Mini-league standings

- **Write Endpoints** (poorly documented, reverse-engineered):
  - The community has reverse-engineered endpoints for transfers
  - R package `{fantasy}` successfully implements programmatic transfers
  - Python libraries exist but are less mature for write operations
  - These endpoints are **unofficial** and could change without notice

**Recommendation**:
- **Phase 1**: Build the agentic system with decision-making capability but manual execution (Ron outputs the transfer recommendations, human executes)
- **Phase 2**: Implement automated execution via reverse-engineered API endpoints with extensive error handling
- **Phase 3**: Build web UI automation (Selenium/Playwright) as fallback if API endpoints break

**Risk Level**: Medium - API could change, rate limiting, account suspension possible

---

### 2. Price Change Prediction

**Research Findings**:
- FPL price changes occur **daily between 1-3 AM GMT**
- Algorithm is **proprietary and opaque** (intentionally by FPL)
- Maximum change per gameweek: ±£0.3m
- Community prediction tools exist:
  - **LiveFPL** (most accurate according to sources)
  - Fantasy Football Scout
  - Fantasy Football Hub
  - FPL Statistics

**How They Work**:
- Monitor transfer volume (transfers_in - transfers_out)
- Track ownership percentage changes
- Use historical patterns and thresholds
- Display "% chance of rise/fall" (100% = likely tonight)

**Key Insight**:
- Prediction tools are reasonably accurate (70-85%) but not perfect
- FPL applies manual overrides occasionally
- Getting ahead of price rises is valuable (can bank £0.1-0.5m team value over season)

**Agent Implication**:
- **Maggie (Data Agent)** should scrape LiveFPL predictions daily at 6 PM
- **Jimmy (Value Agent)** evaluates if early transfer warranted
- Trade-off: Early transfer vs optimal gameweek timing
- EV calculation: Expected price gain vs expected points loss from suboptimal timing

---

### 3. Can a System Be "Agentic" Without LLMs?

**Short Answer**: Yes, but with limitations.

**Research Findings**:

**Levels of Autonomy (IBM/Anthropic Framework)**:
- **L0 (No Intelligence)**: If-this-then-that logic, no reasoning (e.g., Zapier)
- **L1 (Reactive)**: Responds to inputs with predefined rules
- **L2 (Stateful)**: Maintains state, basic pattern recognition
- **L3 (Agentic - Rule-Based)**: Autonomous actions, self-triggering, feedback loops
- **L4 (Agentic - LLM-Enhanced)**: Natural language reasoning, context understanding
- **L5 (Meta-Agentic)**: Multi-agent coordination, emergent strategies

**Rule-Based Agents Can Be Agentic**:
- Classic examples: Chess engines, theorem provers, PID controllers
- Characteristics:
  - Autonomous decision-making (no human in loop)
  - Goal-directed behavior
  - Environmental sensing and response
  - Learning (e.g., Bayesian updates, reinforcement learning)
  - Multi-step planning

**Where LLMs Add Value**:
- **Unstructured data processing**: News articles, press conferences, Twitter sentiment
- **Contextual reasoning**: "Is this injury serious?" requires nuanced understanding
- **Natural language output**: Ron's announcements sound authentically human
- **Adaptive strategy**: Can reason about novel situations not in training data
- **Meta-reasoning**: "Should I trust this source?" "Is this pattern meaningful?"

**Hybrid Approach (Recommended)**:
- **Rule-based core**: Numerical analysis, optimization, pattern matching
- **LLM augmentation**: Text analysis, decision explanation, communication
- **Best of both**: Reliability + flexibility

---

## What Makes a System "Agentic"?

Based on research, a system is **agentic** when it exhibits:

1. **Autonomy**: Makes decisions without human approval
2. **Goal-Directedness**: Optimizes for explicit objectives (maximize FPL points)
3. **Reactivity**: Responds to environmental changes (injuries, price changes)
4. **Proactivity**: Anticipates future states, plans ahead
5. **Social Ability**: Multiple agents communicate and coordinate
6. **Learning**: Improves performance over time from feedback
7. **Temporal Continuity**: Runs continuously, maintains long-term state

**Ron Clanker's Agentic Characteristics**:
- ✅ Autonomous: Makes all FPL decisions without human input
- ✅ Goal-Directed: Maximizes weekly points, season rank
- ✅ Reactive: Responds to injuries, price changes, form shifts
- ✅ Proactive: Plans 3-6 gameweeks ahead, times chips strategically
- ✅ Social: Multiple specialist agents communicate and coordinate
- ⏳ Learning: Phase 3+ (ML models, strategy refinement)
- ✅ Temporal Continuity: Runs 24/7 on dedicated hardware

**Verdict**: Ron Clanker qualifies as a **true agentic system**, even without extensive LLM use in core decision-making.

---

## Architecture Overview

### System Design Philosophy

**Pattern**: Event-Driven Hierarchical Multi-Agent System (EDHMAS)

**Key Principles**:
1. **Specialization**: Each agent masters one domain
2. **Asynchronous Communication**: Agents publish events, subscribe to relevant channels
3. **Decoupled Components**: Agents can fail independently without system collapse
4. **Event Sourcing**: All decisions logged as immutable events
5. **Graceful Degradation**: System continues with reduced capability if agents unavailable

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                  EVENT BUS (Redis Pub/Sub)              │
│  Channels: gameweek, price_changes, injuries, analysis  │
└────────────────┬────────────────────────────────────────┘
                 │
    ┌────────────┴───────────────┐
    │                            │
    ▼                            ▼
┌─────────────────┐      ┌──────────────────┐
│  RON CLANKER    │      │   TASK SCHEDULER │
│  (Orchestrator) │◄─────┤   (Celery Beat)  │
│  Manager Agent  │      │   Cron-like Jobs │
└────────┬────────┘      └──────────────────┘
         │
         │ coordinates
         │
    ┌────┴─────────────────────────────────────┐
    │                                           │
    ▼                                           ▼
┌─────────────┐                         ┌─────────────┐
│  BACKROOM   │                         │   DATA      │
│  STAFF      │◄────────────────────────┤   LAYER     │
│  AGENTS     │    consume data         │             │
└─────────────┘                         └─────────────┘
    │                                           │
    │ publish analyses                          │
    │                                           │
    ├──► Digger (DC Analysis)                   ├──► Maggie (Data Collector)
    ├──► Sophia (xG Analysis)                   ├──► Database (PostgreSQL)
    ├──► Jimmy (Value Analysis)                 ├──► Cache (Redis)
    ├──► Priya (Fixture Analysis)               └──► FPL API (via MCP)
    ├──► Terry (Chip Strategy)
    └──► Ellie (Learning System)
```

### Event Flow Example: Gameweek Planning

```
TIME: 48 hours before GW deadline
┌──────────────────────────────────────────────────────┐
│ 1. TRIGGER: Scheduler publishes event                │
│    Event: GAMEWEEK_DEADLINE_48H                      │
│    Payload: {gameweek: 9, deadline: "2025-10-19..."}│
└──────────────────────────────────────────────────────┘
                         │
         ┌───────────────┴──────────────┐
         ▼                              ▼
┌─────────────────┐            ┌─────────────────┐
│ Maggie hears    │            │ Priya hears     │
│ event, fetches  │            │ event, analyzes │
│ latest FPL data │            │ next 6 fixtures │
└────────┬────────┘            └────────┬────────┘
         │                              │
         │ publishes                    │ publishes
         │ DATA_UPDATE_COMPLETE         │ FIXTURE_ANALYSIS_COMPLETE
         └────────────┬─────────────────┘
                      │
         ┌────────────┴────────────┐
         ▼                         ▼
┌─────────────────┐        ┌─────────────────┐
│ Digger waits    │        │ Sophia waits    │
│ for both events │        │ for both events │
│ Analyzes DC     │        │ Analyzes xG     │
└────────┬────────┘        └────────┬────────┘
         │                          │
         │ publishes                │ publishes
         │ DC_ANALYSIS_COMPLETE     │ XG_ANALYSIS_COMPLETE
         └────────────┬─────────────┘
                      │
                      ▼
         ┌────────────────────────┐
         │ Jimmy waits for all 4  │
         │ Calculates EV          │
         │ Ranks transfer options │
         └────────────┬───────────┘
                      │
                      │ publishes
                      │ TRANSFER_RECOMMENDATIONS
                      │
         ┌────────────┴───────────┐
         ▼                        ▼
┌─────────────────┐      ┌─────────────────┐
│ Terry evaluates │      │ Ron aggregates  │
│ if chip needed  │      │ all inputs      │
└────────┬────────┘      └────────┬────────┘
         │                        │
         │ publishes              │ publishes
         │ CHIP_RECOMMENDATION    │ DECISION_PENDING
         │                        │
         └────────────┬───────────┘
                      │
                      ▼
         ┌────────────────────────┐
         │ Ron makes final call   │
         │ Weighs all inputs      │
         │ Applies philosophy     │
         └────────────┬───────────┘
                      │
                      │ publishes
                      │ TEAM_SELECTION_FINAL
                      │
         ┌────────────┴───────────┐
         ▼                        ▼
┌─────────────────┐      ┌─────────────────┐
│ Ellie logs all  │      │ [Future: API    │
│ decisions with  │      │  executor makes │
│ reasoning       │      │  FPL transfers] │
└─────────────────┘      └─────────────────┘
```

**Key Characteristics**:
- Agents work in parallel where possible
- Dependencies handled via event subscriptions
- Each agent autonomous within its domain
- Ron has final say (hierarchical override)
- All decisions logged (event sourcing)

---

## Agent Communication Protocol

### Message Format

All inter-agent messages follow standardized JSON schema:

```json
{
  "event_type": "FIXTURE_ANALYSIS_COMPLETE",
  "timestamp": "2025-10-17T14:32:11Z",
  "agent_id": "priya_fixture_analyst",
  "gameweek": 9,
  "priority": "normal",
  "payload": {
    "teams_analyzed": 20,
    "fixture_window": [9, 10, 11, 12, 13, 14],
    "top_fixtures": [
      {"team": "BHA", "avg_fdr": 2.1, "trend": "improving"},
      {"team": "NFO", "avg_fdr": 2.3, "trend": "stable"}
    ],
    "worst_fixtures": [
      {"team": "MCI", "avg_fdr": 4.2, "trend": "difficult"},
      {"team": "ARS", "avg_fdr": 3.9, "trend": "worsening"}
    ]
  },
  "confidence": 0.87,
  "dependencies_met": ["DATA_UPDATE_COMPLETE"],
  "next_steps": ["TRANSFER_RECOMMENDATIONS"]
}
```

### Event Types

**System Events**:
- `GAMEWEEK_DEADLINE_{XX}H` - XX hours before deadline
- `GAMEWEEK_STARTED` - Fixtures kicking off
- `GAMEWEEK_COMPLETE` - All fixtures finished
- `PRICE_CHANGE_DETECTED` - Daily 2 AM price update
- `INJURY_NEWS` - Player status change
- `TEAM_NEWS` - Press conference / official updates

**Agent Events**:
- `DATA_UPDATE_COMPLETE` - Maggie finished data fetch
- `DC_ANALYSIS_COMPLETE` - Digger's defensive analysis ready
- `XG_ANALYSIS_COMPLETE` - Sophia's attacking analysis ready
- `FIXTURE_ANALYSIS_COMPLETE` - Priya's fixture outlook ready
- `TRANSFER_RECOMMENDATIONS` - Jimmy's value picks ready
- `CHIP_RECOMMENDATION` - Terry's chip advice ready
- `DECISION_PENDING` - Ron gathering inputs
- `TEAM_SELECTION_FINAL` - Ron's final decision
- `DECISION_LOGGED` - Ellie archived decision

**Urgent Events** (high priority):
- `URGENT_PRICE_OPPORTUNITY` - Player about to rise, good value
- `URGENT_INJURY_NEWS` - Key player ruled out
- `URGENT_TEAM_NEWS` - Starting XI change affecting Ron's team

### Agent Mailboxes

Each agent has:
- **Inbox Queue**: Redis Stream for incoming messages
- **Subscription Set**: Redis Pub/Sub channels it monitors
- **Outbox**: Publishes to event bus
- **State Store**: Redis hash for current working state

Example Agent Registry Entry:
```python
{
  "agent_id": "digger_dc_analyst",
  "agent_name": "Derek 'Digger' Thompson",
  "role": "Defensive Contribution Analysis",
  "status": "active",
  "last_heartbeat": "2025-10-17T14:35:22Z",
  "subscriptions": [
    "DATA_UPDATE_COMPLETE",
    "GAMEWEEK_DEADLINE_48H",
    "GAMEWEEK_DEADLINE_24H"
  ],
  "publishes": [
    "DC_ANALYSIS_COMPLETE",
    "DC_PLAYER_ALERT"
  ],
  "dependencies": ["maggie_data_collector"],
  "config": {
    "min_dc_threshold": 10,
    "analysis_window_gws": 6
  }
}
```

---

## LLM Integration Strategy

### Where LLMs Add Value

**1. Unstructured Data Processing**
- **News Analysis** (future roadmap item)
  - Parse FPL newsletters, official website news
  - Extract injury timelines from press conferences
  - Analyze manager quotes for rotation hints
  - Monitor Twitter/X for breaking news
  - **Agent**: New "Media Monitor Agent" (LLM-powered)

- **Sentiment Analysis**
  - Reddit r/FantasyPL community discussions
  - Twitter FPL expert consensus
  - YouTube video content analysis
  - Identify meta shifts and template trends

**2. Decision Explanation & Communication**
- **Ron's Announcements**: Already uses persona.py for template-based text
  - **Enhancement**: LLM generates more natural, varied announcements
  - Maintains Ron's voice (few-shot prompting with examples)
  - Adds contextual color commentary

- **Post-Match Analysis**: Ron's gameweek reviews
  - LLM analyzes what went right/wrong
  - Generates Ron-style tactical commentary

**3. Contextual Reasoning**
- **Injury Severity Assessment**
  - Input: "Hamstring tightness, precautionary substitution"
  - LLM Output: Risk level, expected timeline, confidence
  - Compared against historical injury data

- **Fixture Difficulty Nuance**
  - Input: "Brighton (H) but they're on a 5-game win streak"
  - LLM Output: Adjusted difficulty considering form, context

**4. Strategy Adaptation**
- **Meta-Game Reasoning**
  - "Template ownership is 70% on Haaland - should we differential?"
  - LLM evaluates risk/reward of contrarian plays
  - Considers Ron's rank, league position, gameweeks remaining

### LLM Architecture: Hybrid Approach

**Design Pattern**: Rule-Based Core + LLM Augmentation

```
┌──────────────────────────────────────────────┐
│         RULE-BASED AGENTS (Core Logic)       │
│  • Numerical analysis (xG, xA, DC stats)     │
│  • Optimization algorithms (team selection)  │
│  • Pattern matching (price predictions)      │
│  • Deterministic calculations (budget, EV)   │
└───────────────────┬──────────────────────────┘
                    │
                    │ publishes structured data
                    │
                    ▼
┌──────────────────────────────────────────────┐
│      LLM AUGMENTATION LAYER (Optional)       │
│  • Text generation (announcements)           │
│  • News parsing (injuries, team news)        │
│  • Sentiment analysis (community trends)     │
│  • Contextual reasoning (nuanced decisions)  │
└───────────────────┬──────────────────────────┘
                    │
                    │ enriches with context
                    │
                    ▼
┌──────────────────────────────────────────────┐
│         RON CLANKER (Final Decision)         │
│  • Weighs rule-based + LLM inputs            │
│  • Applies tactical philosophy               │
│  • Makes autonomous decision                 │
└──────────────────────────────────────────────┘
```

### LLM Invocation Methods

**Option 1: API Calls (Recommended for Production)**
- **Anthropic Claude API**: For Ron's personality, analysis
- **Advantages**:
  - No local GPU needed (RPi3 can't run LLMs)
  - Latest models, best performance
  - Managed infrastructure
  - Token-based pricing ($0.01-0.03 per analysis)
- **Disadvantages**:
  - Requires internet connection
  - API costs (estimate £20-50/month for heavy use)
  - Latency (500ms-2s per call)

**Option 2: Local Lightweight Models**
- **TinyLlama, Phi-2** on RPi3 (possible but slow)
- **Advantages**:
  - No API costs
  - Works offline
  - No rate limits
- **Disadvantages**:
  - RPi3 too slow for real-time (30s+ per inference)
  - Limited reasoning capability
  - Higher power consumption

**Option 3: Claude Code Integration (Development)**
- **Current approach**: Use this interface for prototyping
- Call LLM agents via Task tool during development
- Transition to API calls for production deployment

**Recommended Strategy**:
- **Phase 1-2**: No LLM (prove rule-based agents work)
- **Phase 3**: Add Claude API for Ron's announcements
- **Phase 4**: Add media monitoring agent (LLM-powered)
- **Phase 5**: Advanced contextual reasoning

### Example LLM Agent: Media Monitor

```python
class MediaMonitorAgent(BaseAgent):
    """
    LLM-powered agent that monitors FPL news sources.
    Addresses Ron's disadvantage: cut off from media.
    """

    def __init__(self):
        super().__init__(
            agent_id="media_monitor",
            name="Media Monitor Agent",
            subscriptions=["HOURLY_NEWS_CHECK"]
        )
        self.claude_api = AnthropicAPI(api_key=os.getenv('ANTHROPIC_API_KEY'))

    async def analyze_fpl_news(self):
        """Fetch and analyze FPL official news."""
        # Scrape FPL website news section
        news_html = await self.scrape_fpl_news()

        # Call Claude API to extract structured info
        prompt = f"""
        You are analyzing Fantasy Premier League news for Ron Clanker's FPL team.
        Extract injury updates, price changes announcements, and rule changes.

        News HTML:
        {news_html}

        Return JSON:
        {{
          "injuries": [{{
            "player": "name",
            "team": "code",
            "severity": "minor|moderate|severe",
            "expected_return": "GW number or 'unknown'"
          }}],
          "price_changes": [...],
          "important_updates": [...]
        }}
        """

        response = await self.claude_api.complete(prompt)
        structured_data = json.loads(response)

        # Publish injury alerts
        for injury in structured_data['injuries']:
            if injury['severity'] in ['moderate', 'severe']:
                await self.publish_event('INJURY_NEWS', injury)

        return structured_data
```

**API Call Budget**:
- Hourly news check: ~1,000 tokens input + 500 output = ~$0.02/day
- Daily announcements: ~500 tokens input + 1,000 output = ~$0.03/day
- Weekly deep analysis: ~3,000 tokens = ~$0.10/week
- **Monthly cost estimate**: ~£5-10 for moderate LLM use

---

## Infrastructure Components

### Core Technologies

**Message Queue & Event Bus**:
- **Redis 7.0+**
  - Pub/Sub for event broadcasting
  - Streams for agent mailboxes (persistent queues)
  - Hashes for agent state
  - Cache for FPL data (reduce API calls)
- **Why Redis**: Lightweight, fast, runs on RPi3, perfect for pub/sub

**Task Scheduler**:
- **Celery Beat**
  - Cron-like job scheduling
  - Triggers timed events (gameweek deadlines, daily data fetch)
  - Handles retry logic
- **Celery Workers**
  - Execute agent tasks
  - Can scale to multiple workers per agent type

**Database**:
- **PostgreSQL 15** (primary data store)
  - Player historical data
  - Decision logs (event sourcing)
  - Team state over time
  - Learning metrics
- **Why PostgreSQL**: ACID compliance, JSON support, runs on RPi3

**Application Framework**:
- **Python 3.11+**
- **FastAPI** (optional REST API for monitoring)
- **asyncio** for async agent operations

**Containerization**:
- **Docker Compose**
  - Each agent in separate container
  - Easy to update individual agents
  - Restart policies for resilience
  - Resource limits (critical on RPi3)

### File Structure (Extended)

```
ron_clanker/
├── agents/
│   ├── base_agent.py          # Abstract base class all agents inherit
│   ├── manager.py              # Ron Clanker (orchestrator)
│   ├── data_collector.py       # Maggie (data fetching)
│   ├── dc_analyst.py           # Digger (NEW: dedicated DC analysis)
│   ├── xg_analyst.py           # Sophia (NEW: dedicated xG analysis)
│   ├── value_analyst.py        # Jimmy (NEW: extracted from player_valuation)
│   ├── fixture_analyst.py      # Priya (NEW: dedicated fixture analysis)
│   ├── chip_strategist.py      # Terry (NEW: chip timing)
│   ├── learning_agent.py       # Ellie (NEW: learning & feedback)
│   └── media_monitor.py        # NEW: LLM-powered news agent (Phase 4+)
│
├── infrastructure/
│   ├── __init__.py
│   ├── event_bus.py            # Redis pub/sub wrapper
│   ├── message_queue.py        # Agent mailbox management
│   ├── agent_registry.py       # Service discovery
│   ├── scheduler.py            # Celery configuration
│   └── monitoring.py           # Health checks, metrics
│
├── protocols/
│   ├── __init__.py
│   ├── messages.py             # Message schemas (Pydantic models)
│   ├── events.py               # Event type definitions
│   └── contracts.py            # Agent interface contracts
│
├── llm/
│   ├── __init__.py
│   ├── claude_client.py        # Anthropic API wrapper
│   ├── prompts.py              # Prompt templates
│   └── parsers.py              # LLM response parsing
│
├── docker/
│   ├── docker-compose.yml      # Multi-container orchestration
│   ├── Dockerfile.base         # Base Python image
│   ├── Dockerfile.agent        # Agent container template
│   └── Dockerfile.redis        # Redis configuration
│
├── config/
│   ├── settings.py             # Central configuration
│   ├── agent_config.yaml       # Per-agent settings
│   └── secrets.env             # API keys (not committed)
│
├── scripts/
│   ├── deploy_to_rpi.sh        # Deployment automation
│   ├── health_check.sh         # System monitoring
│   └── backup_database.sh      # Daily backups
│
└── monitoring/
    ├── prometheus.yml          # Metrics collection
    ├── grafana_dashboard.json  # Visualization
    └── alerts.yml              # Alert rules
```

---

## Raspberry Pi Deployment

### Hardware Specifications

**Target Device**: Raspberry Pi 3 Model B+
- **CPU**: 1.4 GHz quad-core ARM Cortex-A53
- **RAM**: 1 GB LPDDR2
- **Storage**: 32+ GB microSD (recommend 64 GB for headroom)
- **Network**: Ethernet (more reliable than WiFi for 24/7 operation)
- **Power**: UPS backup (critical for continuous operation)

### Resource Considerations

**Memory Footprint** (estimated):
- PostgreSQL: 150-200 MB
- Redis: 50-100 MB
- Python agents (7 containers @ ~50 MB each): 350 MB
- Celery workers (2 workers): 100 MB
- System overhead: 200 MB
- **Total**: ~850 MB (comfortable fit in 1 GB with swap)

**CPU Load**:
- Idle: 5-10%
- Data fetch/analysis: 30-50% (periodic bursts)
- Gameweek decision (parallel agents): 70-90% (short duration)
- **Assessment**: Adequate for task

**Network**:
- FPL API calls: ~10 MB/day
- Price prediction scraping: ~5 MB/day
- LLM API calls (if used): ~20 MB/day
- **Total**: <50 MB/day (minimal)

### Docker Compose Configuration

```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    container_name: ron_redis
    command: redis-server --maxmemory 100mb --maxmemory-policy allkeys-lru
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped
    mem_limit: 128m
    cpus: 0.5

  postgres:
    image: postgres:15-alpine
    container_name: ron_postgres
    environment:
      POSTGRES_DB: ron_clanker
      POSTGRES_USER: ron
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped
    mem_limit: 256m
    cpus: 0.5

  # Agent containers
  agent_manager:
    build:
      context: .
      dockerfile: docker/Dockerfile.agent
    container_name: ron_manager
    environment:
      AGENT_TYPE: manager
      REDIS_URL: redis://redis:6379
      DB_URL: postgresql://ron:${DB_PASSWORD}@postgres:5432/ron_clanker
    depends_on:
      - redis
      - postgres
    restart: unless-stopped
    mem_limit: 64m
    cpus: 0.3

  agent_maggie:
    build:
      context: .
      dockerfile: docker/Dockerfile.agent
    environment:
      AGENT_TYPE: data_collector
      REDIS_URL: redis://redis:6379
      FPL_MCP_URL: ${FPL_MCP_URL}
    depends_on:
      - redis
    restart: unless-stopped
    mem_limit: 64m
    cpus: 0.3

  # ... (similar for each agent: digger, sophia, jimmy, priya, terry, ellie)

  scheduler:
    build:
      context: .
      dockerfile: docker/Dockerfile.agent
    container_name: ron_scheduler
    command: celery -A infrastructure.scheduler beat
    environment:
      REDIS_URL: redis://redis:6379
    depends_on:
      - redis
    restart: unless-stopped
    mem_limit: 32m
    cpus: 0.2

  worker:
    build:
      context: .
      dockerfile: docker/Dockerfile.agent
    command: celery -A infrastructure.scheduler worker --concurrency=2
    environment:
      REDIS_URL: redis://redis:6379
    depends_on:
      - redis
    restart: unless-stopped
    mem_limit: 128m
    cpus: 0.5

  # Optional: Monitoring
  prometheus:
    image: prom/prometheus:latest
    container_name: ron_prometheus
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.retention.time=30d'
    ports:
      - "9090:9090"
    restart: unless-stopped
    mem_limit: 64m

volumes:
  redis_data:
  postgres_data:
  prometheus_data:
```

**Total Resource Usage**: ~850 MB RAM, ~2.5 CPU cores (shared)
**RPi3 Capacity**: 1 GB RAM, 4 cores
**Headroom**: Tight but viable with optimization

### Deployment Strategy

**1. Preparation**:
```bash
# On RPi3
sudo apt update && sudo apt upgrade -y
sudo apt install docker.io docker-compose git -y
sudo usermod -aG docker $USER

# Clone repo
git clone <repo_url> /home/pi/ron_clanker
cd /home/pi/ron_clanker

# Create secrets
cp config/secrets.env.template config/secrets.env
nano config/secrets.env  # Add API keys, passwords
```

**2. Initial Deployment**:
```bash
# Build images
docker compose build

# Start core services first
docker compose up -d redis postgres

# Wait for DB to initialize
sleep 10

# Run migrations
docker compose run --rm agent_manager python scripts/setup_database.py

# Start all agents
docker compose up -d

# Check status
docker compose ps
docker compose logs -f
```

**3. Monitoring**:
```bash
# Health check script (runs via cron every 5 min)
#!/bin/bash
# scripts/health_check.sh

CONTAINERS=("ron_manager" "agent_maggie" "agent_digger" ...)

for container in "${CONTAINERS[@]}"; do
  if ! docker ps | grep -q "$container"; then
    echo "WARNING: $container is down! Restarting..."
    docker compose restart "$container"
    # Send alert (email, Discord webhook, etc.)
  fi
done
```

**4. Backup Strategy**:
```bash
#!/bin/bash
# scripts/backup_database.sh (runs daily at 3 AM)

BACKUP_DIR="/home/pi/ron_clanker/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# Backup PostgreSQL
docker exec ron_postgres pg_dump -U ron ron_clanker > \
  "$BACKUP_DIR/db_backup_$DATE.sql"

# Backup Redis (RDB snapshot)
docker exec ron_redis redis-cli BGSAVE
cp /var/lib/docker/volumes/ron_clanker_redis_data/_data/dump.rdb \
  "$BACKUP_DIR/redis_backup_$DATE.rdb"

# Keep last 30 days
find "$BACKUP_DIR" -name "*.sql" -mtime +30 -delete
find "$BACKUP_DIR" -name "*.rdb" -mtime +30 -delete
```

### UPS Integration

**Purpose**: Prevent data corruption during power outages

**Recommended UPS**: APC Back-UPS or similar with USB monitoring

**Setup**:
```bash
# Install NUT (Network UPS Tools)
sudo apt install nut -y

# Configure UPS monitoring
sudo nano /etc/nut/ups.conf
# Add:
# [apc]
#   driver = usbhid-ups
#   port = auto
#   desc = "APC UPS for Ron Clanker"

# Monitor UPS events
sudo nano /etc/nut/upssched.conf
# On ONBATT (power lost): Alert agents, trigger graceful shutdown if <5 min battery
# On ONLINE (power restored): Resume normal operation
```

**Graceful Shutdown Script**:
```bash
#!/bin/bash
# scripts/ups_shutdown.sh

# Publish POWER_FAILURE event
redis-cli PUBLISH system_events '{"event": "POWER_FAILURE", "battery_remaining": "4min"}'

# Wait for agents to finish critical tasks (max 60 sec)
sleep 60

# Stop containers gracefully
docker compose stop

# Shutdown system
sudo shutdown -h now
```

---

## Roadmap & Phases

### Phase 1: Event Infrastructure (Weeks 1-2)

**Goal**: Build the messaging backbone

**Tasks**:
1. Implement `infrastructure/event_bus.py` (Redis pub/sub)
2. Create `agents/base_agent.py` (abstract class)
3. Convert Maggie (Data Collector) to event-driven pattern
4. Implement agent registry and heartbeat monitoring
5. Test end-to-end event flow: Trigger → Maggie → Event published

**Deliverable**: One agent operating autonomously via events

**Success Criteria**:
- Maggie fetches data every 6 hours automatically
- Publishes `DATA_UPDATE_COMPLETE` event with payload
- Other services can subscribe and receive event
- System recovers if Maggie container restarts

---

### Phase 2: Agent Conversion (Weeks 3-4)

**Goal**: All agents event-driven

**Tasks**:
1. Extract specialist agents from monolithic `player_valuation.py`:
   - `dc_analyst.py` (Digger)
   - `xg_analyst.py` (Sophia)
   - `value_analyst.py` (Jimmy)
   - `fixture_analyst.py` (Priya)
2. Implement `chip_strategist.py` (Terry)
3. Implement `learning_agent.py` (Ellie)
4. Each agent subscribes to relevant events
5. Define complete event DAG (directed acyclic graph)

**Deliverable**: 7 autonomous agents + Ron

**Success Criteria**:
- Each agent responds to events independently
- Parallel processing (Digger + Sophia run simultaneously)
- Agent failure doesn't crash system
- All agents log decisions to database

---

### Phase 3: Orchestration & Scheduling (Weeks 5-6)

**Goal**: Automated workflows

**Tasks**:
1. Implement Celery Beat scheduler
2. Define scheduled tasks:
   - Daily data fetch (6 AM)
   - Price change check (2:30 AM)
   - Gameweek planning (48h, 24h, 6h before deadline)
   - Post-gameweek review (Monday 10 AM)
3. Implement Ron's consensus mechanism (weighted voting)
4. Add conflict resolution logic
5. Create gameweek workflow orchestration

**Deliverable**: Fully automated gameweek cycle

**Success Criteria**:
- System plans and selects team without human input
- Ron's announcement generated automatically
- Decisions logged with full reasoning chain
- System handles edge cases (injuries, price rises during planning)

---

### Phase 4: Resilience & Monitoring (Weeks 7-8)

**Goal**: Production-ready reliability

**Tasks**:
1. Add retry logic and circuit breakers
2. Implement agent fallbacks (cached data, conservative defaults)
3. Set up Prometheus + Grafana monitoring
4. Create health check dashboard
5. Configure alert system (email/Discord on agent failure)
6. Add database backup automation
7. Implement UPS shutdown scripts

**Deliverable**: Bulletproof system

**Success Criteria**:
- System runs 7 days without intervention
- Recovers from Redis/PostgreSQL restarts
- Alerts on anomalies (agent down, API failure)
- Zero data loss from power failure (UPS tested)

---

### Phase 5: LLM Integration - Communication (Weeks 9-10)

**Goal**: Natural language announcements

**Tasks**:
1. Implement `llm/claude_client.py` (Anthropic API wrapper)
2. Create Ron's announcement prompts (few-shot with examples)
3. Generate team selections in Ron's voice
4. Generate post-gameweek reviews
5. Add variation/creativity to avoid repetitive text

**Deliverable**: Ron sounds human

**Success Criteria**:
- Announcements indistinguishable from human-written
- Maintains consistent persona
- Adds contextual commentary
- API costs <£10/month

---

### Phase 6: Media Monitoring (Weeks 11-14)

**Goal**: Address Ron's media disadvantage

**Tasks**:
1. Implement `agents/media_monitor.py` (LLM-powered)
2. Scrape FPL official news, newsletters
3. Monitor Twitter/X for breaking news (FPL official, journalists)
4. Parse press conference transcripts
5. Analyze YouTube FPL expert content (transcripts)
6. Extract structured data (injuries, rotation hints, DGW announcements)
7. Publish `INJURY_NEWS`, `TEAM_NEWS`, `URGENT_ALERT` events

**Data Sources**:
- FPL official website news section
- FPL Twitter/X account
- @BenCrellin (fixture expert)
- @OfficialFPL newsletter (email parsing)
- Press conference transcripts (via PremierLeague.com)
- YouTube channels: Let's Talk FPL, FPL Focal, FPL Mate (transcripts via API)

**Deliverable**: Ron informed like human managers

**Success Criteria**:
- Injury news detected within 1 hour of announcement
- DGW/BGW announcements captured immediately
- Press conference hints incorporated (e.g., "rotation likely")
- False positive rate <10%

---

### Phase 7: FPL API Integration - Automated Execution (Weeks 15-18)

**Goal**: Autonomous transfers without human intervention

**CRITICAL**: This phase has highest risk (API changes, account issues)

**Tasks**:
1. Research and document FPL API write endpoints
   - Reverse-engineer transfer POST request
   - Document authentication flow
   - Test on dummy account first
2. Implement `fpl_api/client.py` with authentication
3. Build transfer execution module with extensive error handling
4. Implement dry-run mode (log intended transfers, don't execute)
5. Add human approval gate (optional override)
6. Build fallback: Web UI automation (Playwright) if API fails
7. Extensive testing on test account

**Safety Measures**:
- Dry-run mode for first month (Ron decides, human executes)
- Rate limiting (max 1 request per minute)
- Validation checks (budget, team rules, chip availability)
- Human approval for high-risk decisions (e.g., -8 hit)
- Rollback capability if transfer fails
- Detailed logging of all API interactions

**Deliverable**: True autonomy (with safeguards)

**Success Criteria**:
- Ron successfully makes transfers via API
- Zero invalid transfers (all pass FPL validation)
- Graceful handling of API errors
- Human can override if needed
- Account not suspended/banned

---

### Phase 8: Advanced Learning (Weeks 19-24)

**Goal**: System improves over time

**Tasks**:
1. Implement Ellie's learning algorithms:
   - Track prediction accuracy (expected vs actual points)
   - Identify systematic biases (e.g., overvaluing attackers)
   - Adjust agent weights based on performance
   - A/B test strategy variations
2. Build meta-learner: Which agents' advice to trust most
3. Implement Bayesian updating for price predictions
4. Train ML models on historical data:
   - Player performance prediction (xG regression)
   - Fixture difficulty rating (team strength model)
   - Price change prediction (ownership + transfers)
5. Ensemble models (combine multiple predictions)

**Deliverable**: System gets smarter each week

**Success Criteria**:
- Prediction accuracy improves month-over-month
- System identifies which agents are most reliable
- Adapts to meta shifts (e.g., if DC strategy stops working)
- Beats 50th percentile by end of season

---

### Future Enhancements (Post-Season 1)

**Season 2+**:
- Advanced RL (reinforcement learning) for long-term planning
- Multi-objective optimization (maximize points + rank improvement)
- Risk-adjusted strategies (conservative when leading, aggressive when chasing)
- Template analysis (when to follow vs fade popular picks)
- Differential targeting (ownership-weighted EV calculations)
- League-specific strategies (mini-league rivals analysis)

---

## Open Questions & Challenges

### 1. FPL API Legality & Risk

**Question**: Is automated API usage against FPL Terms of Service?

**Research Needed**:
- Review FPL T&C for automation clauses
- Check if others have been banned for API bots
- Consider if this is "unfair advantage" (unlikely, as all data is public)

**Mitigation**:
- Start with read-only implementation
- Use conservative rate limiting
- Add human-in-loop for final execution initially
- Be prepared to fall back to manual execution if banned

**Risk Level**: Medium-Low (many FPL analytics tools use API, none banned that we know of)

---

### 2. Price Change Prediction Accuracy

**Challenge**: Algorithm is opaque and changes unpredictably

**Approach**:
- Scrape multiple prediction sources (LiveFPL, FFS, FFHub)
- Ensemble predictions (if 3/3 agree on 100% rise, high confidence)
- Track our own prediction accuracy
- Learn optimal threshold (e.g., only act on >95% confidence)
- Accept that we'll miss some and make occasional mistakes

**Trade-off**:
- Act early (risk transfer on false alarm) vs wait (miss price rise)
- Solution: EV calculation. Only act if:
  `(Price gain probability × £0.1m value) > (Suboptimal timing cost × Points lost)`

---

### 3. Raspberry Pi Performance

**Concern**: Will RPi3 handle the load?

**Testing Plan**:
- Deploy on development machine first, measure actual resource usage
- Load test with all agents running simultaneously
- Optimize hot paths (caching, lazy loading, async I/O)
- Consider RPi4 upgrade if needed (2-8 GB RAM, faster CPU)

**Fallback**:
- Deploy to cloud (AWS t2.micro free tier, £5/month)
- Or hybrid: RPi for agents, cloud for database

---

### 4. Media Monitoring Data Sources

**Challenge**: FPL official news is on website (scraping), some sources require auth

**Sources Ranked by Feasibility**:
1. **Easy**: FPL official news page (public HTML scraping)
2. **Easy**: Twitter/X via API (requires API key, £100/month for v2 API or free basic tier)
3. **Medium**: FPL newsletter (requires email IMAP parsing)
4. **Medium**: YouTube transcripts (YouTube Data API free tier)
5. **Hard**: Press conference transcripts (may require Premier League API or scraping)

**Phase 6 MVP**: FPL official + Twitter only. Expand later.

---

### 5. LLM Costs

**Estimated Monthly Costs** (Anthropic Claude API):
- 30 team announcements: 30 × 1,500 tokens × $0.015/1K = ~$0.70
- 4 weekly reviews: 4 × 2,000 tokens × $0.015/1K = ~$0.12
- 30 news analysis (Phase 6): 30 × 1,500 tokens × $0.015/1K = ~$0.70
- **Total**: ~£1.50/month

**Verdict**: Negligible. Even with 10x usage, <£15/month.

---

### 6. Human Override Mechanism

**Design Question**: When/how should humans intervene?

**Proposal - Approval Gates**:
- **No approval needed**:
  - Data fetching
  - Analysis/recommendations
  - Free transfers (1-2 per week)
  - Captain changes
  - Chip usage (if consensus from Terry + Ron)

- **Optional approval** (notification + 6h window to override):
  - Points hits (-4)
  - Early transfers (before deadline -24h)

- **Required approval**:
  - Large hits (-8 or more)
  - Wildcard activation
  - First use of automated API transfers (until proven stable)

**Interface**:
- Discord bot with approve/reject buttons
- Web dashboard showing pending decisions
- Email/SMS alerts for urgent decisions

---

### 7. System Evolution & Versioning

**Challenge**: Agents improve over time, how to manage changes?

**Strategy**:
- Semantic versioning for each agent (e.g., `digger_v1.2.3`)
- Blue-green deployment (run old + new version, compare outputs)
- Gradual rollout (new version for 1 gameweek, monitor, then promote)
- Rollback capability (revert to previous version if performance degrades)
- Decision log includes agent version (for post-season analysis)

---

## Conclusion

This architecture transforms Ron Clanker from a collection of scripts into a **true agentic system**:

✅ **Autonomous**: Makes all decisions without human input
✅ **Distributed**: Specialist agents run independently
✅ **Event-Driven**: Reacts to real-world FPL events in real-time
✅ **Resilient**: Continues operating despite failures
✅ **Learning**: Improves performance over time
✅ **Hybrid Intelligence**: Rule-based core + LLM augmentation

**Key Innovations**:
1. Multi-agent architecture with personality-driven design (backroom staff)
2. Event-driven communication (agents publish findings, subscribe to needs)
3. Hierarchical orchestration (Ron has final say, but agents autonomous within domain)
4. Hybrid LLM approach (use where valuable, not everywhere)
5. Edge deployment (RPi3 with UPS - true 24/7 autonomous operation)

**Development Timeline**: 24 weeks to full autonomy
**Estimated Costs**: £15/month (LLM APIs), £0 hardware (existing RPi3)
**Success Metric**: Top 50% rank by end of Season 1, improving each season

This is a **production-grade agentic system**, suitable as a case study for real-world multi-agent architectures. It demonstrates:
- Service-oriented architecture
- Event sourcing and CQRS patterns
- Microservices communication
- Autonomous decision-making
- Continuous learning
- Edge computing deployment

**The system plays FPL. But the real game is proving agentic AI works in complex, real-world scenarios.**

---

**Next Steps**:
1. Review this architecture with stakeholders
2. Finalize technology stack decisions
3. Begin Phase 1 implementation (event infrastructure)
4. Set up RPi3 development environment
5. Document API endpoints and authentication flow

**Questions for Discussion**:
- Approved to proceed with this architecture?
- Any concerns about FPL API automation risks?
- Preference for LLM provider (Claude vs GPT-4 vs open source)?
- Timeline acceptable or need to accelerate?

---

**Document Version**: 1.0
**Last Updated**: October 6, 2025
**Author**: Claude (Anthropic) + Ron Clanker Development Team
**Status**: Awaiting Approval
