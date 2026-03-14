"""AnalyticsMixin — contracts, outcomes, and analytics queries."""

from __future__ import annotations

import logging
import statistics
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from sqlite3 import Row

import numpy as np

from options_arena.models import (
    ContractOutcome,
    DeltaPerformanceResult,
    DrawdownPoint,
    DTEBucketResult,
    EquityCurvePoint,
    ExerciseStyle,
    GreeksDecompositionResult,
    GreeksGroupBy,
    GreeksSource,
    HoldingPeriodComparison,
    HoldingPeriodResult,
    IndicatorAttributionResult,
    IVRankBucketResult,
    NormalizationStats,
    OptionType,
    OutcomeCollectionMethod,
    PerformanceSummary,
    PricingModel,
    RecommendedContract,
    ScoreCalibrationBucket,
    SectorPerformanceResult,
    SignalDirection,
    WinRateResult,
)

from ._base import RepositoryBase

logger = logging.getLogger(__name__)


class AnalyticsMixin(RepositoryBase):
    """Contracts, outcomes, normalization, and analytics queries."""

    # ------------------------------------------------------------------
    # Analytics: Contracts & Normalization
    # ------------------------------------------------------------------

    async def save_recommended_contracts(
        self,
        scan_id: int,
        contracts: list[RecommendedContract],
        *,
        commit: bool = True,
    ) -> None:
        """Batch-insert recommended contracts for a scan run.

        Decimal fields are stored as TEXT to preserve precision.
        Uses ``executemany()`` for efficient batch insertion.

        Args:
            scan_id: Database ID of the parent scan run.
            contracts: List of recommended contracts to persist.
            commit: Whether to commit immediately (default ``True``).
                Pass ``False`` when batching multiple saves for atomic persistence.
        """
        if not contracts:
            return
        conn = self._db.conn
        await conn.executemany(
            "INSERT INTO recommended_contracts "
            "(scan_run_id, ticker, option_type, strike, expiration, bid, ask, last, "
            "volume, open_interest, market_iv, exercise_style, "
            "delta, gamma, theta, vega, rho, vanna, charm, vomma, "
            "pricing_model, greeks_source, "
            "entry_stock_price, entry_mid, direction, composite_score, "
            "risk_free_rate, created_at) "
            "VALUES ("
            "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    scan_id,
                    c.ticker,
                    c.option_type.value,
                    str(c.strike),
                    c.expiration.isoformat(),
                    str(c.bid),
                    str(c.ask),
                    str(c.last) if c.last is not None else None,
                    c.volume,
                    c.open_interest,
                    c.market_iv,
                    c.exercise_style.value,
                    c.delta,
                    c.gamma,
                    c.theta,
                    c.vega,
                    c.rho,
                    c.vanna,
                    c.charm,
                    c.vomma,
                    c.pricing_model.value if c.pricing_model is not None else None,
                    c.greeks_source.value if c.greeks_source is not None else None,
                    str(c.entry_stock_price) if c.entry_stock_price is not None else None,
                    str(c.entry_mid),
                    c.direction.value,
                    c.composite_score,
                    c.risk_free_rate,
                    c.created_at.isoformat(),
                )
                for c in contracts
            ],
        )
        if commit:
            await conn.commit()
        logger.debug("Saved %d recommended contracts for scan %d", len(contracts), scan_id)

    async def get_contracts_for_scan(self, scan_id: int) -> list[RecommendedContract]:
        """Get all recommended contracts for a scan run.

        Args:
            scan_id: Database ID of the scan run.

        Returns:
            List of ``RecommendedContract`` models (empty if none found).
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM recommended_contracts WHERE scan_run_id = ? ORDER BY id ASC",
            (scan_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        contracts = [self._row_to_recommended_contract(row) for row in rows]
        logger.debug("Retrieved %d contracts for scan %d", len(contracts), scan_id)
        return contracts

    async def get_contracts_for_ticker(
        self, ticker: str, limit: int = 50
    ) -> list[RecommendedContract]:
        """Get recent recommended contracts for a ticker.

        Returns most recent contracts first, limited to *limit* entries.

        Args:
            ticker: Ticker symbol (case-sensitive as stored).
            limit: Maximum number of contracts to return.

        Returns:
            List of ``RecommendedContract`` models (empty if none found).
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM recommended_contracts WHERE ticker = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (ticker, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        contracts = [self._row_to_recommended_contract(row) for row in rows]
        logger.debug("Retrieved %d contracts for ticker=%s", len(contracts), ticker)
        return contracts

    async def save_normalization_stats(
        self,
        scan_id: int,
        stats: list[NormalizationStats],
        *,
        commit: bool = True,
    ) -> None:
        """Batch-insert normalization stats for a scan run.

        Uses ``executemany()`` for efficient batch insertion.

        Args:
            scan_id: Database ID of the parent scan run.
            stats: List of normalization stats to persist.
            commit: Whether to commit immediately (default ``True``).
                Pass ``False`` when batching multiple saves for atomic persistence.
        """
        if not stats:
            return
        conn = self._db.conn
        await conn.executemany(
            "INSERT INTO normalization_metadata "
            "(scan_run_id, indicator_name, ticker_count, "
            "min_value, max_value, median_value, mean_value, std_dev, "
            "p25, p75, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    scan_id,
                    s.indicator_name,
                    s.ticker_count,
                    s.min_value,
                    s.max_value,
                    s.median_value,
                    s.mean_value,
                    s.std_dev,
                    s.p25,
                    s.p75,
                    s.created_at.isoformat(),
                )
                for s in stats
            ],
        )
        if commit:
            await conn.commit()
        logger.debug("Saved %d normalization stats for scan %d", len(stats), scan_id)

    async def get_normalization_stats(self, scan_id: int) -> list[NormalizationStats]:
        """Get normalization stats for a scan run.

        Args:
            scan_id: Database ID of the scan run.

        Returns:
            List of ``NormalizationStats`` models (empty if none found).
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM normalization_metadata WHERE scan_run_id = ? ORDER BY id ASC",
            (scan_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        stats = [self._row_to_normalization_stats(row) for row in rows]
        logger.debug("Retrieved %d normalization stats for scan %d", len(stats), scan_id)
        return stats

    @staticmethod
    def _row_to_recommended_contract(row: Row) -> RecommendedContract:
        """Reconstruct a RecommendedContract from an aiosqlite.Row.

        Decimal fields are stored as TEXT and reconstructed via ``Decimal()``.
        Enum fields are reconstructed via their constructor.
        Optional fields (Greeks, pricing_model, greeks_source, last) handle NULL.
        """
        raw_last: str | None = row["last"]
        raw_pricing_model: str | None = row["pricing_model"]
        raw_greeks_source: str | None = row["greeks_source"]
        raw_entry_stock_price: str | None = row["entry_stock_price"]
        return RecommendedContract(
            id=int(row["id"]),
            scan_run_id=int(row["scan_run_id"]),
            ticker=str(row["ticker"]),
            option_type=OptionType(row["option_type"]),
            strike=Decimal(row["strike"]),
            expiration=date.fromisoformat(row["expiration"]),
            bid=Decimal(row["bid"]),
            ask=Decimal(row["ask"]),
            last=Decimal(raw_last) if raw_last is not None else None,
            volume=int(row["volume"]),
            open_interest=int(row["open_interest"]),
            market_iv=float(row["market_iv"]),
            exercise_style=ExerciseStyle(row["exercise_style"]),
            delta=float(row["delta"]) if row["delta"] is not None else None,
            gamma=float(row["gamma"]) if row["gamma"] is not None else None,
            theta=float(row["theta"]) if row["theta"] is not None else None,
            vega=float(row["vega"]) if row["vega"] is not None else None,
            rho=float(row["rho"]) if row["rho"] is not None else None,
            vanna=float(row["vanna"]) if row["vanna"] is not None else None,
            charm=float(row["charm"]) if row["charm"] is not None else None,
            vomma=float(row["vomma"]) if row["vomma"] is not None else None,
            pricing_model=(
                PricingModel(raw_pricing_model) if raw_pricing_model is not None else None
            ),
            greeks_source=(
                GreeksSource(raw_greeks_source) if raw_greeks_source is not None else None
            ),
            entry_stock_price=(
                Decimal(raw_entry_stock_price) if raw_entry_stock_price is not None else None
            ),
            entry_mid=Decimal(row["entry_mid"]),
            direction=SignalDirection(row["direction"]),
            composite_score=float(row["composite_score"]),
            risk_free_rate=float(row["risk_free_rate"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_normalization_stats(row: Row) -> NormalizationStats:
        """Reconstruct a NormalizationStats from an aiosqlite.Row.

        Optional float stats handle NULL values from the database.
        """
        return NormalizationStats(
            id=int(row["id"]),
            scan_run_id=int(row["scan_run_id"]),
            indicator_name=str(row["indicator_name"]),
            ticker_count=int(row["ticker_count"]),
            min_value=(float(row["min_value"]) if row["min_value"] is not None else None),
            max_value=(float(row["max_value"]) if row["max_value"] is not None else None),
            median_value=(float(row["median_value"]) if row["median_value"] is not None else None),
            mean_value=(float(row["mean_value"]) if row["mean_value"] is not None else None),
            std_dev=(float(row["std_dev"]) if row["std_dev"] is not None else None),
            p25=float(row["p25"]) if row["p25"] is not None else None,
            p75=float(row["p75"]) if row["p75"] is not None else None,
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # ------------------------------------------------------------------
    # Analytics: Outcomes
    # ------------------------------------------------------------------

    async def save_contract_outcomes(self, outcomes: list[ContractOutcome]) -> None:
        """Batch-insert contract outcome records.

        Decimal fields are stored as TEXT to preserve precision.
        Uses ``executemany()`` for efficient batch insertion.

        Args:
            outcomes: List of contract outcomes to persist.
        """
        if not outcomes:
            return
        conn = self._db.conn
        await conn.executemany(
            "INSERT INTO contract_outcomes "
            "(recommended_contract_id, exit_stock_price, exit_contract_mid, "
            "exit_contract_bid, exit_contract_ask, exit_date, "
            "stock_return_pct, contract_return_pct, is_winner, "
            "holding_days, dte_at_exit, collection_method, collected_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    o.recommended_contract_id,
                    str(o.exit_stock_price) if o.exit_stock_price is not None else None,
                    str(o.exit_contract_mid) if o.exit_contract_mid is not None else None,
                    str(o.exit_contract_bid) if o.exit_contract_bid is not None else None,
                    str(o.exit_contract_ask) if o.exit_contract_ask is not None else None,
                    o.exit_date.isoformat() if o.exit_date is not None else None,
                    o.stock_return_pct,
                    o.contract_return_pct,
                    int(o.is_winner) if o.is_winner is not None else None,
                    o.holding_days,
                    o.dte_at_exit,
                    o.collection_method.value,
                    o.collected_at.isoformat(),
                )
                for o in outcomes
            ],
        )
        await conn.commit()
        logger.debug("Saved %d contract outcomes", len(outcomes))

    async def get_outcomes_for_contract(self, contract_id: int) -> list[ContractOutcome]:
        """Get all outcomes for a recommended contract, ordered by holding_days.

        Args:
            contract_id: Database ID of the recommended contract.

        Returns:
            List of ``ContractOutcome`` models (empty if none found).
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM contract_outcomes "
            "WHERE recommended_contract_id = ? ORDER BY holding_days ASC",
            (contract_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        outcomes = [self._row_to_contract_outcome(row) for row in rows]
        logger.debug("Retrieved %d outcomes for contract %d", len(outcomes), contract_id)
        return outcomes

    async def get_contracts_needing_outcomes(
        self, holding_days: int, lookback_date: date
    ) -> list[RecommendedContract]:
        """Get recommended contracts that need outcomes for a given period.

        Returns contracts created on *lookback_date* that do not yet have
        an outcome record for *holding_days*.

        Args:
            holding_days: The holding period to check.
            lookback_date: Date when the contracts were created.

        Returns:
            List of ``RecommendedContract`` models that need outcomes.
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM recommended_contracts rc "
            "WHERE date(rc.created_at) = ? "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM contract_outcomes co "
            "  WHERE co.recommended_contract_id = rc.id "
            "  AND co.holding_days = ?"
            ")",
            (lookback_date.isoformat(), holding_days),
        ) as cursor:
            rows = await cursor.fetchall()
        contracts = [self._row_to_recommended_contract(row) for row in rows]
        logger.debug(
            "Found %d contracts needing outcomes (period=%d, date=%s)",
            len(contracts),
            holding_days,
            lookback_date,
        )
        return contracts

    async def has_outcome(self, contract_id: int, exit_date: date) -> bool:
        """Check if an outcome already exists for a contract and exit date.

        Used for duplicate prevention before inserting new outcomes.

        Args:
            contract_id: Database ID of the recommended contract.
            exit_date: The exit observation date.

        Returns:
            ``True`` if an outcome exists, ``False`` otherwise.
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT EXISTS("
            "  SELECT 1 FROM contract_outcomes "
            "  WHERE recommended_contract_id = ? AND exit_date = ?"
            ") AS has_row",
            (contract_id, exit_date.isoformat()),
        ) as cursor:
            row = await cursor.fetchone()
        return bool(row["has_row"]) if row else False

    @staticmethod
    def _row_to_contract_outcome(row: Row) -> ContractOutcome:
        """Reconstruct a ContractOutcome from an aiosqlite.Row.

        Decimal fields are stored as TEXT and reconstructed via ``Decimal()``.
        Optional fields handle NULL values from the database.
        """
        raw_exit_stock: str | None = row["exit_stock_price"]
        raw_exit_mid: str | None = row["exit_contract_mid"]
        raw_exit_bid: str | None = row["exit_contract_bid"]
        raw_exit_ask: str | None = row["exit_contract_ask"]
        raw_exit_date: str | None = row["exit_date"]
        raw_is_winner = row["is_winner"]
        return ContractOutcome(
            id=int(row["id"]),
            recommended_contract_id=int(row["recommended_contract_id"]),
            exit_stock_price=Decimal(raw_exit_stock) if raw_exit_stock is not None else None,
            exit_contract_mid=Decimal(raw_exit_mid) if raw_exit_mid is not None else None,
            exit_contract_bid=Decimal(raw_exit_bid) if raw_exit_bid is not None else None,
            exit_contract_ask=Decimal(raw_exit_ask) if raw_exit_ask is not None else None,
            exit_date=date.fromisoformat(raw_exit_date) if raw_exit_date is not None else None,
            stock_return_pct=(
                float(row["stock_return_pct"]) if row["stock_return_pct"] is not None else None
            ),
            contract_return_pct=(
                float(row["contract_return_pct"])
                if row["contract_return_pct"] is not None
                else None
            ),
            is_winner=bool(raw_is_winner) if raw_is_winner is not None else None,
            holding_days=(int(row["holding_days"]) if row["holding_days"] is not None else None),
            dte_at_exit=(int(row["dte_at_exit"]) if row["dte_at_exit"] is not None else None),
            collection_method=OutcomeCollectionMethod(row["collection_method"]),
            collected_at=datetime.fromisoformat(row["collected_at"]),
        )

    # ------------------------------------------------------------------
    # Analytics: Queries
    # ------------------------------------------------------------------

    async def get_win_rate_by_direction(self) -> list[WinRateResult]:
        """Compute win rate grouped by signal direction.

        Returns one ``WinRateResult`` per direction that has at least one
        matched outcome. Empty list when no outcomes exist.
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT rc.direction, "
            "  COUNT(*) AS total_contracts, "
            "  SUM(CASE WHEN co.is_winner = 1 THEN 1 ELSE 0 END) AS winners, "
            "  SUM(CASE WHEN co.is_winner = 0 THEN 1 ELSE 0 END) AS losers, "
            "  AVG(co.is_winner) AS win_rate "
            "FROM recommended_contracts rc "
            "JOIN contract_outcomes co ON co.recommended_contract_id = rc.id "
            "WHERE co.is_winner IS NOT NULL "
            "GROUP BY rc.direction"
        ) as cursor:
            rows = await cursor.fetchall()

        results = [
            WinRateResult(
                direction=SignalDirection(row["direction"]),
                total_contracts=int(row["total_contracts"]),
                winners=int(row["winners"]),
                losers=int(row["losers"]),
                win_rate=float(row["win_rate"]),
            )
            for row in rows
        ]
        logger.debug("Win rate query returned %d directions", len(results))
        return results

    async def get_score_calibration(
        self, bucket_size: float = 10.0
    ) -> list[ScoreCalibrationBucket]:
        """Bucket contracts by composite_score and compute returns per bucket.

        Args:
            bucket_size: Width of each score bucket (default 10.0).

        Returns:
            List of ``ScoreCalibrationBucket`` ordered by score_min ascending.
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT "
            "  CAST(rc.composite_score / ? AS INTEGER) * ? AS score_min, "
            "  CAST(rc.composite_score / ? AS INTEGER) * ? + ? AS score_max, "
            "  COUNT(*) AS contract_count, "
            "  AVG(co.contract_return_pct) AS avg_return_pct, "
            "  AVG(co.is_winner) AS win_rate "
            "FROM recommended_contracts rc "
            "JOIN contract_outcomes co ON co.recommended_contract_id = rc.id "
            "WHERE co.contract_return_pct IS NOT NULL AND co.is_winner IS NOT NULL "
            "GROUP BY CAST(rc.composite_score / ? AS INTEGER) "
            "ORDER BY score_min",
            (bucket_size, bucket_size, bucket_size, bucket_size, bucket_size, bucket_size),
        ) as cursor:
            rows = await cursor.fetchall()

        results = [
            ScoreCalibrationBucket(
                score_min=float(row["score_min"]),
                score_max=float(row["score_max"]),
                contract_count=int(row["contract_count"]),
                avg_return_pct=float(row["avg_return_pct"]),
                win_rate=float(row["win_rate"]),
            )
            for row in rows
        ]
        logger.debug("Score calibration: %d buckets (size=%.1f)", len(results), bucket_size)
        return results

    async def get_indicator_attribution(
        self, indicator: str, holding_days: int = 5
    ) -> list[IndicatorAttributionResult]:
        """Correlate a normalized indicator value with contract returns.

        Fetches (indicator_value, contract_return_pct) pairs by JOINing
        ``recommended_contracts`` -> ``ticker_scores`` (via scan_run_id + ticker)
        -> ``contract_outcomes`` (filtered by holding_days). Computes Pearson
        correlation and quartile split averages in Python via numpy.

        Args:
            indicator: Indicator name (e.g. ``"rsi"``, ``"adx"``).
            holding_days: Holding period to filter outcomes.

        Returns:
            Single-element list with correlation result, or empty list if
            insufficient data (fewer than 3 data points).
        """
        # Defense-in-depth: ensure indicator name is a valid Python identifier
        # to prevent JSON path traversal via '$.' || ? construction.
        if not indicator.isidentifier() or indicator.startswith("_"):
            return []
        conn = self._db.conn
        # Join through ticker_scores signals_json to extract the indicator value.
        # json_extract on signals_json pulls the indicator's normalized value.
        async with conn.execute(
            "SELECT "
            "  json_extract(ts.signals_json, '$.' || ?) AS indicator_value, "
            "  co.contract_return_pct "
            "FROM recommended_contracts rc "
            "JOIN ticker_scores ts ON ts.scan_run_id = rc.scan_run_id AND ts.ticker = rc.ticker "
            "JOIN contract_outcomes co ON co.recommended_contract_id = rc.id "
            "WHERE co.holding_days = ? "
            "  AND co.contract_return_pct IS NOT NULL "
            "  AND json_extract(ts.signals_json, '$.' || ?) IS NOT NULL",
            (indicator, holding_days, indicator),
        ) as cursor:
            rows = list(await cursor.fetchall())

        if len(rows) < 3:
            logger.debug(
                "Indicator attribution: insufficient data for %s (n=%d)",
                indicator,
                len(rows),
            )
            return []

        values = np.array([float(row["indicator_value"]) for row in rows])
        returns = np.array([float(row["contract_return_pct"]) for row in rows])

        # Pearson correlation via numpy
        corr_matrix = np.corrcoef(values, returns)
        correlation = float(corr_matrix[0, 1])
        # Guard against NaN from constant arrays
        if not np.isfinite(correlation):
            correlation = 0.0

        # Quartile split: top 25% vs bottom 25%
        p75 = float(np.percentile(values, 75))
        p25 = float(np.percentile(values, 25))
        high_mask = values >= p75
        low_mask = values <= p25

        avg_when_high = float(np.mean(returns[high_mask])) if np.any(high_mask) else 0.0
        avg_when_low = float(np.mean(returns[low_mask])) if np.any(low_mask) else 0.0

        result = IndicatorAttributionResult(
            indicator_name=indicator,
            holding_days=holding_days,
            correlation=correlation,
            avg_return_when_high=avg_when_high,
            avg_return_when_low=avg_when_low,
            sample_size=len(rows),
        )
        logger.debug(
            "Indicator attribution for %s: corr=%.3f n=%d", indicator, correlation, len(rows)
        )
        return [result]

    async def get_optimal_holding_period(
        self, direction: SignalDirection | None = None
    ) -> list[HoldingPeriodResult]:
        """Get return statistics grouped by holding_days and direction.

        Optionally filter by signal direction. Median is computed in Python
        because SQLite lacks a built-in median function.

        Args:
            direction: Optional filter for a specific direction.

        Returns:
            List of ``HoldingPeriodResult`` ordered by holding_days.
        """
        conn = self._db.conn
        direction_val = direction.value if direction is not None else None
        async with conn.execute(
            "SELECT co.holding_days, rc.direction, "
            "  co.contract_return_pct, co.is_winner "
            "FROM recommended_contracts rc "
            "JOIN contract_outcomes co ON co.recommended_contract_id = rc.id "
            "WHERE co.contract_return_pct IS NOT NULL "
            "  AND co.is_winner IS NOT NULL "
            "  AND co.holding_days IS NOT NULL "
            "  AND (? IS NULL OR rc.direction = ?) "
            "ORDER BY co.holding_days, rc.direction",
            (direction_val, direction_val),
        ) as cursor:
            rows = await cursor.fetchall()

        # Group in Python to compute median
        groups: dict[tuple[int, str], list[tuple[float, bool]]] = {}
        for row in rows:
            key = (int(row["holding_days"]), str(row["direction"]))
            if key not in groups:
                groups[key] = []
            groups[key].append((float(row["contract_return_pct"]), bool(row["is_winner"])))

        results: list[HoldingPeriodResult] = []
        for (hd, dir_str), entries in sorted(groups.items()):
            returns_list = [e[0] for e in entries]
            winners = sum(1 for e in entries if e[1])
            total = len(entries)
            results.append(
                HoldingPeriodResult(
                    holding_days=hd,
                    direction=SignalDirection(dir_str),
                    avg_return_pct=sum(returns_list) / total,
                    median_return_pct=statistics.median(returns_list),
                    win_rate=winners / total,
                    sample_size=total,
                )
            )

        logger.debug("Holding period query returned %d groups", len(results))
        return results

    async def get_delta_performance(
        self, bucket_size: float = 0.1, holding_days: int = 5
    ) -> list[DeltaPerformanceResult]:
        """Bucket contracts by delta and compute return statistics.

        Args:
            bucket_size: Width of each delta bucket (default 0.1).
            holding_days: Filter outcomes to a specific holding period.

        Returns:
            List of ``DeltaPerformanceResult`` ordered by delta_min ascending.
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT "
            "  CAST(rc.delta / ? AS INTEGER) * ? AS delta_min, "
            "  CAST(rc.delta / ? AS INTEGER) * ? + ? AS delta_max, "
            "  AVG(co.contract_return_pct) AS avg_return_pct, "
            "  AVG(co.is_winner) AS win_rate, "
            "  COUNT(*) AS sample_size "
            "FROM recommended_contracts rc "
            "JOIN contract_outcomes co ON co.recommended_contract_id = rc.id "
            "WHERE rc.delta IS NOT NULL "
            "  AND co.holding_days = ? "
            "  AND co.contract_return_pct IS NOT NULL "
            "  AND co.is_winner IS NOT NULL "
            "GROUP BY CAST(rc.delta / ? AS INTEGER) "
            "ORDER BY delta_min",
            (
                bucket_size,
                bucket_size,
                bucket_size,
                bucket_size,
                bucket_size,
                holding_days,
                bucket_size,
            ),
        ) as cursor:
            rows = await cursor.fetchall()

        results = [
            DeltaPerformanceResult(
                delta_min=float(row["delta_min"]),
                delta_max=float(row["delta_max"]),
                holding_days=holding_days,
                avg_return_pct=float(row["avg_return_pct"]),
                win_rate=float(row["win_rate"]),
                sample_size=int(row["sample_size"]),
            )
            for row in rows
        ]
        logger.debug(
            "Delta performance returned %d buckets (size=%.2f, hd=%d)",
            len(results),
            bucket_size,
            holding_days,
        )
        return results

    async def get_performance_summary(self, lookback_days: int = 30) -> PerformanceSummary:
        """Compute aggregate performance summary over a lookback window.

        Uses multiple queries: total contracts, outcomes with aggregates,
        best direction by win rate, best holding period by average return.

        Args:
            lookback_days: Number of calendar days to look back.

        Returns:
            ``PerformanceSummary`` with optional fields ``None`` when no data.
        """
        conn = self._db.conn
        cutoff = (datetime.now(UTC) - timedelta(days=lookback_days)).date()

        # Total contracts in window
        async with conn.execute(
            "SELECT COUNT(*) AS cnt FROM recommended_contracts WHERE date(created_at) >= ?",
            (cutoff.isoformat(),),
        ) as cursor:
            row = await cursor.fetchone()
        total_contracts = int(row["cnt"]) if row else 0

        # Outcomes joined with contracts in window
        async with conn.execute(
            "SELECT co.stock_return_pct, co.contract_return_pct, co.is_winner, "
            "  co.holding_days, rc.direction "
            "FROM contract_outcomes co "
            "JOIN recommended_contracts rc ON co.recommended_contract_id = rc.id "
            "WHERE date(rc.created_at) >= ? "
            "  AND co.is_winner IS NOT NULL",
            (cutoff.isoformat(),),
        ) as cursor:
            outcome_rows = list(await cursor.fetchall())

        total_with_outcomes = len(outcome_rows)

        if total_with_outcomes == 0:
            return PerformanceSummary(
                lookback_days=lookback_days,
                total_contracts=total_contracts,
                total_with_outcomes=0,
            )

        # Compute aggregates
        winners = 0
        stock_returns: list[float] = []
        contract_returns: list[float] = []
        direction_wins: dict[str, tuple[int, int]] = {}
        holding_returns: dict[int, list[float]] = {}

        for orow in outcome_rows:
            if bool(orow["is_winner"]):
                winners += 1
            if orow["stock_return_pct"] is not None:
                stock_returns.append(float(orow["stock_return_pct"]))
            if orow["contract_return_pct"] is not None:
                contract_returns.append(float(orow["contract_return_pct"]))

            d = str(orow["direction"])
            if d not in direction_wins:
                direction_wins[d] = (0, 0)
            d_w, d_t = direction_wins[d]
            d_t += 1
            if bool(orow["is_winner"]):
                d_w += 1
            direction_wins[d] = (d_w, d_t)

            if orow["holding_days"] is not None and orow["contract_return_pct"] is not None:
                hd = int(orow["holding_days"])
                if hd not in holding_returns:
                    holding_returns[hd] = []
                holding_returns[hd].append(float(orow["contract_return_pct"]))

        overall_win_rate = winners / total_with_outcomes
        avg_stock = sum(stock_returns) / len(stock_returns) if stock_returns else None
        avg_contract = sum(contract_returns) / len(contract_returns) if contract_returns else None

        # Best direction by win rate
        best_direction: SignalDirection | None = None
        best_dir_rate = -1.0
        for dir_str, (wins, total) in direction_wins.items():
            if total > 0:
                rate = wins / total
                if rate > best_dir_rate:
                    best_dir_rate = rate
                    best_direction = SignalDirection(dir_str)

        # Best holding period by average return
        best_holding: int | None = None
        best_holding_return = float("-inf")
        for hd, rets in holding_returns.items():
            avg = sum(rets) / len(rets) if rets else 0.0
            if avg > best_holding_return:
                best_holding_return = avg
                best_holding = hd

        summary = PerformanceSummary(
            lookback_days=lookback_days,
            total_contracts=total_contracts,
            total_with_outcomes=total_with_outcomes,
            overall_win_rate=overall_win_rate,
            avg_stock_return_pct=avg_stock,
            avg_contract_return_pct=avg_contract,
            best_direction=best_direction,
            best_holding_days=best_holding,
        )
        logger.debug(
            "Performance summary: %d contracts, %d outcomes, wr=%.2f",
            total_contracts,
            total_with_outcomes,
            overall_win_rate,
        )
        return summary

    # ------------------------------------------------------------------
    # Analytics: Backtesting Queries
    # ------------------------------------------------------------------

    async def get_equity_curve(
        self,
        direction: str | None = None,
        period_days: int | None = None,
    ) -> list[EquityCurvePoint]:
        """Compute cumulative equity curve from contract outcomes.

        Joins ``recommended_contracts`` with ``contract_outcomes``, optionally
        filtered by direction and/or lookback period. Returns one
        ``EquityCurvePoint`` per calendar date, with a running cumulative return
        and trade count.

        Args:
            direction: Optional filter for signal direction (e.g. ``"bullish"``).
            period_days: Optional lookback window in calendar days.

        Returns:
            List of ``EquityCurvePoint`` ordered chronologically. Empty list if
            no outcomes exist.
        """
        conn = self._db.conn

        cutoff: str | None = None
        if period_days is not None:
            cutoff = (datetime.now(UTC) - timedelta(days=period_days)).isoformat()

        async with conn.execute(
            "SELECT date(rc.created_at) AS trade_date, co.contract_return_pct "
            "FROM recommended_contracts rc "
            "JOIN contract_outcomes co ON co.recommended_contract_id = rc.id "
            "WHERE co.contract_return_pct IS NOT NULL "
            "  AND (? IS NULL OR rc.direction = ?) "
            "  AND (? IS NULL OR rc.created_at >= ?) "
            "ORDER BY rc.created_at",
            (direction, direction, cutoff, cutoff),
        ) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            return []

        # Group by date, compute cumulative return using geometric compounding
        date_returns: dict[str, list[float]] = {}
        for row in rows:
            d = str(row["trade_date"])
            if d not in date_returns:
                date_returns[d] = []
            date_returns[d].append(float(row["contract_return_pct"]))

        results: list[EquityCurvePoint] = []
        cumulative_factor = 1.0  # multiplicative growth factor
        total_trades = 0
        for dt_str in sorted(date_returns.keys()):
            rets = date_returns[dt_str]
            # Average the day's returns, then compound
            daily_avg = sum(rets) / len(rets)
            cumulative_factor *= 1.0 + daily_avg / 100.0
            total_trades += len(rets)
            results.append(
                EquityCurvePoint(
                    date=date.fromisoformat(dt_str),
                    cumulative_return_pct=(cumulative_factor - 1.0) * 100.0,
                    trade_count=total_trades,
                )
            )

        logger.debug("Equity curve: %d points", len(results))
        return results

    async def get_drawdown_series(
        self,
        direction: str | None = None,
        period_days: int | None = None,
    ) -> list[DrawdownPoint]:
        """Compute drawdown series from the equity curve.

        Tracks peak cumulative return and computes drawdown as percentage of
        peak (standard financial definition). When the equity curve is at its
        peak, drawdown is 0.0. Below peak, drawdown is a negative percentage
        relative to the peak value.

        Args:
            direction: Optional direction filter (forwarded to equity curve).
            period_days: Optional lookback window in calendar days.

        Returns:
            List of ``DrawdownPoint`` ordered chronologically. Empty list if
            no equity curve data exists.
        """
        equity_curve = await self.get_equity_curve(direction=direction, period_days=period_days)
        if not equity_curve:
            return []

        results: list[DrawdownPoint] = []
        peak = 0.0
        for point in equity_curve:
            if point.cumulative_return_pct > peak:
                peak = point.cumulative_return_pct
            # Percentage-of-peak drawdown (standard definition)
            if peak > 0.0:
                drawdown = ((point.cumulative_return_pct - peak) / peak) * 100.0
            else:
                drawdown = point.cumulative_return_pct - peak
            results.append(
                DrawdownPoint(
                    date=point.date,
                    drawdown_pct=drawdown,
                    peak_value=peak,
                )
            )

        logger.debug("Drawdown series: %d points", len(results))
        return results

    async def get_win_rate_by_sector(
        self, holding_days: int = 20
    ) -> list[SectorPerformanceResult]:
        """Compute win rate and average return grouped by GICS sector.

        Joins ``recommended_contracts`` -> ``contract_outcomes`` -> ``ticker_metadata``
        to group by sector. Only includes contracts with a known sector.

        Args:
            holding_days: Filter to outcomes with this holding period.

        Returns:
            List of ``SectorPerformanceResult`` ordered by sector. Empty list
            if no matching outcomes exist.
        """
        conn = self._db.conn

        async with conn.execute(
            "SELECT tm.sector, "
            "  COUNT(*) AS total, "
            "  AVG(co.contract_return_pct) AS avg_return_pct, "
            "  CAST(SUM(CASE WHEN co.is_winner = 1 THEN 1 ELSE 0 END) AS REAL) "
            "    / COUNT(*) * 100.0 AS win_rate_pct "
            "FROM recommended_contracts rc "
            "JOIN contract_outcomes co ON co.recommended_contract_id = rc.id "
            "JOIN ticker_metadata tm ON tm.ticker = rc.ticker "
            "WHERE co.holding_days = ? "
            "  AND co.contract_return_pct IS NOT NULL "
            "  AND co.is_winner IS NOT NULL "
            "  AND tm.sector IS NOT NULL "
            "GROUP BY tm.sector "
            "ORDER BY tm.sector",
            (holding_days,),
        ) as cursor:
            rows = await cursor.fetchall()

        results = [
            SectorPerformanceResult(
                sector=str(row["sector"]),
                total=int(row["total"]),
                win_rate_pct=float(row["win_rate_pct"]),
                avg_return_pct=float(row["avg_return_pct"]),
            )
            for row in rows
        ]
        logger.debug("Sector performance: %d sectors (hd=%d)", len(results), holding_days)
        return results

    async def get_win_rate_by_dte_bucket(self, holding_days: int = 20) -> list[DTEBucketResult]:
        """Compute win rate and average return grouped by DTE buckets.

        DTE is computed as ``julianday(expiration) - julianday(created_at)`` in SQL.
        Buckets: 0-7, 7-14, 14-30, 30-60, 60+.

        Args:
            holding_days: Filter to outcomes with this holding period.

        Returns:
            List of ``DTEBucketResult`` ordered by DTE bucket. Empty list if
            no matching outcomes exist.
        """
        conn = self._db.conn

        async with conn.execute(
            "SELECT "
            "  CASE "
            "    WHEN julianday(rc.expiration) - julianday(rc.created_at) < 7 THEN 0 "
            "    WHEN julianday(rc.expiration) - julianday(rc.created_at) < 14 THEN 7 "
            "    WHEN julianday(rc.expiration) - julianday(rc.created_at) < 30 THEN 14 "
            "    WHEN julianday(rc.expiration) - julianday(rc.created_at) < 60 THEN 30 "
            "    ELSE 60 "
            "  END AS dte_min, "
            "  CASE "
            "    WHEN julianday(rc.expiration) - julianday(rc.created_at) < 7 THEN 7 "
            "    WHEN julianday(rc.expiration) - julianday(rc.created_at) < 14 THEN 14 "
            "    WHEN julianday(rc.expiration) - julianday(rc.created_at) < 30 THEN 30 "
            "    WHEN julianday(rc.expiration) - julianday(rc.created_at) < 60 THEN 60 "
            "    ELSE 999 "
            "  END AS dte_max, "
            "  COUNT(*) AS total, "
            "  AVG(co.contract_return_pct) AS avg_return_pct, "
            "  CAST(SUM(CASE WHEN co.is_winner = 1 THEN 1 ELSE 0 END) AS REAL) "
            "    / COUNT(*) * 100.0 AS win_rate_pct "
            "FROM recommended_contracts rc "
            "JOIN contract_outcomes co ON co.recommended_contract_id = rc.id "
            "WHERE co.holding_days = ? "
            "  AND co.contract_return_pct IS NOT NULL "
            "  AND co.is_winner IS NOT NULL "
            "GROUP BY dte_min "
            "ORDER BY dte_min",
            (holding_days,),
        ) as cursor:
            rows = await cursor.fetchall()

        results = [
            DTEBucketResult(
                dte_min=int(row["dte_min"]),
                dte_max=int(row["dte_max"]),
                total=int(row["total"]),
                win_rate_pct=float(row["win_rate_pct"]),
                avg_return_pct=float(row["avg_return_pct"]),
            )
            for row in rows
        ]
        logger.debug("DTE bucket performance: %d buckets (hd=%d)", len(results), holding_days)
        return results

    async def get_win_rate_by_iv_rank(self, holding_days: int = 20) -> list[IVRankBucketResult]:
        """Compute win rate and average return grouped by IV rank quartiles.

        Buckets ``market_iv * 100`` into: 0-25, 25-50, 50-75, 75-100.
        Only includes contracts where ``market_iv`` is not NULL.

        Args:
            holding_days: Filter to outcomes with this holding period.

        Returns:
            List of ``IVRankBucketResult`` ordered by IV bucket. Empty list if
            no matching outcomes exist.
        """
        conn = self._db.conn

        async with conn.execute(
            "SELECT "
            "  CASE "
            "    WHEN rc.market_iv * 100 < 25 THEN 0.0 "
            "    WHEN rc.market_iv * 100 < 50 THEN 25.0 "
            "    WHEN rc.market_iv * 100 < 75 THEN 50.0 "
            "    ELSE 75.0 "
            "  END AS iv_min, "
            "  CASE "
            "    WHEN rc.market_iv * 100 < 25 THEN 25.0 "
            "    WHEN rc.market_iv * 100 < 50 THEN 50.0 "
            "    WHEN rc.market_iv * 100 < 75 THEN 75.0 "
            "    ELSE 100.0 "
            "  END AS iv_max, "
            "  COUNT(*) AS total, "
            "  AVG(co.contract_return_pct) AS avg_return_pct, "
            "  CAST(SUM(CASE WHEN co.is_winner = 1 THEN 1 ELSE 0 END) AS REAL) "
            "    / COUNT(*) * 100.0 AS win_rate_pct "
            "FROM recommended_contracts rc "
            "JOIN contract_outcomes co ON co.recommended_contract_id = rc.id "
            "WHERE co.holding_days = ? "
            "  AND co.contract_return_pct IS NOT NULL "
            "  AND co.is_winner IS NOT NULL "
            "  AND rc.market_iv IS NOT NULL "
            "GROUP BY iv_min "
            "ORDER BY iv_min",
            (holding_days,),
        ) as cursor:
            rows = await cursor.fetchall()

        results = [
            IVRankBucketResult(
                iv_min=float(row["iv_min"]),
                iv_max=float(row["iv_max"]),
                total=int(row["total"]),
                win_rate_pct=float(row["win_rate_pct"]),
                avg_return_pct=float(row["avg_return_pct"]),
            )
            for row in rows
        ]
        logger.debug("IV rank bucket performance: %d buckets (hd=%d)", len(results), holding_days)
        return results

    async def get_greeks_decomposition(
        self,
        holding_days: int = 20,
        groupby: GreeksGroupBy = GreeksGroupBy.DIRECTION,
    ) -> list[GreeksDecompositionResult]:
        """Decompose P&L into delta-attributable and residual components.

        For each contract with a known ``delta`` and ``stock_return_pct``:
          - Calls: ``delta_pnl = stock_return_pct * delta``
          - Puts: ``delta_pnl = stock_return_pct * (-delta)``   (negate for puts)
          - ``residual_pnl = contract_return_pct - delta_pnl``

        Results are grouped by ``direction`` or ``sector`` (via ``groupby``).

        Args:
            holding_days: Filter to outcomes with this holding period.
            groupby: Grouping column enum (DIRECTION or SECTOR).

        Returns:
            List of ``GreeksDecompositionResult`` ordered by group key.
            Empty list if no matching data exists.
        """
        conn = self._db.conn

        if groupby == GreeksGroupBy.SECTOR:
            sql = (
                "SELECT "
                "  tm.sector AS group_key, "
                "  rc.option_type, rc.delta, "
                "  co.stock_return_pct, co.contract_return_pct "
                "FROM recommended_contracts rc "
                "JOIN contract_outcomes co ON co.recommended_contract_id = rc.id "
                "JOIN ticker_metadata tm ON tm.ticker = rc.ticker "
                "WHERE co.holding_days = ? "
                "  AND co.contract_return_pct IS NOT NULL "
                "  AND co.stock_return_pct IS NOT NULL "
                "  AND rc.delta IS NOT NULL "
                "  AND tm.sector IS NOT NULL "
                "ORDER BY group_key"
            )
        else:
            sql = (
                "SELECT "
                "  rc.direction AS group_key, "
                "  rc.option_type, rc.delta, "
                "  co.stock_return_pct, co.contract_return_pct "
                "FROM recommended_contracts rc "
                "JOIN contract_outcomes co ON co.recommended_contract_id = rc.id "
                "WHERE co.holding_days = ? "
                "  AND co.contract_return_pct IS NOT NULL "
                "  AND co.stock_return_pct IS NOT NULL "
                "  AND rc.delta IS NOT NULL "
                "ORDER BY group_key"
            )

        async with conn.execute(sql, (holding_days,)) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            return []

        # Group in Python and compute decomposition
        groups: dict[str, list[tuple[float, float, float]]] = {}
        for row in rows:
            key = str(row["group_key"])
            option_type = str(row["option_type"])
            delta = float(row["delta"])
            stock_ret = float(row["stock_return_pct"])
            contract_ret = float(row["contract_return_pct"])

            # For puts, negate delta in the decomposition
            if option_type == OptionType.PUT.value:
                delta_pnl = stock_ret * (-delta)
            else:
                delta_pnl = stock_ret * delta
            residual_pnl = contract_ret - delta_pnl

            if key not in groups:
                groups[key] = []
            groups[key].append((delta_pnl, residual_pnl, contract_ret))

        results: list[GreeksDecompositionResult] = []
        for group_key in sorted(groups.keys()):
            entries = groups[group_key]
            total_delta = sum(e[0] for e in entries)
            total_residual = sum(e[1] for e in entries)
            total_pnl = sum(e[2] for e in entries)
            count = len(entries)
            avg_delta = total_delta / count
            avg_residual = total_residual / count
            avg_pnl = total_pnl / count
            results.append(
                GreeksDecompositionResult(
                    group_key=group_key,
                    delta_pnl=avg_delta,
                    residual_pnl=avg_residual,
                    total_pnl=avg_pnl,
                    count=count,
                )
            )

        logger.debug(
            "Greeks decomposition: %d groups (hd=%d, by=%s)",
            len(results),
            holding_days,
            groupby,
        )
        return results

    async def get_holding_period_comparison(self) -> list[HoldingPeriodComparison]:
        """Compare performance across holding periods and directions.

        Groups by ``holding_days`` and ``direction``, computing average return,
        median return, win rate, max loss, and a Sharpe-like ratio
        (``mean / std``, or ``0.0`` if ``std == 0``).

        Returns:
            List of ``HoldingPeriodComparison`` ordered by holding_days then
            direction. Empty list if no outcomes exist.
        """
        conn = self._db.conn

        async with conn.execute(
            "SELECT co.holding_days, rc.direction, co.contract_return_pct "
            "FROM recommended_contracts rc "
            "JOIN contract_outcomes co ON co.recommended_contract_id = rc.id "
            "WHERE co.contract_return_pct IS NOT NULL "
            "  AND co.holding_days IS NOT NULL "
            "ORDER BY co.holding_days, rc.direction",
        ) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            return []

        # Group in Python for median and Sharpe computation
        groups: dict[tuple[int, str], list[float]] = {}
        for row in rows:
            key = (int(row["holding_days"]), str(row["direction"]))
            if key not in groups:
                groups[key] = []
            groups[key].append(float(row["contract_return_pct"]))

        results: list[HoldingPeriodComparison] = []
        for (hd, direction), returns_list in sorted(groups.items()):
            count = len(returns_list)
            avg_ret = sum(returns_list) / count
            med_ret = statistics.median(returns_list)
            winners = sum(1 for r in returns_list if r > 0)
            win_rate = winners / count
            max_loss = min(returns_list)

            # Sharpe-like ratio: mean / std (0.0 if std == 0 or single observation)
            if count >= 2:
                std = statistics.stdev(returns_list)
                sharpe = avg_ret / std if std > 0 else 0.0
            else:
                sharpe = 0.0

            results.append(
                HoldingPeriodComparison(
                    holding_days=hd,
                    direction=SignalDirection(direction),
                    avg_return=avg_ret,
                    median_return=med_ret,
                    win_rate=win_rate,
                    sharpe_like=sharpe,
                    max_loss=max_loss,
                    count=count,
                )
            )

        logger.debug("Holding period comparison: %d groups", len(results))
        return results
