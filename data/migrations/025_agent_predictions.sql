-- Agent predictions for per-agent accuracy tracking (FR-8).
CREATE TABLE IF NOT EXISTS agent_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    debate_id INTEGER NOT NULL REFERENCES ai_theses(id),
    recommended_contract_id INTEGER REFERENCES recommended_contracts(id),
    agent_name TEXT NOT NULL,
    direction TEXT,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(debate_id, agent_name)
);
CREATE INDEX IF NOT EXISTS idx_ap_debate ON agent_predictions(debate_id);
CREATE INDEX IF NOT EXISTS idx_ap_contract ON agent_predictions(recommended_contract_id);
