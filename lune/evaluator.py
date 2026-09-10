from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable

from . import nodes as ast
from .diagnostics import Diagnostic, DiagnosticError
from .parser import parse_source
from .messages import t


class LuneRuntimeError(DiagnosticError):
    def __init__(self, message: str, code: str = "RUN0006", hints: list[str] | None = None):
        super().__init__(Diagnostic(code=code, severity="error", message=message, hints=hints or []))


def _recursive_thunk_error() -> LuneRuntimeError:
    return LuneRuntimeError(
        t("run.recursive-thunk"),
        code="RUN0005",
        hints=[t("hint.recursive-thunk")],
    )


# --- lazy-evaluation tracing -------------------------------------------------
#
# When a hook is installed, thunk forcing reports (depth, message) events:
#   force <expr>     entering evaluation of a thunk
#   => <value>       that evaluation finished (same depth as its `force`)
#   memo <expr> => … a force hit an already-memoized result (no evaluation)
# Messages are only built while a hook is installed, so the hook-off cost is a
# None check per force.

_trace_hook = None
_trace_depth = 0


def set_trace_hook(hook) -> None:
    global _trace_hook, _trace_depth
    _trace_hook = hook
    _trace_depth = 0


def _trace(message: str) -> None:
    _trace_hook(_trace_depth, message)


_SUMMARY_LIMIT = 60


def _expr_summary(expr) -> str:
    try:
        from .formatter import Formatter

        text = " ".join(Formatter([], []).render(expr).split())
    except Exception:
        text = f"<{type(expr).__name__}>"
    if len(text) > _SUMMARY_LIMIT:
        text = text[: _SUMMARY_LIMIT - 1] + "…"
    return text


class Env:
    def __init__(self, parent: Env | None = None):
        self.parent = parent
        self.values: dict[str, Value] = {}
        # Names declared with `var`. `--eval` skips the type check, so the
        # evaluator has to refuse an assignment to a `let` itself, the way it
        # refuses ill-typed operators (issue #117, and #94 before it).
        self.mutable: set[str] = set()

    def define(self, name: str, value: Value, mutable: bool = False) -> None:
        self.values[name] = value
        if mutable:
            self.mutable.add(name)
        else:
            self.mutable.discard(name)

    def set(self, name: str, value: Value) -> None:
        if name in self.values:
            if name not in self.mutable:
                raise LuneRuntimeError(
                    t("run.assign-to-immutable", name=name),
                    hints=[t("hint.declare-with-var", name=name), t("hint.check-first")],
                )
            self.values[name] = value
            return
        if self.parent is not None:
            self.parent.set(name, value)
            return
        raise LuneRuntimeError(t("run.undefined-variable", name=name))

    def lookup_raw(self, name: str) -> Value:
        if name in self.values:
            return self.values[name]
        if self.parent is not None:
            return self.parent.lookup_raw(name)
        raise LuneRuntimeError(t("run.undefined-variable", name=name))

    def lookup(self, name: str) -> Value:
        return force_value(self.lookup_raw(name))

    def child(self) -> Env:
        return Env(self)


class ThunkState:
    UNEVALUATED = "unevaluated"
    EVALUATING = "evaluating"
    EVALUATED = "evaluated"
    FAILED = "failed"


Value = object


@dataclass
class Thunk:
    expr: ast.Expr
    # Cleared once `force` has memoised the result — see the note there.
    env: Env | None
    state: str = ThunkState.UNEVALUATED
    value: Value | None = None
    error: Exception | None = None

    def force(self) -> Value:
        global _trace_depth
        if self.state == ThunkState.EVALUATED:
            if _trace_hook is not None:
                _trace(f"memo {_expr_summary(self.expr)} => {preview_value(self.value)}")
            return self.value
        if self.state == ThunkState.FAILED:
            assert self.error is not None
            if _trace_hook is not None:
                _trace(f"memo {_expr_summary(self.expr)} => <failed>")
            raise self.error
        if self.state == ThunkState.EVALUATING:
            raise _recursive_thunk_error()
        if _trace_hook is not None:
            _trace(f"force {_expr_summary(self.expr)}")
            _trace_depth += 1
        self.state = ThunkState.EVALUATING
        try:
            self.value = eval_expr(self.expr, self.env)
            self.state = ThunkState.EVALUATED
            # Same reason as LazyValue: a memoised thunk has no further use for
            # the environment it closed over, and holding it pins every value
            # bound there. `expr` stays — the trace prints it, and it is shared
            # AST rather than captured values.
            self.env = None
        except Exception as exc:
            self.error = exc
            self.state = ThunkState.FAILED
            raise
        finally:
            if _trace_hook is not None:
                _trace_depth -= 1
        if _trace_hook is not None:
            _trace(f"=> {preview_value(self.value)}")
        return self.value


@dataclass
class LazyValue:
    # Cleared once `force` has memoised the result — see the note there.
    compute: Callable[[], Value] | None
    state: str = ThunkState.UNEVALUATED
    value: Value | None = None
    error: Exception | None = None

    def force(self) -> Value:
        global _trace_depth
        if self.state == ThunkState.EVALUATED:
            if _trace_hook is not None:
                _trace(f"memo <lazy> => {preview_value(self.value)}")
            return self.value
        if self.state == ThunkState.FAILED:
            assert self.error is not None
            if _trace_hook is not None:
                _trace("memo <lazy> => <failed>")
            raise self.error
        if self.state == ThunkState.EVALUATING:
            raise _recursive_thunk_error()
        if _trace_hook is not None:
            _trace("force <lazy>")
            _trace_depth += 1
        self.state = ThunkState.EVALUATING
        try:
            self.value = self.compute()
            self.state = ThunkState.EVALUATED
            # Let go of the closure now that its result is memoised. It is dead
            # weight either way, but it is also a space leak: the closures that
            # build a lazy spine capture the cell they resume from, so keeping
            # them made a walk retain every cell it had passed. `filter` over a
            # long `range` is the case that shows it — the result is nine
            # elements and the scan behind it must not be paid for in memory.
            self.compute = None
        except Exception as exc:
            self.error = exc
            self.state = ThunkState.FAILED
            raise
        finally:
            if _trace_hook is not None:
                _trace_depth -= 1
        if _trace_hook is not None:
            _trace(f"=> {preview_value(self.value)}")
        return self.value


@dataclass(frozen=True)
class FunctionValue:
    name: str | None
    params: list[ast.Param]
    body: ast.Expr
    env: Env

    def __repr__(self) -> str:
        return format_value(self)


@dataclass(frozen=True)
class BuiltinFunction:
    name: str
    func: Callable[[list[Value]], Value]
    force_args: bool = True

    def __repr__(self) -> str:
        return format_value(self)


@dataclass(frozen=True)
class ConstructorValue:
    name: str
    fields: list[ast.Param]

    @property
    def arity(self) -> int:
        return len(self.fields)

    def __repr__(self) -> str:
        return format_value(self)


