"""Coverage meta-test: verifies every function in MATH_FUNCTION_REGISTRY has tests
in all 3 audit layers (correctness, stability, performance).

Instead of running pytest ``--co`` via subprocess (slow, fragile), this test
inspects the test module source files directly to check for import/usage of
each registry function name.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.audit.conftest import MATH_FUNCTION_REGISTRY

# ---------------------------------------------------------------------------
# Test directories for each audit layer
# ---------------------------------------------------------------------------

_AUDIT_DIR = Path(__file__).resolve().parent
_CORRECTNESS_DIR = _AUDIT_DIR / "correctness"
_STABILITY_DIR = _AUDIT_DIR / "stability"
_PERFORMANCE_DIR = _AUDIT_DIR / "performance"

# Map layer name to directory
_LAYER_DIRS: dict[str, Path] = {
    "correctness": _CORRECTNESS_DIR,
    "stability": _STABILITY_DIR,
    "performance": _PERFORMANCE_DIR,
}


def _collect_imported_names(directory: Path) -> set[str]:
    """Collect all imported names from test modules in a directory.

    Parses Python test files and extracts all names brought into scope
    via ``import`` and ``from ... import`` statements.

    Args:
        directory: Path to the test directory to scan.

    Returns:
        A set of imported name strings.
    """
    names: set[str] = set()

    if not directory.exists():
        return names

    for py_file in sorted(directory.glob("test_*.py")):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    # Use the alias name if present, otherwise the original name
                    imported_name = alias.asname if alias.asname else alias.name
                    names.add(imported_name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported_name = alias.asname if alias.asname else alias.name
                    names.add(imported_name)

    return names


def _collect_referenced_names(directory: Path) -> set[str]:
    """Collect all Name nodes referenced in test files within a directory.

    This captures both imports and string-based references to function names
    in test bodies (e.g., parametrized test data, fixture references).

    Args:
        directory: Path to the test directory to scan.

    Returns:
        A set of referenced name strings.
    """
    names: set[str] = set()

    if not directory.exists():
        return names

    for py_file in sorted(directory.glob("test_*.py")):
        try:
            source = py_file.read_text(encoding="utf-8")
        except OSError:
            continue

        # Collect all Name references from the AST
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)

        # Also check for string references (e.g., in comments/docstrings/parametrize)
        for line in source.splitlines():
            stripped = line.strip()
            # Pick up function names mentioned as strings in parametrize or data
            for func_key in MATH_FUNCTION_REGISTRY:
                func_name = func_key.rsplit(".", 1)[-1]
                if func_name in stripped:
                    names.add(func_name)

    return names


def _get_function_short_name(registry_key: str) -> str:
    """Extract the short function name from a dotted registry key.

    Examples:
        ``"pricing.bsm.bsm_price"`` -> ``"bsm_price"``
        ``"indicators.oscillators.rsi"`` -> ``"rsi"``

    Args:
        registry_key: Dotted key from MATH_FUNCTION_REGISTRY.

    Returns:
        The short (leaf) function name.
    """
    return registry_key.rsplit(".", 1)[-1]


# Pre-compute layer coverage data
_LAYER_NAMES: dict[str, set[str]] = {}
for _layer_name, _layer_dir in _LAYER_DIRS.items():
    _imported = _collect_imported_names(_layer_dir)
    _referenced = _collect_referenced_names(_layer_dir)
    _LAYER_NAMES[_layer_name] = _imported | _referenced


class TestRegistryMatchesSource:
    """Verify MATH_FUNCTION_REGISTRY entries correspond to actual callables."""

    def test_registry_not_empty(self) -> None:
        """Registry must contain functions."""
        assert len(MATH_FUNCTION_REGISTRY) > 0, "MATH_FUNCTION_REGISTRY is empty"

    def test_registry_entries_are_callable(self) -> None:
        """Every value in the registry must be callable."""
        for key, func in MATH_FUNCTION_REGISTRY.items():
            assert callable(func), f"Registry entry {key!r} is not callable: {type(func)}"

    def test_registry_count(self) -> None:
        """Registry should contain the expected number of functions (92)."""
        assert len(MATH_FUNCTION_REGISTRY) == 92, (
            f"Expected 92 functions in registry, got {len(MATH_FUNCTION_REGISTRY)}"
        )


class TestCorrectnessLayerCoverage:
    """Every function in the registry has a correctness test."""

    @pytest.mark.parametrize(
        "registry_key",
        sorted(MATH_FUNCTION_REGISTRY.keys()),
        ids=sorted(MATH_FUNCTION_REGISTRY.keys()),
    )
    def test_function_has_correctness_test(self, registry_key: str) -> None:
        """Verify the function name appears in correctness test imports/references."""
        func_name = _get_function_short_name(registry_key)
        coverage_names = _LAYER_NAMES["correctness"]
        assert func_name in coverage_names, (
            f"Function {registry_key!r} (short: {func_name!r}) has no correctness test coverage"
        )


class TestStabilityLayerCoverage:
    """Every function in the registry has a stability test."""

    @pytest.mark.parametrize(
        "registry_key",
        sorted(MATH_FUNCTION_REGISTRY.keys()),
        ids=sorted(MATH_FUNCTION_REGISTRY.keys()),
    )
    def test_function_has_stability_test(self, registry_key: str) -> None:
        """Verify the function name appears in stability test imports/references."""
        func_name = _get_function_short_name(registry_key)
        coverage_names = _LAYER_NAMES["stability"]
        assert func_name in coverage_names, (
            f"Function {registry_key!r} (short: {func_name!r}) has no stability test coverage"
        )


class TestPerformanceLayerCoverage:
    """Every function in the registry has a performance test."""

    @pytest.mark.parametrize(
        "registry_key",
        sorted(MATH_FUNCTION_REGISTRY.keys()),
        ids=sorted(MATH_FUNCTION_REGISTRY.keys()),
    )
    def test_function_has_performance_test(self, registry_key: str) -> None:
        """Verify the function name appears in performance test imports/references."""
        func_name = _get_function_short_name(registry_key)
        coverage_names = _LAYER_NAMES["performance"]
        assert func_name in coverage_names, (
            f"Function {registry_key!r} (short: {func_name!r}) has no performance test coverage"
        )
