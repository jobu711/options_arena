"""Auto-generate docs/technical-reference.md from AST introspection.

Stdlib-only script that parses every .py file under src/options_arena/,
extracts public symbols (classes, functions, constants), builds dependency
graphs from imports, and maps source files to test files.

Usage:
    python tools/docgen.py              # regenerate docs/technical-reference.md
    python tools/docgen.py --check      # exit 1 if file is stale (CI mode)
    python tools/docgen.py -o out.md    # custom output path
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "options_arena"
TEST_ROOT = Path(__file__).resolve().parent.parent / "tests"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "docs" / "technical-reference.md"

MODULE_ORDER: list[str] = [
    "utils",
    "models",
    "indicators",
    "pricing",
    "services",
    "scoring",
    "data",
    "agents",
    "scan",
    "reporting",
    "api",
    "cli",
]

MODULE_TITLES: dict[str, str] = {
    "utils": "Exception Hierarchy",
    "models": "Pydantic Models, Enums, Config",
    "indicators": "Pure Math Functions",
    "pricing": "BSM + BAW Pricing",
    "services": "External API Access",
    "scoring": "Normalization, Composite, Contracts",
    "data": "SQLite Persistence",
    "agents": "PydanticAI Debate System",
    "scan": "4-Phase Pipeline",
    "reporting": "Export Generation",
    "api": "FastAPI REST + WebSocket",
    "cli": "Typer CLI",
}

# Files whose leading-underscore names should still be included
UNDERSCORE_INCLUDE_STEMS = {"_validators", "_common", "_parsing"}

# Maximum enum members to show inline before truncating
MAX_ENUM_VALUES_INLINE = 8


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class SymbolInfo:
    """A single extracted public symbol."""

    name: str
    kind: str  # "class", "model", "StrEnum", "func", "async func", "const"
    signature: str  # "(BaseModel)" or "(param: type) -> ReturnType"
    line: int
    description: str  # first line of docstring
    enum_values: str  # comma-separated for StrEnums, empty otherwise
    is_frozen: bool


@dataclass
class ModuleSymbols:
    """All public symbols extracted from a single .py file."""

    module_path: str  # e.g. "models/market_data.py"
    symbols: list[SymbolInfo] = field(default_factory=list)


@dataclass
class TestMapping:
    """Maps a source file to its test files and approximate test count."""

    source_file: str
    test_files: list[str]
    test_count: int


# ---------------------------------------------------------------------------
# AST Helpers
# ---------------------------------------------------------------------------


def _get_docstring_first_line(
    node: ast.AsyncFunctionDef | ast.FunctionDef | ast.ClassDef | ast.Module,
) -> str:
    """Extract the first non-empty line of a docstring, or empty string."""
    ds = ast.get_docstring(node)
    if not ds:
        return ""
    for line in ds.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _is_upper_case_name(name: str) -> bool:
    """Check if a name looks like a constant (UPPER_CASE)."""
    return bool(re.match(r"^[A-Z][A-Z0-9_]+$", name))


def _is_private(name: str) -> bool:
    """Check if a name is private (starts with _)."""
    return name.startswith("_")


def _unparse_safe(node: ast.expr | None) -> str:
    """Safely unparse an AST expression node to a string."""
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return "..."


def _is_frozen(node: ast.ClassDef) -> bool:
    """Check if a class has model_config = ConfigDict(frozen=True)."""
    for item in node.body:
        if not isinstance(item, ast.Assign):
            continue
        for target in item.targets:
            if (
                isinstance(target, ast.Name)
                and target.id == "model_config"
                and isinstance(item.value, ast.Call)
            ):
                for kw in item.value.keywords:
                    if (
                        kw.arg == "frozen"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value is True
                    ):
                        return True
    return False


def _get_base_names(node: ast.ClassDef) -> list[str]:
    """Extract base class names as strings."""
    names: list[str] = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.append(base.id)
        elif isinstance(base, (ast.Attribute, ast.Subscript)):
            names.append(ast.unparse(base))
    return names


def _extract_enum_values(node: ast.ClassDef) -> list[str]:
    """Extract StrEnum member names from class body."""
    values: list[str] = []
    for item in node.body:
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_"):
                    values.append(target.id)
    return values


def _format_enum_values(values: list[str]) -> str:
    """Format enum values, truncating if too many."""
    if not values:
        return ""
    if len(values) <= MAX_ENUM_VALUES_INLINE:
        return ", ".join(values)
    return f"{len(values)} values ({values[0]} ... {values[-1]})"


# Known Pydantic model subclasses that inherit indirectly from BaseModel
_KNOWN_MODEL_BASES: set[str] = {
    "BaseModel",
    "BaseSettings",
    "TradeThesis",
    "AgentResponse",
    "VolatilityThesis",
    "FlowThesis",
    "RiskAssessment",
    "FundamentalThesis",
    "ContrarianThesis",
    "ExtendedTradeThesis",
}


def _classify_class(node: ast.ClassDef) -> str:
    """Determine the kind of class: model, StrEnum, dataclass, Protocol, class."""
    base_names = _get_base_names(node)
    base_simple = [b.split(".")[-1] for b in base_names]

    if "StrEnum" in base_simple:
        return "StrEnum"
    if any(b in _KNOWN_MODEL_BASES for b in base_simple):
        return "model"
    if "Protocol" in base_simple:
        return "Protocol"

    # Check for @dataclass decorator
    for deco in node.decorator_list:
        if isinstance(deco, ast.Name) and deco.id == "dataclass":
            return "dataclass"
        if isinstance(deco, ast.Attribute) and deco.attr == "dataclass":
            return "dataclass"

    # Heuristic: if the class has model_config = ConfigDict(...), it's a model
    if _is_frozen(node):
        return "model"

    return "class"


def _build_func_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Build a function signature string from AST."""
    parts: list[str] = []
    args = node.args

    # Regular arguments
    num_args = len(args.args)
    num_defaults = len(args.defaults)
    first_default_idx = num_args - num_defaults

    for i, arg in enumerate(args.args):
        if arg.arg == "self" or arg.arg == "cls":
            continue
        param = arg.arg
        if arg.annotation:
            ann = _unparse_safe(arg.annotation)
            # Truncate very long annotations
            if len(ann) > 40:
                ann = ann[:37] + "..."
            param = f"{param}: {ann}"
        if i >= first_default_idx:
            default = args.defaults[i - first_default_idx]
            default_str = _unparse_safe(default)
            if len(default_str) > 20:
                default_str = "..."
            param = f"{param} = {default_str}"
        parts.append(param)

    # *args
    if args.vararg:
        va = f"*{args.vararg.arg}"
        if args.vararg.annotation:
            va += f": {_unparse_safe(args.vararg.annotation)}"
        parts.append(va)
    elif args.kwonlyargs:
        # Bare * separator when there are kwonly args but no *args
        parts.append("*")

    # keyword-only
    for i, arg in enumerate(args.kwonlyargs):
        param = arg.arg
        if arg.annotation:
            ann = _unparse_safe(arg.annotation)
            if len(ann) > 40:
                ann = ann[:37] + "..."
            param = f"{param}: {ann}"
        if i < len(args.kw_defaults) and args.kw_defaults[i] is not None:
            default_str = _unparse_safe(args.kw_defaults[i])
            if len(default_str) > 20:
                default_str = "..."
            param = f"{param} = {default_str}"
        parts.append(param)

    # **kwargs
    if args.kwarg:
        kw = f"**{args.kwarg.arg}"
        if args.kwarg.annotation:
            kw += f": {_unparse_safe(args.kwarg.annotation)}"
        parts.append(kw)

    sig = f"({', '.join(parts)})"

    # Return type
    if node.returns:
        ret = _unparse_safe(node.returns)
        if len(ret) > 50:
            ret = ret[:47] + "..."
        sig += f" -> {ret}"

    # Cap total length
    if len(sig) > 100:
        sig = sig[:97] + "..."

    return sig