@dataclass(frozen=True)
class PartialConstructorValue:
    constructor: ConstructorValue
    bound_fields: list[Value]

    @property
    def remaining_fields(self) -> list[ast.Param]:
        return self.constructor.fields[len(self.bound_fields) :]

    def __repr__(self) -> str:
        return format_value(self)


@dataclass(frozen=True)
class RecordConstructorValue:
    name: str
    fields: list[ast.RecordField]

    def __repr__(self) -> str:
        return format_value(self)


@dataclass(frozen=True)
class RecordValue:
    name: str
    field_order: list[str]
    fields: dict[str, Value]

    def __repr__(self) -> str:
        return format_value(self)


@dataclass(frozen=True)
class DataValue:
    constructor: str
    fields: list[Value]

    def __repr__(self) -> str:
        return format_value(self)


@dataclass(frozen=True)
class TupleValue:
    items: list[Value]

    def __repr__(self) -> str:
        return format_value(self)


UNIT = ()


def eval_source(source: str, filename: str = "<input>") -> Env:
    return eval_module(parse_source(source, filename))


def eval_module(module: ast.ModuleFile) -> Env:
    env = initial_env()
    eval_module_into(module, env)
    return env


def eval_module_into(module: ast.ModuleFile, env: Env) -> Env:
    for decl in module.declarations:
        eval_decl(decl, env)
    return env


def initial_env() -> Env:
    env = Env()
    state = {"ticks": 0}
    env.define("__tuple__", BuiltinFunction("__tuple__", lambda args: TupleValue(args), force_args=False))
    env.define("print", BuiltinFunction("print", _builtin_print))
    env.define("println", BuiltinFunction("println", _builtin_println))
    env.define("show", BuiltinFunction("show", lambda args: format_value(args[0])))
    env.define("id", BuiltinFunction("id", lambda args: force_value(args[0])))
    env.define("const", BuiltinFunction("const", lambda args: force_value(args[0]), force_args=False))
    env.define("not", BuiltinFunction("not", lambda args: not require_bool(args[0], t("ctx.operand-of", op="not"))))
    env.define("crash", BuiltinFunction("crash", _builtin_crash))
    env.define("tick", BuiltinFunction("tick", lambda args: _builtin_tick(state)))
    env.define("tickCount", BuiltinFunction("tickCount", lambda args: state["ticks"]))
    register_standard_library(env)
    return env


def _builtin_print(args: list[Value]) -> Value:
    print(*(_print_text(arg) for arg in args), end="")
    return UNIT


def _builtin_println(args: list[Value]) -> Value:
    print(*(_print_text(arg) for arg in args))
    return UNIT


def _print_text(value: Value) -> str:
    value = force_value(value)
    if isinstance(value, str):
        return value
    return _show_value(value)


def _builtin_crash(args: list[Value]) -> Value:
    raise LuneRuntimeError(t("run.crash-evaluated"))


def _builtin_tick(state: dict[str, int]) -> Value:
    state["ticks"] += 1
    return state["ticks"]


def register_standard_library(env: Env) -> None:
    env.define("Some", ConstructorValue("Some", [_param("value")]))
    env.define("None", DataValue("None", []))
    env.define("Ok", ConstructorValue("Ok", [_param("value")]))
    env.define("Err", ConstructorValue("Err", [_param("error")]))
    env.define("Cons", ConstructorValue("Cons", [_param("head"), _param("tail")]))
    env.define("Nil", DataValue("Nil", []))

    env.define("isSome", BuiltinFunction("isSome", lambda args: _is_constructor(args[0], "Some")))
    env.define("isNone", BuiltinFunction("isNone", lambda args: _is_constructor(args[0], "None")))
    env.define("getOrElse", BuiltinFunction("getOrElse", _builtin_get_or_else, force_args=False))
    env.define("optionMap", BuiltinFunction("optionMap", _builtin_option_map, force_args=False))

    env.define("isOk", BuiltinFunction("isOk", lambda args: _is_constructor(args[0], "Ok")))
    env.define("isErr", BuiltinFunction("isErr", lambda args: _is_constructor(args[0], "Err")))
    env.define("resultMap", BuiltinFunction("resultMap", _builtin_result_map, force_args=False))
    env.define("unwrapOr", BuiltinFunction("unwrapOr", _builtin_unwrap_or, force_args=False))

    env.define("isEmpty", BuiltinFunction("isEmpty", lambda args: _is_constructor(args[0], "Nil")))
    env.define("head", BuiltinFunction("head", _builtin_head))
    env.define("tail", BuiltinFunction("tail", _builtin_tail))
    env.define("length", BuiltinFunction("length", _builtin_length))
    env.define("map", BuiltinFunction("map", _builtin_map, force_args=False))
    env.define("filter", BuiltinFunction("filter", _builtin_filter, force_args=False))
    env.define("fold", BuiltinFunction("fold", _builtin_fold, force_args=False))
    env.define("take", BuiltinFunction("take", _builtin_take, force_args=False))
    env.define("drop", BuiltinFunction("drop", _builtin_drop, force_args=False))
    env.define("range", BuiltinFunction("range", _builtin_range))
    env.define("iterate", BuiltinFunction("iterate", _builtin_iterate, force_args=False))
    env.define("repeat", BuiltinFunction("repeat", _builtin_repeat, force_args=False))
    env.define("naturalsFrom", BuiltinFunction("naturalsFrom", _builtin_naturals_from))
    env.define("takeWhile", BuiltinFunction("takeWhile", _builtin_take_while, force_args=False))
    env.define("dropWhile", BuiltinFunction("dropWhile", _builtin_drop_while, force_args=False))
    env.define("zip", BuiltinFunction("zip", _builtin_zip, force_args=False))
    env.define("zipWith", BuiltinFunction("zipWith", _builtin_zip_with, force_args=False))
    env.define("cycle", BuiltinFunction("cycle", _builtin_cycle, force_args=False))


def _param(name: str, is_strict: bool = False) -> ast.Param:
    return ast.Param(name, None, is_strict)


def _is_constructor(value: Value, name: str) -> bool:
    value = force_value(value)
    return isinstance(value, DataValue) and value.constructor == name


def _builtin_get_or_else(args: list[Value]) -> Value:
    option = force_value(args[0])
    if _is_constructor(option, "Some"):
        return force_value(option.fields[0])
    if _is_constructor(option, "None"):
        return force_value(args[1])
    raise LuneRuntimeError(t("run.expects", func="getOrElse", expected="Option", got=format_value(option)))


def _builtin_option_map(args: list[Value]) -> Value:
    option = force_value(args[0])
    function = force_value(args[1])
    if _is_constructor(option, "None"):
        return DataValue("None", [])
    if _is_constructor(option, "Some"):
        return DataValue("Some", [LazyValue(lambda: apply_value(function, [option.fields[0]]))])
    raise LuneRuntimeError(t("run.expects", func="optionMap", expected="Option", got=format_value(option)))


