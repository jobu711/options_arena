-- Strategy mining tables: rules and agent memory.

CREATE TABLE IF NOT EXISTS strategy_rules (
    rule_id TEXT PRIMARY KEY,
    pattern TEXT NOT NULL,
    conditions_json TEXT NOT NULL,
    win_rate REAL NOT NULL,
    avg_return REAL NOT NULL,
    sample_size INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'candidate',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_memory (
    memory_id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    scope TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    content TEXT NOT NULL,
    sample_size INTEGER NOT NULL DEFAULT 0,
    win_rate REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_strategy_rules_status ON strategy_rules(status);
CREATE INDEX IF NOT EXISTS idx_agent_memory_agent ON agent_memory(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_memory_scope ON agent_memory(scope_type);
