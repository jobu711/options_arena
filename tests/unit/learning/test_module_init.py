"""Tests for learning module __init__.py — public API and boundary checks."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path


class TestPublicApiExports:
    """Verify learning __init__.py exports expected names."""

    def test_exports_compute_auto_tune_weights(self) -> None:
        """compute_auto_tune_weights is importable from learning."""
        from options_arena.learning import compute_auto_tune_weights

        assert callable(compute_auto_tune_weights)

    def test_exports_auto_tune_weights(self) -> None:
        """auto_tune_weights is importable from learning."""
        from options_arena.learning import auto_tune_weights

        assert callable(auto_tune_weights)

    def test_exports_agent_vote_weights(self) -> None:
        """AGENT_VOTE_WEIGHTS is importable from learning."""
        from options_arena.learning import AGENT_VOTE_WEIGHTS

        assert isinstance(AGENT_VOTE_WEIGHTS, dict)

    def test_exports_vote_weights_type(self) -> None:
        """VoteWeights type alias is importable from learning."""
        from options_arena.learning import VoteWeights

        assert VoteWeights is not None

    def test_all_list_matches_exports(self) -> None:
        """__all__ contains exactly the expected names."""
        import options_arena.learning as mod

        expected = {
            "AGENT_VOTE_WEIGHTS",
            "VoteWeights",
            "auto_tune_indicator_weights",
            "auto_tune_weights",
            "compute_auto_tune_weights",
            "compute_indicator_tune_weights",
        }
        assert set(mod.__all__) == expected


def _get_learning_dir() -> Path:
    """Resolve the learning module source directory."""
    spec = importlib.util.find_spec("options_arena.learning")
    assert spec is not None and spec.submodule_search_locations is not None
    return Path(spec.submodule_search_locations[0])


class TestModuleBoundary:
    """Verify learning/ does not import forbidden modules."""

    def test_no_service_imports(self) -> None:
        """learning/ source files do not import from services/."""
        for py_file in _get_learning_dir().glob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert "options_arena.services" not in node.module, (
                        f"{py_file.name} imports from services/"
                    )

    def test_no_cli_imports(self) -> None:
        """learning/ source files do not import from cli/."""
        for py_file in _get_learning_dir().glob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert "options_arena.cli" not in node.module, (
                        f"{py_file.name} imports from cli/"
                    )
