"""Outcome collector service — fetches current market data and computes P&L for contracts.

The ``OutcomeCollector`` queries persisted recommended contracts, fetches current
market prices (or computes intrinsic value for expired contracts), computes stock
and contract returns, and persists the resulting ``ContractOutcome`` records.

Never raises — returns partial results and logs errors per contract.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from options_arena.data.repository import Repository
from options_arena.models.analytics import ContractOutcome, PerformanceSummary, RecommendedContract
from options_arena.models.config import AnalyticsConfig
from options_arena.models.enums import OptionType, OutcomeCollectionMethod
from options_arena.models.options import OptionContract
from options_arena.services.market_data import MarketDataService
from options_arena.services.options_data import OptionsDataService

logger = logging.getLogger(__name__)

_EASTERN = ZoneInfo("America/New_York")


def _market_today() -> date:
    """Return today's date in US Eastern time (market timezone)."""
    return datetime.now(_EASTERN).date()


class OutcomeCollector:
    """Collect and persist contract outcome data.

    Uses DI constructor — config, repository, and market_data injected by caller.
    Never raises from public methods; returns partial results with per-contract
    error logging.

    Parameters
    ----------
    config
        Analytics configuration (holding periods, batch sizing).
    repository
        Database repository for reading contracts and writing outcomes.
    market_data
        Market data service for fetching current quotes.
    options_data
        Options data service for fetching live option chains (optional).
        When provided, active contracts compute exit_contract_mid from
        the live chain. When ``None``, falls back to stock-return-only.
    """

    def __init__(
        self,
        config: AnalyticsConfig,
        repository: Repository,
        market_data: MarketDataService,
        options_data: OptionsDataService | None = None,
    ) -> None:
        self._config = config
        self._repo = repository
        self._market_data = market_data
        self._options_data = options_data

    async def collect_outcomes(
        self,
        holding_days: int | None = None,
    ) -> list[ContractOutcome]:
        """Collect outcomes for contracts from holding_days ago.

        If *holding_days* is ``None``, iterates all configured holding periods
        from ``AnalyticsConfig.holding_periods``.

        Never raises — logs errors and returns partial results.
        """
        all_outcomes: list[ContractOutcome] = []
        periods = [holding_days] if holding_days is not None else self._config.holding_periods

        for period in periods:
            try:
                outcomes = await self._collect_for_period(period)
                all_outcomes.extend(outcomes)
            except Exception:
                logger.exception("Failed to collect outcomes for period=%d", period)

        return all_outcomes

    async def _collect_for_period(
        self,
        holding_days: int,
    ) -> list[ContractOutcome]:
        """Collect outcomes for a single holding period.

        Queries contracts created *holding_days* ago that do not yet have
        outcomes for this period. Fetches current market data per contract
        and computes returns.
        """
        today = _market_today()
        from datetime import timedelta  # noqa: PLC0415

        lookback_date = today - timedelta(days=holding_days)

        contracts = await self._repo.get_contracts_needing_outcomes(holding_days, lookback_date)
        if not contracts:
            logger.debug(
                "No contracts need outcomes for period=%d date=%s",
                holding_days,
                lookback_date,
            )
            return []

        logger.info(
            "Collecting outcomes for %d contracts (period=%d, date=%s)",
            len(contracts),
            holding_days,
            lookback_date,
        )

        outcomes: list[ContractOutcome] = []
        now = datetime.now(UTC)

        # Per-period chain cache to avoid redundant fetch_chain calls for
        # contracts sharing the same (ticker, expiration).  A None sentinel
        # means the lookup already failed/timed-out — don't retry.
        chain_cache: dict[tuple[str, date], list[OptionContract] | None] = {}

        for contract in contracts:
            try:
                outcome = await self._process_contract(
                    contract, holding_days, today, now, chain_cache=chain_cache
                )
                if outcome is not None:
                    outcomes.append(outcome)
            except Exception:
                logger.warning(
                    "Skipping contract id=%s ticker=%s: unexpected error",
                    contract.id,
                    contract.ticker,
                    exc_info=True,
                )
                continue

        # Persist all collected outcomes in a single batch
        if outcomes:
            await self._repo.save_contract_outcomes(outcomes)
            logger.info("Saved %d outcomes for period=%d", len(outcomes), holding_days)

        return outcomes

    async def _process_contract(
        self,
        contract: RecommendedContract,
        holding_days: int,
        exit_date: date,
        collected_at: datetime,
        *,
        chain_cache: dict[tuple[str, date], list[OptionContract] | None] | None = None,
    ) -> ContractOutcome | None:
        """Process a single contract and return its outcome, or None on error."""
        expired = self._is_expired(contract.expiration, exit_date)

        if expired:
            return await self._process_expired_contract(
                contract, holding_days, exit_date, collected_at
            )
        return await self._process_active_contract(
            contract, holding_days, exit_date, collected_at, chain_cache=chain_cache
        )

    async def _process_expired_contract(
        self,
        contract: RecommendedContract,
        holding_days: int,
        exit_date: date,
        collected_at: datetime,
    ) -> ContractOutcome | None:
        """Handle an expired contract — use intrinsic value or mark as worthless."""
        # We need the current stock price to compute intrinsic value
        try:
            quote = await self._market_data.fetch_quote(contract.ticker)
            exit_stock_price = quote.price
        except Exception:
            logger.warning(
                "Cannot fetch quote for expired contract id=%s ticker=%s, skipping",
                contract.id,
                contract.ticker,
            )
            return None

        stock_return = self._compute_stock_return(contract.entry_stock_price, exit_stock_price)
        intrinsic = self._compute_intrinsic_value(
            contract.option_type, contract.strike, exit_stock_price
        )
        dte_at_exit = (contract.expiration - exit_date).days

        if intrinsic == Decimal("0"):
            # Expired worthless — OTM at expiry
            return ContractOutcome(
                recommended_contract_id=contract.id,  # type: ignore[arg-type]
                exit_stock_price=exit_stock_price,
                exit_contract_mid=Decimal("0"),
                exit_date=exit_date,
                stock_return_pct=stock_return,
                contract_return_pct=-100.0,
                is_winner=False,
                holding_days=holding_days,
                dte_at_exit=dte_at_exit,
                collection_method=OutcomeCollectionMethod.EXPIRED_WORTHLESS,
                collected_at=collected_at,
            )

        # Expired ITM — use intrinsic value
        entry_mid = contract.entry_mid
        contract_return = self._compute_contract_return(entry_mid, intrinsic)
        is_winner = contract_return > 0.0 if contract_return is not None else None

        return ContractOutcome(
            recommended_contract_id=contract.id,  # type: ignore[arg-type]
            exit_stock_price=exit_stock_price,
            exit_contract_mid=intrinsic,
            exit_date=exit_date,
            stock_return_pct=stock_return,
            contract_return_pct=contract_return,
            is_winner=is_winner,
            holding_days=holding_days,
            dte_at_exit=dte_at_exit,
            collection_method=OutcomeCollectionMethod.INTRINSIC,
            collected_at=collected_at,
        )

    async def _process_active_contract(
        self,
        contract: RecommendedContract,
        holding_days: int,
        exit_date: date,
        collected_at: datetime,
        *,
        chain_cache: dict[tuple[str, date], list[OptionContract] | None] | None = None,
    ) -> ContractOutcome | None:
        """Handle an active (non-expired) contract — fetch current market data."""
        try:
            quote = await self._market_data.fetch_quote(contract.ticker)
            exit_stock_price = quote.price
        except Exception:
            logger.warning(
                "Cannot fetch quote for contract id=%s ticker=%s, skipping",
                contract.id,
                contract.ticker,
            )
            return None

        stock_return = self._compute_stock_return(contract.entry_stock_price, exit_stock_price)
        dte_at_exit = (contract.expiration - exit_date).days

        # Attempt to fetch live option chain for contract-level P&L
        exit_contract_mid: Decimal | None = None
        exit_contract_bid: Decimal | None = None
        exit_contract_ask: Decimal | None = None
        contract_return: float | None = None
        is_winner: bool | None = None

        if self._options_data is not None:
            cache_key = (contract.ticker, contract.expiration)
            chain: list[OptionContract] | None = None

            # Check per-period cache first to avoid redundant fetches
            if chain_cache is not None and cache_key in chain_cache:
                chain = chain_cache[cache_key]
            else:
                try:
                    chain = await asyncio.wait_for(
                        self._options_data.fetch_chain(contract.ticker, contract.expiration),
                        timeout=10,
                    )
                except Exception:
                    logger.warning(
                        "Failed to fetch option chain for %s %s",
                        contract.ticker,
                        contract.expiration,
                    )
                    chain = None
                if chain_cache is not None:
                    chain_cache[cache_key] = chain

            if chain is not None:
                matching = next(
                    (
                        c
                        for c in chain
                        if c.strike == contract.strike and c.option_type == contract.option_type
                    ),
                    None,
                )
                if matching is not None:
                    exit_contract_bid = matching.bid
                    exit_contract_ask = matching.ask
                    exit_contract_mid = (matching.bid + matching.ask) / Decimal("2")
                    if contract.entry_mid and contract.entry_mid > 0:
                        contract_return = float(
                            (exit_contract_mid - contract.entry_mid)
                            / contract.entry_mid
                            * Decimal("100")
                        )
                        is_winner = contract_return > 0

        return ContractOutcome(
            recommended_contract_id=contract.id,  # type: ignore[arg-type]
            exit_stock_price=exit_stock_price,
            exit_contract_mid=exit_contract_mid,
            exit_contract_bid=exit_contract_bid,
            exit_contract_ask=exit_contract_ask,
            exit_date=exit_date,
            stock_return_pct=stock_return,
            contract_return_pct=contract_return,
            is_winner=is_winner,
            holding_days=holding_days,
            dte_at_exit=dte_at_exit,
            collection_method=OutcomeCollectionMethod.MARKET,
            collected_at=collected_at,
        )

    def _compute_stock_return(
        self,
        entry_price: Decimal | None,
        exit_price: Decimal,
    ) -> float | None:
        """Compute stock return percentage: ``(exit - entry) / entry * 100``.

        Returns ``None`` when *entry_price* is ``None`` (unavailable).
        Guards against division by zero (returns ``None`` if entry_price is zero).
        """
        if entry_price is None or entry_price == Decimal("0"):
            return None
        return float((exit_price - entry_price) / entry_price * Decimal("100"))

    def _compute_contract_return(
        self,
        entry_mid: Decimal,
        exit_mid: Decimal,
    ) -> float | None:
        """Compute contract return percentage from mid prices.

        Returns ``None`` if *entry_mid* is zero (invalid data).
        """
        if entry_mid == Decimal("0"):
            return None
        return float((exit_mid - entry_mid) / entry_mid * Decimal("100"))

    def _compute_intrinsic_value(
        self,
        option_type: OptionType,
        strike: Decimal,
        stock_price: Decimal,
    ) -> Decimal:
        """Compute intrinsic value for expired contracts.

        Call: ``max(0, S - K)``
        Put:  ``max(0, K - S)``
        """
        if option_type is OptionType.CALL:
            return max(Decimal("0"), stock_price - strike)
        return max(Decimal("0"), strike - stock_price)

    def _is_expired(self, expiration: date, today: date) -> bool:
        """Check if a contract has expired (expiration date is before *today*)."""
        return expiration < today

    async def get_summary(
        self,
        lookback_days: int = 30,
    ) -> PerformanceSummary:
        """Get aggregate performance summary over the lookback period.

        Delegates to ``Repository.get_performance_summary()`` — the single
        source of truth for analytics aggregation queries.
        """
        return await self._repo.get_performance_summary(lookback_days)
