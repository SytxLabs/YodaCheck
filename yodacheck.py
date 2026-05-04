"""
yodacheck — detect and auto-fix Yoda conditions in Python source files.

A Yoda condition places the literal on the left side of a comparison:
    if 5 == x: ...       # Yoda   → flagged
    if x == 5: ...       # Normal → ignored

Usage:
    python yodacheck.py <path> [<path> ...] [--fix] [--context N] [--format pretty|plain|json]
"""

import argparse
import ast
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

@dataclass(slots=True)
class Issue:
    path: Path
    lineno: int
    col: int
    end_lineno: int | None   # None only when node was created without source info
    end_col: int | None
    expr: str
    tag: str                 # "is None" | "is not None" | "bool" | "" (plain swap)
    replacement: str         # empty string when chained=True
    chained: bool

_OP: dict[type, str] = {
    ast.Eq: "==", ast.NotEq: "!=",
    ast.Lt: "<",  ast.LtE: "<=",
    ast.Gt: ">",  ast.GtE: ">=",
    ast.Is: "is", ast.IsNot: "is not",
}

def _seg(src: str, node: ast.AST) -> str:
    """Return the source segment for *node*, or an empty string if unavailable."""
    result = ast.get_source_segment(src, node)
    return result if result is not None else ""

def _suggest(left: str, right: str, op: ast.cmpop) -> tuple[str, str]:
    """Return *(short_tag, replacement_code)* for a Yoda condition."""
    if left == "None":
        if isinstance(op, ast.Eq):
            return "is None", f"{right} is None"
        if isinstance(op, ast.NotEq):
            return "is not None", f"{right} is not None"
    if left in {"True", "False"}:
        if isinstance(op, ast.Eq):
            return "bool", f"{right} is {left}"
        if isinstance(op, ast.NotEq):
            return "bool", f"{right} is not {left}"
    op_s = _OP.get(type(op), type(op).__name__)
    return "", f"{right} {op_s} {left}"

class YodaVisitor(ast.NodeVisitor):
    def __init__(self, src: str, path: Path) -> None:
        self.src = src
        self.path = path
        self.issues: list[Issue] = []

    def visit_Compare(self, node: ast.Compare) -> None:
        if isinstance(node.left, ast.Constant):
            op = node.ops[0]
            chained = len(node.comparators) != 1

            if chained:
                self._append(node, tag="", repl="", chained=True)
            elif not isinstance(op, (ast.In, ast.NotIn)):
                # `in`/`not in` with a literal on the left is normal membership
                # syntax (e.g. `1 in items`) — swapping sides makes no sense.
                left = _seg(self.src, node.left)
                right = _seg(self.src, node.comparators[0])
                tag, repl = _suggest(left, right, op)
                self._append(node, tag=tag, repl=repl, chained=False)

        self.generic_visit(node)

    def _append(self, node: ast.Compare, *, tag: str, repl: str, chained: bool) -> None:
        self.issues.append(Issue(
            path=self.path,
            lineno=node.lineno,
            col=node.col_offset,
            end_lineno=node.end_lineno,
            end_col=node.end_col_offset,
            expr=_seg(self.src, node),
            tag=tag,
            replacement=repl,
            chained=chained,
        ))

def analyze_file(path: Path) -> tuple[list[Issue], str]:
    """Parse *path* and return *(issues, source)*. Returns *([], "")* on error."""
    try:
        src = path.read_text(encoding="utf-8")
    except OSError:
        return [], ""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return [], ""
    visitor = YodaVisitor(src, path)
    visitor.visit(tree)
    return visitor.issues, src

_ANSI: dict[str, str] = {
    "bold":  "\x1b[1m",
    "dim":   "\x1b[2m",
    "red":   "\x1b[31m",
    "green": "\x1b[32m",
    "cyan":  "\x1b[36m",
    "blue":  "\x1b[34m",
    "reset": "\x1b[0m",
}

def _c(text: str, style: str, on: bool) -> str:
    """Wrap *text* in an ANSI escape sequence when *on* is True."""
    return f"{_ANSI.get(style, '')}{text}{_ANSI['reset']}" if on else text

def _snippet(lines: list[str], lineno: int, col: int, ctx: int, color: bool) -> str:
    """Render *ctx* context lines around *lineno* with a caret at *col*."""
    lo = max(1, lineno - ctx)
    hi = min(len(lines), lineno + ctx)
    out: list[str] = []
    for ln in range(lo, hi + 1):
        bar = _c("│", "dim", color)
        num = _c(f"{ln:4d}", "dim", color)
        out.append(f"       {num} {bar} {lines[ln - 1].rstrip()}")
        if ln == lineno:
            caret = " " * min(col, len(lines[ln - 1].rstrip())) + "^"
            out.append(f"            {_c(caret, 'cyan', color)}")
    return "\n".join(out)

