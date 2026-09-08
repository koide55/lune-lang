from __future__ import annotations

import contextlib
import io
import os
import re
import tempfile
import unittest
from pathlib import Path

from lune import __version__
from lune.cli import main
from lune.messages import set_language
from lune.repl import ReplSession

ROOT = Path(__file__).resolve().parent.parent


def setUpModule() -> None:
    # See the note in test_explanations.py: `lune.cli.main` turns an exported
    # LUNE_LANG into a process-global language, which would break the English
    # assertions below for a developer who followed the book's advice.
    os.environ.pop("LUNE_LANG", None)
    set_language("en")


EMPTY_FOLD_SOURCE = """module repro

record Stats:
    count: Int

let empty = Stats(count = 0)

let emptySummary = fold([], empty, fn a x -> a)
let twice = fold([], fold([], empty, fn a x -> a), fn a x -> a)
"""


class VersionTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_language("en")  # `--lang ja` below is process-global

    def run_main(self, argv: list[str]) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(argv)
        return code, out.getvalue()

    def test_version_flag_prints_the_package_version(self) -> None:
        for flag in ("--version", "-V"):
            with self.subTest(flag=flag):
                code, output = self.run_main([flag])
                self.assertEqual(code, 0)
                self.assertEqual(output, f"lune {__version__}\n")

    def test_version_flag_ignores_a_global_lang_option(self) -> None:
        code, output = self.run_main(["--lang", "ja", "--version"])
        self.assertEqual(code, 0)
        self.assertEqual(output, f"lune {__version__}\n")

    def test_version_looks_like_a_release_number(self) -> None:
        # pyproject.toml reads the version from lune/__init__.py through
        # hatchling, so this string is what ends up in the wheel metadata.
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+([ab]\d+|rc\d+)?$")

    def test_pyproject_reads_the_version_from_the_package(self) -> None:
        # Guards against someone putting a literal `version = "..."` back into
        # pyproject.toml, which would let the two numbers drift apart.
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('dynamic = ["version"]', text)
        self.assertIsNone(re.search(r'^version\s*=', text, re.M), "static version in pyproject.toml")
        self.assertIn('path = "lune/__init__.py"', text)


class EvalOperandTypeTests(unittest.TestCase):
    """`--eval` skips the type check; ill-typed operators must still fail as Lune diagnostics (issue #94)."""

    def eval_binding(self, source: str, name: str) -> tuple[int, str, str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.lune"
            path.write_text(source, encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main([str(path), "--eval", name])
        return code, out.getvalue(), err.getvalue()

    def test_eval_reports_operand_type_errors_as_run0006(self) -> None:
        # The issue's headline case: `"%d" % 5` used to print "5" — Python's
        # string formatting operator showing through.
        code, out, err = self.eval_binding('let r = "%d" % 5\n', "r")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("error[RUN0006]: `%` needs Int or Double operands, got String and Int", err)
        self.assertIn("= hint: `lune --check` reports this before the program runs", err)
        self.assertIn("lune explain RUN0006", err)
        self.assertNotIn("Traceback", err)

    def test_eval_does_not_leak_python_exceptions(self) -> None:
        code, out, err = self.eval_binding('let r = "a" - 1\n', "r")
        self.assertEqual(code, 1)
        self.assertIn("error[RUN0006]", err)
        self.assertNotIn("unsupported operand type", err)


class EvalDisplayTests(unittest.TestCase):
    def eval_binding(self, source: str, name: str) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.lune"
            path.write_text(source, encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main([str(path), "--eval", name])
        return code, out.getvalue()

    def test_eval_prints_record_returned_by_fold_over_empty_list(self) -> None:
        # fold over [] hands back the initial value untouched, so the binding
        # is a thunk whose value is *another* thunk (the one bound to `empty`).
        # Display forces what it needs (VALUE_DISPLAY_SPEC.md §5), which means
        # forcing the whole chain to WHNF -- stopping after one step used to
        # print the Python repr of the inner thunk.
        code, output = self.eval_binding(EMPTY_FOLD_SOURCE, "emptySummary")
        self.assertEqual(code, 0)
        self.assertEqual(output, "{ count = 0 }\n")

    def test_eval_prints_value_behind_a_longer_thunk_chain(self) -> None:
        code, output = self.eval_binding(EMPTY_FOLD_SOURCE, "twice")
        self.assertEqual(code, 0)
        self.assertEqual(output, "{ count = 0 }\n")

    def test_eval_never_prints_internal_representations(self) -> None:
        # VALUE_DISPLAY_SPEC.md §4: display shows Lune surface syntax, never
        # the evaluator's own objects.
        _, output = self.eval_binding(EMPTY_FOLD_SOURCE, "emptySummary")
        for internal in ("Thunk(", "LazyValue(", "NameExpr(", "<lune."):
            self.assertNotIn(internal, output)

    def test_eval_and_repl_render_the_same_value_identically(self) -> None:
        # VALUE_DISPLAY_SPEC.md §1: the REPL and CLI displays agree. The REPL
        # forced the binding once before formatting it, so it survived the
        # shallow-force bug that `--eval` exposed.
        _, output = self.eval_binding(EMPTY_FOLD_SOURCE, "emptySummary")
        session = ReplSession()
        session.submit("record Stats:\n    count: Int\n")
        session.submit("let empty = Stats(count = 0)\n")
        result = session.submit("fold([], empty, fn a x -> a)\n")
        self.assertEqual(result.message, f"{output.rstrip()} : Stats")


if __name__ == "__main__":
    unittest.main()
