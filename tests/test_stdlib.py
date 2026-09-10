from __future__ import annotations

import contextlib
import io
import pathlib
import tracemalloc
import unittest

from lune.evaluator import (
    DataValue,
    LazyValue,
    LuneRuntimeError,
    Thunk,
    ThunkState,
    eval_source,
    force_value,
    format_value,
)
from lune.typechecker import INT, STRING, Type, check_source


ROOT = pathlib.Path(__file__).resolve().parents[1]


class StdlibTests(unittest.TestCase):
    def value_of(self, source: str, name: str):
        env = eval_source(source)
        return force_value(env.lookup_raw(name))

    def assert_data(self, value, constructor: str) -> DataValue:
        value = force_value(value)
        self.assertIsInstance(value, DataValue)
        self.assertEqual(value.constructor, constructor)
        return value

    def list_to_py(self, value) -> list[object]:
        result = []
        current = force_value(value)
        while True:
            current = force_value(current)
            if current.constructor == "Nil":
                return result
            self.assertEqual(current.constructor, "Cons")
            result.append(force_value(current.fields[0]))
            current = current.fields[1]

    def test_option_is_available_without_user_definition(self) -> None:
        source = """
let someValue = getOrElse(Some(42), 0)
let noneValue = getOrElse(None, 7)
"""
        self.assertEqual(self.value_of(source, "someValue"), 42)
        self.assertEqual(self.value_of(source, "noneValue"), 7)

    def test_option_map_is_lazy_for_none(self) -> None:
        source = """
let answer = optionMap(None, fn x: Int -> crash())
"""
        value = self.value_of(source, "answer")
        self.assert_data(value, "None")

    def test_result_helpers(self) -> None:
        source = """
let ok = unwrapOr(Ok(42), 0)
let err = unwrapOr(Err("nope"), 7)
let mapped = resultMap(Ok(20), fn x: Int -> x + 22)
"""
        env = eval_source(source)
        self.assertEqual(force_value(env.lookup_raw("ok")), 42)
        self.assertEqual(force_value(env.lookup_raw("err")), 7)
        mapped = self.assert_data(force_value(env.lookup_raw("mapped")), "Ok")
        self.assertEqual(force_value(mapped.fields[0]), 42)

    def test_list_helpers(self) -> None:
        source = """
let numbers = range(1, 5)
let doubled = map(numbers, fn x: Int -> x * 2)
let evens = filter(doubled, fn x: Int -> x % 4 == 0)
let total = fold(numbers, 0, fn acc: Int x: Int -> acc + x)
let first = head(numbers)
let rest = tail(numbers)
let firstTwo = take(numbers, 2)
let afterTwo = drop(numbers, 2)
let tooMany = take(numbers, 99)
let noneLeft = drop(numbers, 99)
let size = length(numbers)
"""
        env = eval_source(source)
        self.assertEqual(self.list_to_py(env.lookup_raw("numbers")), [1, 2, 3, 4])
        self.assertEqual(self.list_to_py(env.lookup_raw("doubled")), [2, 4, 6, 8])
        self.assertEqual(self.list_to_py(env.lookup_raw("evens")), [4, 8])
        self.assertEqual(force_value(env.lookup_raw("total")), 10)
        first = self.assert_data(force_value(env.lookup_raw("first")), "Some")
        self.assertEqual(force_value(first.fields[0]), 1)
        rest = self.assert_data(force_value(env.lookup_raw("rest")), "Some")
        self.assertEqual(self.list_to_py(rest.fields[0]), [2, 3, 4])
        self.assertEqual(self.list_to_py(env.lookup_raw("firstTwo")), [1, 2])
        self.assertEqual(self.list_to_py(env.lookup_raw("afterTwo")), [3, 4])
        self.assertEqual(self.list_to_py(env.lookup_raw("tooMany")), [1, 2, 3, 4])
        self.assertEqual(self.list_to_py(env.lookup_raw("noneLeft")), [])
        self.assertEqual(force_value(env.lookup_raw("size")), 4)

    def test_fold_over_empty_list_displays_the_initial_value(self) -> None:
        # fold over [] returns the initial value untouched, so the binding is a
        # thunk wrapping another thunk. format_value must force that chain on
        # its own: the callers that pre-force (value_of, the REPL) hide the bug
        # that CLI `--eval` -- which formats the raw binding -- ran into.
        source = """
record Stats:
    count: Int
let empty = Stats(count = 0)
let emptySummary = fold([], empty, fn a x -> a)
"""
        env = eval_source(source)
        self.assertEqual(format_value(env.lookup_raw("emptySummary")), "{ count = 0 }")

    def test_take_zero_does_not_force_list(self) -> None:
        source = """
let answer = take(crash(), 0)
"""
        self.assertEqual(self.list_to_py(self.value_of(source, "answer")), [])

    def test_take_preserves_lazy_tail(self) -> None:
        source = """
let answer = head(take([1, crash()], 1))
"""
        self.assertEqual(format_value(self.value_of(source, "answer")), "Some(1)")

    def test_core_helpers(self) -> None:
        source = """
let text = show(Some(1))
let listText = show(range(1, 3))
let stringText = show("Ada")
let same = id(42)
let kept = const(1, crash())
let flipped = not(false)
"""
        env = eval_source(source)
        self.assertEqual(force_value(env.lookup_raw("text")), "Some(1)")
        self.assertEqual(force_value(env.lookup_raw("listText")), "(1 2)")
        self.assertEqual(force_value(env.lookup_raw("stringText")), '"Ada"')
        self.assertEqual(force_value(env.lookup_raw("same")), 42)
        self.assertEqual(force_value(env.lookup_raw("kept")), 1)
        self.assertEqual(force_value(env.lookup_raw("flipped")), True)

    def test_show_function_values_use_short_form(self) -> None:
        source = """
def greet(name: String): String =
    "hello, " + name

let named = show(greet)
let partial = show(greet())
let anonymous = show(fn x -> x)
let builtin = show(println)
let constructor = show(Some)
"""
        env = eval_source(source)
        self.assertEqual(force_value(env.lookup_raw("named")), "<fn greet>")
        self.assertEqual(force_value(env.lookup_raw("partial")), "<fn greet>")
        self.assertEqual(force_value(env.lookup_raw("anonymous")), "<fn>")
        self.assertEqual(force_value(env.lookup_raw("builtin")), "<fn println>")
        self.assertEqual(force_value(env.lookup_raw("constructor")), "<fn Some>")

    def test_println_prints_function_values_with_short_form(self) -> None:
        source = """
def greet(name: String): String =
    "hello, " + name

let main = println(greet(), fn x -> x, println)
"""
        env = eval_source(source)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            force_value(env.lookup_raw("main"))
        self.assertEqual(buffer.getvalue(), "<fn greet> <fn> <fn println>\n")

    def test_stdlib_sample_typechecks(self) -> None:
        env = check_source((ROOT / "samples" / "stdlib.lune").read_text(encoding="utf-8"))
        self.assertEqual(env.lookup_value("optionValue"), INT)
        self.assertEqual(env.lookup_value("noneValue"), INT)
        self.assertEqual(env.lookup_value("numbers"), Type("List", (INT,)))
        self.assertEqual(env.lookup_value("doubled"), Type("List", (INT,)))
        self.assertEqual(env.lookup_value("firstTwo"), Type("List", (INT,)))
        self.assertEqual(env.lookup_value("afterTwo"), Type("List", (INT,)))
        self.assertEqual(env.lookup_value("total"), INT)
        self.assertEqual(env.lookup_value("size"), INT)
        self.assertEqual(env.lookup_value("shown"), STRING)

    def test_list_tools_sample(self) -> None:
        source = (ROOT / "samples" / "list_tools.lune").read_text(encoding="utf-8")
        type_env = check_source(source)
        self.assertEqual(type_env.lookup_value("doubled"), Type("List", (INT,)))
        self.assertEqual(type_env.lookup_value("firstThree"), Type("List", (INT,)))
        self.assertEqual(type_env.lookup_value("afterThree"), Type("List", (INT,)))
        env = eval_source(source)
        self.assertEqual(format_value(env.lookup_raw("doubled")), "(2 4 6 8 10 12)")
        self.assertEqual(format_value(env.lookup_raw("firstThree")), "(1 2 3)")
        self.assertEqual(format_value(env.lookup_raw("afterThree")), "(4 5 6)")
        self.assertEqual(format_value(env.lookup_raw("adultNames")), '("Grace")')
        self.assertEqual(force_value(env.lookup_raw("totalAge")), 176)
        self.assertEqual(format_value(env.lookup_raw("lazySlice")), "(1)")

    # --- infinite / lazy streams ---

    def test_naturals_from_take(self) -> None:
        env = eval_source("let xs = take(naturalsFrom(1), 5)\n")
        self.assertEqual(self.list_to_py(env.lookup_raw("xs")), [1, 2, 3, 4, 5])

    def test_iterate_builds_stream(self) -> None:
        source = "def double(n: Int): Int =\n    n * 2\nlet xs = take(iterate(double, 1), 5)\n"
        self.assertEqual(self.list_to_py(self.value_of(source, "xs")), [1, 2, 4, 8, 16])

    def test_repeat_is_infinite(self) -> None:
        self.assertEqual(self.list_to_py(self.value_of("let xs = take(repeat(7), 3)\n", "xs")), [7, 7, 7])

    def test_map_and_filter_on_infinite_stream(self) -> None:
        evens = "let e = take(filter(naturalsFrom(1), fn x: Int -> x % 2 == 0), 4)\n"
        self.assertEqual(self.list_to_py(self.value_of(evens, "e")), [2, 4, 6, 8])
        mapped = "def double(n: Int): Int =\n    n * 2\nlet m = take(map(naturalsFrom(1), double), 4)\n"
        self.assertEqual(self.list_to_py(self.value_of(mapped, "m")), [2, 4, 6, 8])

    def test_head_of_infinite_stream_terminates(self) -> None:
        first = self.assert_data(self.value_of("let f = head(naturalsFrom(10))\n", "f"), "Some")
        self.assertEqual(force_value(first.fields[0]), 10)

    def test_stream_builtins_typecheck(self) -> None:
        env = check_source(
            """
def double(n: Int): Int =
    n * 2
let a: List[Int] = take(iterate(double, 1), 3)
let b: List[Int] = take(naturalsFrom(1), 3)
let c: List[Int] = take(repeat(5), 3)
"""
        )
        self.assertEqual(env.lookup_value("a"), Type("List", (INT,)))
        self.assertEqual(env.lookup_value("b"), Type("List", (INT,)))
        self.assertEqual(env.lookup_value("c"), Type("List", (INT,)))

    # --- stream combinators ---

    def test_take_while(self) -> None:
        src = "def lt5(n: Int): Bool =\n    n < 5\nlet xs = takeWhile(naturalsFrom(1), lt5)\n"
        self.assertEqual(self.list_to_py(self.value_of(src, "xs")), [1, 2, 3, 4])

    def test_drop_while(self) -> None:
        src = "def lt5(n: Int): Bool =\n    n < 5\nlet xs = take(dropWhile(naturalsFrom(1), lt5), 3)\n"
        self.assertEqual(self.list_to_py(self.value_of(src, "xs")), [5, 6, 7])

    def test_take_after_drop_on_infinite_stream(self) -> None:
        # drop returns the (still lazy) tail of the stream; take must force it
        # to WHNF instead of reading fields off the unevaluated LazyValue.
        src = "let xs = take(drop(naturalsFrom(1), 1), 3)\n"
        self.assertEqual(self.list_to_py(self.value_of(src, "xs")), [2, 3, 4])

    def test_head_after_drop_on_infinite_stream(self) -> None:
        src = "let x = head(drop(naturalsFrom(1), 1))\n"
        self.assertEqual(format_value(self.value_of(src, "x")), "Some(2)")

    def test_take_after_drop_on_finite_list(self) -> None:
        src = "let xs = take(drop([1, 2, 3, 4, 5], 2), 2)\n"
        self.assertEqual(self.list_to_py(self.value_of(src, "xs")), [3, 4])
        src = "let xs = take(drop(range(1, 10), 2), 2)\n"
        self.assertEqual(self.list_to_py(self.value_of(src, "xs")), [3, 4])

    def test_drop_does_not_force_dropped_elements(self) -> None:
        # drop walks the spine of the dropped prefix but must not force the
        # element values themselves.
        src = "let x = head(drop([crash(), 2], 1))\n"
        self.assertEqual(format_value(self.value_of(src, "x")), "Some(2)")

    def test_zip_pairs_and_stops_at_shorter(self) -> None:
        src = "let xs = zip(naturalsFrom(1), [10, 20])\n"
        self.assertEqual(format_value(self.value_of(src, "xs")), "((1, 10) (2, 20))")

    def test_zip_with_combines_elementwise(self) -> None:
        src = "def add(a: Int, b: Int): Int =\n    a + b\nlet xs = take(zipWith(naturalsFrom(1), naturalsFrom(10), add), 3)\n"
        self.assertEqual(self.list_to_py(self.value_of(src, "xs")), [11, 13, 15])

    def test_cycle_repeats_finite_list(self) -> None:
        src = "let xs = take(cycle([1, 2, 3]), 7)\n"
        self.assertEqual(self.list_to_py(self.value_of(src, "xs")), [1, 2, 3, 1, 2, 3, 1])

    def test_cycle_of_empty_is_empty(self) -> None:
        self.assertEqual(self.list_to_py(self.value_of("let xs = cycle([])\n", "xs")), [])

    def stdout_of(self, source: str, name: str) -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.value_of(source, name)
        return out.getvalue()

    def test_println_prints_string_without_quotes(self) -> None:
        output = self.stdout_of('let r = println("hello, world")\n', "r")
        self.assertEqual(output, "hello, world\n")

    def test_println_resolves_escapes_in_string(self) -> None:
        output = self.stdout_of('let r = println("a\\nb")\n', "r")
        self.assertEqual(output, "a\nb\n")

    def test_print_prints_string_without_newline(self) -> None:
        output = self.stdout_of('let r = print("hi")\n', "r")
        self.assertEqual(output, "hi")

    def test_println_uses_show_for_non_strings(self) -> None:
        self.assertEqual(self.stdout_of("let r = println(42)\n", "r"), "42\n")
        self.assertEqual(self.stdout_of("let r = println([1, 2])\n", "r"), "(1 2)\n")
        self.assertEqual(self.stdout_of('let r = println(Some("ok"))\n', "r"), 'Some("ok")\n')

    def test_println_show_keeps_quoted_form(self) -> None:
        output = self.stdout_of('let r = println(show("Ada"))\n', "r")
        self.assertEqual(output, '"Ada"\n')

    def test_combinators_typecheck(self) -> None:
        env = check_source(
            """
def lt5(n: Int): Bool =
    n < 5
def add(a: Int, b: Int): Int =
    a + b
let a: List[Int] = takeWhile(naturalsFrom(1), lt5)
let b: List[Int] = take(dropWhile(naturalsFrom(1), lt5), 2)
let c: List[Int] = take(zipWith(naturalsFrom(1), naturalsFrom(1), add), 2)
let d: List[Int] = take(cycle([1, 2]), 3)
let z = zip(naturalsFrom(1), naturalsFrom(1))
"""
        )
        self.assertEqual(env.lookup_value("a"), Type("List", (INT,)))
        self.assertEqual(env.lookup_value("z"), Type("List", (Type("Tuple", (INT, INT)),)))


