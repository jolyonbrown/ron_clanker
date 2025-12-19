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

# 2. Run pre-deadline selection (generates team, transfers, captain)
python scripts/pre_deadline_selection.py

# Or specify gameweek and override free transfers (e.g., AFCON GW16 = 5 FTs)
python scripts/pre_deadline_selection.py --gameweek 16 --free-transfers 5

# 3. View the selection
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

# 3. Performance review
python scripts/post_gameweek_review.py --gw 15

# 4. Update ML models with new data
python scripts/update_ml_models.py
```

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

### ML Training
| Script | Purpose | When to Use |
|--------|---------|-------------|
| `train_prediction_models.py` | Train sklearn ensemble (RF+XGB+Ridge) | Weekly or after data changes |
| `train_neural_models.py` | Train PyTorch neural models (GPU) | Weekly |
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

# 3. Train price model
python scripts/train_price_model.py
```

### Quick Update (post-gameweek)

```bash
python scripts/update_ml_models.py
```

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

---

*Last updated: December 2025*