def _builtin_result_map(args: list[Value]) -> Value:
    result = force_value(args[0])
    function = force_value(args[1])
    if _is_constructor(result, "Err"):
        return DataValue("Err", [result.fields[0]])
    if _is_constructor(result, "Ok"):
        return DataValue("Ok", [LazyValue(lambda: apply_value(function, [result.fields[0]]))])
    raise LuneRuntimeError(t("run.expects", func="resultMap", expected="Result", got=format_value(result)))


def _builtin_unwrap_or(args: list[Value]) -> Value:
    result = force_value(args[0])
    if _is_constructor(result, "Ok"):
        return force_value(result.fields[0])
    if _is_constructor(result, "Err"):
        return force_value(args[1])
    raise LuneRuntimeError(t("run.expects", func="unwrapOr", expected="Result", got=format_value(result)))


def _builtin_head(args: list[Value]) -> Value:
    items = force_value(args[0])
    if _is_constructor(items, "Nil"):
        return DataValue("None", [])
    if _is_constructor(items, "Cons"):
        return DataValue("Some", [items.fields[0]])
    raise LuneRuntimeError(t("run.expects", func="head", expected="List", got=format_value(items)))


def _builtin_tail(args: list[Value]) -> Value:
    items = force_value(args[0])
    if _is_constructor(items, "Nil"):
        return DataValue("None", [])
    if _is_constructor(items, "Cons"):
        return DataValue("Some", [items.fields[1]])
    raise LuneRuntimeError(t("run.expects", func="tail", expected="List", got=format_value(items)))


def _builtin_length(args: list[Value]) -> Value:
    value = force_value(_consumed_arg(args))
    if isinstance(value, str):
        return len(value)
    count = 0
    while True:
        value = force_value(value)
        if _is_constructor(value, "Nil"):
            return count
        if not _is_constructor(value, "Cons"):
            raise LuneRuntimeError(t("run.expects", func="length", expected="List or String", got=format_value(value)))
        count += 1
        value = _forced_tail(value)


def _builtin_map(args: list[Value]) -> Value:
    items = force_value(args[0])
    function = force_value(args[1])
    if _is_constructor(items, "Nil"):
        return DataValue("Nil", [])
    if _is_constructor(items, "Cons"):
        head = LazyValue(lambda: apply_value(function, [items.fields[0]]))
        tail = LazyValue(lambda: _builtin_map([items.fields[1], function]))
        return DataValue("Cons", [head, tail])
    raise LuneRuntimeError(t("run.expects", func="map", expected="List", got=format_value(items)))


def _builtin_filter(args: list[Value]) -> Value:
    items = force_value(_consumed_arg(args))
    predicate = force_value(args[1])
    while True:
        items = force_value(items)
        if _is_constructor(items, "Nil"):
            return DataValue("Nil", [])
        if not _is_constructor(items, "Cons"):
            raise LuneRuntimeError(t("run.expects", func="filter", expected="List", got=format_value(items)))
        head = items.fields[0]
        tail = items.fields[1]
        if require_bool(apply_value(predicate, [head]), t("ctx.predicate-of", func="filter")):
            # The tail closes over the argument *list*, not over `tail` itself.
            # Resuming empties the list (`_consumed_arg`) before the scan for
            # the next match begins, so a long run of non-matches does not keep
            # this cell — and with it every cell the scan walks past — alive.
            # Capturing `tail` directly would hold it for the whole call, which
            # is what made `filter(range(1, 100000000), fn x -> x < 10)` grow
            # without bound after producing its nine elements.
            rest = [tail, predicate]
            return DataValue("Cons", [head, LazyValue(lambda: _builtin_filter(rest))])
        items = _forced_tail(items)


def _builtin_fold(args: list[Value]) -> Value:
    items = force_value(_consumed_arg(args))
    acc = args[1]
    function = force_value(args[2])
    while True:
        items = force_value(items)
        if _is_constructor(items, "Nil"):
            return acc
        if not _is_constructor(items, "Cons"):
            raise LuneRuntimeError(t("run.expects", func="fold", expected="List", got=format_value(items)))
        acc = apply_value(function, [acc, items.fields[0]])
        items = _forced_tail(items)


def _builtin_take(args: list[Value]) -> Value:
    count = require_int(args[1], "take")
    if count <= 0:
        return DataValue("Nil", [])
    items = force_value(args[0])
    if _is_constructor(items, "Nil"):
        return DataValue("Nil", [])
    if _is_constructor(items, "Cons"):
        tail = LazyValue(lambda: _builtin_take([items.fields[1], count - 1]))
        return DataValue("Cons", [items.fields[0], tail])
    raise LuneRuntimeError(t("run.expects", func="take", expected="List", got=format_value(items)))


def _builtin_drop(args: list[Value]) -> Value:
    items = _consumed_arg(args)
    count = require_int(args[1], "drop")
    while count > 0:
        items = force_value(items)
        if _is_constructor(items, "Nil"):
            return DataValue("Nil", [])
        if not _is_constructor(items, "Cons"):
            raise LuneRuntimeError(t("run.expects", func="drop", expected="List", got=format_value(items)))
        items = _forced_tail(items)
        count -= 1
    return items


def _builtin_range(args: list[Value]) -> Value:
    # Both ends are checked here rather than inside the spine, so a bad argument
    # still fails at the call: `range(crash(), 5)` explodes on the call, not
    # when someone eventually asks for the first element.
    start = require_int(args[0], "range")
    end = require_int(args[1], "range")
    return _range_from(start, end)


def _range_from(start: int, end: int) -> Value:
    # `range` is a producer like naturalsFrom/iterate/repeat, and lazy for the
    # same reason: the cost of the list should follow what the consumer asks
    # for, not the width of the interval. Building it eagerly made
    # `head(filter(range(1, n), p))` linear in `n` and cost ~192 bytes an
    # element, so a range wide enough to be interesting ran out of memory
    # before the predicate saw its first value.
    if start >= end:
        return DataValue("Nil", [])
    return DataValue("Cons", [start, LazyValue(lambda: _range_from(start + 1, end))])


def _builtin_iterate(args: list[Value]) -> Value:
    # iterate(f, x) = [x, f(x), f(f(x)), ...] — infinite, with a lazy tail.
    function = force_value(args[0])
    x = args[1]
    return DataValue(
        "Cons",
        [x, LazyValue(lambda: _builtin_iterate([function, LazyValue(lambda: apply_value(function, [x]))]))],
    )


def _builtin_repeat(args: list[Value]) -> Value:
    # repeat(x) = [x, x, x, ...] — infinite, with a lazy tail.
    x = args[0]
    return DataValue("Cons", [x, LazyValue(lambda: _builtin_repeat([x]))])


def _builtin_naturals_from(args: list[Value]) -> Value:
    # naturalsFrom(n) = [n, n+1, n+2, ...] — infinite, with a lazy tail.
    n = require_int(args[0], "naturalsFrom")
    return DataValue("Cons", [n, LazyValue(lambda: _builtin_naturals_from([n + 1]))])