class LazyRangeTests(unittest.TestCase):
    """`range` builds its spine on demand, like the other producers.

    It used to build every cell up front, which made the width of the interval
    the cost of the call: `head(filter(range(1, n), p))` was linear in `n` and
    a range wide enough to be interesting ran out of memory. Every test here
    is written so that it cannot pass if the spine is built eagerly — the
    ranges are far too wide to materialise.
    """

    WIDE = 100_000_000

    def value_of(self, source: str, name: str):
        return force_value(eval_source(source).lookup_raw(name))

    def test_a_wide_range_is_free_until_it_is_consumed(self) -> None:
        self.assertEqual(format_value(self.value_of(f"let xs = take(range(1, {self.WIDE}), 5)\n", "xs")), "(1 2 3 4 5)")

    def test_filter_over_a_wide_range_yields_its_first_matches(self) -> None:
        source = f"let xs = take(filter(range(1, {self.WIDE}), fn x: Int -> x % 7 == 0), 3)\n"
        self.assertEqual(format_value(self.value_of(source, "xs")), "(7 14 21)")

    def test_take_while_finishes_over_a_wide_range(self) -> None:
        """The whole result, not just its head — takeWhile stops at the first false."""
        source = f"let xs = takeWhile(range(1, {self.WIDE}), fn x: Int -> x < 10)\n"
        self.assertEqual(format_value(self.value_of(source, "xs")), "(1 2 3 4 5 6 7 8 9)")

    def test_head_and_drop_do_not_walk_the_whole_range(self) -> None:
        self.assertEqual(
            format_value(self.value_of(f"let x = head(drop(range(1, {self.WIDE}), 4))\n", "x")),
            "Some(5)",
        )

    def test_the_spine_is_only_built_as_far_as_it_is_asked_for(self) -> None:
        """tick() counts the evaluations: three elements taken, three ticks."""
        # `before` and `after` are separate bindings on purpose: one binding
        # read twice would answer from its memo, not from the counter.
        source = (
            f"let xs = take(map(range(1, {self.WIDE}), fn x: Int -> tick()), 3)\n"
            "let before = tickCount()\n"
            "let after = tickCount()\n"
        )
        env = eval_source(source)
        self.assertEqual(force_value(env.lookup_raw("before")), 0, "binding alone must evaluate nothing")
        self.assertEqual(format_value(env.lookup_raw("xs")), "(1 2 3)")
        self.assertEqual(force_value(env.lookup_raw("after")), 3)

    def test_the_finite_meaning_of_range_is_unchanged(self) -> None:
        for source, expected in (
            ("let xs = range(1, 5)\n", "(1 2 3 4)"),
            ("let xs = range(5, 1)\n", "()"),
            ("let xs = range(-2, 2)\n", "(-2 -1 0 1)"),
            ("let xs = range(3, 3)\n", "()"),
        ):
            with self.subTest(source=source):
                self.assertEqual(format_value(self.value_of(source, "xs")), expected)

    def test_a_lazy_range_equals_the_literal_list(self) -> None:
        self.assertIs(self.value_of("let same = range(1, 4) == [1, 2, 3]\n", "same"), True)

    def test_consuming_functions_still_consume(self) -> None:
        self.assertEqual(self.value_of("let n = length(range(1, 1000))\n", "n"), 999)
        self.assertEqual(self.value_of("let n = fold(range(1, 101), 0, fn a: Int -> fn b: Int -> a + b)\n", "n"), 5050)

    def test_the_ends_are_still_evaluated_at_the_call(self) -> None:
        """`range(crash(), 5)` must fail at the call, not at the first element."""
        with self.assertRaises(LuneRuntimeError):
            eval_source("let xs = range(crash(), 5)\n").lookup("xs")


