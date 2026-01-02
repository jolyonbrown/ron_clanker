# Ron Clanker Operations Runbook

## Quick Reference

### Core Commands (Most Used)

```bash
# Daily data sync
python scripts/collect_fpl_data.py

# Pre-deadline team selection (run 6 hours before deadline)
python scripts/pre_deadline_selection.py

# Post-gameweek workflow (unified - run after GW finishes)
python scripts/post_gameweek_workflow.py

# Track Ron's performance
python scripts/track_ron_team.py --sync

# System health check
python scripts/health_check.py
```

---

## Gameweek Workflow

### Pre-Deadline (6 hours before)

```bash
# 1. Sync latest FPL data
python scripts/collect_fpl_data.py

# 2. Gather intelligence (injuries, press conferences, expert picks)
# Use Claude Code subagent pattern - see "Intelligence Gathering" section below

# 3. Run pre-deadline selection (generates team, transfers, captain)
python scripts/pre_deadline_selection.py

# Or specify gameweek and override free transfers (e.g., AFCON GW16 = 5 FTs)
python scripts/pre_deadline_selection.py --gameweek 16 --free-transfers 5

# 4. View the selection
python scripts/show_latest_team.py
```

**Special Events (AFCON etc.):**
FT top-ups are now configured in `config/special_events.yaml` and applied automatically.
No manual override needed - the system reads the config.

### Post-Gameweek (After all matches complete)

**Recommended: Use the unified workflow script**
```bash
# Single command that orchestrates all post-GW tasks
python scripts/post_gameweek_workflow.py

# Or specify gameweek explicitly
python scripts/post_gameweek_workflow.py --gw 15

# Skip ML update (faster)
python scripts/post_gameweek_workflow.py --skip-ml
```

**Manual steps (if running individually):**
```bash
# 1. Collect results and update database
python scripts/collect_post_gameweek_data.py

# 2. Track Ron's performance
python scripts/track_ron_team.py --sync

# 3. Performance review (calculates RMSE/MAE, stores learning adjustments)
python scripts/post_gameweek_review.py --gw 15

# 4. Update ML models with new data
python scripts/update_ml_models.py
```

**What the workflow learns:**
The post-GW workflow calculates prediction errors and stores bias corrections:
- **Position corrections**: If we over-predict DEF by 0.3 pts, future DEF predictions reduced by 0.3
- **Price bracket corrections**: If we over-predict mid-price players by 0.8 pts, those are reduced

These adjustments are automatically applied in the next `pre_deadline_selection.py` run.
Check current adjustments: `python -c "from learning.performance_tracker import PerformanceTracker; from data.database import Database; print(PerformanceTracker(Database()).get_active_adjustments())"`

---

## Script Categories

### Workflow Scripts
| Script | Purpose | When to Use |
|--------|---------|-------------|
| `post_gameweek_workflow.py` | **Unified post-GW workflow** (orchestrates all steps) | After GW finishes |
| `pre_deadline_selection.py` | Full team selection with ML predictions | 6 hours before deadline |

### Data Collection
| Script | Purpose | When to Use |
|--------|---------|-------------|
| `collect_fpl_data.py` | Sync players, teams, fixtures from FPL API | Daily |
| `collect_post_gameweek_data.py` | Collect GW results after matches | Post-GW (or via workflow) |
| `collect_price_snapshots.py` | Record price changes | Hourly (automated) |

### Team Selection
| Script | Purpose | When to Use |
|--------|---------|-------------|
| `pre_deadline_selection.py` | Full team selection with ML predictions | Pre-deadline |
| `pre_deadline_optimizer.py` | Transfer optimization only | Debug/analysis |
| `show_latest_team.py` | Display current draft team | Any time |
| `send_team_announcement.py` | Send Slack announcement after Chrome submission | Post-submission |

### ML Training
| Script | Purpose | When to Use |
|--------|---------|-------------|
| `train_prediction_models.py` | Train sklearn ensemble (RF+XGB+Ridge) | Weekly or after data changes |
| `train_neural_models.py` | Train PyTorch neural models (GPU) | Weekly |
| `train_transformer.py` | Train transformer with player embeddings (GPU) | Weekly (post-GW) |
| `train_price_model.py` | Train price change predictor | Weekly |
| `tune_hyperparameters.py` | Optuna hyperparameter tuning | Occasionally |
| `update_ml_models.py` | Incremental model update | Post-GW |

