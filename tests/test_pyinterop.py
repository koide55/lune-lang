"""Python interop: `import python.X` and the `Py` type (documents/PYTHON_INTEROP_SPEC.md).

Everything except `NumPyTests` uses standard-library modules, so CI needs no
third-party package; the NumPy tests skip themselves when NumPy is absent.
"""

from __future__ import annotations

import io
import importlib.util
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from lune import pyinterop
from lune.cli import main
from lune.diagnostics import DiagnosticError
from lune.evaluator import LuneRuntimeError, eval_source, force_value, format_value
from lune.messages import set_language
from lune.module_loader import ModuleLoadError, check_file, eval_file
from lune.repl import ReplSession
from lune.typechecker import ANY, INT, PY, LuneTypeError, Type, check_source


def setUpModule() -> None:
    os.environ.pop("LUNE_LANG", None)
    set_language("en")


def tearDownModule() -> None:
    pyinterop.set_enabled(True)
    pyinterop.set_show_traceback(False)


def evaluate(source: str, name: str):
    return force_value(eval_source(source).lookup_raw(name))


def shown(source: str, name: str) -> str:
    return format_value(eval_source(source).lookup_raw(name))


def type_error(source: str) -> DiagnosticError:
    try:
        check_source(source)
    except LuneTypeError as exc:
        return exc
    raise AssertionError("expected a type error")


def runtime_error(source: str, name: str) -> LuneRuntimeError:
    try:
        evaluate(source, name)
    except LuneRuntimeError as exc:
        return exc
    raise AssertionError("expected a runtime error")


class PyTypeTests(unittest.TestCase):
    def test_python_import_binds_py_and_java_stays_any(self) -> None:
        env = check_source("import python.math\nimport java.time.LocalDate\n")
        self.assertEqual(env.lookup_value("math"), PY)
        self.assertEqual(env.lookup_value("LocalDate"), ANY)

    def test_alias_names_the_binding(self) -> None:
        env = check_source("import python.fractions as fr\n")
        self.assertEqual(env.lookup_value("fr"), PY)

    def test_members_calls_indexes_and_operators_are_py(self) -> None:
        env = check_source(
            """
import python.math

let a = math.pi
let b = math.sqrt(2)
let c = toPy([1, 2])[0]
let d = math.pi * 2
let e = -math.pi
let f = math.pi > 3
"""
        )
        for name in "abcdef":
            self.assertEqual(env.lookup_value(name), PY, name)

    def test_conversions_give_lune_types(self) -> None:
        env = check_source(
            """
import python.math

let a = asInt(math.floor(2.5))
let b = asList(toPy([1]))
let c = asNullable(math.pi)
"""
        )
        self.assertEqual(env.lookup_value("a"), INT)
        self.assertEqual(env.lookup_value("b"), Type("List", (PY,)))
        self.assertEqual(env.lookup_value("c"), Type("Nullable", (PY,)))

    def test_py_is_not_assignable_to_a_lune_type(self) -> None:
        exc = type_error("import python.math\n\nlet n: Int = math.floor(2.5)\n")
        self.assertEqual(exc.diagnostic.code, "TYP0003")
        self.assertIn("expected Int, got Py", exc.diagnostic.message)
        self.assertIn("use `asInt(...)` to convert a Python value to Int", exc.diagnostic.hints)

    def test_py_condition_is_rejected_with_array_hints(self) -> None:
        exc = type_error("import python.math\n\nlet c = if math.pi > 3 then 1 else 2\n")
        self.assertEqual(exc.diagnostic.code, "TYP0003")
        hints = " ".join(exc.diagnostic.hints)
        self.assertIn("asBool(...)", hints)
        self.assertIn("np.all(...)", hints)

    def test_lune_value_where_py_is_expected_suggests_to_py(self) -> None:
        exc = type_error("def f(x: Py): Py = x\n\nlet y = f(1)\n")
        self.assertIn("a Lune value becomes a Py value with `toPy(...)`", exc.diagnostic.hints)

    def test_unconvertible_arguments_are_rejected(self) -> None:
        for argument in ("Some(1)", "fn (x: Int) -> x"):
            with self.subTest(argument=argument):
                exc = type_error(f"import python.math\n\nlet y = math.sqrt({argument})\n")
                self.assertEqual(exc.diagnostic.code, "TYP0003")
                self.assertIn("cannot be passed to Python", exc.diagnostic.message)

    def test_to_py_checks_its_argument(self) -> None:
        check_source("let a = toPy([(1, \"x\"), (2, \"y\")])\n")
        exc = type_error("let a = toPy(Some(1))\n")
        self.assertIn("Option[Int] cannot be passed to Python", exc.diagnostic.message)

    def test_index_on_a_lune_list_is_rejected(self) -> None:
        exc = type_error("let a = [1, 2][0]\n")
        self.assertEqual(exc.diagnostic.code, "TYP0003")
        self.assertIn("only on Python values", exc.diagnostic.message)

    def test_named_arguments_only_for_python_calls(self) -> None:
        check_source("import python.builtins as py\n\nlet n = py.int(\"ff\", base = 16)\n")
        exc = type_error("def f(x: Int): Int = x\n\nlet y = f(x = 1)\n")
        self.assertEqual(exc.diagnostic.code, "TYP0012")

    def test_for_over_py_binds_py_items(self) -> None:
        check_source(
            """
import python.math

def main(): Unit =
    for x in toPy([1, 2]):
        println(asInt(x) + 1)
"""
        )


