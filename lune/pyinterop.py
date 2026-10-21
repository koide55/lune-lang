"""Python interop: `import python.X` and the `Py` values it produces.

Spec: documents/PYTHON_INTEROP_SPEC.md. Everything that crosses between Lune
and Python goes through this module, so the evaluator only has to recognise a
`PyObject` and hand it over:

- Lune -> Python is implicit. Arguments, index keys and operands are forced
  and converted by `to_python` (spec §5.1). A Lune function becomes a Python
  callable that takes Py arguments (spec §5.5).
- Python -> Lune is explicit. Every result is wrapped in a `PyObject`, and only
  the `as*` builtins turn one back into a Lune value (spec §6).
- A Python exception becomes `RUN0007` (spec §9). Python's own traceback is
  hidden unless `--py-traceback` asked for it.

Like the active language (messages.set_language), the two switches below are
process-wide and set once at the CLI entry point.
"""

from __future__ import annotations

import dataclasses
import difflib
import importlib
import importlib.util
import numbers
import operator
import sys
import traceback

from . import nodes as ast
from .diagnostics import DiagnosticError
from .evaluator import (
    UNIT,
    BuiltinFunction,
    ConstructorValue,
    DataValue,
    Env,
    FunctionValue,
    LazyValue,
    LuneRuntimeError,
    PartialConstructorValue,
    PyObject,
    RecordConstructorValue,
    TupleValue,
    _forced_tail,
    apply_function,
    apply_value,
    force_value,
    type_name,
)
from .messages import t
from .typechecker import is_python_import, python_module_name

_enabled = True
_show_traceback = False


def set_enabled(enabled: bool) -> None:
    """`--no-python` / `LUNE_PYTHON=off` turn every `python.*` import into MOD0004."""
    global _enabled
    _enabled = enabled


def is_enabled() -> bool:
    return _enabled


def set_show_traceback(show: bool) -> None:
    global _show_traceback
    _show_traceback = show


# --- import ------------------------------------------------------------------


def module_exists(name: str) -> bool:
    """Whether `name` can be imported, without importing it (spec §3.2).

    `find_spec` on a submodule imports its parent package; an error raised
    while doing that is not "missing", so it is left for the real import to
    report as RUN0007 with the actual exception.
    """
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False
    except Exception:
        return True


def install_hint(name: str) -> str:
    if sys.platform == "emscripten":
        # The Playground (Pyodide): there is no pip to point at, and the page
        # loads every package Pyodide has before the program is checked.
        return t("hint.python-playground")
    return t("hint.python-install", python=sys.executable or "python3", package=name.split(".", 1)[0])


def bind_imports(module: ast.ModuleFile, env: Env) -> None:
    """Bind each `import python.X` of `module` to the module, imported lazily.

    The import itself waits until the name is first forced: a program pays for
    `import python.torch` only on the path that uses it.
    """
    for import_decl in module.imports:
        if not is_python_import(import_decl.path):
            continue
        name = import_decl.alias or import_decl.path.rsplit(".", 1)[-1]
        env.define(name, LazyValue(lambda module_name=python_module_name(import_decl.path): _import(module_name)))


def _import(name: str) -> PyObject:
    if not _enabled:
        raise LuneRuntimeError(t("mod.python-disabled", name=name), code="MOD0004", hints=[t("hint.python-disabled")])
    try:
        return PyObject(importlib.import_module(name))
    except ModuleNotFoundError as exc:
        if exc.name is not None and (name == exc.name or name.startswith(exc.name + ".")):
            raise LuneRuntimeError(t("mod.python-not-found", name=name), code="MOD0004", hints=[install_hint(name)]) from exc
        raise python_error(exc) from exc
    except Exception as exc:
        raise python_error(exc) from exc


# --- errors ------------------------------------------------------------------


def python_error(exc: BaseException) -> LuneRuntimeError:
    """Report a Python exception as RUN0007: its type and first line in the
    message, any further lines as notes, the traceback only on request."""
    lines = [line.rstrip() for line in str(exc).splitlines()]
    summary = f"{type(exc).__name__}: {lines[0]}" if lines else type(exc).__name__
    error = LuneRuntimeError(t("run.python-exception", exc=summary), code="RUN0007")
    notes = lines[1:]
    if _show_traceback:
        notes += [line for chunk in traceback.format_exception(exc) for line in chunk.rstrip("\n").splitlines()]
        hints: list[str] = []
    else:
        hints = [t("hint.py-traceback")]
    error.diagnostic = dataclasses.replace(error.diagnostic, notes=notes, hints=hints)
    return error


