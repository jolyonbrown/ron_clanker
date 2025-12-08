-- Model Registry Schema
-- Tracks ML model versions, metadata, and performance metrics
-- Created: 2025-12-02

-- ============================================================================
-- MODEL REGISTRY
-- ============================================================================

-- Main registry of trained models
CREATE TABLE IF NOT EXISTS model_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,              -- e.g., 'ensemble', 'price_predictor'
    model_type TEXT NOT NULL,              -- e.g., 'xp_prediction', 'price_change'
    version TEXT NOT NULL,                 -- e.g., 'historical_20251202', 'gw13_full'
    position INTEGER,                      -- 1-4 for position-specific models, NULL for general
    file_path TEXT NOT NULL,               -- relative path to model file
    feature_columns_path TEXT,             -- relative path to feature columns file

    -- Training metadata
    training_data_start TEXT,              -- earliest data point used
    training_data_end TEXT,                -- latest data point used
    training_samples INTEGER,              -- number of training samples
    training_duration_seconds REAL,        -- how long training took

    -- Model configuration (JSON)
    hyperparameters TEXT,                  -- JSON of hyperparameters used

    -- Evaluation metrics (JSON)
    metrics TEXT,                          -- JSON of evaluation metrics

    -- Status
    is_active BOOLEAN DEFAULT FALSE,       -- is this the current production model?
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deactivated_at TIMESTAMP,

    -- Ensure unique version per model/position combo
    UNIQUE(model_name, model_type, version, position)
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_model_registry_active
    ON model_registry(model_name, model_type, position, is_active);
CREATE INDEX IF NOT EXISTS idx_model_registry_version
    ON model_registry(version);

-- Track model performance over time
CREATE TABLE IF NOT EXISTS model_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id INTEGER NOT NULL,
    gameweek INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    predicted_value REAL NOT NULL,
    actual_value REAL,                     -- filled in after GW completes
    prediction_error REAL,                 -- actual - predicted
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (model_id) REFERENCES model_registry(id)
);

CREATE INDEX IF NOT EXISTS idx_model_predictions_lookup
    ON model_predictions(model_id, gameweek);

-- Aggregate performance metrics per gameweek
CREATE TABLE IF NOT EXISTS model_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id INTEGER NOT NULL,
    gameweek INTEGER NOT NULL,
    metric_name TEXT NOT NULL,             -- 'rmse', 'mae', 'r2', 'accuracy'
    metric_value REAL NOT NULL,
    sample_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (model_id) REFERENCES model_registry(id),
    UNIQUE(model_id, gameweek, metric_name)
);

CREATE INDEX IF NOT EXISTS idx_model_performance_lookup
    ON model_performance(model_id, gameweek);

-- View for getting current active models
CREATE VIEW IF NOT EXISTS v_active_models AS
SELECT
    mr.id,
    mr.model_name,
    mr.model_type,
    mr.version,
    mr.position,
    CASE mr.position
        WHEN 1 THEN 'Goalkeepers'
        WHEN 2 THEN 'Defenders'
        WHEN 3 THEN 'Midfielders'
        WHEN 4 THEN 'Forwards'
        ELSE 'General'
    END as position_name,
    mr.file_path,
    mr.training_samples,
    mr.metrics,
    mr.created_at
FROM model_registry mr
WHERE mr.is_active = TRUE;

-- View for model performance summary
CREATE VIEW IF NOT EXISTS v_model_performance_summary AS
SELECT
    mr.model_name,
    mr.version,
    mr.position,
    mp.gameweek,
    MAX(CASE WHEN mp.metric_name = 'rmse' THEN mp.metric_value END) as rmse,
    MAX(CASE WHEN mp.metric_name = 'mae' THEN mp.metric_value END) as mae,
    MAX(CASE WHEN mp.metric_name = 'r2' THEN mp.metric_value END) as r2,
    MAX(CASE WHEN mp.metric_name = 'accuracy' THEN mp.metric_value END) as accuracy,
    MAX(mp.sample_count) as sample_count
FROM model_registry mr
JOIN model_performance mp ON mr.id = mp.model_id
GROUP BY mr.model_name, mr.version, mr.position, mp.gameweek;