class SpineCompressionTests(unittest.TestCase):
    """Walking a lazy spine writes the forced tail back into the cell.

    Without it the cell keeps pointing at the thunk, which keeps pointing at
    both the memoised value and the closure that produced it — three objects
    per element where a strict list holds one. That made a lazy `range` cost
    several times a strict one to traverse, which would have been a bad trade
    for the laziness.
    """

    def spine(self, value) -> list[object]:
        """The raw tail fields, without forcing anything."""
        cells = []
        current = force_value(value)
        while isinstance(current, DataValue) and current.constructor == "Cons":
            cells.append(current.fields[1])
            current = force_value(current.fields[1])
        return cells

    def test_a_walked_spine_holds_no_thunks(self) -> None:
        env = eval_source("let xs = range(1, 20)\nlet n = length(xs)\n")
        self.assertEqual(force_value(env.lookup_raw("n")), 19)
        tails = self.spine(env.lookup_raw("xs"))
        self.assertEqual(len(tails), 19)
        self.assertFalse(
            [tail for tail in tails if isinstance(tail, Thunk | LazyValue)],
            "length() walked the whole spine, so no cell should still hold a thunk",
        )

    def test_an_unwalked_spine_keeps_its_thunk(self) -> None:
        """The compression is a side effect of walking, not eager evaluation."""
        env = eval_source("let xs = range(1, 20)\nlet first = head(xs)\n")
        force_value(env.lookup_raw("first"))
        head_cell = force_value(env.lookup_raw("xs"))
        self.assertIsInstance(head_cell.fields[1], Thunk | LazyValue)

    def test_compression_does_not_change_what_is_seen(self) -> None:
        env = eval_source("let xs = range(1, 6)\nlet a = length(xs)\nlet b = fold(xs, 0, fn p: Int -> fn q: Int -> p + q)\n")
        self.assertEqual(force_value(env.lookup_raw("a")), 5)
        self.assertEqual(force_value(env.lookup_raw("b")), 15)
        self.assertEqual(format_value(env.lookup_raw("xs")), "(1 2 3 4 5)")

    def test_a_failing_tail_is_left_in_place(self) -> None:
        """A failed thunk is not written back, so the memoised failure survives."""
        env = eval_source("let xs = Cons(1, crash())\n")
        for _ in range(2):
            with self.assertRaises(LuneRuntimeError):
                format_value(env.lookup_raw("xs"))
        cell = force_value(env.lookup_raw("xs"))
        self.assertIsInstance(cell.fields[1], Thunk | LazyValue)
        self.assertEqual(cell.fields[1].state, ThunkState.FAILED)