def _guard(compute):
    """Run Python code and wrap its result; translate what it raises.

    A Lune diagnostic raised underneath passes through unchanged, and so do
    KeyboardInterrupt and SystemExit, which are not Exceptions.
    """
    try:
        return PyObject(compute())
    except DiagnosticError:
        raise
    except Exception as exc:
        raise python_error(exc) from exc


# --- Lune -> Python ----------------------------------------------------------

# What Python can call. A record constructor is missing on purpose: it takes
# only named fields, and a Python callback is called positionally.
_CALLABLE_KINDS = (FunctionValue, BuiltinFunction, ConstructorValue, PartialConstructorValue)


def _as_python_callable(function):
    """A Lune function as a Python callable (spec §5.5).

    Python's arguments arrive as Py values and the result goes back through
    `to_python`, forced in full: the call is a strict boundary in this
    direction too. A Lune error raised inside passes through the Python code
    that called it and reaches the user unchanged, because `_guard` lets
    diagnostics through.
    """
    name = getattr(function, "name", None) or "<lambda>"
    params = function.params if isinstance(function, FunctionValue) else None

    def call_from_python(*args, **kwargs):
        if kwargs:
            raise TypeError(f"Lune function `{name}` takes no keyword arguments")
        if params is not None and len(args) != len(params):
            # Currying would turn too few arguments into a function handed
            # back to Python, which is never what the Python side meant.
            expected = f"{len(params)} argument" + ("" if len(params) == 1 else "s")
            raise TypeError(f"Lune function `{name}` takes {expected}, got {len(args)}")
        values = [PyObject(arg) for arg in args]
        if params is not None and not params:
            result = apply_function(function, [])
        else:
            result = apply_value(function, values)
        return to_python(result)

    call_from_python.__name__ = call_from_python.__qualname__ = name
    return call_from_python


def to_python(value) -> object:
    """Force a Lune value and convert it for Python (spec §5.1).

    A list is converted in full, so it must be finite: `toPy(naturalsFrom(0))`
    never returns, exactly as `length(naturalsFrom(0))` does not.
    """
    value = force_value(value)
    if isinstance(value, PyObject):
        return value.obj
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, tuple) and value == UNIT:
        return None
    if isinstance(value, TupleValue):
        return tuple(to_python(item) for item in value.items)
    if isinstance(value, DataValue) and value.constructor in ("Cons", "Nil"):
        items = []
        current = value
        while isinstance(current, DataValue) and current.constructor == "Cons":
            items.append(to_python(current.fields[0]))
            current = _forced_tail(current)
        return items
    if isinstance(value, _CALLABLE_KINDS):
        return _as_python_callable(value)
    raise LuneRuntimeError(t("run.py-unconvertible", type=type_name(value)), hints=[t("hint.py-convertible")])


# --- operations on Py values -------------------------------------------------

BINARY_OPS = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": operator.truediv,
    "//": operator.floordiv,
    "%": operator.mod,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
}

UNARY_OPS = {"-": operator.neg, "+": operator.pos}


def call(callee: PyObject, args: list, kwargs: list[tuple[str, object]]) -> PyObject:
    py_args = [to_python(arg) for arg in args]
    py_kwargs: dict[str, object] = {}
    for name, value in kwargs:
        if name in py_kwargs:
            raise LuneRuntimeError(t("run.py-duplicate-kwarg", name=name))
        py_kwargs[name] = to_python(value)
    return _guard(lambda: callee.obj(*py_args, **py_kwargs))


def get_attr(receiver: PyObject, name: str) -> PyObject:
    try:
        return _guard(lambda: getattr(receiver.obj, name))
    except LuneRuntimeError as error:
        if not isinstance(error.__cause__, AttributeError):
            raise
        # The one Python error a typo produces: offer the closest attribute,
        # the way TYP0001 offers the closest name.
        try:
            candidates = [attr for attr in dir(receiver.obj) if not attr.startswith("_")]
        except Exception:
            candidates = []
        match = difflib.get_close_matches(name, candidates, n=1, cutoff=0.6)
        if match:
            hints = [t("hint.did-you-mean", name=match[0]), *error.diagnostic.hints]
            error.diagnostic = dataclasses.replace(error.diagnostic, hints=hints)
        raise


def get_item(receiver: PyObject, keys: list) -> PyObject:
    converted = [to_python(key) for key in keys]
    key = converted[0] if len(converted) == 1 else tuple(converted)
    return _guard(lambda: receiver.obj[key])


def binary(op: str, left, right) -> PyObject:
    function = BINARY_OPS[op]
    a, b = to_python(left), to_python(right)
    return _guard(lambda: function(a, b))


def unary(op: str, value: PyObject) -> PyObject:
    function = UNARY_OPS[op]
    return _guard(lambda: function(value.obj))