### Analysis
| Script | Purpose | When to Use |
|--------|---------|-------------|
| `analyze_dc_performers.py` | Defensive contribution analysis | Pre-selection |
| `analyze_fixtures.py` | Fixture difficulty analysis | Planning |
| `analyze_gw_results.py` | Post-GW performance review | Post-GW |
| `analyze_player_performance.py` | Player stats deep dive | Research |

### Tracking
| Script | Purpose | When to Use |
|--------|---------|-------------|
| `track_ron_team.py` | Track Ron's FPL performance | Post-GW |
| `track_mini_league.py` | Track mini-league standings | Weekly |
| `track_global_rankings.py` | Track overall rank | Weekly |
| `track_gameweek_live.py` | Live GW tracking | During matches |

### Intelligence Gathering
| Script | Purpose | When to Use |
|--------|---------|-------------|
| `daily_scout.py` | Gather news from all sources | Daily (automated) |
| `gather_news_intelligence.py` | Manual news collection | As needed |
| `process_press_conferences.py` | Extract injury info from pressers | Pre-GW |

### Maintenance
| Script | Purpose | When to Use |
|--------|---------|-------------|
| `health_check.py` | System health verification | Daily |
| `backup_database.py` | Backup SQLite database | Daily |
| `db_maintenance.py` | Database optimization | Weekly |
| `cleanup_expired_transcripts.py` | Clean old YouTube transcripts | Weekly |
| `rotate_logs.py` | Rotate log files | Weekly |

### Setup (One-time)
| Script | Purpose | When to Use |
|--------|---------|-------------|
| `setup_database.py` | Initialize database schema | Initial setup |
| `setup_cron.py` | Configure scheduled jobs | Initial setup |
| `setup_notifications.py` | Configure webhooks | Initial setup |
| `import_historical_seasons.py` | Load historical FPL data | Initial setup |

---

## Training Models

### Full Retrain (after major data changes)

```bash
# 1. Train sklearn ensemble
python scripts/train_prediction_models.py --seasons 2022-23 2023-24 2024-25

# 2. Train neural models (requires GPU)
python scripts/train_neural_models.py --epochs 100 --batch-size 512

# 3. Train transformer model (requires GPU) - learns player embeddings
python scripts/train_transformer.py --epochs 50

# 4. Train price model
python scripts/train_price_model.py
```

### Weekly Update (post-gameweek)

Run after each gameweek completes to incorporate new data:

```bash
# Quick incremental update
python scripts/update_ml_models.py

# Retrain transformer (recommended weekly - uses latest form data)
# ~5-10 mins on GPU, free to run locally
python scripts/train_transformer.py --epochs 30
```

The transformer model learns 32-dimensional player embeddings that capture:
- Form momentum and patterns
- Consistency vs boom/bust tendencies
- Underlying quality beyond raw stats

These embeddings improve predictions by 5-10% and are blended with the existing ensemble.

---

## Common Parameters

Most scripts accept these parameters:

```bash
--gameweek N       # Specify gameweek (default: current)
--free-transfers N # Override free transfer count (e.g., 5 for AFCON)
--seasons          # Specify seasons for training
--dry-run          # Preview without making changes
--verbose          # Extra logging output
```

### Special Events

Configured in `config/special_events.yaml`. Update before each season.

```yaml
ft_topups:
  - name: "AFCON 2025/26"
    trigger_after_gw: 15    # Top-up after this GW deadline
    effective_from_gw: 16   # Available from this GW
    topup_to: 5
```

---

## Intelligence Gathering (Claude Code Subagents)

Pre-deadline intelligence gathering uses Claude Code's Task tool with subagents.
This keeps raw web content out of the main conversation context.

### Why Subagents?

- Raw HTML/content stays in subagent context (not main conversation)
- Only structured summaries return
- Preserves context for decision-making
- Can visit multiple sources without context bloat

### Available Prompts

Prompts are defined in `intelligence/subagent_prompts.py`:

| Type | Purpose |
|------|---------|
| `injury` | Current injury/availability news |
| `press` | Manager press conference summaries |
| `expert` | Captain picks and transfer recommendations |
| `fixture` | Fixture difficulty analysis |
| `youtube` | FPL YouTube creator content |
| `full` | Comprehensive pre-deadline sweep |

### Usage (in Claude Code conversation)

```
# Injury news
Task(subagent_type="Explore", prompt=get_prompt('injury', gameweek=18))

# Full pre-deadline intelligence sweep
Task(subagent_type="general-purpose", prompt=get_prompt('full', gameweek=18))

# Fixture analysis for planning
Task(subagent_type="Explore", prompt=get_prompt('fixture', gameweek=18, end_gameweek=23))
```

### Critical: Training Data Warning

All prompts include explicit instructions for subagents to:
- **TRUST** freshly fetched web sources
- **DISTRUST** their training knowledge (outdated for current season)
- Report exactly what sources say, not "correct" based on memory

This prevents errors like assuming a player is still at their old club after a transfer.

---

## Team Submission via Chrome Plugin

### Overview

Ron's team selections can be submitted to FPL using the **Claude Chrome Plugin**. This provides:
- Human-in-the-loop confirmation before submission
- No need for FPL API authentication tokens
- Visual verification of changes
- No risk of account issues from unofficial API access

### Credentials

Stored in `.env` (never committed to git):
```
FPL_WEB_URL=https://fantasy.premierleague.com
FPL_USER_NAME=<email>
FPL_PASSWORD=<password>
```

### Workflow

1. **Generate team selection** using Ron's pipeline:
   ```bash
   # Use --no-notify to skip Slack (we'll send after Chrome confirms)
   python scripts/pre_deadline_selection.py --no-notify
   python scripts/show_latest_team.py
   ```

2. **Open Chrome** with Claude plugin active

3. **In Claude Code conversation**, use browser automation:
   - Navigate to FPL website
   - Login using credentials from `.env`
   - View current team, points, transfers
   - Make changes as needed (transfers, captain, bench order)
   - Confirm submission

4. **Send Slack announcement** (after Chrome confirms):
   ```bash
   # After deadline passes - syncs from FPL API (authoritative)
   python scripts/send_team_announcement.py

   # Or before deadline - reads from database (may have stale data)
   python scripts/send_team_announcement.py --from-database --gameweek 20

   # Preview without sending
   python scripts/send_team_announcement.py --dry-run
   ```

### What the Plugin Can Do

| Action | Status | Notes |
|--------|--------|-------|
| Login to FPL | ✅ Tested | Uses email/password from .env |
| View Points/Team | ✅ Tested | See GW results, player scores |
| View Pick Team | ✅ Tested | See current squad, fixtures |
| Make Transfers | ✅ Ready | Click through transfer UI |
| Set Captain/VC | ✅ Ready | Click on player → set captain |
| Reorder Bench | ✅ Ready | Drag or click bench positions |
| Activate Chips | ✅ Ready | Click chip buttons |
| Confirm Deadline | ✅ Ready | Final submission confirmation |

### Example Session

```
User: "Submit Ron's team for GW19"
Claude: [Reads .env for credentials]
        [Navigates to fantasy.premierleague.com]
        [Logs in]
        [Goes to Pick Team]
        [Makes transfers per Ron's recommendation]
        [Sets captain]
        [Asks user to confirm before final submit]
```

### Safety

- Claude will **always ask for confirmation** before irreversible actions
- Transfers, chip activation, and team submission require explicit approval
- User can review all changes visually before confirming

---

## Automated Jobs (Cron)

These run automatically if cron is configured:

| Schedule | Script | Purpose |
|----------|--------|---------|
| Daily 06:00 | `collect_fpl_data.py` | Morning data sync |
| Daily 08:00 | `daily_scout.py` | Intelligence gathering |
| Hourly | `collect_price_snapshots.py` | Price monitoring |
| Pre-deadline | `pre_deadline_selection.py` | Team selection |

Configure with:
```bash
python scripts/setup_cron.py
```

---

## Troubleshooting

### Model errors (feature mismatch)
```bash
# Retrain all models
python scripts/train_prediction_models.py
python scripts/train_neural_models.py
```

### Stale team data
```bash
python scripts/track_ron_team.py --sync
```

### Database issues
```bash
python scripts/health_check.py
python scripts/db_maintenance.py
```

