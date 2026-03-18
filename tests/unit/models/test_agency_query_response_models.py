"""Tests for Citation, AgencyQuery, and AgencyResponse models.

Covers construction, frozen validation, confidence/UTC validators, and JSON roundtrip
for the three new agency routing models added in Issue #581.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from options_arena.models import (
    AgencyQuery,
    AgencyResponse,
    Citation,
    DeskResponse,
    DeskType,
    QueryIntent,
    QueryType,
)


class TestCitation:
    """Citation frozen model."""

    def test_construction(self) -> None:
        c = Citation(source="fetch_quote", content="Price: $185.50", desk=DeskType.VOLATILITY)
        assert c.source == "fetch_quote"
        assert c.content == "Price: $185.50"
        assert c.desk == DeskType.VOLATILITY

    def test_frozen_rejects_mutation(self) -> None:
        c = Citation(source="fetch_quote", content="test", desk=DeskType.RISK)
        with pytest.raises(ValidationError):
            c.source = "other"  # type: ignore[misc]

    def test_json_roundtrip(self) -> None:
        c = Citation(source="compute_iv", content="IV: 35%", desk=DeskType.VOLATILITY)
        roundtripped = Citation.model_validate_json(c.model_dump_json())
        assert roundtripped == c

    def test_all_desk_types(self) -> None:
        for desk in DeskType:
            c = Citation(source="tool", content="data", desk=desk)
            assert c.desk == desk


class TestAgencyQuery:
    """AgencyQuery frozen model with UTC-validated created_at."""

    def test_construction(self) -> None:
        q = AgencyQuery(
            query_id="abc-123",
            query_text="What's AAPL IV?",
            created_at=datetime.now(UTC),
        )
        assert q.query_id == "abc-123"
        assert q.query_text == "What's AAPL IV?"
        assert q.desk_override is None

    def test_desk_override(self) -> None:
        q = AgencyQuery(
            query_id="abc-124",
            query_text="test",
            created_at=datetime.now(UTC),
            desk_override=DeskType.RISK,
        )
        assert q.desk_override == DeskType.RISK

    def test_frozen_rejects_mutation(self) -> None:
        q = AgencyQuery(
            query_id="abc-125",
            query_text="test",
            created_at=datetime.now(UTC),
        )
        with pytest.raises(ValidationError):
            q.query_text = "other"  # type: ignore[misc]

    def test_naive_datetime_rejected(self) -> None:
        with pytest.raises(ValidationError, match="UTC"):
            AgencyQuery(
                query_id="abc-126",
                query_text="test",
                created_at=datetime(2026, 1, 1, 12, 0, 0),  # naive
            )

    def test_non_utc_timezone_rejected(self) -> None:
        est = timezone(timedelta(hours=-5))
        with pytest.raises(ValidationError, match="UTC"):
            AgencyQuery(
                query_id="abc-127",
                query_text="test",
                created_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=est),
            )

    def test_utc_datetime_accepted(self) -> None:
        ts = datetime(2026, 3, 18, 16, 0, 0, tzinfo=UTC)
        q = AgencyQuery(query_id="ok", query_text="test", created_at=ts)
        assert q.created_at == ts

    def test_json_roundtrip(self) -> None:
        q = AgencyQuery(
            query_id="roundtrip-1",
            query_text="Analyze TSLA risk",
            created_at=datetime(2026, 3, 18, 16, 0, 0, tzinfo=UTC),
            desk_override=DeskType.RISK,
        )
        roundtripped = AgencyQuery.model_validate_json(q.model_dump_json())
        assert roundtripped == q

    def test_json_roundtrip_no_override(self) -> None:
        q = AgencyQuery(
            query_id="roundtrip-2",
            query_text="General query",
            created_at=datetime(2026, 3, 18, 16, 0, 0, tzinfo=UTC),
        )
        roundtripped = AgencyQuery.model_validate_json(q.model_dump_json())
        assert roundtripped == q
        assert roundtripped.desk_override is None


class TestAgencyResponse:
    """AgencyResponse frozen model with confidence + UTC validators."""

    def _make_response(self, **overrides: object) -> AgencyResponse:
        defaults: dict[str, object] = {
            "query_id": "resp-581",
            "query_text": "What's AAPL IV?",
            "intent": QueryIntent(
                desks=[DeskType.VOLATILITY],
                query_type=QueryType.ANALYSIS,
                tickers=["AAPL"],
            ),
            "desk_responses": [
                DeskResponse(
                    desk=DeskType.VOLATILITY,
                    response="IV rank is 85.",
                    tools_used=["fetch_quote"],
                    confidence=0.75,
                ),
            ],
            "synthesis": "AAPL implied volatility is elevated.",
            "citations": [],
            "confidence": 0.75,
            "created_at": datetime(2026, 3, 18, 16, 0, 0, tzinfo=UTC),
        }
        defaults.update(overrides)
        return AgencyResponse(**defaults)  # type: ignore[arg-type]

    @pytest.mark.critical
    def test_construction(self) -> None:
        resp = self._make_response()
        assert isinstance(resp, AgencyResponse)
        assert resp.query_id == "resp-581"

    def test_confidence_boundary_zero(self) -> None:
        resp = self._make_response(confidence=0.0)
        assert resp.confidence == pytest.approx(0.0)

    def test_confidence_boundary_one(self) -> None:
        resp = self._make_response(confidence=1.0)
        assert resp.confidence == pytest.approx(1.0)

    def test_confidence_nan_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            self._make_response(confidence=float("nan"))

    def test_confidence_inf_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            self._make_response(confidence=float("inf"))

    def test_confidence_neg_inf_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            self._make_response(confidence=float("-inf"))

    def test_confidence_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._make_response(confidence=-0.1)

    def test_confidence_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._make_response(confidence=1.1)

    def test_naive_datetime_rejected(self) -> None:
        with pytest.raises(ValidationError, match="UTC"):
            self._make_response(created_at=datetime(2026, 1, 1))

    def test_non_utc_datetime_rejected(self) -> None:
        est = timezone(timedelta(hours=-5))
        with pytest.raises(ValidationError, match="UTC"):
            self._make_response(created_at=datetime(2026, 1, 1, tzinfo=est))

    def test_frozen_rejects_mutation(self) -> None:
        resp = self._make_response()
        with pytest.raises(ValidationError):
            resp.confidence = 0.5  # type: ignore[misc]

    def test_json_roundtrip(self) -> None:
        resp = self._make_response()
        roundtripped = AgencyResponse.model_validate_json(resp.model_dump_json())
        assert roundtripped == resp

    def test_empty_desk_responses_valid(self) -> None:
        resp = self._make_response(desk_responses=[], confidence=0.0)
        assert resp.desk_responses == []

    def test_multiple_citations(self) -> None:
        citations = [
            Citation(source="fetch_quote", content="Price: $185", desk=DeskType.VOLATILITY),
            Citation(source="fetch_correlation", content="Corr: 0.8", desk=DeskType.RISK),
        ]
        resp = self._make_response(citations=citations)
        assert len(resp.citations) == 2
        assert resp.citations[0].desk == DeskType.VOLATILITY
        assert resp.citations[1].desk == DeskType.RISK

    def test_multiple_desk_responses(self) -> None:
        responses = [
            DeskResponse(
                desk=DeskType.VOLATILITY,
                response="IV is elevated.",
                tools_used=["iv_rank"],
                confidence=0.8,
            ),
            DeskResponse(
                desk=DeskType.RISK,
                response="Risk is moderate.",
                tools_used=["fetch_quote"],
                confidence=0.6,
            ),
        ]
        resp = self._make_response(desk_responses=responses, confidence=0.7)
        assert len(resp.desk_responses) == 2