def _get_annotation_str(node: ast.AnnAssign) -> str:
    """Get the annotation string from an annotated assignment."""
    if node.annotation:
        ann = _unparse_safe(node.annotation)
        if len(ann) > 50:
            ann = ann[:47] + "..."
        return ann
    return ""


# ---------------------------------------------------------------------------
# Symbol Extractor
# ---------------------------------------------------------------------------


class SymbolExtractor(ast.NodeVisitor):
    """Visit a parsed file and extract public symbols."""

    def __init__(self, file_stem: str) -> None:
        self.symbols: list[SymbolInfo] = []
        self._file_stem = file_stem
        self._include_underscore = file_stem in UNDERSCORE_INCLUDE_STEMS
        self._in_class: str | None = None

    def _should_include(self, name: str) -> bool:
        """Decide whether to include a name based on privacy rules."""
        if not _is_private(name):
            return True
        return self._include_underscore and not name.startswith("__")

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if not self._should_include(node.name):
            return

        kind = _classify_class(node)
        base_names = _get_base_names(node)
        desc = _get_docstring_first_line(node)
        frozen = _is_frozen(node)

        # Build signature
        if kind == "StrEnum":
            values = _extract_enum_values(node)
            enum_str = _format_enum_values(values)
            sig = ""
        elif kind == "model":
            # Don't put frozen=True in sig — renderer handles it via is_frozen flag
            sig = ""
            base0 = base_names[0] if base_names else ""
            show_parent = (
                base0
                and base0 not in ("BaseModel", "BaseSettings")
                and (base0 not in _KNOWN_MODEL_BASES or base0 in ("TradeThesis", "AgentResponse"))
            )
            if show_parent:
                sig = f"({base0})"
            enum_str = ""
        elif kind == "dataclass":
            sig = ""
            enum_str = ""
        else:
            sig = f"({', '.join(base_names)})" if base_names else ""
            enum_str = ""

        self.symbols.append(
            SymbolInfo(
                name=node.name,
                kind=kind,
                signature=sig,
                line=node.lineno,
                description=desc,
                enum_values=enum_str,
                is_frozen=frozen,
            )
        )

        # Extract public methods for service/data/api/scan classes
        if kind == "class":
            old_class = self._in_class
            self._in_class = node.name
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                    not item.name.startswith("_")
                    or item.name in ("__init__", "__aenter__", "__aexit__")
                ):
                    self._extract_method(item, node.name)
            self._in_class = old_class

    def _extract_method(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        class_name: str,
    ) -> None:
        """Extract a public method from a class."""
        if node.name == "__init__":
            return  # Skip __init__, class signature covers it
        desc = _get_docstring_first_line(node)
        sig = _build_func_signature(node)
        is_async = isinstance(node, ast.AsyncFunctionDef)
        kind = "async method" if is_async else "method"

        # Check for @property
        for deco in node.decorator_list:
            if isinstance(deco, ast.Name) and deco.id == "property":
                kind = "property"
                break

        self.symbols.append(
            SymbolInfo(
                name=f".{node.name}",
                kind=kind,
                signature=sig,
                line=node.lineno,
                description=desc,
                enum_values="",
                is_frozen=False,
            )
        )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self._in_class is not None:
            return  # Handled by class visitor
        if not self._should_include(node.name):
            return
        desc = _get_docstring_first_line(node)
        sig = _build_func_signature(node)
        self.symbols.append(
            SymbolInfo(
                name=node.name,
                kind="func",
                signature=sig,
                line=node.lineno,
                description=desc,
                enum_values="",
                is_frozen=False,
            )
        )

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if self._in_class is not None:
            return  # Handled by class visitor
        if not self._should_include(node.name):
            return
        desc = _get_docstring_first_line(node)
        sig = _build_func_signature(node)
        self.symbols.append(
            SymbolInfo(
                name=node.name,
                kind="async func",
                signature=sig,
                line=node.lineno,
                description=desc,
                enum_values="",
                is_frozen=False,
            )
        )

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._in_class is not None:
            return
        for target in node.targets:
            if isinstance(target, ast.Name) and _is_upper_case_name(target.id):
                if not self._should_include(target.id):
                    continue
                # Try to get a type hint from the value
                val_type = ""
                if isinstance(node.value, ast.Call):
                    val_type = _unparse_safe(node.value.func)
                elif isinstance(node.value, ast.Constant):
                    val_type = type(node.value.value).__name__
                elif isinstance(node.value, (ast.List, ast.Tuple)):
                    val_type = "list" if isinstance(node.value, ast.List) else "tuple"
                elif isinstance(node.value, ast.Dict):
                    val_type = "dict"

                self.symbols.append(
                    SymbolInfo(
                        name=target.id,
                        kind="const",
                        signature=val_type,
                        line=node.lineno,
                        description="",
                        enum_values="",
                        is_frozen=False,
                    )
                )

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if self._in_class is not None:
            return
        if isinstance(node.target, ast.Name) and _is_upper_case_name(node.target.id):
            if not self._should_include(node.target.id):
                return
            ann_str = _get_annotation_str(node)
            self.symbols.append(
                SymbolInfo(
                    name=node.target.id,
                    kind="const",
                    signature=ann_str,
                    line=node.lineno,
                    description="",
                    enum_values="",
                    is_frozen=False,
                )
            )


