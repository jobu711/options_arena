-- Backfill agent_predictions.recommended_contract_id from ai_theses + recommended_contracts.
-- Links each prediction to its contract via the debate's scan_run_id and ticker.
UPDATE agent_predictions
SET recommended_contract_id = (
    SELECT rc.id
    FROM ai_theses at_
    JOIN recommended_contracts rc
      ON rc.scan_run_id = at_.scan_run_id AND rc.ticker = at_.ticker
    WHERE at_.id = agent_predictions.debate_id
    ORDER BY rc.id DESC
    LIMIT 1
)
WHERE recommended_contract_id IS NULL;