def _builtin_take_while(args: list[Value]) -> Value:
    # Take elements while the predicate holds; stop at the first that fails.
    items = force_value(args[0])
    predicate = force_value(args[1])
    if _is_constructor(items, "Nil"):
        return DataValue("Nil", [])
    if not _is_constructor(items, "Cons"):
        raise LuneRuntimeError(t("run.expects", func="takeWhile", expected="List", got=format_value(items)))
    head = items.fields[0]
    tail = items.fields[1]
    if require_bool(apply_value(predicate, [head]), t("ctx.predicate-of", func="takeWhile")):
        return DataValue(
            "Cons", [head, LazyValue(lambda tail=tail, predicate=predicate: _builtin_take_while([tail, predicate]))]
        )
    return DataValue("Nil", [])


def _builtin_drop_while(args: list[Value]) -> Value:
    # Drop elements while the predicate holds; return the rest (lazy tail kept).
    items = _consumed_arg(args)
    predicate = force_value(args[1])
    while True:
        items = force_value(items)
        if _is_constructor(items, "Nil"):
            return DataValue("Nil", [])
        if not _is_constructor(items, "Cons"):
            raise LuneRuntimeError(t("run.expects", func="dropWhile", expected="List", got=format_value(items)))
        if not require_bool(apply_value(predicate, [items.fields[0]]), t("ctx.predicate-of", func="dropWhile")):
            return items
        items = _forced_tail(items)


def _builtin_zip(args: list[Value]) -> Value:
    # Pair up two lists into tuples, stopping at the shorter one.
    a = force_value(args[0])
    b = force_value(args[1])
    if _is_constructor(a, "Nil") or _is_constructor(b, "Nil"):
        return DataValue("Nil", [])
    if not (_is_constructor(a, "Cons") and _is_constructor(b, "Cons")):
        raise LuneRuntimeError(t("run.expects-lists", func="zip"))
    at, bt = a.fields[1], b.fields[1]
    head = TupleValue([a.fields[0], b.fields[0]])
    return DataValue("Cons", [head, LazyValue(lambda: _builtin_zip([at, bt]))])


def _builtin_zip_with(args: list[Value]) -> Value:
    # Combine two lists element-wise with f, stopping at the shorter one.
    a = force_value(args[0])
    b = force_value(args[1])
    function = force_value(args[2])
    if _is_constructor(a, "Nil") or _is_constructor(b, "Nil"):
        return DataValue("Nil", [])
    if not (_is_constructor(a, "Cons") and _is_constructor(b, "Cons")):
        raise LuneRuntimeError(t("run.expects-lists", func="zipWith"))
    ah, at = a.fields[0], a.fields[1]
    bh, bt = b.fields[0], b.fields[1]
    head = LazyValue(lambda: apply_value(function, [ah, bh]))
    return DataValue("Cons", [head, LazyValue(lambda: _builtin_zip_with([at, bt, function]))])


def _builtin_cycle(args: list[Value]) -> Value:
    # Repeat a finite list forever: [1,2] -> [1,2,1,2,...]. Empty stays empty.
    original = force_value(args[0])
    if _is_constructor(original, "Nil"):
        return DataValue("Nil", [])

    def step(current: Value) -> Value:
        current = force_value(current)
        if _is_constructor(current, "Nil"):
            return step(original)
        if not _is_constructor(current, "Cons"):
            raise LuneRuntimeError(t("run.expects", func="cycle", expected="List", got=format_value(current)))
        tail = current.fields[1]
        return DataValue("Cons", [current.fields[0], LazyValue(lambda tail=tail: step(tail))])

    return step(original)


def eval_decl(decl: ast.Decl, env: Env) -> Value:
    if isinstance(decl, ast.FunctionDecl):
        env.define(decl.name, FunctionValue(decl.name, decl.params, decl.body, env))
        return UNIT
    if isinstance(decl, ast.LetDecl):
        bind_let(decl, env)
        return UNIT
    if isinstance(decl, ast.VarDecl):
        env.define(decl.name, force_value(eval_expr(decl.value, env)), mutable=True)
        return UNIT
    if isinstance(decl, ast.TypeDecl):
        for ctor in decl.constructors:
            env.define(ctor.name, ConstructorValue(ctor.name, ctor.fields))
        return UNIT
    if isinstance(decl, ast.RecordDecl):
        env.define(decl.name, RecordConstructorValue(decl.name, decl.fields))
        return UNIT
    raise LuneRuntimeError(t("run.unsupported-declaration", kind=type(decl).__name__))


def bind_let(decl: ast.LetDecl, env: Env) -> None:
    if isinstance(decl.pattern, ast.NamePattern) and not decl.is_strict:
        env.define(decl.pattern.name, Thunk(decl.value, env))
        return
    value = force_value(eval_expr(decl.value, env)) if decl.is_strict else eval_expr(decl.value, env)
    bindings = match_pattern(decl.pattern, force_value(value))
    if bindings is None:
        raise LuneRuntimeError(t("run.let-pattern"))
    for name, bound in bindings.items():
        env.define(name, bound)


def eval_expr(expr: ast.Expr, env: Env) -> Value:
    if isinstance(expr, ast.BlockExpr):
        return eval_block(expr, env.child())
    if isinstance(expr, ast.LiteralExpr):
        return expr.value
    if isinstance(expr, ast.NameExpr):
        return env.lookup(expr.name)
    if isinstance(expr, ast.NullExpr):
        return None
    if isinstance(expr, ast.CallExpr):
        return eval_call(expr, env)
    if isinstance(expr, ast.ListExpr):
        return eval_list_expr(expr, env)
    if isinstance(expr, ast.UnaryExpr):
        value = force_value(eval_expr(expr.expr, env))
        if expr.op in ("-", "+"):
            if not _is_number(value):
                raise LuneRuntimeError(
                    t("run.unary-numeric", op=expr.op, got=type_name(value)), hints=[t("hint.check-first")]
                )
            return -value if expr.op == "-" else value
        if expr.op == "!":
            return not require_bool(value, t("ctx.unary-not"))
        raise LuneRuntimeError(t("run.unsupported-unary-op", op=expr.op))
    if isinstance(expr, ast.BinaryExpr):
        return eval_binary(expr, env)
    if isinstance(expr, ast.IfExpr):
        return eval_if(expr, env)
    if isinstance(expr, ast.WhileExpr):
        return eval_while(expr, env)
    if isinstance(expr, ast.ForExpr):
        return eval_for(expr, env)
    if isinstance(expr, ast.MatchExpr):
        return eval_match(expr, env)
    if isinstance(expr, ast.LambdaExpr):
        return FunctionValue(None, expr.params, expr.body, env)
    if isinstance(expr, ast.LazyExpr):
        return Thunk(expr.body, env)
    if isinstance(expr, ast.ForceExpr):
        return force_value(eval_expr(expr.expr, env))
    if isinstance(expr, ast.SeqExpr):
        force_value(eval_expr(expr.first, env))
        return eval_expr(expr.second, env)
    if isinstance(expr, ast.DeepForceExpr):
        return deep_force(eval_expr(expr.expr, env))
    if isinstance(expr, ast.IOBlockExpr):
        return eval_block(expr.body, env.child())
    if isinstance(expr, ast.RaiseExpr):
        raise LuneRuntimeError(str(force_value(eval_expr(expr.expr, env))))
    if isinstance(expr, ast.MemberExpr):
        receiver = force_value(eval_expr(expr.receiver, env))
        return eval_member(receiver, expr.name)
    if isinstance(expr, ast.SafeMemberExpr):
        receiver = force_value(eval_expr(expr.receiver, env))
        return None if receiver is None else eval_member(receiver, expr.name)
    if isinstance(expr, ast.AssignExpr):
        return eval_assign(expr, env)
    raise LuneRuntimeError(t("run.unsupported-expression", kind=type(expr).__name__))


