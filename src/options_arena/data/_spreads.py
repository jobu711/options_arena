"""SpreadsMixin — spread recommendation persistence."""

from __future__ import annotations

import json
import logging
from datetime import date
from decimal import Decimal

from options_arena.models.enums import (
    ExerciseStyle,
    OptionType,
    PositionSide,
    SpreadType,
    VolRegime,
)
from options_arena.models.options import (
    OptionContract,
    OptionSpread,
    SpreadAnalysis,
    SpreadLeg,
)

from ._base import RepositoryBase

logger = logging.getLogger(__name__)


class SpreadsMixin(RepositoryBase):
    """Spread recommendation CRUD operations."""

    async def save_spread_recommendation(
        self,
        scan_run_id: int,
        ticker: str,
        spread: SpreadAnalysis,
        *,
        commit: bool = True,
    ) -> int:
        """Persist a SpreadAnalysis with all its legs.

        Inserts one row into ``spread_recommendations`` and one row per leg into
        ``spread_legs``.  Decimal fields are stored as TEXT strings.

        Args:
            scan_run_id: Database ID of the parent scan run.
            ticker: Underlying ticker symbol.
            spread: The spread analysis to persist.
            commit: Whether to commit immediately (default ``True``).
                Pass ``False`` when batching multiple saves for atomic persistence.

        Returns:
            The database-assigned ID of the spread recommendation.
        """
        breakevens_json = json.dumps([str(b) for b in spread.breakevens])
        conn = self._db.conn
        cursor = await conn.execute(
            "INSERT INTO spread_recommendations "
            "(scan_run_id, ticker, spread_type, net_premium, max_profit, max_loss, "
            "risk_reward_ratio, pop_estimate, strategy_rationale, iv_regime, breakevens_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                scan_run_id,
                ticker,
                spread.spread.spread_type.value,
                str(spread.net_premium),
                str(spread.max_profit),
                str(spread.max_loss),
                spread.risk_reward_ratio,
                spread.pop_estimate,
                spread.strategy_rationale,
                spread.iv_regime.value if spread.iv_regime is not None else None,
                breakevens_json,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("INSERT into spread_recommendations returned no lastrowid")
        spread_id: int = cursor.lastrowid

        # Persist each leg
        for leg_index, leg in enumerate(spread.spread.legs):
            contract = leg.contract
            greeks = contract.greeks
            await conn.execute(
                "INSERT INTO spread_legs "
                "(spread_recommendation_id, leg_index, contract_ticker, option_type, "
                "strike, expiration, side, quantity, bid, ask, mid, "
                "delta, gamma, theta, vega) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    spread_id,
                    leg_index,
                    contract.ticker,
                    contract.option_type.value,
                    str(contract.strike),
                    contract.expiration.isoformat(),
                    leg.side.value,
                    leg.quantity,
                    str(contract.bid),
                    str(contract.ask),
                    str(contract.mid),
                    greeks.delta if greeks is not None else None,
                    greeks.gamma if greeks is not None else None,
                    greeks.theta if greeks is not None else None,
                    greeks.vega if greeks is not None else None,
                ),
            )

        if commit:
            await conn.commit()
        logger.debug(
            "Saved spread recommendation id=%d (%s) for %s scan=%d",
            spread_id,
            spread.spread.spread_type.value,
            ticker,
            scan_run_id,
        )
        return spread_id

    async def get_spread_recommendations(
        self,
        scan_run_id: int,
    ) -> list[SpreadAnalysis]:
        """Retrieve all spread analyses for a scan run.

        Reconstructs full ``SpreadAnalysis`` objects from the database,
        including all legs with their ``OptionContract`` models.

        Args:
            scan_run_id: Database ID of the scan run.

        Returns:
            List of ``SpreadAnalysis`` objects. Empty list if none exist.
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM spread_recommendations WHERE scan_run_id = ? ORDER BY id ASC",
            (scan_run_id,),
        ) as cursor:
            spread_rows = await cursor.fetchall()

        results: list[SpreadAnalysis] = []
        for row in spread_rows:
            spread_id = int(row["id"])
            analysis = await self._reconstruct_spread_analysis(spread_id, row)
            if analysis is not None:
                results.append(analysis)

        logger.debug(
            "Retrieved %d spread recommendations for scan %d",
            len(results),
            scan_run_id,
        )
        return results

    async def get_spread_for_ticker(
        self,
        scan_run_id: int,
        ticker: str,
    ) -> SpreadAnalysis | None:
        """Retrieve the spread analysis for a specific ticker in a scan run.

        Args:
            scan_run_id: Database ID of the scan run.
            ticker: Underlying ticker symbol.

        Returns:
            ``SpreadAnalysis`` or ``None`` if no spread was saved for this ticker.
        """
        conn = self._db.conn
        async with conn.execute(
            "SELECT * FROM spread_recommendations WHERE scan_run_id = ? AND ticker = ? LIMIT 1",
            (scan_run_id, ticker),
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            return None

        spread_id = int(row["id"])
        return await self._reconstruct_spread_analysis(spread_id, row)

    async def _reconstruct_spread_analysis(
        self,
        spread_id: int,
        row: object,
    ) -> SpreadAnalysis | None:
        """Reconstruct a SpreadAnalysis from a spread_recommendations row + legs.

        Args:
            spread_id: The spread recommendation ID.
            row: The aiosqlite.Row for the spread recommendation.

        Returns:
            Reconstructed ``SpreadAnalysis`` or ``None`` if reconstruction fails.
        """
        conn = self._db.conn

        # Fetch legs
        async with conn.execute(
            "SELECT * FROM spread_legs WHERE spread_recommendation_id = ? ORDER BY leg_index ASC",
            (spread_id,),
        ) as cursor:
            leg_rows = await cursor.fetchall()

        if not leg_rows:
            logger.warning("Spread %d has no legs, skipping", spread_id)
            return None

        # Reconstruct legs
        legs: list[SpreadLeg] = []
        for leg_row in leg_rows:
            contract = OptionContract(
                ticker=str(leg_row["contract_ticker"]),
                option_type=OptionType(leg_row["option_type"]),
                strike=Decimal(leg_row["strike"]),
                expiration=date.fromisoformat(leg_row["expiration"]),
                bid=Decimal(leg_row["bid"]) if leg_row["bid"] is not None else Decimal("0"),
                ask=Decimal(leg_row["ask"]) if leg_row["ask"] is not None else Decimal("0"),
                last=Decimal("0"),  # not stored in spread_legs
                volume=0,  # not stored in spread_legs
                open_interest=0,  # not stored in spread_legs
                exercise_style=ExerciseStyle.AMERICAN,
                market_iv=0.0,  # not stored in spread_legs
            )
            leg = SpreadLeg(
                contract=contract,
                side=PositionSide(leg_row["side"]),
                quantity=int(leg_row["quantity"]),
            )
            legs.append(leg)

        # Reconstruct spread
        spread_type = SpreadType(row["spread_type"])  # type: ignore[index]
        ticker_str = str(row["ticker"])  # type: ignore[index]
        option_spread = OptionSpread(
            spread_type=spread_type,
            legs=legs,
            ticker=ticker_str,
        )

        # Reconstruct breakevens — not stored in DB, derive empty list
        # (breakevens are a computed property of the spread, not independently persisted)
        # For round-trip fidelity, we store a minimal placeholder.
        # The breakevens were computed at construction time and used for PoP.
        # After retrieval, the P&L fields are the authoritative data.

        iv_regime_raw: str | None = row["iv_regime"]  # type: ignore[index]
        rr_raw = row["risk_reward_ratio"]  # type: ignore[index]

        return SpreadAnalysis(
            spread=option_spread,
            net_premium=Decimal(row["net_premium"]),  # type: ignore[index]
            max_profit=Decimal(row["max_profit"]),  # type: ignore[index]
            max_loss=Decimal(row["max_loss"]),  # type: ignore[index]
            breakevens=self._deserialize_breakevens(row),
            risk_reward_ratio=float(rr_raw) if rr_raw is not None else None,
            pop_estimate=float(row["pop_estimate"]) if row["pop_estimate"] is not None else 0.5,  # type: ignore[index]
            strategy_rationale=str(row["strategy_rationale"] or ""),  # type: ignore[index]
            iv_regime=VolRegime(iv_regime_raw) if iv_regime_raw is not None else None,
        )

    @staticmethod
    def _deserialize_breakevens(row: object) -> list[Decimal]:
        """Deserialize breakevens_json column, falling back to empty list."""
        raw: str | None = row["breakevens_json"]  # type: ignore[index]
        if raw is None:
            return [Decimal("0")]  # legacy rows without breakevens_json
        try:
            values = json.loads(raw)
            return [Decimal(v) for v in values]
        except (json.JSONDecodeError, ValueError):
            return [Decimal("0")]