class PyEvalTests(unittest.TestCase):
    def test_call_and_convert(self) -> None:
        self.assertEqual(evaluate("import python.math\n\nlet r = asDouble(math.sqrt(16))\n", "r"), 4.0)

    def test_keyword_arguments(self) -> None:
        source = """
import python.builtins as py

let n = asInt(py.int("ff", base = 16))
let s = map(asList(py.sorted([3, 1, 2], reverse = true)), asInt)
"""
        self.assertEqual(evaluate(source, "n"), 255)
        self.assertEqual(shown(source, "s"), "(3 2 1)")

    def test_operators_follow_python(self) -> None:
        source = """
import python.fractions as fr

let half = fr.Fraction(1, 3) + fr.Fraction(1, 6)
let same = asBool(half == fr.Fraction(2, 4))
let text = pyStr(half)
"""
        self.assertIs(evaluate(source, "same"), True)
        self.assertEqual(evaluate(source, "text"), "1/2")

    def test_index_and_slice(self) -> None:
        source = """
let xs = toPy([10, 20, 30, 40])
let second = asInt(xs[1])
let middle = map(asList(xs[pySlice(1, 3)]), asInt)
let tail = map(asList(xs[pySlice(2, null)]), asInt)
"""
        self.assertEqual(evaluate(source, "second"), 20)
        self.assertEqual(shown(source, "middle"), "(20 30)")
        self.assertEqual(shown(source, "tail"), "(30 40)")

    def test_as_list_is_lazy_over_an_infinite_iterator(self) -> None:
        source = """
import python.itertools as it

let evens = take(map(asList(it.count(0, 2)), asInt), 4)
"""
        self.assertEqual(shown(source, "evens"), "(0 2 4 6)")

    def test_as_list_memoises_a_stateful_iterator(self) -> None:
        source = """
import python.builtins as py

let xs = map(asList(py.iter([1, 2, 3])), asInt)
let twice = (fold(xs, 0, fn acc x -> acc + x), fold(xs, 0, fn acc x -> acc + x))
"""
        self.assertEqual(shown(source, "twice"), "(6, 6)")

    def test_for_walks_a_python_iterable(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            evaluate("let run = for x in toPy([1, 2]):\n    println(asInt(x) * 10)\n", "run")
        self.assertEqual(out.getvalue(), "10\n20\n")

    def test_as_nullable_turns_none_into_null(self) -> None:
        source = "let a = asNullable(toPy(()))\nlet b = asNullable(toPy(1)) ?? toPy(0)\n"
        self.assertIsNone(evaluate(source, "a"))
        self.assertEqual(shown(source, "b"), "1")

    def test_display_uses_python_str(self) -> None:
        self.assertEqual(shown("import python.fractions as fr\n\nlet f = fr.Fraction(1, 2)\n", "f"), "1/2")

    def test_import_waits_until_first_use(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "lune_probe_module.py").write_text("VALUE = 7\n", encoding="utf-8")
            sys.path.insert(0, tmp)
            try:
                env = eval_source("import python.lune_probe_module as probe\n\nlet v = asInt(probe.VALUE)\n")
                self.assertNotIn("lune_probe_module", sys.modules)
                self.assertEqual(force_value(env.lookup_raw("v")), 7)
                self.assertIn("lune_probe_module", sys.modules)
            finally:
                sys.path.remove(tmp)
                sys.modules.pop("lune_probe_module", None)

    def test_python_exception_is_run0007(self) -> None:
        exc = runtime_error("import python.builtins as py\n\nlet r = py.int(\"x\")\n", "r")
        self.assertEqual(exc.diagnostic.code, "RUN0007")
        self.assertEqual(exc.diagnostic.message, "Python raised ValueError: invalid literal for int() with base 10: 'x'")
        self.assertIn("--py-traceback", " ".join(exc.diagnostic.hints))

    def test_traceback_on_request(self) -> None:
        pyinterop.set_show_traceback(True)
        try:
            exc = runtime_error("import python.math\n\nlet r = math.sqrt(-1)\n", "r")
        finally:
            pyinterop.set_show_traceback(False)
        self.assertTrue(any(note.startswith("Traceback") for note in exc.diagnostic.notes))
        self.assertEqual(exc.diagnostic.hints, [])

    def test_attribute_typo_suggests_the_closest_name(self) -> None:
        exc = runtime_error("import python.math\n\nlet r = math.sqr(4)\n", "r")
        self.assertEqual(exc.diagnostic.code, "RUN0007")
        self.assertIn("did you mean `sqrt`?", exc.diagnostic.hints)

    def test_failed_conversion_is_run0006(self) -> None:
        exc = runtime_error("import python.math\n\nlet n = asInt(math.pi)\n", "n")
        self.assertEqual(exc.diagnostic.code, "RUN0006")
        self.assertIn("asInt: a Python float cannot be converted to Int", exc.diagnostic.message)

    def test_as_bool_never_uses_truthiness(self) -> None:
        exc = runtime_error("let b = asBool(toPy(1))\n", "b")
        self.assertIn("cannot be converted to Bool", exc.diagnostic.message)

    def test_eval_without_check_still_guards_the_border(self) -> None:
        # `--eval` skips the type checker; the evaluator must refuse on its own.
        cases = {
            "let y = toPy(1) + Some(1)\n": "Some cannot be passed to Python",
            # Python may call `Some`; it is the result that cannot come back.
            "let y = toPy(Some)(1)\n": "a Lune value of type Some cannot be passed to Python",
            "let y = asInt(1)\n": "asInt expects a Py value, got Int",
            "let y = [1, 2][0]\n": "only on Python values",
            "let y = if toPy(true) then 1 else 2\n": "expected Bool, got Py",
        }
        for source, message in cases.items():
            with self.subTest(source=source):
                self.assertIn(message, runtime_error(source, "y").diagnostic.message)

    def test_nested_equality_needs_a_single_truth_value(self) -> None:
        self.assertIs(evaluate("let e = [toPy(1)] == [toPy(1)]\n", "e"), True)

    def test_attribute_named_like_a_keyword(self) -> None:
        source = """
import python.re

let m = re.match("(\\d+)-(\\d+)", "12-34")
let first = asString(m.group(1))
let missing = asNullable(re.match("x", "y"))
"""
        self.assertEqual(evaluate(source, "first"), "12")
        self.assertIsNone(evaluate(source, "missing"))

    def test_side_effects_follow_forcing_order(self) -> None:
        # Spec section 8.2: `y` is used first, so it receives the first draw.
        # A statement (`random.seed(42)`) runs in place; a `let` runs when used.
        source = """
import python.random

def draws(): (Double, Double) =
    random.seed(42)
    let x = asDouble(random.random())
    let y = asDouble(random.random())
    seq y (x, y)

let pair = draws()
"""
        import random

        random.seed(42)
        first, second = random.random(), random.random()
        self.assertEqual(shown(source, "pair"), f"({second}, {first})")
        # `strict let` restores the written order.
        self.assertEqual(shown(source.replace("    let", "    strict let"), "pair"), f"({first}, {second})")

    def test_mutating_a_converted_list_leaves_the_lune_list_alone(self) -> None:
        # Spec section 8.3: a Lune list is copied into a new Python list.
        source = """
import python.random

let xs = [3, 1, 2]
let shuffled = random.shuffle(xs)
let after = (shuffled, xs)
"""
        self.assertEqual(shown(source, "after"), "(None, (3 1 2))")

    def test_duplicate_keyword_is_reported(self) -> None:
        exc = runtime_error("import python.builtins as py\n\nlet n = py.int(\"1\", base = 2, base = 3)\n", "n")
        self.assertIn("`base` is given more than once", exc.diagnostic.message)


class PyCallbackTests(unittest.TestCase):
    """Lune functions handed to Python (PYTHON_INTEROP_SPEC.md section 5.5)."""

    SOURCE = """
import python.builtins as py
import python.functools as ft
import python.collections as col

def byLast(x: Py): Int = asInt(x) % 10

let xs = [31, 12, 23, 44]
let lambdaKey = map(asList(py.sorted(xs, key = fn x -> asInt(x) % 10)), asInt)
let defKey = map(asList(py.sorted(xs, key = byLast, reverse = true)), asInt)
let builtinKey = map(asList(py.sorted([toPy(2.5), toPy(1)], key = asDouble)), pyStr)
let mapped = map(asList(py.map(fn x -> asInt(x) * 2, xs)), asInt)
let folded = asInt(ft.reduce(fn acc x -> asInt(acc) + asInt(x), xs, 0))
let factory = asInt(col.defaultdict(fn -> 0)["missing"])
"""

    def test_lambdas_defs_and_builtins_are_called_by_python(self) -> None:
        check_source(self.SOURCE)
        self.assertEqual(shown(self.SOURCE, "lambdaKey"), "(31 12 23 44)")
        self.assertEqual(shown(self.SOURCE, "defKey"), "(44 23 12 31)")
        self.assertEqual(shown(self.SOURCE, "builtinKey"), '("1" "2.5")')
        self.assertEqual(shown(self.SOURCE, "mapped"), "(62 24 46 88)")
        self.assertEqual(evaluate(self.SOURCE, "folded"), 110)
        self.assertEqual(evaluate(self.SOURCE, "factory"), 0)

    def test_an_unannotated_lambda_in_a_python_call_takes_py(self) -> None:
        # No TYP0010 warning: Python is what calls it, and Python passes Py.
        env = check_source("import python.builtins as py\n\nlet a = py.map(fn x -> asInt(x), [1])\n")
        self.assertEqual(env.warnings, [])

    def test_a_function_taking_lune_types_is_rejected(self) -> None:
        for argument in ("fn (x: Int) -> x", "inc"):
            with self.subTest(argument=argument):
                exc = type_error(
                    f"import python.builtins as py\n\ndef inc(x: Int): Int = x + 1\n\nlet a = py.sorted([1], key = {argument})\n"
                )
                self.assertIn("Int -> Int cannot be passed to Python", exc.diagnostic.message)
                self.assertIn("declare its parameters as Py", exc.diagnostic.hints[0])

    def test_a_function_returning_a_lune_only_value_is_rejected(self) -> None:
        exc = type_error("import python.builtins as py\n\nlet a = py.map(fn x -> Some(x), [1])\n")
        self.assertEqual(exc.diagnostic.hints[0], "the function returns Option[Py], which Python cannot receive")

    def test_wrong_argument_count_is_a_python_type_error(self) -> None:
        exc = runtime_error("import python.functools as ft\n\nlet a = ft.reduce(fn x -> x, [1, 2, 3])\n", "a")
        self.assertEqual(exc.diagnostic.code, "RUN0007")
        self.assertIn("Lune function `<lambda>` takes 1 argument, got 2", exc.diagnostic.message)

    def test_a_lune_error_inside_passes_through_python(self) -> None:
        exc = runtime_error("import python.builtins as py\n\nlet a = py.sorted([1, 2], key = fn x -> crash())\n", "a")
        self.assertEqual(exc.diagnostic.code, "RUN0006")

    def test_keyword_arguments_from_python_are_refused(self) -> None:
        source = "import python.functools as ft\n\nlet a = ft.partial(fn x -> x, x = 1)()\n"
        exc = runtime_error(source, "a")
        self.assertIn("takes no keyword arguments", exc.diagnostic.message)


class PyImportTests(unittest.TestCase):
    def _write(self, root: Path, source: str) -> Path:
        path = root / "main.lune"
        path.write_text(source, encoding="utf-8")
        return path

    def test_check_and_eval_through_the_loader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            main_file = self._write(Path(tmp), "module main\n\nimport python.math\n\nlet r = asInt(math.floor(2.5))\n")
            self.assertEqual(check_file(main_file).lookup_value("r"), INT)
            self.assertEqual(force_value(eval_file(main_file).lookup_raw("r")), 2)

    def test_missing_module_is_mod0004_at_the_import(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            main_file = self._write(Path(tmp), "module main\n\nimport python.lune_no_such_module as q\n")
            with self.assertRaises(ModuleLoadError) as caught:
                check_file(main_file)
        diagnostic = caught.exception.diagnostic
        self.assertEqual(diagnostic.code, "MOD0004")
        self.assertEqual(diagnostic.primary.span.start_line, 3)
        self.assertIn(f"{sys.executable} -m pip install lune_no_such_module", diagnostic.hints[0])

    def test_disabled_python_is_mod0004(self) -> None:
        pyinterop.set_enabled(False)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                main_file = self._write(Path(tmp), "module main\n\nimport python.math\n")
                with self.assertRaises(ModuleLoadError) as caught:
                    check_file(main_file)
            self.assertIn("Python imports are disabled", caught.exception.diagnostic.message)
            # A program that never went through the loader is refused when it uses the module.
            exc = runtime_error("import python.math\n\nlet r = math.pi\n", "r")
            self.assertEqual(exc.diagnostic.code, "MOD0004")
        finally:
            pyinterop.set_enabled(True)

    def test_repl_binds_python_imports(self) -> None:
        session = ReplSession()
        self.assertEqual(session.submit("import python.math").message, "ok")
        self.assertEqual(session.submit("asInt(math.floor(7.9))").message, "7 : Int")
        self.assertEqual(session.submit("math.floor(7.9)").message, "7 : Py")


class PyCliTests(unittest.TestCase):
    def tearDown(self) -> None:
        # `main` sets both switches process-wide; the last call must not
        # decide them for the tests that run after this class.
        pyinterop.set_enabled(True)
        pyinterop.set_show_traceback(False)

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_no_python_flag_and_reset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "main.lune"
            path.write_text("module main\n\nimport python.math\n\nlet r = asInt(math.floor(2.5))\n", encoding="utf-8")
            code, _, err = self._run("--no-python", "--check", str(path))
            self.assertEqual(code, 1)
            self.assertIn("MOD0004", err)
            # The switch is per invocation: the next run has Python again.
            code, out, _ = self._run("--eval", "r", str(path))
            self.assertEqual((code, out), (0, "2\n"))

    def test_py_traceback_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "main.lune"
            path.write_text("module main\n\nimport python.math\n\nlet r = math.sqrt(-1)\n", encoding="utf-8")
            _, _, plain = self._run("--eval", "r", str(path))
            _, _, full = self._run("--py-traceback", "--eval", "r", str(path))
        self.assertIn("error[RUN0007]", plain)
        self.assertNotIn("Traceback", plain)
        self.assertIn("Traceback", full)


@unittest.skipUnless(importlib.util.find_spec("numpy"), "NumPy is not installed")
class NumPyTests(unittest.TestCase):
    SOURCE = """
import python.numpy as np

let a = np.array([1.5, 2.0, 3.5, 4.0])
let centered = a - np.mean(a)
let total = asDouble(np.sum(centered * centered))
let m = np.arange(6).reshape(2, 3)
let col = np.sum(m, axis = 0)
let corner = asInt(m[1, 2])
let column = m[pySlice(null, null), 1]
let mask = a > 2.0
let anyBig = asBool(np.any(mask))
let items = map(asList(col), asInt)
"""

    def test_numpy_program(self) -> None:
        self.assertEqual(evaluate(self.SOURCE, "total"), 4.25)
        self.assertEqual(shown(self.SOURCE, "col"), "[3 5 7]")
        self.assertEqual(evaluate(self.SOURCE, "corner"), 5)
        self.assertEqual(shown(self.SOURCE, "column"), "[1 4]")
        self.assertEqual(shown(self.SOURCE, "mask"), "[False False  True  True]")
        self.assertIs(evaluate(self.SOURCE, "anyBig"), True)
        self.assertEqual(shown(self.SOURCE, "items"), "(3 5 7)")

    def test_numpy_scalars_convert(self) -> None:
        source = "import python.numpy as np\n\nlet i = asInt(np.int64(3))\nlet b = asBool(np.bool_(true))\n"
        self.assertEqual(evaluate(source, "i"), 3)
        self.assertIs(evaluate(source, "b"), True)

    def test_broadcast_error_is_run0007(self) -> None:
        exc = runtime_error("import python.numpy as np\n\nlet b = np.array([1, 2, 3]) + np.array([1, 2])\n", "b")
        self.assertEqual(exc.diagnostic.code, "RUN0007")
        self.assertIn("could not be broadcast", exc.diagnostic.message)
        self.assertFalse(exc.diagnostic.message.endswith(" "))

    def test_array_equality_inside_a_list_is_refused(self) -> None:
        exc = runtime_error("import python.numpy as np\n\nlet a = np.array([1, 2])\nlet e = [a] == [a]\n", "e")
        self.assertIn("np.array_equal", " ".join(exc.diagnostic.hints))

    def test_numpy_calls_lune_functions(self) -> None:
        source = """
import python.numpy as np

let doubled = np.vectorize(fn x -> asDouble(x) * 2.0)(np.arange(3))
let table = np.fromfunction(fn i j -> i * 10 + j, (2, 3))
"""
        self.assertEqual(shown(source, "doubled"), "[0. 2. 4.]")
        self.assertEqual(shown(source, "table"), "[[ 0.  1.  2.]\n [10. 11. 12.]]")

    def test_as_bool_on_an_array_is_refused(self) -> None:
        exc = runtime_error("import python.numpy as np\n\nlet b = asBool(np.array([true, false]))\n", "b")
        self.assertIn("ndarray cannot be converted to Bool", exc.diagnostic.message)


if __name__ == "__main__":
    unittest.main()
