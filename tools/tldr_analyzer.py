"""TLDR 5-Layer Code Analyzer — AST-based code summaries for agent orientation.

Parses Python files under src/options_arena/ and produces compressed summaries
with 5 analysis layers: Structure, Call Graph, Control Flow, Data Flow, Dependencies.

Summaries are cached to .claude/cache/tldr/ and invalidated by SHA-256 hash.
Typical compression: ~96% for files >150 lines.

Usage:
    python tools/tldr_analyzer.py                      # Index all files (incremental)
    python tools/tldr_analyzer.py --file path/to/X.py  # Single file summary to stdout
    python tools/tldr_analyzer.py --module scoring      # Index one module
    python tools/tldr_analyzer.py --check               # Report stale/missing summaries
    python tools/tldr_analyzer.py --stats               # Print cache statistics
    python tools/tldr_analyzer.py --clean               # Remove orphaned summaries

Stdlib-only — no external dependencies.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "options_arena"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / ".claude" / "cache" / "tldr"
MANIFEST_PATH = CACHE_DIR / "manifest.json"

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
    "analysis",
    "learning",
    "api",
    "cli",
]

# Minimum file size (lines) to generate a summary
MIN_LINES_THRESHOLD = 30

# Max control flow items per function
MAX_CONTROL_FLOW_PER_FUNC = 5

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class FuncInfo:
    """Extracted function/method information."""

    name: str
    line: int
    is_async: bool
    params: list[str]
    return_type: str
    docstring_first_line: str
    calls: list[str] = field(default_factory=list)
    control_flow: list[str] = field(default_factory=list)
    input_types: list[str] = field(default_factory=list)
    output_types: list[str] = field(default_factory=list)


@dataclass
class ClassInfo:
    """Extracted class information."""

    name: str
    line: int
    kind: str  # "model", "StrEnum", "dataclass", "class", "Protocol"
    bases: list[str]
    is_frozen: bool
    docstring_first_line: str
    methods: list[FuncInfo] = field(default_factory=list)
    constants: list[str] = field(default_factory=list)


@dataclass
class FileAnalysis:
    """Complete 5-layer analysis of a single file."""

    rel_path: str
    total_lines: int
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FuncInfo] = field(default_factory=list)
    constants: list[tuple[str, str, int]] = field(default_factory=list)  # (name, type, line)
    imports: list[str] = field(default_factory=list)  # internal imports (options_arena.*)
    external_imports: list[str] = field(default_factory=list)  # third-party imports


# ---------------------------------------------------------------------------
# AST Helpers (adapted from docgen.py)
# ---------------------------------------------------------------------------


def _get_docstring_first_line(
    node: ast.AsyncFunctionDef | ast.FunctionDef | ast.ClassDef | ast.Module,
) -> str:
    """Extract the first non-empty line of a docstring."""
    ds = ast.get_docstring(node)
    if not ds:
        return ""
    for line in ds.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _unparse_safe(node: ast.expr | None) -> str:
    """Safely unparse an AST expression node."""
    if node is None:
        return ""
    try:
        result = ast.unparse(node)
        return result[:60] + "..." if len(result) > 60 else result
    except Exception:
        return "..."


def _get_base_names(node: ast.ClassDef) -> list[str]:
    """Extract base class names as strings."""
    names: list[str] = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.append(base.id)
        elif isinstance(base, (ast.Attribute, ast.Subscript)):
            try:
                names.append(ast.unparse(base))
            except Exception:
                names.append("...")
    return names


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


_KNOWN_MODEL_BASES = {
    "BaseModel", "BaseSettings", "TradeThesis", "AgentResponse",
    "VolatilityThesis", "FlowThesis", "RiskAssessment",
    "FundamentalThesis", "ContrarianThesis", "ExtendedTradeThesis",
}


def _classify_class(node: ast.ClassDef) -> str:
    """Determine class kind."""
    base_names = _get_base_names(node)
    base_simple = [b.split(".")[-1] for b in base_names]

    if "StrEnum" in base_simple:
        return "StrEnum"
    if any(b in _KNOWN_MODEL_BASES for b in base_simple):
        return "model"
    if "Protocol" in base_simple:
        return "Protocol"

    for deco in node.decorator_list:
        if isinstance(deco, ast.Name) and deco.id == "dataclass":
            return "dataclass"
        if isinstance(deco, ast.Attribute) and deco.attr == "dataclass":
            return "dataclass"

    if _is_frozen(node):
        return "model"

    return "class"


# ---------------------------------------------------------------------------
# L1: Structure Extractor
# ---------------------------------------------------------------------------


def _build_param_list(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Build parameter list with type annotations."""
    params: list[str] = []
    for arg in node.args.args:
        if arg.arg in ("self", "cls"):
            continue
        if arg.annotation:
            ann = _unparse_safe(arg.annotation)
            params.append(f"{arg.arg}: {ann}")
        else:
            params.append(arg.arg)
    return params


