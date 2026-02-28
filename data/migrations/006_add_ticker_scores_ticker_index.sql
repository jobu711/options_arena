-- 006_add_ticker_scores_ticker_index.sql — Index for score history queries
--
-- The get_score_history() and get_trending_tickers() queries filter
-- ticker_scores by ticker column.  This index ensures sub-millisecond
-- lookups even with large scan histories.

CREATE INDEX IF NOT EXISTS idx_ticker_scores_ticker ON ticker_scores(ticker);
