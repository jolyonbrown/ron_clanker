-- Migration: drop dead tables identified during 2025-26 season-end cleanup
--
-- Run with: sqlite3 data/ron_clanker.db < data/migrations/0001_drop_dead_tables_2025_26.sql
--
-- These tables had zero rows at season end AND zero INSERT statements found
-- anywhere in the codebase (only schema definitions exist). The youtube intel
-- feature was scaffolded but never implemented — gather_news_intelligence.py
-- references them but never writes.
--
-- Other empty tables retained with documentation in EMPTY_TABLES.md:
--   model_predictions, model_performance  (writer exists in ml/model_registry.py
--     but record_prediction() is never called from any caller)
--   chips_used, agent_performance         (writers in agents/learning_agent.py
--     but LearningAgent is never instantiated)
--   learned_thresholds                    (read by transfer_optimizer with
--     graceful default fallback — feature gate)
--   price_changes, price_predictions,
--   price_model_performance               (writer scripts exist but no systemd
--     timer schedules them — pending feature)

BEGIN TRANSACTION;

DROP TABLE IF EXISTS youtube_intelligence;
DROP TABLE IF EXISTS youtube_transcripts;
DROP TABLE IF EXISTS youtube_videos;
DROP TABLE IF EXISTS youtube_channels;

COMMIT;
