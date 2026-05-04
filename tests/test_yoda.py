"""Unit tests for yodacheck."""

import ast
import textwrap
import unittest
from pathlib import Path

from yodacheck import Issue, YodaVisitor, _apply_fixes, _suggest, analyze_file, collect_py


def _issues(src: str) -> list[Issue]:
    """Parse *src* and return all detected issues."""
    path = Path("<test>")
    visitor = YodaVisitor(src, path)
    visitor.visit(ast.parse(src))
    return visitor.issues


class TestSuggest(unittest.TestCase):
    def test_none_eq(self) -> None:
        tag, repl = _suggest("None", "x", ast.Eq())
        self.assertEqual(tag, "is None")
        self.assertEqual(repl, "x is None")

    def test_none_neq(self) -> None:
        tag, repl = _suggest("None", "x", ast.NotEq())
        self.assertEqual(tag, "is not None")
        self.assertEqual(repl, "x is not None")

    def test_true_eq(self) -> None:
        tag, repl = _suggest("True", "flag", ast.Eq())
        self.assertEqual(tag, "bool")
        self.assertEqual(repl, "flag is True")

    def test_false_neq(self) -> None:
        tag, repl = _suggest("False", "flag", ast.NotEq())
        self.assertEqual(tag, "bool")
        self.assertEqual(repl, "flag is not False")

    def test_plain_swap(self) -> None:
        tag, repl = _suggest("5", "x", ast.Eq())
        self.assertEqual(tag, "")
        self.assertEqual(repl, "x == 5")

    def test_inequality_swap(self) -> None:
        tag, repl = _suggest("0", "count", ast.NotEq())
        self.assertEqual(tag, "")
        self.assertEqual(repl, "count != 0")

    def test_gt_swap(self) -> None:
        tag, repl = _suggest("10", "value", ast.Lt())
        self.assertEqual(tag, "")
        self.assertEqual(repl, "value < 10")


class TestDetection(unittest.TestCase):
    def _exprs(self, src: str) -> list[str]:
        return [i.expr for i in _issues(src)]

    def test_numeric_yoda(self) -> None:
        issues = _issues("if 5 == x: pass")
        self.assertEqual(len(issues), 1)
        self.assertFalse(issues[0].chained)
        self.assertEqual(issues[0].replacement, "x == 5")

    def test_none_yoda(self) -> None:
        issues = _issues("if None == obj: pass")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].tag, "is None")
        self.assertEqual(issues[0].replacement, "obj is None")

    def test_bool_yoda(self) -> None:
        issues = _issues("if True == flag: pass")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].tag, "bool")

    def test_normal_not_flagged(self) -> None:
        self.assertEqual(_issues("if x == 5: pass"), [])

    def test_is_none_not_flagged(self) -> None:
        self.assertEqual(_issues("if obj is None: pass"), [])

    def test_chained_flagged_no_fix(self) -> None:
        issues = _issues("if 1 < x < 3: pass")
        self.assertEqual(len(issues), 1)
        self.assertTrue(issues[0].chained)
        self.assertEqual(issues[0].replacement, "")

    def test_membership_not_flagged(self) -> None:
        # `1 in items` — literal on left, but `in` is normal membership syntax
        self.assertEqual(_issues("if 1 in items: pass"), [])

    def test_not_in_not_flagged(self) -> None:
        self.assertEqual(_issues("if 0 not in items: pass"), [])

    def test_string_yoda(self) -> None:
        issues = _issues('if "hello" == s: pass')
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].replacement, 's == "hello"')

    def test_ternary(self) -> None:
        issues = _issues("result = 'ok' if 0 == code else 'fail'")
        self.assertEqual(len(issues), 1)

    def test_combined_conditions(self) -> None:
        issues = _issues("if 42 == answer and 0 != answer: pass")
        self.assertEqual(len(issues), 2)

    def test_nested_in_function(self) -> None:
        src = "def check(a):\n    if 7 == a:\n        return True"
        issues = _issues(src)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].replacement, "a == 7")

    def test_attribute_compare(self) -> None:
        issues = _issues("if 'x' == obj.prop: pass")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].replacement, "obj.prop == 'x'")

    def test_paren_expressions(self) -> None:
        issues = _issues("if (100 == value) or (None == maybe): pass")
        self.assertEqual(len(issues), 2)

    def test_unreadable_file_returns_empty(self) -> None:
        issues, src = analyze_file(Path("/nonexistent/path.py"))
        self.assertEqual(issues, [])
        self.assertEqual(src, "")

    def test_syntax_error_returns_empty(self) -> None:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("def broken(\n")
            tmp = Path(f.name)
        try:
            issues, src = analyze_file(tmp)
            self.assertEqual(issues, [])
        finally:
            tmp.unlink()


class TestApplyFixes(unittest.TestCase):
    def test_single_fix(self) -> None:
        src = "if 5 == x: pass"
        # Replace "5 == x" (chars 3-9) with "x == 5"
        result = _apply_fixes(src, [(3, 9, "x == 5")])
        self.assertEqual(result, "if x == 5: pass")

    def test_multiple_fixes_sorted(self) -> None:
        src = "a = 1; b = 2"
        result = _apply_fixes(src, [(7, 8, "X"), (0, 1, "Y")])
        self.assertEqual(result, "Y = 1; X = 2")

    def test_overlapping_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            _apply_fixes("abc", [(0, 3, "x"), (1, 2, "y")])


class TestCollectPy(unittest.TestCase):
    def test_skips_venv(self) -> None:
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".venv").mkdir()
            (root / ".venv" / "lib.py").write_text("")
            (root / "real.py").write_text("")
            files = collect_py([root], [])
        self.assertEqual([f.name for f in files], ["real.py"])

    def test_skips_pycache(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "cached.py").write_text("")
            (root / "src.py").write_text("")
            files = collect_py([root], [])
        self.assertEqual([f.name for f in files], ["src.py"])

    def test_custom_exclude(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "migrations").mkdir()
            (root / "migrations" / "0001.py").write_text("")
            (root / "app.py").write_text("")
            files = collect_py([root], ["migrations"])
        self.assertEqual([f.name for f in files], ["app.py"])


class TestEndToEnd(unittest.TestCase):
    def test_full_scan_and_fix(self) -> None:
        """Scan a temp file with Yoda issues, apply fixes, verify clean."""
        import tempfile
        src = textwrap.dedent("""\
            x = 5
            if 5 == x:
                print('yoda')
            if None == x:
                print('none yoda')
        """)
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write(src)
            tmp = Path(f.name)
        try:
            from yodacheck import run
            exit_code = run([str(tmp), "--format", "plain"])
            self.assertEqual(exit_code, 0)
            run([str(tmp), "--fix", "--format", "plain"])
            fixed = tmp.read_text()
            self.assertIn("x == 5", fixed)
            self.assertIn("x is None", fixed)
            self.assertNotIn("5 == x", fixed)
            self.assertNotIn("None == x", fixed)
        finally:
            tmp.unlink()
            for bak in tmp.parent.glob(tmp.name + ".bak.*"):
                bak.unlink()


if __name__ == "__main__":
    unittest.main()
