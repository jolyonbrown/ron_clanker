# Quick Start - Ron Clanker for Gameweek 8

**Goal**: Get Ron analyzing GW1-7 data and selecting his optimal GW8 squad.

---

## Step 1: Install Dependencies

```bash
# Install all Python dependencies including fpl-mcp
pip install -r requirements.txt

# Verify installation
fpl-mcp --help
```

---

## Step 2: Test MCP Server Connection

```bash
# Start the MCP server in one terminal
fpl-mcp

# Server should start and be ready to accept requests
# Keep this terminal open
```

---

## Step 3: Test Data Access (Optional)

In Python, test that we can fetch FPL data:

```python
# Quick test to verify MCP connection
import asyncio
from fpl_mcp import MCPClient  # May need to check actual import

async def test_connection():
    # Get bootstrap data
    response = await client.get_bootstrap_static()
    print(f"Found {len(response['elements'])} players")
    print(f"Current gameweek: {response['events'][0]['id']}")

# Run test
asyncio.run(test_connection())
```

---

## Step 4: Run Ron's Data Analysis

```bash
# Ron's first task: Analyze GW1-7 to find DC performers
python scripts/analyze_gw1_7.py

# This will:
# 1. Fetch all player data from FPL API via MCP
# 2. Calculate defensive contribution stats for each player
# 3. Identify consistent DC performers
# 4. Generate report of top DC players by position
```

**Note**: This script doesn't exist yet - we need to create it!

---

## Step 5: Select GW8 Squad

```bash
# Use Ron's Manager Agent to select optimal team
python scripts/select_gw8_team.py

# This will:
# 1. Use valuation agent to rank all players
# 2. Build optimal 15-player squad (£100m budget)
# 3. Prioritize proven DC performers
# 4. Select captain based on GW8 fixtures
# 5. Generate Ron's team announcement
```

**Note**: This script doesn't exist yet - we need to create it!

---

## What We Need to Build

### Priority 1: GW1-7 Analysis Script

**File**: `scripts/analyze_gw1_7.py`

**Purpose**: Fetch and analyze all GW1-7 data to identify:
- Defenders hitting 10+ CBI+tackles consistently
- Midfielders hitting 12+ defensive actions consistently
- Best value players (points per million)
- Form trends
- Price changes

**Output**:
- CSV/JSON with player rankings
- DC consistency scores
- Recommendations for GW8 squad

### Priority 2: GW8 Squad Selection Script

**File**: `scripts/select_gw8_team.py`

**Purpose**: Use Ron's agents to select optimal team:
- DataCollector: Fetch current prices and fixtures
- PlayerValuation: Rank players by value + DC potential
- Manager: Make final squad selection
- Ron's Persona: Generate team announcement

**Output**:
- 15-player squad
- Captain selection
- Team announcement in Ron's voice
- Save to database

### Priority 3: MCP Integration Updates

**Files**: `agents/data_collector.py`

**Changes needed**:
- Replace placeholder MCP calls with actual implementation
- Add methods to fetch GW1-7 history
- Extract defensive statistics from player data
- Calculate DC consistency metrics

---

## Development Workflow

### For immediate testing without scripts:

```python
# In Python REPL or Jupyter notebook
from agents.data_collector import DataCollector
from agents.player_valuation import PlayerValuationAgent
from agents.manager import ManagerAgent
from data.database import Database

# Initialize
db = Database()
collector = DataCollector()  # Will need MCP client
valuation = PlayerValuationAgent()
ron = ManagerAgent(db, collector)

# When MCP is connected:
# 1. Fetch data
data = await collector.update_all_data()

# 2. Analyze DC performers
for player in data['players']:
    dc_assessment = valuation.assess_defensive_contribution_potential(player)
    if dc_assessment['competitive_edge']:
        print(f"{player['web_name']}: {dc_assessment}")

# 3. Select team (once we have GW1-7 data)
team, announcement = await ron.select_initial_team()
print(announcement)
```

---

## Current Blockers

1. **MCP Integration**: Need to connect DataCollector to actual MCP server
2. **GW1-7 Data**: Need to fetch historical gameweek data (not just current)
3. **Defensive Stats**: Need to verify FPL API provides tackles/interceptions/CBI/recoveries
4. **Scripts**: Need to create analysis and selection scripts

---

## Next Immediate Actions

**Option A: Manual Testing**
1. Install fpl-mcp: `pip install fpl-mcp`
2. Start MCP server: `fpl-mcp`
3. Use Claude Desktop with MCP to explore available data
4. Verify defensive stats are accessible

**Option B: Build Scripts**
1. Create `scripts/analyze_gw1_7.py`
2. Create `scripts/select_gw8_team.py`
3. Update `agents/data_collector.py` with MCP calls
4. Run analysis and select team

**Option C: Use Claude Code**
1. Let Claude Code help build the integration scripts
2. Test MCP data access
3. Build analysis pipeline
4. Generate GW8 squad selection

---

## Expected Timeline

- **MCP Setup & Testing**: 30 mins
- **Build Analysis Script**: 1-2 hours
- **Build Selection Script**: 1-2 hours
- **Test & Refine**: 1 hour
- **GW8 Squad Ready**: ~4-6 hours total

We have the international break, so plenty of time!

---

**Ron says**: *"Right, enough talk. Let's get the server running, fetch the data, and build this squad properly. International break won't last forever."*