def eval_block(block: ast.BlockExpr, env: Env) -> Value:
    for item in block.statements:
        if isinstance(item, ast.Decl):
            eval_decl(item, env)
        else:
            force_value(eval_expr(item, env))
    if block.result is None:
        return UNIT
    return eval_expr(block.result, env)


def reject_named_args(args: list[ast.Argument]) -> None:
    """Guard the positional callees against `name = value` arguments.

    The typechecker rejects these too (typechecker.py reject_named_args), but
    `--eval` and `deepForce` reach the evaluator without a type-check pass, so
    the positional binding needs its own gate: otherwise a label would still be
    silently dropped and `P(y = 1, x = 2)` would still swap the two values.
    Record construction resolves names properly and is not routed here.

    Like the parallel record guard in `apply_record_constructor`, this reports
    the generic `RUN0006`; the precise `TYP0012` belongs to the static check.
    """
    for arg in args:
        if arg.name is not None:
            raise LuneRuntimeError(t("run.named-arg", name=arg.name), hints=[t("hint.positional-only")])


def eval_call(expr: ast.CallExpr, env: Env) -> Value:
    callee = force_value(eval_expr(expr.callee, env))
    if isinstance(callee, RecordConstructorValue):
        return apply_record_constructor(callee, expr.args, env)
    reject_named_args(expr.args)
    if isinstance(callee, BuiltinFunction):
        if callee.force_args:
            args = [force_value(eval_expr(arg.value, env)) for arg in expr.args]
        else:
            args = [Thunk(arg.value, env) for arg in expr.args]
        return callee.func(args)
    if isinstance(callee, ConstructorValue):
        args = prepare_constructor_args(callee, [], expr.args, env)
        return apply_constructor(callee, [], args)
    if isinstance(callee, PartialConstructorValue):
        args = prepare_constructor_args(callee.constructor, callee.bound_fields, expr.args, env)
        return apply_constructor(callee.constructor, callee.bound_fields, args)
    if isinstance(callee, FunctionValue):
        if not expr.args and not callee.params:
            return apply_function(callee, [])
        return apply_function_to_ast_args(callee, expr.args, env)
    raise LuneRuntimeError(t("run.not-callable", value=format_value(callee)))


def eval_list_expr(expr: ast.ListExpr, env: Env) -> Value:
    result: Value = DataValue("Nil", [])
    for item in reversed(expr.items):
        result = DataValue("Cons", [Thunk(item, env), result])
    return result


def apply_record_constructor(constructor: RecordConstructorValue, args: list[ast.Argument], env: Env) -> Value:
    by_name = {field.name: field for field in constructor.fields}
    values: dict[str, Value] = {}
    for arg in args:
        if arg.name is None:
            raise LuneRuntimeError(t("run.named-fields", ctor=constructor.name))
        field = by_name.get(arg.name)
        if field is None:
            raise LuneRuntimeError(t("run.unexpected-record-field", ctor=constructor.name, field=arg.name))
        if arg.name in values:
            raise LuneRuntimeError(t("run.duplicate-init", field=arg.name))
        if field.is_strict:
            values[arg.name] = force_value(eval_expr(arg.value, env))
        else:
            values[arg.name] = Thunk(arg.value, env)
    for field in constructor.fields:
        if field.name not in values:
            raise LuneRuntimeError(t("run.missing-record-field", ctor=constructor.name, field=field.name))
    return RecordValue(constructor.name, [field.name for field in constructor.fields], values)


def prepare_function_args(function: FunctionValue, args: list[ast.Argument], env: Env) -> list[Value]:
    values: list[Value] = []
    for param, arg in zip(function.params, args):
        if param.is_strict:
            values.append(force_value(eval_expr(arg.value, env)))
        else:
            values.append(Thunk(arg.value, env))
    return values


def apply_function_to_ast_args(function: FunctionValue, args: list[ast.Argument], env: Env) -> Value:
    current: Value = function
    remaining = args
    while remaining:
        current = force_value(current)
        if not isinstance(current, FunctionValue):
            raise LuneRuntimeError(t("run.not-callable", value=format_value(current)))
        if not current.params:
            current = apply_function(current, [])
            continue
        batch = remaining[: len(current.params)]
        values = prepare_function_args(current, batch, env)
        current = apply_function(current, values)
        remaining = remaining[len(batch) :]
    return current


def apply_function(function: FunctionValue, args: list[Value]) -> Value:
    if len(args) > len(function.params):
        raise LuneRuntimeError(t("run.arity-fn", func=function.name or "<lambda>", max=len(function.params), got=len(args)))
    call_env = function.env.child()
    for param, arg in zip(function.params, args):
        call_env.define(param.name, arg)
    remaining = function.params[len(args) :]
    if remaining:
        return FunctionValue(function.name, remaining, function.body, call_env)
    return eval_expr(function.body, call_env)


def prepare_constructor_args(constructor: ConstructorValue, bound_fields: list[Value], args: list[ast.Argument], env: Env) -> list[Value]:
    remaining_fields = constructor.fields[len(bound_fields) :]
    if len(args) > len(remaining_fields):
        raise LuneRuntimeError(t("run.arity-ctor-more", ctor=constructor.name, max=len(remaining_fields), got=len(args)))
    values: list[Value] = []
    for field, arg in zip(remaining_fields, args):
        if field.is_strict:
            values.append(force_value(eval_expr(arg.value, env)))
        else:
            values.append(Thunk(arg.value, env))
    return values


def apply_constructor(constructor: ConstructorValue, bound_fields: list[Value], args: list[Value]) -> Value:
    fields = [*bound_fields, *args]
    if len(fields) > constructor.arity:
        raise LuneRuntimeError(t("run.arity-fn", func=constructor.name, max=constructor.arity, got=len(fields)))
    if len(fields) < constructor.arity:
        return PartialConstructorValue(constructor, fields)
    return DataValue(constructor.name, fields)


