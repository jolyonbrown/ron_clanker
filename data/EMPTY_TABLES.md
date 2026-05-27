# Empty tables (as of 2025-26 season end)

Audit run 2026-05-26 after the 2025-26 season. These tables existed in
`schema.sql` with zero rows at season end. Triaged by whether INSERT
writers exist in the codebase and whether any writer is actually invoked.

## Dropped

Migrated away in `migrations/0001_drop_dead_tables_2025_26.sql`:

- `youtube_intelligence`, `youtube_transcripts`, `youtube_videos`,
  `youtube_channels` — no INSERT statements anywhere; the YouTube intel
  pipeline was scaffolded but never built. `gather_news_intelligence.py`
  and `daily_scout.py` reference the tables for reads only.

## Retained (writer exists but never runs)

These have writer code but the writer is either never instantiated or
never scheduled. Leaving the tables in place so re-enabling the feature
is a one-line change instead of a schema migration.

| Table | Writer | Why empty |
|---|---|---|
| `chips_used` | `agents/learning_agent.py:254` | `LearningAgent` is never instantiated anywhere |
| `agent_performance` | `agents/learning_agent.py:306` | Same — learning agent is dead code |
| `model_predictions` | `ml/model_registry.py:393` `record_prediction()` | Method exists but no caller invokes it |
| `model_performance` | `ml/model_registry.py` `update_actuals()` | Same |
| `learned_thresholds` | (no writer found) | Read by `transfer_optimizer.py:88` with default fallback. Feature gate for learned per-position transfer thresholds. |
| `price_changes` | `scripts/monitor_prices.py:136` | Script not on any systemd timer |
| `price_predictions` | `scripts/predict_price_changes.py:118` | Script not on any systemd timer |
| `price_model_performance` | `scripts/train_price_model.py:140` | Script not on any systemd timer |

## What to do over the summer

- **Price tracking trio** (`price_changes`, `price_predictions`,
  `price_model_performance`): wire up `monitor_prices.py` + the predictor
  into the daily scout timer. Schema is ready, code is ready, just not
  scheduled.
- **Learning agent tables** (`chips_used`, `agent_performance`): decide if
  the post-GW learning loop is worth building. If not, delete
  `learning_agent.py` and these two tables in a second migration.
- **Model registry tables** (`model_predictions`, `model_performance`):
  hook `record_prediction()` into the synthesis pipeline so we can
  backtest model accuracy week over week.
- **`learned_thresholds`**: the data-flow design that would populate this
  was never implemented. Either build it (analyse past transfer outcomes
  → per-position min-gain thresholds) or remove the reader.