def equal(left, right) -> bool:
    """`==` between Py values nested inside Lune values (`[a] == [b]`).

    Only a single truth value can decide structural equality. An array
    comparison yields an array, which is the ambiguity Lune refuses to resolve
    by truthiness.
    """
    a, b = to_python(left), to_python(right)
    result = _guard(lambda: a == b).obj
    if not _is_bool(result):
        raise LuneRuntimeError(
            t("run.py-equality", pytype=type(result).__name__), hints=[t("hint.py-array-equal")]
        )
    return bool(result)


def iterate(value: PyObject):
    """A Python iterable as a lazy Lune list (spec §6.3).

    Each cell calls `next()` when it is forced and is memoised like every lazy
    cell, so a stateful iterator advances exactly once per element however
    often the list is walked.
    """
    try:
        iterator = iter(value.obj)
    except TypeError as exc:
        raise LuneRuntimeError(t("run.py-not-iterable", pytype=type(value.obj).__name__)) from exc
    except Exception as exc:
        raise python_error(exc) from exc

    def cell():
        try:
            item = next(iterator)
        except StopIteration:
            return DataValue("Nil", [])
        except DiagnosticError:
            raise
        except Exception as exc:
            raise python_error(exc) from exc
        return DataValue("Cons", [PyObject(item), LazyValue(cell)])

    return cell()


def format_py(value: PyObject) -> str:
    try:
        return str(value.obj)
    except Exception:
        return f"<py {type(value.obj).__name__}>"


# --- Python -> Lune: the prelude builtins ------------------------------------


def _is_bool(obj: object) -> bool:
    # numpy.bool_ is not a bool subclass; under NumPy 2 its class is named `bool`.
    return isinstance(obj, bool) or type(obj).__name__ in ("bool", "bool_")


def _expect_py(function: str, value) -> object:
    # The type checker guarantees a Py argument; `--eval` does not.
    if not isinstance(value, PyObject):
        raise LuneRuntimeError(t("run.py-expected-py", fn=function, type=type_name(value)), hints=[t("hint.check-first")])
    return value.obj


def _cannot_convert(function: str, target: str, obj: object) -> LuneRuntimeError:
    return LuneRuntimeError(
        t("run.py-convert", fn=function, pytype=type(obj).__name__, type=target), hints=[t("hint.py-item")]
    )


def _as_int(args: list):
    obj = _expect_py("asInt", args[0])
    if isinstance(obj, numbers.Integral) and not _is_bool(obj):
        return int(obj)
    raise _cannot_convert("asInt", "Int", obj)


def _as_double(args: list):
    obj = _expect_py("asDouble", args[0])
    if isinstance(obj, numbers.Real) and not _is_bool(obj):
        return float(obj)
    raise _cannot_convert("asDouble", "Double", obj)


def _as_string(args: list):
    obj = _expect_py("asString", args[0])
    if isinstance(obj, str):
        return str(obj)
    raise _cannot_convert("asString", "String", obj)


def _as_bool(args: list):
    # Never truthiness: `asBool(np.array([1, 2]))` must fail here the way
    # `if 1` fails in require_bool, not pick an answer.
    obj = _expect_py("asBool", args[0])
    if _is_bool(obj):
        return bool(obj)
    raise _cannot_convert("asBool", "Bool", obj)


def _as_list(args: list):
    _expect_py("asList", args[0])
    return iterate(args[0])


def _as_nullable(args: list):
    obj = _expect_py("asNullable", args[0])
    return None if obj is None else args[0]


def _to_py(args: list):
    return PyObject(to_python(args[0]))


def _py_str(args: list):
    obj = _expect_py("pyStr", args[0])
    try:
        return str(obj)
    except Exception as exc:
        raise python_error(exc) from exc


def _py_slice(args: list):
    bounds = []
    for value in args:
        if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
            raise LuneRuntimeError(t("run.py-slice-bound", type=type_name(value)), hints=[t("hint.check-first")])
        bounds.append(value)
    return PyObject(slice(*bounds))


def register_builtins(env: Env) -> None:
    env.define("asInt", BuiltinFunction("asInt", _as_int))
    env.define("asDouble", BuiltinFunction("asDouble", _as_double))
    env.define("asString", BuiltinFunction("asString", _as_string))
    env.define("asBool", BuiltinFunction("asBool", _as_bool))
    env.define("asList", BuiltinFunction("asList", _as_list))
    env.define("asNullable", BuiltinFunction("asNullable", _as_nullable))
    env.define("toPy", BuiltinFunction("toPy", _to_py))
    env.define("pyStr", BuiltinFunction("pyStr", _py_str))
    env.define("pySlice", BuiltinFunction("pySlice", _py_slice))
