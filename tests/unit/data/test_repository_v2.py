"""Tests for v2 agent persistence — DebateRow with v2 JSON fields.

Tests cover:
  - save_debate with all 4 v2 JSON fields + debate_protocol persisted correctly
  - load DebateRow with v2 JSON round-trippable via model_validate_json
  - backward compat: save_debate without v2 fields → None v2 columns, protocol='v1'
  - debate_protocol values 'v1' and 'v2' survive round-trip
  - FlowThesis / FundamentalThesis / RiskAssessment / ContrarianThesis JSON round-trip
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from options_arena.data.database import Database
from options_arena.data.repository import DebateRow, Repository
from options_arena.models import (
    CatalystImpact,
    ContrarianThesis,
    FlowThesis,
    FundamentalThesis,
    RiskAssessment,
    RiskLevel,
    SignalDirection,
)

pytestmark = pytest.mark.db

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db() -> Database:
    """Fresh in-memory database with all migrations applied."""
    database = Database(":memory:")
    await database.connect()
    yield database  # type: ignore[misc]
    await database.close()


@pytest_asyncio.fixture
async def repo(db: Database) -> Repository:
    """Repository wrapping the in-memory database."""
    return Repository(db)


# ---------------------------------------------------------------------------
# Helpers — build realistic v2 models
# ---------------------------------------------------------------------------


def _make_flow_thesis() -> FlowThesis:
    return FlowThesis(
        direction=SignalDirection.BULLISH,
        confidence=0.72,
        gex_interpretation="Positive GEX at 185 strike suggests dealer hedging supports price.",
        smart_money_signal="Large block trades skewing to calls over puts.",
        oi_analysis="Open interest concentrated near 185-190 calls.",
        volume_confirmation="Call volume 2x average with rising OI.",
        key_flow_factors=["GEX positive", "Call skew dominant"],
        model_used="llama-3.3-70b-versatile",
    )


def _make_fundamental_thesis() -> FundamentalThesis:
    return FundamentalThesis(
        direction=SignalDirection.BULLISH,
        confidence=0.65,
        catalyst_impact=CatalystImpact.MODERATE,
        earnings_assessment="Beat last quarter EPS by 8%; revenue guidance raised.",
        iv_crush_risk="Moderate — IV percentile at 52, post-earnings crush likely 15-20%.",
        short_interest_analysis="Short interest at 1.2% of float — minimal squeeze potential.",
        dividend_impact=None,
        key_fundamental_factors=["EPS beat", "Revenue guidance raise"],
        model_used="llama-3.3-70b-versatile",
    )


def _make_risk_assessment() -> RiskAssessment:
    return RiskAssessment(
        risk_level=RiskLevel.MODERATE,
        confidence=0.80,
        pop_estimate=0.55,
        max_loss_estimate="$345 per contract (entry mid)",
        charm_decay_warning="Theta decay accelerates inside 21 DTE.",
        spread_quality_assessment="Bid-ask spread 0.05 — excellent liquidity.",
        key_risks=["Earnings in 7 days", "IV crush post-earnings"],
        risk_mitigants=["Tight spread", "High OI at strike"],
        recommended_position_size="1-2% of portfolio",
        model_used="llama-3.3-70b-versatile",
    )


def _make_contrarian_thesis() -> ContrarianThesis:
    return ContrarianThesis(
        dissent_direction=SignalDirection.BEARISH,
        dissent_confidence=0.45,
        primary_challenge="Consensus bullish bias ignores macro headwinds.",
        overlooked_risks=["Fed rate decision next week", "Sector rotation underway"],
        consensus_weakness="Bull thesis relies on single-quarter earnings beat.",
        alternative_scenario="Pullback to 175 support if macro deteriorates.",
        model_used="llama-3.3-70b-versatile",
    )


# ---------------------------------------------------------------------------
# Test: save_debate with v2 fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_debate_with_v2_fields(repo: Repository) -> None:
    """save_debate persists all 4 v2 JSON columns + debate_protocol='v2'."""
    flow = _make_flow_thesis()
    fundamental = _make_fundamental_thesis()
    risk_v2 = _make_risk_assessment()
    contrarian = _make_contrarian_thesis()

    debate_id = await repo.save_debate(
        scan_run_id=None,
        ticker="AAPL",
        bull_json='{"agent_name": "bull"}',
        bear_json='{"agent_name": "bear"}',
        risk_json=None,
        verdict_json='{"direction": "bullish"}',
        total_tokens=2400,
        model_name="llama-3.3-70b-versatile",
        duration_ms=8500,
        is_fallback=False,
        flow_thesis=flow,
        fundamental_thesis=fundamental,
        risk_v2_assessment=risk_v2,
        contrarian_thesis=contrarian,
        debate_protocol="v2",
    )
    assert isinstance(debate_id, int)
    assert debate_id > 0


# ---------------------------------------------------------------------------
# Test: load DebateRow with v2 fields round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_debate_with_v2_fields(repo: Repository) -> None:
    """Loaded DebateRow has v2 JSON fields round-trippable via model_validate_json."""
    flow = _make_flow_thesis()
    fundamental = _make_fundamental_thesis()
    risk_v2 = _make_risk_assessment()
    contrarian = _make_contrarian_thesis()

    debate_id = await repo.save_debate(
        scan_run_id=None,
        ticker="AAPL",
        bull_json=None,
        bear_json=None,
        risk_json=None,
        verdict_json=None,
        total_tokens=1000,
        model_name="test-model",
        duration_ms=3000,
        is_fallback=False,
        flow_thesis=flow,
        fundamental_thesis=fundamental,
        risk_v2_assessment=risk_v2,
        contrarian_thesis=contrarian,
        debate_protocol="v2",
    )

    loaded = await repo.get_debate_by_id(debate_id)
    assert loaded is not None
    assert isinstance(loaded, DebateRow)

    # All 4 v2 JSON fields are non-None strings
    assert loaded.flow_json is not None
    assert loaded.fundamental_json is not None
    assert loaded.risk_v2_json is not None
    assert loaded.contrarian_json is not None
    assert loaded.debate_protocol == "v2"


# ---------------------------------------------------------------------------
# Test: save_debate without v2 fields — backward compat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_debate_without_v2_fields(repo: Repository) -> None:
    """v1 backward compat: save_debate without v2 params → None v2 columns, protocol='v1'."""
    debate_id = await repo.save_debate(
        scan_run_id=None,
        ticker="MSFT",
        bull_json='{"agent_name": "bull"}',
        bear_json='{"agent_name": "bear"}',
        risk_json=None,
        verdict_json=None,
        total_tokens=500,
        model_name="test",
        duration_ms=2000,
        is_fallback=False,
    )

    loaded = await repo.get_debate_by_id(debate_id)
    assert loaded is not None
    assert loaded.flow_json is None
    assert loaded.fundamental_json is None
    assert loaded.risk_v2_json is None
    assert loaded.contrarian_json is None
    assert loaded.debate_protocol == "v1"


# ---------------------------------------------------------------------------
# Test: debate_protocol persists both 'v1' and 'v2'
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_debate_protocol_persists(repo: Repository) -> None:
    """debate_protocol stores and retrieves 'v1' and 'v2' correctly."""
    id_v1 = await repo.save_debate(
        scan_run_id=None,
        ticker="SPY",
        bull_json=None,
        bear_json=None,
        risk_json=None,
        verdict_json=None,
        total_tokens=0,
        model_name="test",
        duration_ms=0,
        is_fallback=True,
        debate_protocol="v1",
    )
    id_v2 = await repo.save_debate(
        scan_run_id=None,
        ticker="QQQ",
        bull_json=None,
        bear_json=None,
        risk_json=None,
        verdict_json=None,
        total_tokens=0,
        model_name="test",
        duration_ms=0,
        is_fallback=True,
        debate_protocol="v2",
    )

    row_v1 = await repo.get_debate_by_id(id_v1)
    row_v2 = await repo.get_debate_by_id(id_v2)

    assert row_v1 is not None
    assert row_v1.debate_protocol == "v1"
    assert row_v2 is not None
    assert row_v2.debate_protocol == "v2"


# ---------------------------------------------------------------------------
# Test: v2 JSON model roundtrip (validate_json on loaded row)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_v2_json_model_roundtrip(repo: Repository) -> None:
    """FlowThesis/FundamentalThesis/RiskAssessment/ContrarianThesis survive JSON round-trip."""
    flow = _make_flow_thesis()
    fundamental = _make_fundamental_thesis()
    risk_v2 = _make_risk_assessment()
    contrarian = _make_contrarian_thesis()

    debate_id = await repo.save_debate(
        scan_run_id=None,
        ticker="NVDA",
        bull_json=None,
        bear_json=None,
        risk_json=None,
        verdict_json=None,
        total_tokens=1500,
        model_name="test-model",
        duration_ms=4000,
        is_fallback=False,
        flow_thesis=flow,
        fundamental_thesis=fundamental,
        risk_v2_assessment=risk_v2,
        contrarian_thesis=contrarian,
        debate_protocol="v2",
    )

    loaded = await repo.get_debate_by_id(debate_id)
    assert loaded is not None

    # Deserialize from stored JSON and compare to originals
    assert loaded.flow_json is not None
    loaded_flow = FlowThesis.model_validate_json(loaded.flow_json)
    assert loaded_flow == flow
    assert loaded_flow.direction == SignalDirection.BULLISH
    assert loaded_flow.confidence == pytest.approx(0.72)
    assert loaded_flow.key_flow_factors == ["GEX positive", "Call skew dominant"]

    assert loaded.fundamental_json is not None
    loaded_fundamental = FundamentalThesis.model_validate_json(loaded.fundamental_json)
    assert loaded_fundamental == fundamental
    assert loaded_fundamental.catalyst_impact == CatalystImpact.MODERATE
    assert loaded_fundamental.confidence == pytest.approx(0.65)

    assert loaded.risk_v2_json is not None
    loaded_risk = RiskAssessment.model_validate_json(loaded.risk_v2_json)
    assert loaded_risk == risk_v2
    assert loaded_risk.risk_level == RiskLevel.MODERATE
    assert loaded_risk.pop_estimate == pytest.approx(0.55)
    assert loaded_risk.key_risks == ["Earnings in 7 days", "IV crush post-earnings"]

    assert loaded.contrarian_json is not None
    loaded_contrarian = ContrarianThesis.model_validate_json(loaded.contrarian_json)
    assert loaded_contrarian == contrarian
    assert loaded_contrarian.dissent_direction == SignalDirection.BEARISH
    assert loaded_contrarian.dissent_confidence == pytest.approx(0.45)
    assert loaded_contrarian.overlooked_risks == [
        "Fed rate decision next week",
        "Sector rotation underway",
    ]


# ---------------------------------------------------------------------------
# Test: partial v2 fields (some None, some populated)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_partial_v2_fields(repo: Repository) -> None:
    """Only some v2 fields provided — others stay None."""
    flow = _make_flow_thesis()

    debate_id = await repo.save_debate(
        scan_run_id=None,
        ticker="TSLA",
        bull_json=None,
        bear_json=None,
        risk_json=None,
        verdict_json=None,
        total_tokens=500,
        model_name="test",
        duration_ms=1000,
        is_fallback=False,
        flow_thesis=flow,
        debate_protocol="v2",
    )

    loaded = await repo.get_debate_by_id(debate_id)
    assert loaded is not None
    assert loaded.flow_json is not None
    assert loaded.fundamental_json is None
    assert loaded.risk_v2_json is None
    assert loaded.contrarian_json is None
    assert loaded.debate_protocol == "v2"

    # Flow still round-trips
    loaded_flow = FlowThesis.model_validate_json(loaded.flow_json)
    assert loaded_flow == flow


# ---------------------------------------------------------------------------
# Test: v2 fields accessible via get_recent_debates and get_debates_for_ticker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_v2_fields_via_get_recent_debates(repo: Repository) -> None:
    """get_recent_debates returns v2 fields correctly."""
    flow = _make_flow_thesis()
    await repo.save_debate(
        scan_run_id=None,
        ticker="AMZN",
        bull_json=None,
        bear_json=None,
        risk_json=None,
        verdict_json=None,
        total_tokens=300,
        model_name="test",
        duration_ms=500,
        is_fallback=False,
        flow_thesis=flow,
        debate_protocol="v2",
    )

    debates = await repo.get_recent_debates(limit=5)
    assert len(debates) == 1
    row = debates[0]
    assert row.flow_json is not None
    assert row.debate_protocol == "v2"
    loaded_flow = FlowThesis.model_validate_json(row.flow_json)
    assert loaded_flow.direction == SignalDirection.BULLISH


@pytest.mark.asyncio
async def test_v2_fields_via_get_debates_for_ticker(repo: Repository) -> None:
    """get_debates_for_ticker returns v2 fields correctly."""
    contrarian = _make_contrarian_thesis()
    await repo.save_debate(
        scan_run_id=None,
        ticker="GOOGL",
        bull_json=None,
        bear_json=None,
        risk_json=None,
        verdict_json=None,
        total_tokens=200,
        model_name="test",
        duration_ms=400,
        is_fallback=False,
        contrarian_thesis=contrarian,
        debate_protocol="v2",
    )

    debates = await repo.get_debates_for_ticker("GOOGL")
    assert len(debates) == 1
    row = debates[0]
    assert row.contrarian_json is not None
    assert row.debate_protocol == "v2"
    loaded_contrarian = ContrarianThesis.model_validate_json(row.contrarian_json)
    assert loaded_contrarian.dissent_direction == SignalDirection.BEARISH