# ---------------------------------------------------------------------------
# Import Analyzer
# ---------------------------------------------------------------------------


class ImportAnalyzer(ast.NodeVisitor):
    """Collect imports from options_arena submodules."""

    def __init__(self) -> None:
        self.imports: set[str] = set()

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and node.module.startswith("options_arena."):
            # Extract the first submodule
            parts = node.module.split(".")
            if len(parts) >= 2:
                submodule = parts[1]
                self.imports.add(submodule)


# ---------------------------------------------------------------------------
# File Discovery
# ---------------------------------------------------------------------------


def discover_py_files(module_dir: Path) -> list[Path]:
    """Find all .py files in a module directory, sorted alphabetically.

    Skips __init__.py and __pycache__.
    Includes files in subdirectories (e.g. api/routes/).
    """
    files: list[Path] = []
    if not module_dir.exists():
        return files
    for py_file in sorted(module_dir.rglob("*.py")):
        if py_file.name == "__init__.py":
            continue
        if "__pycache__" in str(py_file):
            continue
        files.append(py_file)
    return files


def parse_file(file_path: Path) -> ast.Module | None:
    """Parse a Python file, returning None on error."""
    try:
        source = file_path.read_text(encoding="utf-8")
        return ast.parse(source, filename=str(file_path))
    except SyntaxError as e:
        print(f"WARNING: Syntax error in {file_path}: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"WARNING: Could not read {file_path}: {e}", file=sys.stderr)
        return None


def extract_symbols(file_path: Path) -> ModuleSymbols:
    """Parse a file and extract its public symbols."""
    rel = file_path.relative_to(SRC_ROOT)
    module_path = rel.as_posix()

    tree = parse_file(file_path)
    if tree is None:
        return ModuleSymbols(module_path=module_path)

    extractor = SymbolExtractor(file_path.stem)
    extractor.visit(tree)

    # Sort by line number
    extractor.symbols.sort(key=lambda s: s.line)

    return ModuleSymbols(module_path=module_path, symbols=extractor.symbols)


def analyze_imports(file_path: Path) -> set[str]:
    """Analyze imports from a single file."""
    tree = parse_file(file_path)
    if tree is None:
        return set()
    analyzer = ImportAnalyzer()
    analyzer.visit(tree)
    return analyzer.imports


# ---------------------------------------------------------------------------
# Dependency Graph
# ---------------------------------------------------------------------------


def build_dependency_graph() -> dict[str, set[str]]:
    """Build module-level dependency graph from imports."""
    graph: dict[str, set[str]] = {m: set() for m in MODULE_ORDER}

    for module_name in MODULE_ORDER:
        module_dir = SRC_ROOT / module_name
        for py_file in discover_py_files(module_dir):
            imports = analyze_imports(py_file)
            for imp in imports:
                if imp != module_name and imp in graph:
                    graph[module_name].add(imp)

    return graph


# ---------------------------------------------------------------------------
# Test Mapping
# ---------------------------------------------------------------------------


def count_test_functions(file_path: Path) -> int:
    """Count test functions in a test file, including parametrize expansion."""
    tree = parse_file(file_path)
    if tree is None:
        return 0

    count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
            "test_"
        ):
            # Check for parametrize decorator
            param_count = 1
            for deco in node.decorator_list:
                if isinstance(deco, ast.Call):
                    func = deco.func
                    deco_name = ""
                    if isinstance(func, ast.Attribute):
                        deco_name = func.attr
                    elif isinstance(func, ast.Name):
                        deco_name = func.id
                    if deco_name == "parametrize" and len(deco.args) >= 2:
                        # Count list elements in second arg
                        arg2 = deco.args[1]
                        if isinstance(arg2, (ast.List, ast.Tuple)):
                            param_count *= max(len(arg2.elts), 1)
            count += param_count

    return count


