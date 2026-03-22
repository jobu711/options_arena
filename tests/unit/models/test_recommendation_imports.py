"""Tests for recommendation model re-exports from models package."""

import pytest


@pytest.mark.critical
class TestRecommendationImports:
    def test_domain_assessment_importable(self) -> None:
        """from options_arena.models import DomainAssessment works."""
        from options_arena.models import DomainAssessment

        assert DomainAssessment is not None

    def test_all_subclasses_importable(self) -> None:
        """All 6 assessment subclasses importable from models package."""
        from options_arena.models import (
            ContrarianAssessment,
            FlowAssessment,
            FundamentalAssessment,
            RiskDeskAssessment,
            TrendAssessment,
            VolatilityAssessment,
        )

        for cls in [
            TrendAssessment,
            VolatilityAssessment,
            FlowAssessment,
            FundamentalAssessment,
            RiskDeskAssessment,
            ContrarianAssessment,
        ]:
            assert cls is not None

    def test_any_assessment_importable(self) -> None:
        """AnyAssessment type alias importable from models package."""
        from options_arena.models import AnyAssessment

        assert AnyAssessment is not None

    def test_position_recommendation_importable(self) -> None:
        """PositionRecommendation importable from models package."""
        from options_arena.models import PositionRecommendation

        assert PositionRecommendation is not None

    def test_recommendation_result_importable(self) -> None:
        """RecommendationResult importable from models package."""
        from options_arena.models import RecommendationResult

        assert RecommendationResult is not None

    def test_models_all_contains_recommendation_names(self) -> None:
        """__all__ in models package includes all 10 recommendation names."""
        from options_arena import models

        expected = {
            "AnyAssessment",
            "ContrarianAssessment",
            "DomainAssessment",
            "FlowAssessment",
            "FundamentalAssessment",
            "PositionRecommendation",
            "RecommendationResult",
            "RiskDeskAssessment",
            "TrendAssessment",
            "VolatilityAssessment",
        }
        assert expected <= set(models.__all__)