def print_pretty(
    issues: list[Issue],
    *,
    color: bool,
    context: int,
    src_cache: dict[Path, str],
) -> None:
    if not issues:
        print(_c("✓ no yoda issues found", "green", color))
        return

    by_file: dict[Path, list[Issue]] = {}
    for issue in issues:
        by_file.setdefault(issue.path, []).append(issue)

    n = len(issues)
    f = len(by_file)
    header = f"{n} issue{'s' if n != 1 else ''} · {f} file{'s' if f != 1 else ''}"
    print(_c(header, "bold", color))

    for path, file_issues in by_file.items():
        print()
        print(_c(f"  {path}", "blue", color))

        loc_w  = max(len(f"{it.lineno}:{it.col}") for it in file_issues)
        expr_w = max(len(it.expr) for it in file_issues)
        lines  = src_cache.get(path, "").splitlines(keepends=True) if context else []

        for it in file_issues:
            loc  = _c(f"{it.lineno}:{it.col}".ljust(loc_w), "dim", color)
            expr = it.expr.ljust(expr_w)

            if it.chained:
                print(f"  {loc}  {expr}  {_c('⚠ chained, no fix', 'red', color)}")
            else:
                repl = _c(it.replacement, "green", color)
                tag  = f"  {_c('[' + it.tag + ']', 'cyan', color)}" if it.tag else ""
                print(f"  {loc}  {expr}  →  {repl}{tag}")

            if context and lines and it.lineno <= len(lines):
                print(_snippet(lines, it.lineno, it.col, context, color))

def print_plain(issues: list[Issue]) -> None:
    for it in issues:
        fix = "chained, no fix" if it.chained else it.replacement
        print(f"{it.path}:{it.lineno}:{it.col}: {it.expr!r}  →  {fix}")

def to_json(issues: list[Issue]) -> str:
    return json.dumps(
        [
            {
                "path": str(i.path),
                "lineno": i.lineno,
                "col": i.col,
                "expr": i.expr,
                "tag": i.tag,
                "replacement": i.replacement,
                "chained": i.chained,
            }
            for i in issues
        ],
        indent=2,
    )

def _pos(lines: list[str], lineno: int, col: int) -> int:
    """Convert a (lineno, col) position to a byte offset in the joined source."""
    return sum(len(line) for line in lines[: lineno - 1]) + col

def _apply_fixes(src: str, fixes: list[tuple[int, int, str]]) -> str:
    """Apply non-overlapping *fixes* (start, end, replacement) to *src*."""
    parts: list[str] = []
    last = 0
    for start, end, repl in sorted(fixes):
        if start < last:
            raise RuntimeError("overlapping fixes")
        parts.append(src[last:start])
        parts.append(repl)
        last = end
    parts.append(src[last:])
    return "".join(parts)

DEFAULT_EXCLUDES: tuple[str, ...] = (".venv", "__pycache__", ".git", "build", "dist")

def collect_py(paths: Iterable[Path], exclude: Iterable[str]) -> list[Path]:
    """Collect all *.py files under *paths*, skipping excluded dirs/patterns."""
    excludes = DEFAULT_EXCLUDES + tuple(exclude)
    candidates: list[Path] = []
    for p in paths:
        if p.is_file() and p.suffix == ".py":
            candidates.append(p)
        elif p.is_dir():
            candidates.extend(p.rglob("*.py"))
    return sorted({
        f for f in candidates
        if not any(f.match(exc) or exc in f.parts for exc in excludes)
    })

def run(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="yodacheck",
        description="Detect and auto-fix Yoda conditions in Python source files.",
    )
    ap.add_argument("paths", nargs="+", help="files or directories to scan")
    ap.add_argument("--fix",     action="store_true", help="apply autofixes (creates .bak backup)")
    ap.add_argument("--exclude", action="append", default=[], metavar="PAT",
                    help="glob pattern or directory name to exclude (repeatable)")
    ap.add_argument("--format",  choices=["pretty", "plain", "json"], default="pretty",
                    help="output format (default: pretty)")
    ap.add_argument("--context", type=int, default=0, metavar="N",
                    help="number of context lines to show per issue")
    ap.add_argument("--color",    dest="color", action="store_true")
    ap.add_argument("--no-color", dest="color", action="store_false")
    ap.set_defaults(color=None)
    args = ap.parse_args(argv)

    color = sys.stdout.isatty() if args.color is None else args.color

    files = collect_py([Path(p) for p in args.paths], args.exclude)
    if not files:
        print("no Python files found")
        return 1

    all_issues: list[Issue] = []
    src_cache: dict[Path, str] = {}
    for f in files:
        issues, src = analyze_file(f)
        all_issues.extend(issues)
        if src:
            src_cache[f] = src

    if args.format == "json":
        print(to_json(all_issues))
    elif args.format == "plain":
        print_plain(all_issues)
    else:
        print_pretty(all_issues, color=color, context=args.context, src_cache=src_cache)

    if not args.fix:
        return 0

    fixes_by_file: dict[Path, list[tuple[int, int, str]]] = {}
    for it in all_issues:
        if it.chained or not it.replacement or it.end_lineno is None or it.end_col is None:
            continue
        lines = src_cache.get(it.path, "").splitlines(keepends=True)
        fixes_by_file.setdefault(it.path, []).append((
            _pos(lines, it.lineno, it.col),
            _pos(lines, it.end_lineno, it.end_col),
            it.replacement,
        ))

    for path, fixes in fixes_by_file.items():
        try:
            new_src = _apply_fixes(src_cache[path], fixes)
            ts = datetime.now().strftime("%Y%m%dT%H%M%SZ")
            bak = path.with_name(path.name + f".bak.{ts}")
            shutil.copy2(path, bak)
            path.write_text(new_src, encoding="utf-8")
            print(f"fixed {path}  ({bak.name})")
        except Exception as e:
            print(f"error fixing {path}: {e}", file=sys.stderr)

    return 0

def main() -> None:
    raise SystemExit(run())

if __name__ == "__main__":
    main()