def find_test_files(source_module: str, source_stem: str) -> list[Path]:
    """Find test files matching a source file by naming convention."""
    test_files: list[Path] = []

    # Search in tests/unit/{module}/
    unit_dir = TEST_ROOT / "unit" / source_module
    if unit_dir.exists():
        # Look for test_{stem}.py
        candidate = unit_dir / f"test_{source_stem}.py"
        if candidate.exists():
            test_files.append(candidate)
        # Also check without leading underscore
        if source_stem.startswith("_"):
            candidate2 = unit_dir / f"test{source_stem}.py"
            if candidate2.exists():
                test_files.append(candidate2)

    # Search for test files in subdirectories (e.g. tests/unit/api/)
    if not test_files and source_module == "api":
        # For api/routes/X.py, look for tests/unit/api/test_X_routes.py
        candidate = unit_dir / f"test_{source_stem}_routes.py"
        if candidate.exists():
            test_files.append(candidate)
        candidate = unit_dir / f"test_{source_stem}.py"
        if candidate.exists():
            test_files.append(candidate)

    return test_files


def build_test_mapping(module_name: str, file_path: Path) -> TestMapping:
    """Build test mapping for a source file."""
    stem = file_path.stem
    source_rel = file_path.relative_to(SRC_ROOT).as_posix()

    test_files = find_test_files(module_name, stem)
    total_tests = sum(count_test_functions(tf) for tf in test_files)

    test_rel_paths = [tf.relative_to(PROJECT_ROOT).as_posix() for tf in test_files]

    return TestMapping(
        source_file=source_rel,
        test_files=test_rel_paths,
        test_count=total_tests,
    )


