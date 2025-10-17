# FPL MCP Server Setup - Ron Clanker

## Overview

Ron uses the `fantasy-pl-mcp` server to fetch all FPL data. This MCP server provides access to:
- Player statistics (including GW1-7 performance)
- Team data
- Fixtures
- Gameweek information
- Player comparisons

**Repository**: https://github.com/rishijatia/fantasy-pl-mcp

---

## Installation

### Option 1: PyPI (Recommended)

```bash
pip install fpl-mcp
```

### Option 2: From GitHub

```bash
pip install git+https://github.com/rishijatia/fantasy-pl-mcp.git
```

---

## Running the MCP Server

### Standalone Server

```bash
# Using CLI command
fpl-mcp

# OR using Python module
python -m fpl_mcp
```

### With Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "fantasy-pl": {
      "command": "python",
      "args": ["-m", "fpl_mcp"]
    }
  }
}
```

---

## Authentication (Optional)

For authenticated features:

```bash
fpl-mcp-config setup
```

This will prompt for FPL credentials if needed.

---

## Available MCP Tools

The server provides these tools that Ron can use:

1. **Get Gameweek Status**
   - Current gameweek information
   - Deadlines
   - Status

2. **Analyze Player Fixtures**
   - Upcoming fixtures for specific players
   - Difficulty ratings
   - Home/away analysis

3. **Compare Players**
   - Side-by-side player comparisons
   - Stats comparison
   - Performance analysis

4. **Player Search**
   - Search by name
   - Search by team
   - Filter by position

5. **Player Statistics**
   - Full player data including:
     - Points, form, value
     - Goals, assists, clean sheets
     - **Defensive stats** (tackles, interceptions, etc.) - THE KEY DATA!
     - Minutes played
     - Price changes

---

## Integration with Ron's System

### Current Implementation

Ron's `DataCollector` agent (`agents/data_collector.py`) has placeholder methods ready for MCP integration:

```python
async def fetch_bootstrap_data(self) -> Dict[str, Any]:
    if self.mcp_client:
        # TODO: Use MCP client when available
        pass
```

### What We Need to Do

1. **Install the MCP server**
   ```bash
   pip install fpl-mcp
   ```

2. **Start the MCP server** (in separate terminal or background)
   ```bash
   fpl-mcp
   ```

3. **Connect Ron's DataCollector to MCP**
   - Update `agents/data_collector.py` to use MCP client
   - Replace placeholder methods with actual MCP calls
   - Fetch GW1-7 data for analysis

---

## Critical Data Needed for GW8 Squad Selection

### 1. Bootstrap Static Data
Contains all players, teams, and current gameweek info:
- All 600+ players with current stats
- All 20 teams
- Current gameweek status
- Player prices (current)

### 2. Player Detailed Stats (GW1-7)
For each player we need:
- Total points scored
- Minutes played
- Goals, assists, clean sheets
- **CRITICAL: Defensive stats**
  - Tackles
  - Interceptions
  - Clearances/blocks/interceptions (CBI)
  - Recoveries
- Bonus points earned
- Form (recent performance)

### 3. Fixtures Data
- Upcoming fixtures (GW8+)
- Difficulty ratings
- Home/away
- Double gameweeks (if any)

### 4. Gameweek-by-Gameweek History
To identify **consistent** DC performers:
- GW1 stats, GW2 stats, GW3 stats, etc.
- See who hits DC thresholds regularly
- Not just total, but consistency

---

## Usage Example (Conceptual)

```python
from fpl_mcp import MCPClient

# Initialize MCP client
mcp_client = MCPClient()

# Get all current player data
bootstrap = await mcp_client.get_bootstrap_static()
players = bootstrap['elements']

# Get detailed player history
player_id = 123
player_detail = await mcp_client.get_player_summary(player_id)

# Analyze fixtures
fixtures = await mcp_client.get_fixtures()
```

---

## Next Steps for Ron

1. **Install MCP server**
   ```bash
   pip install fpl-mcp
   ```

2. **Test MCP connection**
   - Start server
   - Verify data access
   - Check defensive stats availability

3. **Update DataCollector agent**
   - Replace placeholders with MCP calls
   - Add defensive stats extraction
   - Build DC analysis methods

4. **Fetch GW1-7 data**
   - Get all player performance
   - Extract defensive statistics
   - Identify consistent DC performers

5. **Build GW8 squad**
   - Use Ron's valuation agent
   - Prioritize proven DC players
   - Optimize within £100m budget

---

## Requirements

- Python 3.10+
- `fpl-mcp` package
- Internet connection (for FPL API access)

---

## Troubleshooting

### MCP Server Won't Start
- Check Python version: `python --version` (needs 3.10+)
- Reinstall: `pip install --upgrade fpl-mcp`

### No Data Returned
- Check internet connection
- Verify FPL API is accessible
- Try authentication setup if needed

### Missing Defensive Stats
- Ensure using latest version of fpl-mcp
- Check if FPL API provides these stats
- May need to calculate from detailed player data

---

**Status**: Ready to install and test MCP server connection.

**Next Action**: Install `fpl-mcp` and verify data access for GW1-7 analysis.