def eval_binary(expr: ast.BinaryExpr, env: Env, op_label: str | None = None) -> Value:
    # `op_label` names the operator in diagnostics; it differs from `expr.op`
    # only for a desugared compound assignment (`+=` typed as `+`).
    label = op_label or expr.op
    if expr.op in ("&&", "||"):
        # Short-circuit on the left; the right operand is only evaluated when
        # it decides the result, and then it must be a Bool as well.
        left = require_bool(eval_expr(expr.left, env), t("ctx.operand-of", op=label))
        if expr.op == "&&" and not left:
            return False
        if expr.op == "||" and left:
            return True
        return require_bool(eval_expr(expr.right, env), t("ctx.operand-of", op=label))
    if expr.op == "??":
        left = force_value(eval_expr(expr.left, env))
        return left if left is not None else eval_expr(expr.right, env)

    left = force_value(eval_expr(expr.left, env))
    right = force_value(eval_expr(expr.right, env))
    # Operand types are checked here as well as in the type checker, because
    # `lune --eval` runs without the latter and Python's own operators would
    # otherwise supply their semantics (`"%d" % 5`, `"ab" * 3`, `true + 1`).
    if expr.op == "+":
        if isinstance(left, str) and isinstance(right, str):
            return left + right
        require_numeric_operands(label, left, right, plus=True)
        return left + right
    if expr.op in ("-", "*", "/", "//", "%", "<", "<=", ">", ">="):
        require_numeric_operands(label, left, right)
    if expr.op == "-":
        return left - right
    if expr.op == "*":
        return left * right
    if expr.op == "/":
        if right == 0:
            raise LuneRuntimeError(t("run.division-by-zero"), hints=[t("hint.division-by-zero", op="/")])
        return left / right
    if expr.op == "//":
        if right == 0:
            raise LuneRuntimeError(t("run.division-by-zero"), hints=[t("hint.division-by-zero", op="//")])
        # Floor division, so that `a // b` and `a % b` agree on negatives:
        # a == (a // b) * b + (a % b) holds because "%" floors too.
        return left // right
    if expr.op == "%":
        if right == 0:
            raise LuneRuntimeError(t("run.division-by-zero"), hints=[t("hint.division-by-zero", op="%")])
        return left % right
    if expr.op == "==":
        return values_equal(left, right)
    if expr.op == "!=":
        return not values_equal(left, right)
    if expr.op == "<":
        return left < right
    if expr.op == "<=":
        return left <= right
    if expr.op == ">":
        return left > right
    if expr.op == ">=":
        return left >= right
    if expr.op == "|>":
        return apply_value(right, [left])
    raise LuneRuntimeError(t("run.unsupported-binary-op", op=expr.op))


def eval_if(expr: ast.IfExpr, env: Env) -> Value:
    if require_bool(eval_expr(expr.condition, env), t("ctx.if-condition")):
        return eval_expr(expr.then_branch, env)
    for condition, branch in expr.elif_branches:
        if require_bool(eval_expr(condition, env), t("ctx.elif-condition")):
            return eval_expr(branch, env)
    if expr.else_branch is None:
        return UNIT
    return eval_expr(expr.else_branch, env)


def eval_while(expr: ast.WhileExpr, env: Env) -> Value:
    while require_bool(eval_expr(expr.condition, env), t("ctx.while-condition")):
        eval_block(expr.body, env.child())
    return UNIT


def eval_for(expr: ast.ForExpr, env: Env) -> Value:
    current = force_value(eval_expr(expr.iterable, env))
    while True:
        if isinstance(current, DataValue) and current.constructor == "Nil":
            return UNIT
        if not isinstance(current, DataValue) or current.constructor != "Cons" or len(current.fields) != 2:
            raise LuneRuntimeError(t("run.for-iterable", got=format_value(current)))
        bindings = match_pattern(expr.pattern, current.fields[0])
        if bindings is None:
            raise LuneRuntimeError(t("run.for-pattern", value=format_value(current.fields[0])))
        body_env = env.child()
        for name, bound in bindings.items():
            body_env.define(name, bound)
        eval_block(expr.body, body_env)
        current = _forced_tail(current)


def eval_match(expr: ast.MatchExpr, env: Env) -> Value:
    value = force_value(eval_expr(expr.scrutinee, env))
    for case in expr.cases:
        bindings = match_pattern(case.pattern, value)
        if bindings is None:
            continue
        case_env = env.child()
        for name, bound in bindings.items():
            case_env.define(name, bound)
        if case.guard is not None and not require_bool(eval_expr(case.guard, case_env), t("ctx.match-guard")):
            continue
        return eval_expr(case.body, case_env)
    raise LuneRuntimeError(t("run.non-exhaustive", value=format_value(value)))


def match_pattern(pattern: ast.Pattern, value: Value) -> dict[str, Value] | None:
    if isinstance(pattern, ast.WildcardPattern):
        return {}
    if isinstance(pattern, ast.NullPattern):
        return {} if force_value(value) is None else None
    if isinstance(pattern, ast.NamePattern):
        return {pattern.name: value}
    if isinstance(pattern, ast.LiteralPattern):
        return {} if force_value(value) == pattern.value else None
    if isinstance(pattern, ast.ConstructorPattern):
        value = force_value(value)
        if not isinstance(value, DataValue) or value.constructor != pattern.name:
            return None
        if len(value.fields) != len(pattern.args):
            return None
        bindings: dict[str, Value] = {}
        for subpattern, field in zip(pattern.args, value.fields, strict=True):
            sub = match_pattern(subpattern, field)
            if sub is None:
                return None
            bindings.update(sub)
        return bindings
    if isinstance(pattern, ast.TuplePattern):
        value = force_value(value)
        if not isinstance(value, TupleValue) or len(value.items) != len(pattern.items):
            return None
        bindings = {}
        for subpattern, item in zip(pattern.items, value.items, strict=True):
            sub = match_pattern(subpattern, item)
            if sub is None:
                return None
            bindings.update(sub)
        return bindings
    if isinstance(pattern, ast.OrPattern):
        for item in pattern.patterns:
            sub = match_pattern(item, value)
            if sub is not None:
                return sub
        return None
    if isinstance(pattern, ast.TypedPattern):
        return match_pattern(pattern.pattern, value)
    raise LuneRuntimeError(t("run.unsupported-pattern", kind=type(pattern).__name__))


def eval_member(receiver: Value, name: str) -> Value:
    if isinstance(receiver, RecordValue):
        if name not in receiver.fields:
            raise LuneRuntimeError(t("run.unknown-record-field", record=receiver.name, field=name))
        return force_value(receiver.fields[name])
    if isinstance(receiver, DataValue):
        raise LuneRuntimeError(t("run.data-field-access"))
    if isinstance(receiver, str) and name == "length":
        return BuiltinFunction("String.length", lambda args: len(receiver))
    raise LuneRuntimeError(t("run.unsupported-member", receiver=format_value(receiver), name=name))