# ---------------------------------------------------------------------------
# Version Reader
# ---------------------------------------------------------------------------


def read_version() -> str:
    """Read version from pyproject.toml."""
    pyproject = PROJECT_ROOT / "pyproject.toml"
    if not pyproject.exists():
        return "unknown"
    content = pyproject.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    return match.group(1) if match else "unknown"


# ---------------------------------------------------------------------------
# Section 2: Preserve ASCII Graphs
# ---------------------------------------------------------------------------


def extract_section2_graphs(existing_path: Path) -> str | None:
    """Extract the content between Section 2 header and Section 3 header.

    Returns the full Section 2 content (including header) if found,
    or None if the file doesn't exist or markers aren't found.
    """
    if not existing_path.exists():
        return None

    content = existing_path.read_text(encoding="utf-8")

    # Find Section 2 start
    s2_match = re.search(r"^## Section 2: Call / Dependency Graph", content, re.MULTILINE)
    if not s2_match:
        return None

    # Find Section 3 start
    s3_match = re.search(r"^## Section 3: Traceability Matrix", content, re.MULTILINE)
    if not s3_match:
        return None

    return content[s2_match.start() : s3_match.start()]


# ---------------------------------------------------------------------------
# Rendering: Section 1 — API Reference
# ---------------------------------------------------------------------------


def _escape_pipe(text: str) -> str:
    """Escape pipe characters for markdown tables."""
    return text.replace("|", "\\|")


