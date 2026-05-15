"""
stub_gen.py - Automatic .pyi stub generator for SemanticType subclasses.

Scans Python source files, detects all SemanticType subclasses transitively,
and generates corresponding .pyi stub files that teach Pyright the correct
types for uppercase string attributes defined via SemanticTypesMeta metaclass.

Why this script exists:
    SemanticTypesMeta transforms uppercase string attributes into SemanticType
    instances at class creation time. Pyright cannot observe this runtime
    transformation statically and therefore raises assignment type errors
    like: Type "Literal['info']" is not assignable to declared type "LevelType".
    Manually maintained stubs are error-prone and do not scale when new
    SemanticType subclasses are added. This script generates them automatically.

Why ast and not import-based introspection:
    Importing modules executes them, which introduces side effects and requires
    all dependencies to be installed. ast parses source files as plain text
    without execution, making it safe, dependency-free, and suitable for
    pre-commit hooks and CI pipelines.

Transformations applied:
    SemanticType subclasses:
        ATTR = "value"  →  ATTR: ClassName
    All function and method bodies:
        body            →  ...
    Everything else:
        kept as-is (imports, dataclass fields, docstrings, decorators)

Usage:
    python tools/stub_gen.py                            # scan entire project
    python tools/stub_gen.py --src observer/            # specific package
    python tools/stub_gen.py --src observer/ --out stubs/
    python tools/stub_gen.py --src observer/core/domain/instruction.py
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# Analysis
# ─────────────────────────────────────────────────────────────


def collect_semantic_subclasses(
    tree: ast.Module,
    global_known: set[str] | None = None,
) -> set[str]:
    """
    Transitively collects all class names that inherit from SemanticType
    within a single parsed module.

    Why transitive:
        A file may define a chain of subclasses where each inherits from
        the previous one. A single linear pass would miss subclasses whose
        parents appear later in the file. Repeated passes continue until
        no new subclasses are discovered, guaranteeing full coverage
        regardless of definition order.

    Why global_known:
        SemanticType subclasses defined in other modules are imported by name.
        Without global_known, a class like InotifyEventType(EventType) would
        not be recognized as semantic because EventType is not defined in the
        same file. global_known carries names collected from previously
        processed files, resolving cross-module inheritance chains.

    Example chain handled across files:
        semantic_type.py  →  SemanticType
        event.py          →  EventType(SemanticType), CrossPlatformEventType(EventType)
        inotify_types.py  →  InotifyEventType(EventType)  ← requires global_known

    Notes:
        - SemanticType itself is excluded from the result because it defines
            no uppercase string attributes and requires no transformation.
        - global_known must be populated by a directory-level two-pass scan
            before per-file stub generation begins.
    """
    known: set[str] = {"SemanticType"} | (global_known or set())
    changed = True

    while changed:
        changed = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if node.name in known:
                continue

            for base in node.bases:
                base_name: str | None = None
                if isinstance(base, ast.Name):
                    base_name = base.id
                elif isinstance(base, ast.Attribute):
                    base_name = base.attr

                if base_name in known:
                    known.add(node.name)
                    changed = True
                    break

    known.discard("SemanticType")
    return known


def build_global_known(py_files: list[Path]) -> set[str]:
    """
    Performs a first pass over all source files to collect every SemanticType
    subclass name visible across the entire directory tree.

    Why two passes are needed:
        Cross-module inheritance requires knowing which class names are semantic
        before generating stubs. A single pass processes each file in isolation
        and misses cases where a subclass imports its base from another module.
        The first pass accumulates all known names. The second pass uses them
        during stub generation so that imported base class names are recognized.

    Notes:
        - Files are processed in sorted order for deterministic results.
        - Each file's findings are accumulated into a shared set that grows
            as more files are processed.
    """
    global_known: set[str] = set()

    for py_file in py_files:
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        global_known |= collect_semantic_subclasses(tree, global_known)

    return global_known


# ─────────────────────────────────────────────────────────────
# AST Transformation
# ─────────────────────────────────────────────────────────────


class StubTransformer(ast.NodeTransformer):
    """
    Transforms a module AST into its .pyi stub equivalent.

    Inherits from ast.NodeTransformer which provides recursive tree traversal.
    Subclassing NodeTransformer and overriding visit_* methods allows
    selective transformation of specific node types while leaving everything
    else untouched.

    Why NodeTransformer and not manual recursion:
        NodeTransformer handles the recursive traversal automatically.
        Overriding only the nodes we care about keeps the implementation
        focused and avoids reimplementing tree walking logic.

    Transformation Rules:
        - SemanticType subclasses: uppercase string assignments are replaced
            with annotated declarations so Pyright understands the correct type.
        - Functions and methods: bodies are replaced with ellipsis.
            Signatures, decorators and docstrings are preserved.
        - All other nodes: passed through unchanged.

    Notes:
        - generic_visit() must be called explicitly on non-semantic classes
            to ensure inner functions still receive body stubbing.
        - SemanticType subclass methods are stubbed via explicit iteration
            because generic_visit() is not called on their body in that branch.
    """

    def __init__(self, semantic_subclasses: set[str]) -> None:
        self._semantic_subclasses = semantic_subclasses

    # ── Functions ─────────────────────────────────────────────

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        """Replaces function body with ellipsis, preserving docstring if present."""
        return self._stub_function(node)  # type: ignore[return-value]

    def visit_AsyncFunctionDef(
        self,
        node: ast.AsyncFunctionDef,
    ) -> ast.AsyncFunctionDef:
        """
        Same transformation as visit_FunctionDef.

        Why separate method:
            ast treats async def and def as distinct node types.
            NodeTransformer dispatches to visit_* by exact type name,
            so both must be overridden individually even though the
            transformation logic is identical.
        """
        return self._stub_function(node)  # type: ignore[return-value]

    def _stub_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> ast.FunctionDef | ast.AsyncFunctionDef:
        """
        Replaces the body of a function or method with ellipsis.

        Docstring Preservation:
            In AST a docstring is always the first statement of a function body
            represented as Expr(Constant(str)). It is preserved in the stub
            because it carries semantic documentation that Pyright and IDEs
            surface to users during autocompletion and hover.

        Notes:
            - Does not recurse into nested functions. Nested function stubs
                are not required for .pyi correctness and are omitted.
        """
        new_body: list[ast.stmt] = []

        if self._has_docstring(node):
            new_body.append(node.body[0])

        new_body.append(ast.Expr(value=ast.Constant(value=...)))
        node.body = new_body
        return node

    # ── Classes ───────────────────────────────────────────────

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        """
        Transforms SemanticType subclasses by replacing uppercase string
        assignments with annotated declarations.

        Non-semantic classes are passed through with generic_visit() to
        ensure their inner functions are still stubbed correctly.

        Why generic_visit for non-semantic classes:
            When visit_ClassDef is overridden, NodeTransformer stops
            automatic recursion into the class body. generic_visit()
            restores that recursion so visit_FunctionDef is still
            called on all methods inside non-semantic classes.
        """
        if node.name not in self._semantic_subclasses:
            self.generic_visit(node)
            return node

        new_body: list[ast.stmt] = []

        for item in node.body:
            if self._is_semantic_attribute(item):
                new_body.append(self._make_annotated(item, node.name))  # type: ignore[assignment]
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                new_body.append(self._stub_function(item))
            else:
                new_body.append(item)

        node.body = new_body or [ast.Expr(value=ast.Constant(value=...))]
        return node

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _has_docstring(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        """Returns True if the first statement of a function body is a docstring."""
        return (
            bool(node.body)
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        )

    @staticmethod
    def _is_semantic_attribute(node: ast.stmt) -> bool:
        """
        Returns True if the node is an uppercase string constant assignment.

        This is the exact pattern produced by SemanticTypesMeta:
            INFO = "info"

        All six conditions must hold:
            - It is an assignment statement.
            - It has exactly one target (not a chained assignment like a = b = "x").
            - The target is a plain name (not self.x or obj.attr).
            - The name is fully uppercase.
            - The value is a literal constant.
            - The constant value is a string.
        """
        return (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id.isupper()
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        )

    @staticmethod
    def _make_annotated(node: ast.Assign, class_name: str) -> ast.AnnAssign:
        """
        Converts an uppercase string assignment into an annotated declaration.

        Before:  INFO = "info"      (ast.Assign)
        After:   INFO: LevelType    (ast.AnnAssign)

        AnnAssign fields:
            - target:     the attribute name (Store context - we are defining it)
            - annotation: the type name (Load context - we are referencing the class)
            - value:      None - no value on the right side in a stub declaration
            - simple:     1 - signals a plain name target, not an attribute like self.x
        """
        target = node.targets[0]
        assert isinstance(target, ast.Name)

        return ast.AnnAssign(
            target=ast.Name(id=target.id, ctx=ast.Store()),
            annotation=ast.Name(id=class_name, ctx=ast.Load()),
            value=None,
            simple=1,
        )


# ─────────────────────────────────────────────────────────────
# File Processing
# ─────────────────────────────────────────────────────────────


def generate_stub(source_path: Path, global_known: set[str] | None = None) -> str:
    """
    Parses a Python source file and returns its .pyi stub content as a string.

    Pipeline:
        source text → ast.parse → collect_semantic_subclasses
        → StubTransformer.visit → ast.fix_missing_locations → ast.unparse

    Notes:
        - ast.fix_missing_locations fills in line/column metadata for nodes
            created manually during transformation. Without it ast.unparse
            may raise on nodes that lack required location fields.
        - ast.unparse was introduced in Python 3.9. This script requires 3.9+.
    """
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    semantic_subclasses = collect_semantic_subclasses(tree, global_known)
    transformer = StubTransformer(semantic_subclasses)
    new_tree = transformer.visit(tree)
    ast.fix_missing_locations(new_tree)

    return ast.unparse(new_tree)


def process_file(
    source_path: Path,
    source_root: Path,
    stubs_root: Path,
    global_known: set[str] | None = None,
) -> None:
    """
    Generates a stub for a single .py file and writes it to the stubs directory.

    Path Mirroring:
        The source file path relative to source_root is preserved under
        stubs_root with the .py extension replaced by .pyi.

        Example:
            source_root = Python-Journey/
            source_path = Python-Journey/vakt_refac/observer/core/domain/instruction.py
            stubs_root  = Python-Journey/stubs/
            stub_path   = Python-Journey/stubs/vakt_refac/observer/core/domain/instruction.pyi
    """
    rel_path = source_path.relative_to(source_root)
    stub_path = stubs_root / rel_path.with_suffix(".pyi")

    stub_path.parent.mkdir(parents=True, exist_ok=True)
    stub_content = generate_stub(source_path, global_known)
    stub_path.write_text(stub_content, encoding="utf-8")

    print(f"  ✓  {stub_path.relative_to(stubs_root.parent)}")


def process_directory(source_dir: Path, stubs_root: Path) -> None:
    """
    Recursively generates stubs for all .py files found under source_dir.

    Two-Pass Strategy:
        Pass 1 - build_global_known: parses all files and collects every
            SemanticType subclass name visible across the entire directory.
            This resolves cross-module inheritance chains where a subclass
            imports its base class from another module.
        Pass 2 - generate stubs: uses global_known during transformation
            so that imported base class names are recognized correctly.

    Notes:
        - source_root is derived as source_dir.parent to preserve the
            package directory name in the mirrored stub path.
        - Files are processed in sorted order for deterministic output.
    """
    source_root = source_dir.parent
    py_files = sorted(source_dir.rglob("*.py"))

    global_known = build_global_known(py_files)

    for py_file in py_files:
        process_file(py_file, source_root, stubs_root, global_known)


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stub_gen",
        description="Generates .pyi stubs for SemanticType subclasses.",
    )
    parser.add_argument(
        "--src",
        type=Path,
        default=Path("."),
        metavar="PATH",
        help="Source file or directory to scan. Defaults to current directory.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "Output directory for generated stubs. "
            "Defaults to stubs/ next to the source root."
        ),
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    src: Path = args.src.resolve()

    if not src.exists():
        print(f"Error: path does not exist: {src}", file=sys.stderr)
        sys.exit(1)

    if src.is_file():
        stubs_root: Path = (
            args.out.resolve() if args.out else src.parent.parent / "stubs"
        )
        source_root = src.parent.parent
        print(f"stub_gen  {src.name}  →  {stubs_root}\n")
        process_file(src, source_root, stubs_root)
    else:
        stubs_root = args.out.resolve() if args.out else src.parent / "stubs"
        print(f"stub_gen  {src}  →  {stubs_root}\n")
        process_directory(src, stubs_root)

    print("\nDone.")


if __name__ == "__main__":
    main()