def _extract_return_type(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Extract return type annotation."""
    if node.returns:
        return _unparse_safe(node.returns)
    return ""


def _extract_func(node: ast.FunctionDef | ast.AsyncFunctionDef) -> FuncInfo:
    """Extract function info from AST node."""
    return FuncInfo(
        name=node.name,
        line=node.lineno,
        is_async=isinstance(node, ast.AsyncFunctionDef),
        params=_build_param_list(node),
        return_type=_extract_return_type(node),
        docstring_first_line=_get_docstring_first_line(node),
    )


# ---------------------------------------------------------------------------
# L2: Call Graph Extractor
# ---------------------------------------------------------------------------

# Common builtins/stdlib to filter out
_SKIP_CALLS = frozenset({
    "len", "str", "int", "float", "bool", "list", "dict", "set", "tuple",
    "range", "enumerate", "zip", "map", "filter", "sorted", "reversed",
    "print", "isinstance", "issubclass", "hasattr", "getattr", "setattr",
    "type", "super", "property", "staticmethod", "classmethod",
    "min", "max", "sum", "abs", "round", "any", "all", "next", "iter",
    "open", "repr", "format", "id", "hash", "callable",
})


class _CallExtractor(ast.NodeVisitor):
    """Extract function/method calls within a function body."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        name = self._get_call_name(node.func)
        if name and name not in _SKIP_CALLS:
            if name not in self.calls:
                self.calls.append(name)
        self.generic_visit(node)

    def _get_call_name(self, node: ast.expr) -> str:
        """Extract call name from AST node."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            # For self.method() -> self.method
            # For module.func() -> module.func
            prefix = self._get_call_name(node.value)
            if prefix:
                return f"{prefix}.{node.attr}"
            return node.attr
        return ""


def _extract_calls(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Extract call targets from a function body."""
    extractor = _CallExtractor()
    for child in ast.iter_child_nodes(func_node):
        extractor.visit(child)
    return extractor.calls[:15]  # Cap at 15 calls


# ---------------------------------------------------------------------------
# L3: Control Flow Extractor
# ---------------------------------------------------------------------------


def _extract_control_flow(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Extract key control flow constructs from a function."""
    items: list[str] = []

    for node in ast.walk(func_node):
        if len(items) >= MAX_CONTROL_FLOW_PER_FUNC:
            break

        if isinstance(node, ast.If):
            cond = _unparse_safe(node.test)
            if len(cond) > 50:
                cond = cond[:47] + "..."
            # Classify
            if "raise" in ast.dump(node):
                items.append(f"guard: if {cond}")
            else:
                items.append(f"branch: if {cond}")

        elif isinstance(node, ast.Match):
            subject = _unparse_safe(node.subject)
            items.append(f"dispatch: match {subject}")

        elif isinstance(node, ast.Try):
            handlers = []
            for handler in node.handlers:
                if handler.type:
                    handlers.append(_unparse_safe(handler.type))
                else:
                    handlers.append("Exception")
            items.append(f"error_handling: try/except {', '.join(handlers)}")

        elif isinstance(node, (ast.For, ast.AsyncFor)):
            target = _unparse_safe(node.target)
            iter_val = _unparse_safe(node.iter)
            if len(iter_val) > 30:
                iter_val = iter_val[:27] + "..."
            items.append(f"loop: for {target} in {iter_val}")

        elif isinstance(node, ast.While):
            cond = _unparse_safe(node.test)
            items.append(f"loop: while {cond}")

    return items


# ---------------------------------------------------------------------------
# L4: Data Flow Extractor
# ---------------------------------------------------------------------------


def _extract_data_flow(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[list[str], list[str]]:
    """Extract input types and output types from annotations and return stmts."""
    # Input types from parameters
    input_types: list[str] = []
    for arg in func_node.args.args:
        if arg.arg in ("self", "cls"):
            continue
        if arg.annotation:
            ann = _unparse_safe(arg.annotation)
            input_types.append(ann)

    # Output types from return annotation + return statements
    output_types: list[str] = []
    if func_node.returns:
        output_types.append(_unparse_safe(func_node.returns))

    # Also look for model construction in return statements
    for node in ast.walk(func_node):
        if isinstance(node, ast.Return) and node.value:
            if isinstance(node.value, ast.Call):
                call_name = ""
                if isinstance(node.value.func, ast.Name):
                    call_name = node.value.func.id
                elif isinstance(node.value.func, ast.Attribute):
                    call_name = node.value.func.attr
                if call_name and call_name[0].isupper() and call_name not in output_types:
                    output_types.append(call_name)

    return input_types[:5], output_types[:3]


# ---------------------------------------------------------------------------
# L5: Import Analyzer
# ---------------------------------------------------------------------------


def _extract_imports(tree: ast.Module) -> tuple[list[str], list[str]]:
    """Extract internal (options_arena.*) and external imports."""
    internal: list[str] = []
    external: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("options_arena."):
                parts = node.module.split(".")
                if len(parts) >= 2:
                    submod = parts[1]
                    if submod not in internal:
                        internal.append(submod)
            elif not node.module.startswith("__"):
                top = node.module.split(".")[0]
                if top not in external and top not in (
                    "typing", "collections", "abc", "enum", "dataclasses",
                    "functools", "itertools", "contextlib", "pathlib",
                ):
                    external.append(top)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top not in external:
                    external.append(top)

    return internal, external


# ---------------------------------------------------------------------------
# Full File Analysis
# ---------------------------------------------------------------------------


def analyze_file(file_path: Path) -> FileAnalysis | None:
    """Perform full 5-layer analysis on a Python file."""
    try:
        source = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return None

    total_lines = len(source.splitlines())
    rel_path = file_path.relative_to(SRC_ROOT).as_posix()

    analysis = FileAnalysis(rel_path=rel_path, total_lines=total_lines)

    # L5: Imports
    internal_imports, external_imports = _extract_imports(tree)
    analysis.imports = internal_imports
    analysis.external_imports = external_imports

    # Walk top-level nodes
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            class_info = _analyze_class(node)
            analysis.classes.append(class_info)

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_info = _analyze_function(node)
            analysis.functions.append(func_info)

        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    val_type = _guess_value_type(node.value)
                    analysis.constants.append((target.id, val_type, node.lineno))

        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id.isupper():
                ann = _unparse_safe(node.annotation)
                analysis.constants.append((node.target.id, ann, node.lineno))

    return analysis


def _analyze_class(node: ast.ClassDef) -> ClassInfo:
    """Analyze a class definition."""
    info = ClassInfo(
        name=node.name,
        line=node.lineno,
        kind=_classify_class(node),
        bases=_get_base_names(node),
        is_frozen=_is_frozen(node),
        docstring_first_line=_get_docstring_first_line(node),
    )

    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if item.name.startswith("__") and item.name != "__init__":
                continue
            func_info = _analyze_function(item)
            info.methods.append(func_info)

        elif isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    info.constants.append(target.id)

    return info


def _analyze_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> FuncInfo:
    """Analyze a function/method definition with all 5 layers."""
    func_info = _extract_func(node)

    # L2: Call graph
    func_info.calls = _extract_calls(node)

    # L3: Control flow
    func_info.control_flow = _extract_control_flow(node)

    # L4: Data flow
    input_types, output_types = _extract_data_flow(node)
    func_info.input_types = input_types
    func_info.output_types = output_types

    return func_info


def _guess_value_type(node: ast.expr) -> str:
    """Guess the type of a constant's value."""
    if isinstance(node, ast.Call):
        return _unparse_safe(node.func)
    if isinstance(node, ast.Constant):
        return type(node.value).__name__
    if isinstance(node, ast.List):
        return "list"
    if isinstance(node, ast.Dict):
        return "dict"
    if isinstance(node, ast.Set):
        return "set"
    if isinstance(node, ast.Tuple):
        return "tuple"
    return ""


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_summary(analysis: FileAnalysis) -> str:
    """Render a FileAnalysis as concise markdown."""
    lines: list[str] = []

    lines.append(f"# {analysis.rel_path}")
    lines.append(f"**{analysis.total_lines} lines**")
    lines.append("")

    # L1: Structure
    if analysis.classes or analysis.functions or analysis.constants:
        lines.append("## Structure")

        for cls in analysis.classes:
            frozen = " (frozen)" if cls.is_frozen else ""
            bases = f"({', '.join(cls.bases)})" if cls.bases else ""
            lines.append(f"- **{cls.kind}** `{cls.name}{bases}`{frozen} L{cls.line}")
            if cls.docstring_first_line:
                lines.append(f"  {cls.docstring_first_line}")
            for method in cls.methods:
                async_prefix = "async " if method.is_async else ""
                ret = f" -> {method.return_type}" if method.return_type else ""
                params_str = ", ".join(method.params[:4])
                if len(method.params) > 4:
                    params_str += ", ..."
                lines.append(f"  - `{async_prefix}{method.name}({params_str}){ret}` L{method.line}")

        for func in analysis.functions:
            async_prefix = "async " if func.is_async else ""
            ret = f" -> {func.return_type}" if func.return_type else ""
            params_str = ", ".join(func.params[:4])
            if len(func.params) > 4:
                params_str += ", ..."
            lines.append(f"- `{async_prefix}{func.name}({params_str}){ret}` L{func.line}")
            if func.docstring_first_line:
                lines.append(f"  {func.docstring_first_line}")

        if analysis.constants:
            const_strs = [f"`{n}`:{t}" if t else f"`{n}`" for n, t, _ in analysis.constants[:10]]
            lines.append(f"- Constants: {', '.join(const_strs)}")

        lines.append("")

    # L2: Call Graph (only for non-trivial functions)
    call_edges: list[str] = []
    all_funcs = list(analysis.functions)
    for cls in analysis.classes:
        all_funcs.extend(cls.methods)

    for func in all_funcs:
        if func.calls:
            calls_str = ", ".join(func.calls[:8])
            if len(func.calls) > 8:
                calls_str += ", ..."
            call_edges.append(f"- `{func.name}` -> {calls_str}")

    if call_edges:
        lines.append("## Call Graph")
        lines.extend(call_edges[:20])
        lines.append("")

    # L3: Control Flow (only significant items)
    flow_items: list[str] = []
    for func in all_funcs:
        if func.control_flow:
            for cf in func.control_flow:
                flow_items.append(f"- `{func.name}`: {cf}")

    if flow_items:
        lines.append("## Control Flow")
        lines.extend(flow_items[:15])
        lines.append("")

    # L4: Data Flow (only for functions with type info)
    data_items: list[str] = []
    for func in all_funcs:
        if func.input_types or func.output_types:
            inputs = ", ".join(func.input_types[:3]) if func.input_types else "?"
            outputs = ", ".join(func.output_types[:2]) if func.output_types else "?"
            data_items.append(f"- `{func.name}`: {inputs} -> {outputs}")

    if data_items:
        lines.append("## Data Flow")
        lines.extend(data_items[:15])
        lines.append("")

    # L5: Dependencies
    if analysis.imports or analysis.external_imports:
        lines.append("## Dependencies")
        if analysis.imports:
            lines.append(f"- Internal: {', '.join(analysis.imports)}")
        if analysis.external_imports:
            lines.append(f"- External: {', '.join(analysis.external_imports)}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Cache Management
# ---------------------------------------------------------------------------


def _file_hash(path: Path) -> str:
    """Compute SHA-256 of a file."""
    h = hashlib.sha256()
    try:
        h.update(path.read_bytes())
    except OSError:
        return ""
    return h.hexdigest()


def _load_manifest() -> dict:
    """Load the cache manifest."""
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"files": {}, "reverse_deps": {}}


def _save_manifest(manifest: dict) -> None:
    """Save the cache manifest."""
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _cache_path_for(rel_path: str) -> Path:
    """Get the cache file path for a source file's relative path."""
    # Convert "models/market_data.py" -> ".claude/cache/tldr/models/market_data.md"
    md_path = rel_path.replace(".py", ".md")
    return CACHE_DIR / md_path


def _is_stale(rel_path: str, file_path: Path, manifest: dict) -> bool:
    """Check if a cached summary is stale."""
    entry = manifest.get("files", {}).get(rel_path)
    if entry is None:
        return True

    cache_path = _cache_path_for(rel_path)
    if not cache_path.exists():
        return True

    # Quick mtime check first
    try:
        current_mtime = file_path.stat().st_mtime
    except OSError:
        return True

    if current_mtime != entry.get("mtime"):
        # mtime changed — do hash check
        current_hash = _file_hash(file_path)
        if current_hash != entry.get("hash"):
            return True
        # Hash matches despite mtime change — update mtime in manifest
        entry["mtime"] = current_mtime

    return False


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_source_files(module_filter: str | None = None) -> list[Path]:
    """Find all Python source files, optionally filtered by module."""
    files: list[Path] = []
    modules = [module_filter] if module_filter else MODULE_ORDER

    for module_name in modules:
        module_dir = SRC_ROOT / module_name
        if not module_dir.exists():
            continue
        for py_file in sorted(module_dir.rglob("*.py")):
            if py_file.name == "__init__.py":
                continue
            if "__pycache__" in str(py_file):
                continue
            files.append(py_file)

    return files


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_index(module_filter: str | None = None) -> int:
    """Index all files (incremental). Returns number of files updated."""
    manifest = _load_manifest()
    files = discover_source_files(module_filter)
    updated = 0
    skipped = 0

    for file_path in files:
        rel_path = file_path.relative_to(SRC_ROOT).as_posix()

        # Skip small files
        try:
            line_count = len(file_path.read_text(encoding="utf-8").splitlines())
        except (OSError, UnicodeDecodeError):
            continue

        if line_count < MIN_LINES_THRESHOLD:
            skipped += 1
            continue

        if not _is_stale(rel_path, file_path, manifest):
            skipped += 1
            continue

        analysis = analyze_file(file_path)
        if analysis is None:
            continue

        summary = render_summary(analysis)
        cache_path = _cache_path_for(rel_path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(summary, encoding="utf-8")

        # Update manifest
        file_hash = _file_hash(file_path)
        try:
            mtime = file_path.stat().st_mtime
        except OSError:
            mtime = 0

        if "files" not in manifest:
            manifest["files"] = {}
        manifest["files"][rel_path] = {
            "hash": file_hash,
            "mtime": mtime,
            "lines": line_count,
            "summary_lines": len(summary.splitlines()),
        }
        updated += 1

    # Build reverse dependency map
    reverse_deps: dict[str, list[str]] = {}
    for rel_path, entry in manifest.get("files", {}).items():
        cache_path = _cache_path_for(rel_path)
        if cache_path.exists():
            content = cache_path.read_text(encoding="utf-8")
            # Parse "Internal:" line for dependencies
            for line in content.splitlines():
                if line.startswith("- Internal:"):
                    deps = line.replace("- Internal:", "").strip().split(", ")
                    for dep in deps:
                        dep = dep.strip()
                        if dep:
                            if dep not in reverse_deps:
                                reverse_deps[dep] = []
                            # Extract module from rel_path
                            src_module = rel_path.split("/")[0] if "/" in rel_path else ""
                            if src_module and src_module not in reverse_deps[dep]:
                                reverse_deps[dep].append(src_module)

    manifest["reverse_deps"] = reverse_deps
    _save_manifest(manifest)

    scope = f"module={module_filter}" if module_filter else "all"
    print(f"TLDR index ({scope}): {updated} updated, {skipped} skipped, {len(files)} total")
    return updated


def cmd_single_file(file_path_str: str) -> int:
    """Analyze a single file and print summary to stdout."""
    file_path = Path(file_path_str).resolve()

    if not file_path.exists():
        print(f"File not found: {file_path}", file=sys.stderr)
        return 1

    if not file_path.suffix == ".py":
        print(f"Not a Python file: {file_path}", file=sys.stderr)
        return 1

    analysis = analyze_file(file_path)
    if analysis is None:
        print(f"Could not analyze: {file_path}", file=sys.stderr)
        return 1

    print(render_summary(analysis))
    return 0


def cmd_check() -> int:
    """Report stale or missing summaries."""
    manifest = _load_manifest()
    files = discover_source_files()
    stale: list[str] = []
    missing: list[str] = []

    for file_path in files:
        rel_path = file_path.relative_to(SRC_ROOT).as_posix()

        try:
            line_count = len(file_path.read_text(encoding="utf-8").splitlines())
        except (OSError, UnicodeDecodeError):
            continue

        if line_count < MIN_LINES_THRESHOLD:
            continue

        cache_path = _cache_path_for(rel_path)
        if not cache_path.exists():
            missing.append(rel_path)
        elif _is_stale(rel_path, file_path, manifest):
            stale.append(rel_path)

    if not stale and not missing:
        print("All summaries are up to date.")
        return 0

    if missing:
        print(f"\nMissing summaries ({len(missing)}):")
        for p in sorted(missing):
            print(f"  {p}")

    if stale:
        print(f"\nStale summaries ({len(stale)}):")
        for p in sorted(stale):
            print(f"  {p}")

    print(f"\nRun 'python tools/tldr_analyzer.py' to refresh.")
    return 1


def cmd_stats() -> int:
    """Print cache statistics."""
    manifest = _load_manifest()
    files_info = manifest.get("files", {})

    if not files_info:
        print("No cached summaries. Run 'python tools/tldr_analyzer.py' to build.")
        return 0

    total_source_lines = 0
    total_summary_lines = 0
    count = 0
    by_module: dict[str, dict[str, int]] = {}

    for rel_path, entry in files_info.items():
        source_lines = entry.get("lines", 0)
        summary_lines = entry.get("summary_lines", 0)
        total_source_lines += source_lines
        total_summary_lines += summary_lines
        count += 1

        module = rel_path.split("/")[0] if "/" in rel_path else "root"
        if module not in by_module:
            by_module[module] = {"files": 0, "source": 0, "summary": 0}
        by_module[module]["files"] += 1
        by_module[module]["source"] += source_lines
        by_module[module]["summary"] += summary_lines

    compression = (
        (1 - total_summary_lines / total_source_lines) * 100
        if total_source_lines > 0
        else 0
    )

    print(f"TLDR Cache Statistics")
    print(f"{'=' * 60}")
    print(f"Files cached:      {count}")
    print(f"Source lines:      {total_source_lines:,}")
    print(f"Summary lines:     {total_summary_lines:,}")
    print(f"Compression:       {compression:.1f}%")
    print()
    print(f"{'Module':<15} {'Files':>6} {'Source':>8} {'Summary':>8} {'Ratio':>7}")
    print(f"{'-' * 15} {'-' * 6} {'-' * 8} {'-' * 8} {'-' * 7}")

    for module in sorted(by_module.keys()):
        info = by_module[module]
        ratio = (
            f"{info['summary'] / info['source'] * 100:.0f}%"
            if info["source"] > 0
            else "N/A"
        )
        print(
            f"{module:<15} {info['files']:>6} "
            f"{info['source']:>8} {info['summary']:>8} {ratio:>7}"
        )

    # Reverse deps
    reverse_deps = manifest.get("reverse_deps", {})
    if reverse_deps:
        print(f"\nReverse dependencies (imported_by):")
        for module, importers in sorted(reverse_deps.items()):
            print(f"  {module} <- {', '.join(sorted(importers))}")

    return 0


def cmd_clean() -> int:
    """Remove orphaned cache files (source file deleted)."""
    manifest = _load_manifest()
    removed = 0

    files_to_remove: list[str] = []
    for rel_path in list(manifest.get("files", {}).keys()):
        source_path = SRC_ROOT / rel_path
        if not source_path.exists():
            cache_path = _cache_path_for(rel_path)
            if cache_path.exists():
                cache_path.unlink()
                removed += 1
            files_to_remove.append(rel_path)

    for rel_path in files_to_remove:
        del manifest["files"][rel_path]

    # Also clean orphaned .md files not in manifest
    if CACHE_DIR.exists():
        for md_file in CACHE_DIR.rglob("*.md"):
            rel_cache = md_file.relative_to(CACHE_DIR).as_posix()
            rel_source = rel_cache.replace(".md", ".py")
            if rel_source not in manifest.get("files", {}) and md_file.name != "manifest.json":
                source_path = SRC_ROOT / rel_source
                if not source_path.exists():
                    md_file.unlink()
                    removed += 1

    _save_manifest(manifest)
    print(f"Cleaned {removed} orphaned summaries.")
    return 0


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="TLDR 5-Layer Code Analyzer — AST-based code summaries."
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Analyze a single file and print summary to stdout.",
    )
    parser.add_argument(
        "--module",
        type=str,
        choices=MODULE_ORDER,
        help="Index only a specific module.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report stale or missing summaries.",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print cache statistics.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove orphaned summaries.",
    )

    args = parser.parse_args()

    if args.file:
        return cmd_single_file(args.file)
    if args.check:
        return cmd_check()
    if args.stats:
        return cmd_stats()
    if args.clean:
        return cmd_clean()

    return cmd_index(args.module)


if __name__ == "__main__":
    sys.exit(main())