def render_symbol_table(symbols: list[SymbolInfo], is_enum_file: bool = False) -> str:
    """Render a symbol table in markdown."""
    if not symbols:
        return ""

    lines: list[str] = []

    if is_enum_file:
        # Special table for enum files
        lines.append("| Symbol | Kind | Values | Line | Description |")
        lines.append("|--------|------|--------|------|-------------|")
        for sym in symbols:
            values = _escape_pipe(sym.enum_values) if sym.enum_values else sym.signature
            lines.append(
                f"| `{sym.name}` | {sym.kind} | {values} | {sym.line} "
                f"| {_escape_pipe(sym.description)} |"
            )
    else:
        lines.append("| Symbol | Kind | Signature | Line | Description |")
        lines.append("|--------|------|-----------|------|-------------|")
        for sym in symbols:
            sig = sym.signature
            if sym.kind == "model" and sym.is_frozen:
                sig = "`frozen=True`" if not sig else f"`frozen=True` {sig}"
            elif sig:
                sig = f"`{sig}`"
            lines.append(
                f"| `{sym.name}` | {sym.kind} | {sig} | {sym.line} "
                f"| {_escape_pipe(sym.description)} |"
            )

    return "\n".join(lines)


def render_section1() -> str:
    """Render Section 1: API Reference."""
    lines: list[str] = []
    lines.append("## Section 1: API Reference")
    lines.append("")
    lines.append("Modules ordered by dependency depth (leaf modules first, entry points last).")
    lines.append("")
    lines.append("---")
    lines.append("")

    for idx, module_name in enumerate(MODULE_ORDER, start=1):
        title = MODULE_TITLES.get(module_name, module_name)
        lines.append(f"### 1.{idx} `{module_name}/` — {title}")
        lines.append("")

        module_dir = SRC_ROOT / module_name
        py_files = discover_py_files(module_dir)

        if not py_files:
            lines.append(f"*No Python files found in `{module_name}/`.*")
            lines.append("")
            continue

        for py_file in py_files:
            ms = extract_symbols(py_file)
            if not ms.symbols:
                continue

            lines.append(f"#### {ms.module_path}")
            lines.append("")

            is_enum = "enum" in py_file.stem.lower()
            table = render_symbol_table(ms.symbols, is_enum_file=is_enum)
            lines.append(table)
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rendering: Section 2 — Dependency Graph
# ---------------------------------------------------------------------------


def render_dependency_table(graph: dict[str, set[str]]) -> str:
    """Render the auto-generated dependency table."""
    lines: list[str] = []
    lines.append("### Module Dependency Table (auto-generated)")
    lines.append("")
    lines.append("| Module | Depends On |")
    lines.append("|--------|-----------|")

    for module in MODULE_ORDER:
        deps = sorted(graph.get(module, set()))
        dep_str = ", ".join(f"`{d}`" for d in deps) if deps else "—"
        lines.append(f"| `{module}/` | {dep_str} |")

    lines.append("")
    return "\n".join(lines)


def render_section2(existing_output: Path) -> str:
    """Render Section 2: Call / Dependency Graph.

    Auto-generates the dependency table. Preserves ASCII call graphs
    from the existing file if available.
    """
    lines: list[str] = []

    # Try to preserve the existing Section 2 content (ASCII graphs)
    existing_section2 = extract_section2_graphs(existing_output)

    if existing_section2:
        # Return the existing Section 2 as-is (hand-crafted ASCII graphs
        # are preserved verbatim, not auto-generated)
        return existing_section2
    else:
        # Generate a minimal Section 2
        lines.append("## Section 2: Call / Dependency Graph")
        lines.append("")

        graph = build_dependency_graph()
        lines.append(render_dependency_table(graph))

        lines.append("*ASCII call graphs not available. Run the generator against an existing*")
        lines.append("*`docs/technical-reference.md` with hand-crafted graphs to preserve them.*")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rendering: Section 3 — Traceability Matrix
# ---------------------------------------------------------------------------


