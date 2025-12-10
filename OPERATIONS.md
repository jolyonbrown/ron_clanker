# Ron Clanker Operations Runbook

## Quick Reference

### Core Commands (Most Used)

```bash
# Daily data sync
python scripts/collect_fpl_data.py

# Pre-deadline team selection (run 6 hours before deadline)
python scripts/pre_deadline_selection.py

# Post-gameweek data collection
python scripts/collect_post_gameweek_data.py

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

**IMPORTANT - GW16 AFCON Rule:**
For GW16 (after GW15 deadline), all managers are topped up to 5 free transfers due to AFCON.
Until automated detection is implemented, manually override with `--free-transfers 5`.

### Post-Gameweek (After all matches complete)

```bash
# 1. Collect results and update database
python scripts/collect_post_gameweek_data.py

# 2. Track Ron's performance
python scripts/track_ron_team.py --sync

# 3. Update ML models with new data
python scripts/update_ml_models.py
```

---

## Script Categories

### Data Collection
| Script | Purpose | When to Use |
|--------|---------|-------------|
| `collect_fpl_data.py` | Sync players, teams, fixtures from FPL API | Daily |
| `collect_post_gameweek_data.py` | Collect GW results after matches | Post-GW |
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

| Event | Gameweek | Effect | Override |
|-------|----------|--------|----------|
| AFCON | GW16 | 5 free transfers (topped up after GW15 deadline) | `--free-transfers 5` |

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

See `bd list --status open` for current tasks. Key issues:

- **ron_clanker-ckn** [P0]: AFCON 5 FT top-up not auto-detected (use `--free-transfers 5` for GW16)
- **ron_clanker-ht0** [P1]: Chip strategy not integrated into decision flow
- **ron_clanker-53d** [P1]: FPL rules validation during selection needs implementation

---

## Recent Changes (December 2025)

- Fixed bank parameter not being passed to transfer optimizer
- Fixed transfer dict missing `element_type` causing formation errors
- Fixed `log_transfer()` parameter names (`cost` → `transfer_cost`)
- Added `--free-transfers` override flag to `pre_deadline_selection.py`

---

*Last updated: December 2025*
