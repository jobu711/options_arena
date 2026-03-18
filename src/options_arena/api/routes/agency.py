"""Agency desk endpoints — submit queries, retrieve results, list history."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from options_arena.agents import run_agency_query
from options_arena.agents.model_config import build_debate_model
from options_arena.api.deps import (
    get_fred,
    get_market_data,
    get_operation_lock,
    get_options_data,
    get_repo,
    get_settings,
)
from options_arena.api.schemas import AgencyQueryRequest
from options_arena.data import Repository
from options_arena.models import (
    AgencyQuery,
    AgencyResponse,
    AppSettings,
)
from options_arena.services.fred import FredService
from options_arena.services.market_data import MarketDataService
from options_arena.services.options_data import OptionsDataService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agency", tags=["agency"])


@router.post("/query", response_model=AgencyResponse)
async def submit_query(
    request: AgencyQueryRequest,
    repo: Repository = Depends(get_repo),  # noqa: B008
    market_data: MarketDataService = Depends(get_market_data),  # noqa: B008
    options_data: OptionsDataService = Depends(get_options_data),  # noqa: B008
    fred: FredService = Depends(get_fred),  # noqa: B008
    settings: AppSettings = Depends(get_settings),  # noqa: B008
    lock: asyncio.Lock = Depends(get_operation_lock),  # noqa: B008
) -> AgencyResponse:
    """Submit a natural language agency query."""
    try:
        await asyncio.wait_for(lock.acquire(), timeout=0.01)
    except TimeoutError:
        raise HTTPException(409, "Another operation is in progress") from None

    try:
        query_id = str(uuid.uuid4())

        # Build PydanticAI model from debate config
        try:
            model = build_debate_model(settings.debate)
        except ValueError:
            logger.warning("No LLM API key configured — desk agents will fail")
            model = None

        # Build AgencyQuery
        agency_query = AgencyQuery(
            query_id=query_id,
            query_text=request.query,
            created_at=datetime.now(UTC),
            desk_override=request.desk,
        )

        # Run the agency query
        response = await run_agency_query(
            agency_query,
            market_data=market_data,
            options_data=options_data,
            fred=fred,
            repo=repo,
            model=model,
            config=settings.agency,
        )

        # Persist
        desk_str: str | None = None
        if response.intent.desks:
            desk_str = ",".join(d.value for d in response.intent.desks)

        await repo.save_agency_query(
            query_id=response.query_id,
            query_text=response.query_text,
            desk=desk_str,
            tickers=response.intent.tickers,
            intent_json=response.intent.model_dump_json(),
            response_json=response.model_dump_json(),
            confidence=response.confidence,
        )

        return response
    finally:
        lock.release()


@router.get("/query/{query_id}", response_model=AgencyResponse)
async def get_query(
    query_id: str,
    repo: Repository = Depends(get_repo),  # noqa: B008
) -> AgencyResponse:
    """Retrieve a persisted agency query response by ID."""
    row = await repo.get_agency_query(query_id)
    if row is None:
        raise HTTPException(404, "Agency query not found")
    return AgencyResponse.model_validate_json(row.response_json)


@router.get("/queries", response_model=list[AgencyResponse])
async def list_queries(
    limit: int = Query(default=20, ge=1, le=100),
    repo: Repository = Depends(get_repo),  # noqa: B008
) -> list[AgencyResponse]:
    """List recent agency queries."""
    rows = await repo.list_agency_queries(limit=limit)
    return [AgencyResponse.model_validate_json(r.response_json) for r in rows]