def eval_assign(expr: ast.AssignExpr, env: Env) -> Value:
    if not isinstance(expr.target, ast.NameExpr):
        raise LuneRuntimeError(t("run.only-var-assign"))
    if expr.op == "=":
        value = force_value(eval_expr(expr.value, env))
    else:
        # `x op= e` computes `x op e`, so it goes through eval_binary: the
        # operator semantics and the RUN0006 division-by-zero diagnostics stay
        # in one place (documents/SYNTAX_SPEC.md section 14.1).
        compound = ast.desugar_compound_assign(expr)
        if compound is None:
            raise LuneRuntimeError(t("run.unsupported-binary-op", op=expr.op))
        value = force_value(eval_binary(compound, env, op_label=expr.op))
    env.set(expr.target.name, value)
    return value


def apply_value(function: Value, args: list[Value]) -> Value:
    function = force_value(function)
    if isinstance(function, BuiltinFunction):
        values = [force_value(arg) for arg in args] if function.force_args else args
        return function.func(values)
    if isinstance(function, ConstructorValue):
        values = prepare_runtime_constructor_args(function, [], args)
        return apply_constructor(function, [], values)
    if isinstance(function, PartialConstructorValue):
        values = prepare_runtime_constructor_args(function.constructor, function.bound_fields, args)
        return apply_constructor(function.constructor, function.bound_fields, values)
    if isinstance(function, FunctionValue):
        return apply_function_to_values(function, args)
    raise LuneRuntimeError(t("run.not-callable", value=format_value(function)))


def apply_function_to_values(function: FunctionValue, args: list[Value]) -> Value:
    current: Value = function
    remaining = args
    while remaining:
        current = force_value(current)
        if not isinstance(current, FunctionValue):
            raise LuneRuntimeError(t("run.not-callable", value=format_value(current)))
        if not current.params:
            current = apply_function(current, [])
            continue
        batch = remaining[: len(current.params)]
        values = prepare_runtime_function_args(current, batch)
        current = apply_function(current, values)
        remaining = remaining[len(batch) :]
    return current


def prepare_runtime_function_args(function: FunctionValue, args: list[Value]) -> list[Value]:
    return [force_value(arg) if param.is_strict else arg for param, arg in zip(function.params, args)]


def prepare_runtime_constructor_args(constructor: ConstructorValue, bound_fields: list[Value], args: list[Value]) -> list[Value]:
    remaining_fields = constructor.fields[len(bound_fields) :]
    if len(args) > len(remaining_fields):
        raise LuneRuntimeError(t("run.arity-ctor-more", ctor=constructor.name, max=len(remaining_fields), got=len(args)))
    return [force_value(arg) if field.is_strict else arg for field, arg in zip(remaining_fields, args)]


def force_value(value: Value) -> Value:
    # Loop until WHNF: forcing one wrapper can yield another (e.g. a Thunk
    # for `drop(...)` evaluates to the LazyValue tail of the source list).
    while isinstance(value, Thunk | LazyValue):
        value = value.force()
    return value


def _consumed_arg(args: list[Value], index: int = 0) -> Value:
    """Read an argument and clear the caller's slot.

    A builtin that walks a spine must not leave the *first* cell reachable.
    `_forced_tail` rewrites each cell as the walk passes it, but that frees
    nothing while something still names the head, because every cell behind it
    stays reachable through the chain. The argument list names it for as long
    as the builtin runs, which is what made `length(range(1, n))` cost O(n)
    memory even though it keeps no result.

    A builtin owns its argument list — both dispatch sites (`eval_call` and
    `apply_value`) hand over a fresh one — so clearing the slot is invisible
    to the caller.
    """
    value = args[index]
    args[index] = None
    return value


def _forced_tail(cons: DataValue) -> Value:
    """Force a list's tail to WHNF and write the result back into the cell.

    Forcing alone does not free anything: the cell still points at the thunk,
    and the thunk holds both its memoised value and the closure that produced
    it. Walking a lazy spine therefore retains three objects per element where
    a strict list retains one. Overwriting the field lets the wrapper and its
    closure be collected as the walk moves past them, which is what keeps a
    lazy `range` from costing several times a strict one to traverse.

    Thunks memoise, so the swap is invisible — forcing the cell again would
    have returned this same value. A force that raises is deliberately left in
    place, so the memoised failure is raised again on the next visit.
    """
    tail = cons.fields[1]
    if isinstance(tail, Thunk | LazyValue):
        tail = force_value(tail)
        cons.fields[1] = tail
    return tail


def deep_force(value: Value) -> Value:
    value = force_value(value)
    if isinstance(value, DataValue):
        for field in value.fields:
            deep_force(field)
    elif isinstance(value, RecordValue):
        for field in value.fields.values():
            deep_force(field)
    elif isinstance(value, TupleValue):
        for item in value.items:
            deep_force(item)
    return value


def values_equal(left: Value, right: Value) -> bool:
    """Structural equality for `==` / `!=`.

    Forces both sides only as far as the comparison needs, left to right,
    and stops at the first mismatch — so comparing two infinite lists only
    diverges when no mismatch is ever found. Uses an explicit stack instead
    of recursion so long list spines don't hit Python's recursion limit.
    """
    stack: list[tuple[Value, Value]] = [(left, right)]
    while stack:
        a, b = stack.pop()
        a = force_value(a)
        b = force_value(b)
        # bool first: Python would otherwise conflate true == 1.
        if isinstance(a, bool) or isinstance(b, bool):
            if not (isinstance(a, bool) and isinstance(b, bool) and a == b):
                return False
            continue
        if a is None or b is None:
            if a is not b:
                return False
            continue
        if isinstance(a, TupleValue) and isinstance(b, TupleValue):
            if len(a.items) != len(b.items):
                return False
            stack.extend(zip(reversed(a.items), reversed(b.items), strict=True))
            continue
        if isinstance(a, DataValue) and isinstance(b, DataValue):
            if a.constructor != b.constructor or len(a.fields) != len(b.fields):
                return False
            stack.extend(zip(reversed(a.fields), reversed(b.fields), strict=True))
            continue
        if isinstance(a, RecordValue) and isinstance(b, RecordValue):
            if a.name != b.name or a.field_order != b.field_order:
                return False
            stack.extend((a.fields[name], b.fields[name]) for name in reversed(a.field_order))
            continue
        # Functions and constructors have no structural equality: without this
        # guard, dataclass eq would call two same-shaped lambdas equal.
        callable_kinds = (FunctionValue, BuiltinFunction, ConstructorValue, PartialConstructorValue, RecordConstructorValue)
        if isinstance(a, callable_kinds) or isinstance(b, callable_kinds):
            if a is not b:
                return False
            continue
        # Int and Double are distinct types; the type checker rejects
        # `1 == 1.0`, so Python's numeric tower must not make it true here.
        if _is_number(a) and _is_number(b) and type(a) is not type(b):
            return False
        # Scalars (Int, Double, String, Unit) compare by value.
        if a != b:
            return False
    return True