def render_section3() -> str:
    """Render Section 3: Traceability Matrix."""
    lines: list[str] = []
    lines.append("## Section 3: Traceability Matrix")
    lines.append("")
    lines.append("Each row maps a source file to its test files and approximate test count.")
    lines.append("")

    for module_name in MODULE_ORDER:
        module_dir = SRC_ROOT / module_name
        py_files = discover_py_files(module_dir)

        if not py_files:
            continue

        lines.append(f"### {module_name}/")
        lines.append("")
        lines.append("| Source File | Test File(s) | Tests |")
        lines.append("|------------|--------------|-------|")

        for py_file in py_files:
            tm = build_test_mapping(module_name, py_file)
            source_rel = tm.source_file
            test_str = ", ".join(f"`{tf}`" for tf in tm.test_files) if tm.test_files else "—"
            lines.append(f"| `{source_rel}` | {test_str} | {tm.test_count} |")

        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rendering: Summary Statistics
# ---------------------------------------------------------------------------


def render_summary() -> str:
    """Render summary statistics table."""
    lines: list[str] = []
    lines.append("### Summary Statistics")
    lines.append("")
    lines.append("| Module | Files | Public Symbols | Test Files | Tests |")
    lines.append("|--------|-------|----------------|------------|-------|")

    total_files = 0
    total_symbols = 0
    total_test_files = 0
    total_tests = 0

    for module_name in MODULE_ORDER:
        module_dir = SRC_ROOT / module_name
        py_files = discover_py_files(module_dir)

        file_count = len(py_files)
        symbol_count = 0
        test_file_set: set[str] = set()
        test_count = 0

        for py_file in py_files:
            ms = extract_symbols(py_file)
            symbol_count += len(ms.symbols)

            tm = build_test_mapping(module_name, py_file)
            test_file_set.update(tm.test_files)
            test_count += tm.test_count

        tf_count = len(test_file_set)

        lines.append(
            f"| {module_name}/ | {file_count} | {symbol_count} | {tf_count} | {test_count} |"
        )

        total_files += file_count
        total_symbols += symbol_count
        total_test_files += tf_count
        total_tests += test_count

    lines.append(
        f"| **Total** | **{total_files}** | **{total_symbols}** "
        f"| **{total_test_files}** | **{total_tests}** |"
    )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main Assembly
# ---------------------------------------------------------------------------


def generate_document(output_path: Path) -> str:
    """Generate the full technical reference document."""
    version = read_version()

    parts: list[str] = []

    # Header
    parts.append("# Options Arena — Technical Reference")
    parts.append("")
    parts.append(f"> Auto-generated codebase reference. Version {version}.")
    parts.append("")
    parts.append("## Table of Contents")
    parts.append("")
    parts.append("- [Section 1: API Reference](#section-1-api-reference)")
    parts.append("- [Section 2: Call / Dependency Graph](#section-2-call--dependency-graph)")
    parts.append("- [Section 3: Traceability Matrix](#section-3-traceability-matrix)")
    parts.append("")
    parts.append("---")
    parts.append("")

    # Section 1
    parts.append(render_section1())

    # Section 2
    parts.append(render_section2(output_path))

    # Section 3
    parts.append(render_section3())

    # Summary
    parts.append("---")
    parts.append("")
    parts.append(render_summary())

    content = "\n".join(parts)

    # Normalize: strip trailing whitespace, collapse 3+ blank lines to 2
    content_lines = [line.rstrip() for line in content.split("\n")]
    content = "\n".join(content_lines)
    while "\n\n\n" in content:
        content = content.replace("\n\n\n", "\n\n")
    if not content.endswith("\n"):
        content += "\n"

    return content


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate docs/technical-reference.md from AST introspection."
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output file path (default: {DEFAULT_OUTPUT.relative_to(PROJECT_ROOT)})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if output is up-to-date; exit 1 if stale.",
    )
    args = parser.parse_args()

    output_path: Path = args.output

    content = generate_document(output_path)

    if args.check:
        if not output_path.exists():
            print(f"STALE: {output_path} does not exist.", file=sys.stderr)
            return 1
        existing = output_path.read_text(encoding="utf-8")
        if existing != content:
            print(
                f"STALE: {output_path} is out of date. "
                f"Run 'python tools/docgen.py' to regenerate.",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {output_path} is up to date.")
        return 0

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(content, encoding="utf-8")
    print(f"Generated {output_path} ({len(content):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
