-- Performance indexes for backtesting analytics queries
CREATE INDEX IF NOT EXISTS idx_co_holding_days ON contract_outcomes(holding_days);
CREATE INDEX IF NOT EXISTS idx_co_collected_at ON contract_outcomes(collected_at);
CREATE INDEX IF NOT EXISTS idx_ap_agent_direction ON agent_predictions(agent_name, direction);
CREATE INDEX IF NOT EXISTS idx_rc_market_iv ON recommended_contracts(market_iv);
CREATE INDEX IF NOT EXISTS idx_rc_direction_created ON recommended_contracts(direction, created_at);