def type_name(value: Value) -> str:
    """Name a value's type the way the type checker prints it, for diagnostics.

    Data values know their constructor but not their type, so `Some(1)` is
    reported as `Some`; lists (`Cons`/`Nil`) are reported as `List`.
    """
    value = force_value(value)
    if isinstance(value, bool):
        return "Bool"
    if isinstance(value, int):
        return "Int"
    if isinstance(value, float):
        return "Double"
    if isinstance(value, str):
        return "String"
    if value is None:
        return "null"
    if value == UNIT:
        return "Unit"
    if isinstance(value, DataValue):
        return "List" if value.constructor in ("Cons", "Nil") else value.constructor
    if isinstance(value, RecordValue):
        return value.name
    if isinstance(value, TupleValue):
        return "Tuple"
    if _format_callable(value) is not None:
        return "function"
    return type(value).__name__


def _is_number(value: Value) -> bool:
    # bool is a subclass of int in Python; in Lune, Bool is not a number.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def require_bool(value: Value, context: str) -> bool:
    """Force `value` and return it as a bool, or raise RUN0006.

    Every place the type checker requires a Bool (`if`/`elif`/`while`
    conditions, `&&`/`||`/`!`, match guards, predicates, `not`) comes through
    here, so a program that skipped the type check (`lune --eval`) cannot
    fall back to Python truthiness, where `if 1` passes and `if ""` fails.
    """
    value = force_value(value)
    if not isinstance(value, bool):
        raise LuneRuntimeError(
            t("run.expected-bool", context=context, got=type_name(value)), hints=[t("hint.check-first")]
        )
    return value


def require_int(value: Value, func: str) -> int:
    """Force `value` and return it as an int, or raise RUN0006.

    Every builtin that takes an Int count (`take`, `drop`, `range`,
    `naturalsFrom`) comes through here. They used to write
    `int(force_value(...))`, which handed Python's own message to the user
    ("invalid literal for int() with base 10"), truncated a Double and read
    `true` as 1. As with `require_bool`, only a program that skipped the type
    check (`lune --eval`) can get here.
    """
    value = force_value(value)
    # bool is a subclass of int in Python; in Lune, Bool is not an Int.
    if not isinstance(value, int) or isinstance(value, bool):
        raise LuneRuntimeError(
            t("run.expects", func=func, expected="Int", got=format_value(value)), hints=[t("hint.check-first")]
        )
    return value


def require_numeric_operands(op: str, left: Value, right: Value, *, plus: bool = False) -> None:
    """Reject non-numeric or mixed Int/Double operands of a binary operator.

    Mirrors the type checker (`require_numeric` + `require_assignable`): both
    operands must be Int or Double, and both the same. `plus` picks the
    message that also mentions Strings, which `+` accepts (two of them).
    """
    if not (_is_number(left) and _is_number(right)):
        got = dict(op=op, left=type_name(left), right=type_name(right))
        message = t("run.binary-plus", **got) if plus else t("run.binary-numeric", **got)
        raise LuneRuntimeError(message, hints=[t("hint.check-first")])
    if type(left) is not type(right):
        raise LuneRuntimeError(
            t("run.binary-mixed", op=op, left=type_name(left), right=type_name(right)),
            hints=[t("hint.check-first")],
        )


def _format_callable(value: Value) -> str | None:
    """Spec: VALUE_DISPLAY_SPEC.md §4 — callables display as `<fn name>` / `<fn>`."""
    if isinstance(value, (FunctionValue, BuiltinFunction)):
        return f"<fn {value.name}>" if value.name else "<fn>"
    if isinstance(value, (ConstructorValue, RecordConstructorValue)):
        return f"<fn {value.name}>"
    if isinstance(value, PartialConstructorValue):
        return f"<fn {value.constructor.name}>"
    return None


def format_value(value: Value) -> str:
    value = force_value(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if value == UNIT:
        return "()"
    if isinstance(value, RecordValue):
        items = ", ".join(f"{name} = {format_value(value.fields[name])}" for name in value.field_order)
        return f"{{ {items} }}" if items else "{}"
    if isinstance(value, DataValue):
        rendered_list = _try_render_list(value)
        if rendered_list is not None:
            return rendered_list
        if not value.fields:
            return value.constructor
        return f"{value.constructor}({', '.join(format_value(field) for field in value.fields)})"
    if isinstance(value, TupleValue):
        items = ", ".join(format_value(item) for item in value.items)
        if len(value.items) == 1:
            return f"({items},)"
        return f"({items})"
    rendered_callable = _format_callable(value)
    if rendered_callable is not None:
        return rendered_callable
    if isinstance(value, (int, float)):
        return repr(value)
    # Nothing else is a Lune value. Spec: VALUE_DISPLAY_SPEC.md §4 — never let
    # an evaluator object reach the user as a Python repr; name its shape the
    # way preview_value does instead.
    return f"<{type(value).__name__}>"


_PREVIEW_DEPTH = 3


def preview_value(value: Value, depth: int = _PREVIEW_DEPTH) -> str:
    """Render a value WITHOUT forcing anything.

    Unevaluated parts show as `<thunk>`, so the printed shape is exactly the
    part that has been computed so far (safe even for infinite streams).
    """
    if isinstance(value, (Thunk, LazyValue)):
        if value.state == ThunkState.EVALUATED:
            return preview_value(value.value, depth)
        if value.state == ThunkState.FAILED:
            return "<failed thunk>"
        return "<thunk>"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if value == UNIT:
        return "()"
    if isinstance(value, DataValue):
        if not value.fields:
            return value.constructor
        if depth <= 0:
            return f"{value.constructor}(…)"
        return f"{value.constructor}({', '.join(preview_value(field, depth - 1) for field in value.fields)})"
    if isinstance(value, RecordValue):
        if depth <= 0:
            return "{…}"
        items = ", ".join(f"{name} = {preview_value(value.fields[name], depth - 1)}" for name in value.field_order)
        return f"{{ {items} }}" if items else "{}"
    if isinstance(value, TupleValue):
        if depth <= 0:
            return "(…)"
        items = ", ".join(preview_value(item, depth - 1) for item in value.items)
        return f"({items},)" if len(value.items) == 1 else f"({items})"
    rendered_callable = _format_callable(value)
    if rendered_callable is not None:
        return rendered_callable
    if isinstance(value, (int, float)):
        return repr(value)
    return f"<{type(value).__name__}>"


def _try_render_list(value: DataValue) -> str | None:
    if value.constructor == "Nil":
        return "()"
    if value.constructor != "Cons":
        return None

    items: list[str] = []
    current: Value = value
    while True:
        current = force_value(current)
        if isinstance(current, DataValue) and current.constructor == "Nil":
            return f"({' '.join(items)})"
        if not isinstance(current, DataValue) or current.constructor != "Cons" or len(current.fields) != 2:
            return None
        items.append(format_value(current.fields[0]))
        current = _forced_tail(current)


def _show_value(value: Value) -> str:
    return format_value(value)