class SpineRetentionTests(unittest.TestCase):
    """A walk that keeps no result must not keep the spine either.

    `SpineCompressionTests` covers the first half: the walk rewrites each cell
    so the thunk behind it can be collected. That frees nothing while anything
    still *names* the head, because every cell stays reachable through the
    chain, and two things did. A builtin's argument list named it for the whole
    call, so `length(range(1, n))` held all n cells. And a lazy tail closed over
    the cell it resumes from, so `filter` held every cell it scanned looking for
    the next match — the case that made

        filter(range(1, 100000000), fn x -> x < 10)

    produce its nine elements and then grow to roughly 19 GB during the scan
    that follows them, instead of finishing. Both walks are now flat, so the
    measure here is memory that does not grow with the length of the walk.
    """

    SMALL = 5_000
    LARGE = 25_000
    ALLOWANCE = 500_000

    def peak_bytes(self, source: str) -> int:
        tracemalloc.start()
        try:
            env = eval_source(source)
            format_value(env.lookup_raw("r"))
            return tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()

    def assert_flat(self, source: str) -> None:
        """The same walk, five times as long, must not cost more memory.

        A retained spine costs about 190 bytes an element, so the leak this
        guards against grows these walks by ~3.8 MB. Flat, they differ by about
        11 KB. The allowance sits between the two with room on both sides, so
        the test neither flickers nor lets a regression through.
        """
        small = self.peak_bytes(source.replace("N", str(self.SMALL)))
        large = self.peak_bytes(source.replace("N", str(self.LARGE)))
        self.assertLess(
            large - small,
            self.ALLOWANCE,
            f"{source}: peak memory grew from {small} to {large} bytes when the "
            f"walk went from {self.SMALL} to {self.LARGE} elements",
        )

    def test_filter_does_not_retain_the_range_it_scans(self) -> None:
        # Nine elements out, and everything after them scanned and dropped.
        self.assert_flat("let r = filter(range(1, N), fn x -> x < 10)\n")

    def test_filter_does_not_retain_the_gaps_between_matches(self) -> None:
        self.assert_flat("let r = length(filter(range(1, N), fn x -> x % 1000 == 0))\n")

    def test_length_does_not_retain_the_spine_it_counts(self) -> None:
        self.assert_flat("let r = length(range(1, N))\n")

    def test_fold_does_not_retain_the_spine_it_folds(self) -> None:
        self.assert_flat("let r = fold(range(1, N), 0, fn a -> fn b -> a + b)\n")

    def test_drop_does_not_retain_the_prefix_it_skips(self) -> None:
        self.assert_flat("let r = length(drop(range(1, N), 10))\n")

    def test_a_forced_thunk_lets_go_of_its_environment(self) -> None:
        """The other half of the same rule, where it can be seen directly."""
        env = eval_source("let n = 1 + 2\n")
        thunk = env.lookup_raw("n")
        self.assertIsInstance(thunk, Thunk)
        self.assertIsNotNone(thunk.env)
        self.assertEqual(force_value(thunk), 3)
        self.assertIsNone(thunk.env)
        self.assertEqual(force_value(thunk), 3, "the memoised value survives")

    def test_a_forced_lazy_tail_lets_go_of_its_closure(self) -> None:
        env = eval_source("let xs = range(1, 5)\n")
        tail = force_value(env.lookup_raw("xs")).fields[1]
        self.assertIsInstance(tail, LazyValue)
        self.assertIsNotNone(tail.compute)
        force_value(tail)
        self.assertIsNone(tail.compute)
        self.assertEqual(format_value(env.lookup_raw("xs")), "(1 2 3 4)")

    def test_a_failed_tail_still_raises_on_the_next_visit(self) -> None:
        """Dropping the producer must not disturb a memoised failure."""
        env = eval_source("let xs = map([1], fn x -> crash())\n")
        head = force_value(env.lookup_raw("xs")).fields[0]
        for _ in range(2):
            with self.assertRaises(LuneRuntimeError):
                force_value(head)
        self.assertEqual(head.state, ThunkState.FAILED)


if __name__ == "__main__":
    unittest.main()
