"""Guard tests for Repository mixin decomposition.

Verifies the mixin MRO composition, method availability, import paths,
and class hierarchy after the Repository monolith was split into mixins.
"""

from __future__ import annotations

from options_arena.data import Database, DebateRow, Repository
from options_arena.data._analytics import AnalyticsMixin
from options_arena.data._base import RepositoryBase
from options_arena.data._debate import DebateMixin
from options_arena.data._metadata import MetadataMixin
from options_arena.data._scan import ScanMixin


class TestRepositoryDecomposition:
    """Verify Repository mixin composition is correct."""

    def test_mro_order(self) -> None:
        """Verify MRO matches expected inheritance chain."""
        mro_names = [cls.__name__ for cls in Repository.__mro__]
        assert mro_names == [
            "Repository",
            "ScanMixin",
            "DebateMixin",
            "AnalyticsMixin",
            "MetadataMixin",
            "RepositoryBase",
            "object",
        ]

    def test_all_public_methods_present(self) -> None:
        """Introspection guard — all public methods accessible on Repository."""
        expected = {
            # ScanMixin
            "save_scan_run",
            "save_ticker_scores",
            "get_latest_scan",
            "get_scan_by_id",
            "get_scores_for_scan",
            "get_recent_scans",
            "get_score_history",
            "get_trending_tickers",
            "get_last_debate_dates",
            # DebateMixin
            "save_debate",
            "save_agent_predictions",
            "get_debate_by_id",
            "get_recent_debates",
            "get_debates_for_ticker",
            "get_agent_accuracy",
            "get_agent_calibration",
            "get_latest_auto_tune_weights",
            "save_auto_tune_weights",
            # AnalyticsMixin
            "save_recommended_contracts",
            "get_contracts_for_scan",
            "get_contracts_for_ticker",
            "save_normalization_stats",
            "get_normalization_stats",
            "save_contract_outcomes",
            "get_outcomes_for_contract",
            "get_contracts_needing_outcomes",
            "has_outcome",
            "get_win_rate_by_direction",
            "get_score_calibration",
            "get_indicator_attribution",
            "get_optimal_holding_period",
            "get_delta_performance",
            "get_performance_summary",
            # MetadataMixin
            "upsert_ticker_metadata",
            "upsert_ticker_metadata_batch",
            "get_ticker_metadata",
            "get_all_ticker_metadata",
            "get_stale_tickers",
            "get_metadata_coverage",
            # RepositoryBase
            "commit",
        }
        actual = {
            name
            for name in dir(Repository)
            if not name.startswith("_") and callable(getattr(Repository, name))
        }
        missing = expected - actual
        assert not missing, f"Missing methods on Repository: {missing}"

    def test_import_paths_unchanged(self) -> None:
        """Verify both import paths resolve correctly."""
        from options_arena.data import DebateRow as D1
        from options_arena.data import Repository as R1
        from options_arena.data.repository import DebateRow as D2
        from options_arena.data.repository import Repository as R2

        assert R1 is R2
        assert D1 is D2

    def test_debate_row_is_dataclass(self) -> None:
        """DebateRow remains a dataclass importable from data package."""
        import dataclasses

        assert dataclasses.is_dataclass(DebateRow)

    def test_all_mixins_inherit_repository_base(self) -> None:
        """Every mixin inherits from RepositoryBase."""
        for mixin in (ScanMixin, DebateMixin, AnalyticsMixin, MetadataMixin):
            assert issubclass(mixin, RepositoryBase), f"{mixin.__name__} missing RepositoryBase"

    def test_database_not_needed_for_class_construction(self) -> None:
        """Repository class itself is importable without a live Database."""
        assert Repository is not None
        assert Database is not None