### Check GPU status
```bash
python scripts/train_neural_models.py --check-gpu
```

---

## File Locations

| Type | Location |
|------|----------|
| Database | `data/ron_clanker.db` |
| ML Models | `models/prediction/`, `models/neural/` |
| Logs | `logs/` |
| Backups | `backups/` |
| Config | `config/ron_config.json` |

---

## Known Issues / TODOs

See `bd list --status open` for current tasks.

---

## Recent Changes (January 2026)

- **Slack Announcement Workflow Fix** (January 2026):
  - Added `--no-notify` flag to `pre_deadline_selection.py` to skip Slack notification
  - Created `send_team_announcement.py` script for post-submission announcements
  - Workflow: Run selection with `--no-notify` → Submit via Chrome → Send announcement
  - Prevents announcements going out before team is actually confirmed on FPL website

## Recent Changes (December 2025)

- **Squad Optimizer** added for Wildcard/Free Hit chips (`services/squad_optimizer.py`):
  - **Free Hit**: Builds optimal £100m squad for single GW, ignoring current squad
  - **Wildcard**: Builds optimal squad using selling prices + bank for 4-GW horizon
  - Automatically triggered when chip strategy recommends WC/FH
  - Respects all FPL constraints (budget, positions, max 3 per team)
  - Integrated with `manager_agent_v2.py` - rebuilds squad when WC/FH activated
- **Chip strategy consolidated** into `services/chip_strategy.py`:
  - BB/TC can be used alongside transfers (not mutually exclusive)
  - WC/FH replace normal transfers
  - Evaluates DGW/BGW, bench strength, captain xP
- **Rules validation** added to `pre_deadline_selection.py`:
  - Validates squad, formation, transfers, chip availability
  - Checks special events (AFCON etc.)
- Added `config/special_events.yaml` for FT top-ups (AFCON etc.) - auto-applied
- Fixed bank parameter not being passed to transfer optimizer
- Fixed transfer dict missing `element_type` causing formation errors

### ML & Strategy Improvements (December 2025)

- **xG/xA Feature Engineering** (`ml/prediction/features.py`):
  - Added expected goals/assists features from historical data
  - New features: `avg_xg`, `avg_xa`, `avg_xgi`, `xg_overperformance`, `xa_overperformance`
  - Maps current player IDs to historical player codes for cross-season data

- **Template vs Differential Strategy** (`agents/transfer_optimizer.py`):
  - Transfer scoring now adjusts based on league position
  - **Leading (LOW risk)**: Boosts high-ownership template players (+15%)
  - **Chasing (BOLD risk)**: Boosts low-ownership differentials (+20%)
  - Strategy flows from synthesis engine → manager agent → optimizer

- **Adaptive Threshold Learning** (`learning/performance_tracker.py`):
  - Analyzes historical transfer performance (expected vs actual gains)
  - Adjusts position-specific transfer thresholds automatically
  - Added to post-GW workflow as Step 5
  - Thresholds stored in `learned_thresholds` table

- **Learning Feedback Loop** (`ml/prediction/learning_adjustment.py`):
  - Predictions are compared to actuals after each gameweek
  - Position-specific and price-bracket bias corrections are calculated
  - Corrections are **automatically applied** to all future predictions
  - Example: If we over-predict MID by 0.57 pts on average, future MID predictions are reduced by 0.57
  - Stored in `learning_metrics` table as `learning_adjustments`
  - No manual intervention needed - runs as part of post-GW workflow

- **Transformer Model with Player Embeddings** (`ml/prediction/transformer_model.py`):
  - Self-attention architecture for form sequence modeling
  - Learns 32-dim player embeddings automatically
  - 75,805 training sequences from 1,346 players across 3 seasons
  - Integrated into prediction ensemble (70% traditional, 30% neural/transformer)
  - **Weekly training recommended** post-GW (~5-10 mins on GPU)
  - Run: `python scripts/train_transformer.py --epochs 30`

- **Price Tracking Fix** (`scripts/track_ron_team.py`):
  - Now fetches actual purchase prices from transfer history API
  - Calculates selling prices using FPL's 50% profit rule
  - TransferOptimizer uses real selling prices for budget calculations

---

*Last updated: December 2025*
