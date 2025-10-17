-- Price Change Tracking for ML Prediction
-- Optimized for Raspberry Pi 3 (low memory, efficient queries)

-- Historical price changes (actual changes that occurred)
CREATE TABLE IF NOT EXISTS price_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    old_price INTEGER NOT NULL,  -- Price in 0.1m units (e.g., 55 = £5.5m)
    new_price INTEGER NOT NULL,
    change_amount INTEGER NOT NULL,  -- Positive for rise, negative for fall
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    gameweek INTEGER
);

CREATE INDEX IF NOT EXISTS idx_price_changes_player ON price_changes(player_id);
CREATE INDEX IF NOT EXISTS idx_price_changes_detected ON price_changes(detected_at);

-- Daily snapshots of player transfer data (for feature extraction)
CREATE TABLE IF NOT EXISTS player_transfer_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    snapshot_date DATE NOT NULL,

    -- Transfer metrics
    transfers_in INTEGER DEFAULT 0,
    transfers_out INTEGER DEFAULT 0,
    net_transfers INTEGER DEFAULT 0,
    transfers_in_event INTEGER DEFAULT 0,  -- Since last GW deadline
    transfers_out_event INTEGER DEFAULT 0,

    -- Ownership metrics
    selected_by_percent REAL DEFAULT 0.0,

    -- Performance metrics
    form REAL DEFAULT 0.0,
    points_per_game REAL DEFAULT 0.0,
    total_points INTEGER DEFAULT 0,

    -- Price metrics
    now_cost INTEGER NOT NULL,
    cost_change_event INTEGER DEFAULT 0,
    cost_change_start INTEGER DEFAULT 0,

    -- Metadata
    gameweek INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(player_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_player_date ON player_transfer_snapshots(player_id, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_snapshots_date ON player_transfer_snapshots(snapshot_date);

-- Price predictions (model outputs)
CREATE TABLE IF NOT EXISTS price_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    predicted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    prediction_for_date DATE NOT NULL,  -- When we expect the change

    -- Prediction
    predicted_change INTEGER NOT NULL,  -- -1 (fall), 0 (hold), +1 (rise)
    confidence REAL NOT NULL,  -- 0.0 to 1.0

    -- Model metadata
    model_version TEXT,
    features TEXT,  -- JSON of features used

    -- Outcome tracking (filled in after event)
    actual_change INTEGER,  -- -1, 0, +1 (NULL if not happened yet)
    prediction_correct BOOLEAN
);

CREATE INDEX IF NOT EXISTS idx_predictions_player ON price_predictions(player_id);
CREATE INDEX IF NOT EXISTS idx_predictions_date ON price_predictions(prediction_for_date);
CREATE INDEX IF NOT EXISTS idx_predictions_correct ON price_predictions(prediction_correct);

-- Model performance tracking (for learning)
CREATE TABLE IF NOT EXISTS price_model_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_version TEXT NOT NULL,
    evaluation_date DATE NOT NULL,

    -- Performance metrics
    accuracy REAL,  -- Overall accuracy
    precision_rise REAL,  -- Precision for predicting rises
    recall_rise REAL,  -- Recall for predicting rises
    precision_fall REAL,
    recall_fall REAL,
    f1_score REAL,

    -- Data size
    training_samples INTEGER,
    test_samples INTEGER,

    -- Metadata
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_model_perf_version ON price_model_performance(model_version);
CREATE INDEX IF NOT EXISTS idx_model_perf_date ON price_model_performance(evaluation_date);
