from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import sys
from typing import Iterable, TextIO

from . import __version__
from . import nodes as ast
from .diagnostics import (
    Diagnostic,
    DiagnosticError,
    SourceMap,
    SourceSpan,
    format_diagnostic,
    format_exception,
)
from .evaluator import (
    Env,
    LazyValue,
    Thunk,
    ThunkState,
    eval_module_into,
    force_value,
    format_value,
    initial_env,
    preview_value,
    set_trace_hook,
)
from .explanations import LANGUAGES, render_explanation
from .messages import get_language, set_language, t
from .module_loader import (
    ModuleLoadError,
    check_python_import,
    define_external_imports,
    is_external_import,
    load_program,
    resolve_module_path,
)
from .parser import parse_source
from .tokens import LuneSyntaxError
from .typechecker import LuneTypeError, TypeEnv, check_module_into, initial_type_env


REPL_VALUE = "__repl_value"
# A bare expression is parsed as a declaration; spans must be mapped back afterwards.
EXPRESSION_WRAPPER = f"let {REPL_VALUE} = "
DECLARATION_PREFIXES = (
    "module ",
    "import ",
    "let ",
    "strict let ",
    "var ",
    "def ",
    "type ",
    "record ",
    "class ",
    "interface ",
)


@dataclass(frozen=True)
class ReplResult:
    kind: str
    message: str
    value: object | None = None
    type_repr: str | None = None
    warnings: tuple = ()


@dataclass
class PendingBinding:
    """A lazy top-level binding whose type check is waiting on another name.

    Lune's top-level bindings are lazy, so `let main = greet("world")` is a
    fine thing to type before `greet` exists: nothing runs until `main` is
    forced, and a file would have accepted the same two declarations in
    either order. The REPL therefore treats its inputs as one module built
    up over time. The binding is evaluated into the environment (as a
    thunk, or a closure for `def`) right away; its *type check* is replayed
    once the missing name arrives. Until then the name has no type, and
    using it reports the original TYP0001 for the missing name.
    """

    name: str
    module: ast.ModuleFile
    missing: str
    diagnostic: Diagnostic


class ReplSession:
    def __init__(self, module_paths: Iterable[str | Path] = (), source_map: SourceMap | None = None):
        self.type_env = initial_type_env()
        self.eval_env = initial_env()
        self.trace_enabled = False
        # Where `import` looks. A REPL has no entry file to sit beside, so the
        # working directory takes that role; --module-path adds to it exactly
        # as it does for a file.
        self.module_paths = [Path(path) for path in module_paths]
        # Imported sources have to reach the caller's map or their diagnostics
        # render without the offending line.
        self.source_map = source_map
        self._loaded_modules: set[Path] = set()
        self._pending: dict[str, PendingBinding] = {}

    def submit(self, source: str, filename: str = "<repl>") -> ReplResult:
        source = source.strip("\n")
        if not source.strip():
            return ReplResult("empty", "")
        if source.lstrip().startswith(":"):
            return self.run_command(source.strip())

        module, is_expr = self._parse_input(source, filename)
        if not is_expr:
            return self._run(module, is_expr)
        try:
            result = self._run(module, is_expr)
        except DiagnosticError as exc:
            exc.diagnostic = _unwrap_expression_spans(exc.diagnostic, filename)
            raise
        return replace(
            result,
            warnings=tuple(_unwrap_expression_spans(warning, filename) for warning in result.warnings),
        )

    def _search_roots(self) -> list[Path]:
        return [Path.cwd().resolve(), *(path.resolve() for path in self.module_paths)]

    def _load_imports(self, module: ast.ModuleFile) -> None:
        """Bring the modules an `import` names into the session.

        Without this the typechecker binds the imported *name* to `Any` and
        nothing is loaded, so the REPL answered `ok` and then reported every
        function in the module as undefined.
        """
        roots = self._search_roots()
        for import_decl in module.imports:
            if is_external_import(import_decl.path):
                check_python_import(import_decl)
                continue                      # java.* stays opaque; python.* binds lazily
            resolved = resolve_module_path(import_decl.path, roots)
            if resolved is None:
                raise ModuleLoadError(
                    t("mod.not-found", path=import_decl.path),
                    "MOD0001",
                    import_decl.span,
                    t("label.module-not-found"),
                    [t("hint.module-searched", roots=", ".join(str(root) for root in roots))],
                )
            program = load_program(
                resolved, self.module_paths, self.source_map, entry_import_path=import_decl.path
            )
            for loaded in program.modules:    # dependencies first
                if loaded.path in self._loaded_modules:
                    continue
                define_external_imports(loaded.module, self.type_env)
                check_module_into(loaded.module, self.type_env, process_imports=False)
                eval_module_into(loaded.module, self.eval_env)
                self._loaded_modules.add(loaded.path)

    def _run(self, module: ast.ModuleFile, is_expr: bool) -> ReplResult:
        type_snapshot = _clone_type_env(self.type_env)
        warning_start = len(self.type_env.warnings)
        declared = _declared_names(module)
        try:
            self._load_imports(module)
            # Imports are resolved above, so the name must not also be bound to
            # `Any` — that is what hid the real declarations (`process_imports`
            # is how module_loader.check_file draws the same line).
            define_external_imports(module, self.type_env)
            check_module_into(module, self.type_env, process_imports=False)
        except LuneTypeError as exc:
            self.type_env = type_snapshot
            if not is_expr and self._can_defer(module, exc):
                return self._defer(module, exc)
            raise self._with_pending_context(exc) from None
        except Exception:
            self.type_env = type_snapshot
            raise
        warnings = tuple(self.type_env.warnings[warning_start:])
        del self.type_env.warnings[warning_start:]
        # A redefinition supersedes whatever was still waiting under that name.
        for name in declared:
            self._pending.pop(name, None)

        trace_lines: list[str] = []
        if self.trace_enabled:
            set_trace_hook(lambda depth, message: trace_lines.append("  " * depth + message))
        try:
            eval_module_into(module, self.eval_env)
            if is_expr:
                value = force_value(self.eval_env.lookup_raw(REPL_VALUE))
                typ = self.type_env.lookup_value(REPL_VALUE)
                rendered = format_value(value)
        finally:
            if self.trace_enabled:
                set_trace_hook(None)

        if is_expr:
            message = "\n".join([*trace_lines, f"{rendered} : {typ!r}"])
            return ReplResult("value", message, value, repr(typ), warnings)
        notes, resolution_errors = self._resolve_pending()
        message = "\n".join([*trace_lines, "ok", *(f"   = note: {note}" for note in notes)])
        return ReplResult("ok", message, warnings=(*warnings, *resolution_errors))

    # --- forward references -------------------------------------------------

    def _can_defer(self, module: ast.ModuleFile, exc: LuneTypeError) -> bool:
        """Whether a TYP0001 from `module` may wait instead of being an error.

        Only when every declaration is lazy at the top level — a plain
        `let name = ...` (a thunk) or a `def` (a closure) — and the missing
        name is one the session does not know yet. `strict let`, `var` and
        pattern `let`s evaluate on the spot, so they cannot wait; a name the
        session *does* know is a real type error, not a forward reference.
        """
        missing = exc.undefined_name
        if missing is None or not module.declarations:
            return False
        if missing in self.type_env.values or missing in _declared_names(module):
            return False
        return all(_is_lazy_top_level(decl) for decl in module.declarations)

    def _defer(self, module: ast.ModuleFile, exc: LuneTypeError) -> ReplResult:
        assert exc.undefined_name is not None
        notes = []
        for name in _declared_names(module):
            self._pending[name] = PendingBinding(name, module, exc.undefined_name, exc.diagnostic)
            notes.append(t("repl.deferred", missing=exc.undefined_name, name=name))
        # The binding itself is lazy, so evaluating the declaration binds a
        # thunk (or closure) and runs nothing.
        eval_module_into(module, self.eval_env)
        return ReplResult("ok", "\n".join(["ok", *(f"   = note: {note}" for note in notes)]))

    def _with_pending_context(self, exc: LuneTypeError) -> DiagnosticError:
        """Using a pending name reports *why* it is unusable: the original
        diagnostic for the name it is waiting on, pointing at the input that
        introduced it."""
        pending = self._pending.get(exc.undefined_name or "")
        if pending is None:
            return exc
        hint = t("hint.waiting-for", name=pending.name, missing=pending.missing)
        return DiagnosticError(replace(pending.diagnostic, hints=[*pending.diagnostic.hints, hint]))

    def _resolve_pending(self) -> tuple[list[str], list[Diagnostic]]:
        """Replay the type check of every binding whose missing name now exists.

        Runs to a fixpoint, because resolving one binding can unblock another
        (`a` waits on `b`, which waits on the name just defined). A binding
        that fails for some other reason once its dependency exists stays
        pending with that error, so using it reports the real problem.
        """
        notes: list[str] = []
        errors: list[Diagnostic] = []
        progress = True
        while progress:
            progress = False
            for name, pending in list(self._pending.items()):
                if pending.missing not in self.type_env.values:
                    continue
                snapshot = _clone_type_env(self.type_env)
                warning_start = len(self.type_env.warnings)
                try:
                    check_module_into(pending.module, self.type_env, process_imports=False)
                except LuneTypeError as exc:
                    self.type_env = snapshot
                    if exc.undefined_name is not None and exc.undefined_name not in self.type_env.values:
                        # Still a forward reference, to the next missing name.
                        pending.missing = exc.undefined_name
                        pending.diagnostic = exc.diagnostic
                    else:
                        pending.diagnostic = exc.diagnostic
                        errors.append(exc.diagnostic)
                    continue
                del self.type_env.warnings[warning_start:]
                del self._pending[name]
                notes.append(t("repl.resolved", name=name, type=repr(self.type_env.lookup_value(name))))
                progress = True
        return notes, errors

    def run_command(self, command: str) -> ReplResult:
        parts = command.split()
        name = parts[0]
        if name in {":quit", ":q"}:
            return ReplResult("quit", "bye")
        if name == ":help":
            return ReplResult(
                "info",
                "commands: :help, :quit, :q, :env, :type NAME, :thunks [NAME], :trace [on|off], :lang [en|ja], :explain CODE [en|ja]",
            )
        if name == ":env":
            public = sorted(key for key in self.type_env.values if not key.startswith("__"))
            lines = [f"{key} : {self.type_env.values[key]!r}" for key in public]
            lines.extend(
                f"{key} : ? (waiting for {self._pending[key].missing})" for key in sorted(self._pending)
            )
            return ReplResult("info", "\n".join(lines))
        if name == ":type":
            if len(parts) != 2:
                return ReplResult("error", "usage: :type NAME")
            if parts[1] in self._pending:
                return ReplResult("info", f"{parts[1]} : ? (waiting for {self._pending[parts[1]].missing})")
            typ = self.type_env.lookup_value(parts[1])
            return ReplResult("info", f"{parts[1]} : {typ!r}")
        if name == ":thunks":
            if len(parts) > 2:
                return ReplResult("error", "usage: :thunks [NAME]")
            if len(parts) == 2:
                target = parts[1]
                if target not in self.eval_env.values:
                    return ReplResult("error", f"unknown name: {target}")
                return ReplResult("info", _describe_binding(target, self.eval_env.values[target]))
            lines = [
                _describe_binding(key, value)
                for key, value in self.eval_env.values.items()
                if not key.startswith("__") and isinstance(value, (Thunk, LazyValue))
            ]
            if not lines:
                return ReplResult("info", "no thunks: nothing is bound lazily yet (try `let x = 1 + 1`)")
            return ReplResult("info", "\n".join(lines))
        if name == ":lang":
            if len(parts) == 1:
                return ReplResult("info", f"language is {get_language()}")
            if len(parts) == 2 and parts[1] in LANGUAGES:
                set_language(parts[1])
                return ReplResult("info", f"language: {parts[1]}")
            return ReplResult("error", "usage: :lang [en|ja]")
        if name == ":trace":
            if len(parts) == 1:
                return ReplResult("info", f"trace is {'on' if self.trace_enabled else 'off'}")
            if len(parts) == 2 and parts[1] in {"on", "off"}:
                self.trace_enabled = parts[1] == "on"
                return ReplResult("info", f"trace {parts[1]}")
            return ReplResult("error", "usage: :trace [on|off]")
        if name == ":explain":
            if len(parts) not in {2, 3} or (len(parts) == 3 and parts[2] not in LANGUAGES):
                return ReplResult("error", "usage: :explain CODE [en|ja]")
            lang = parts[2] if len(parts) == 3 else get_language()
            text = render_explanation(parts[1], lang)
            if text is None:
                return ReplResult("error", f"no explanation for diagnostic code {parts[1]!r}")
            return ReplResult("info", text)
        return ReplResult("error", f"unknown command: {name}")

    def _parse_input(self, source: str, filename: str) -> tuple[ast.ModuleFile, bool]:
        normalized = _ensure_trailing_newline(source)
        if source.lstrip().startswith(DECLARATION_PREFIXES):
            return parse_source(normalized, filename), False
        try:
            return parse_source(normalized, filename), False
        except LuneSyntaxError:
            try:
                return parse_source(EXPRESSION_WRAPPER + normalized, filename), True
            except LuneSyntaxError as exc:
                exc.diagnostic = _unwrap_expression_spans(exc.diagnostic, filename)
                raise


def repl_main(stdin: TextIO, stdout: TextIO, stderr: TextIO, module_paths: Iterable[str | Path] = ()) -> int:
    source_map = SourceMap()
    session = ReplSession(module_paths, source_map)
    input_index = 1
    line_editor = _configure_line_editor(stdin, stdout)
    stdout.write(f"Lune v{__version__} REPL. Type :help or :quit.\n")
    buffer: list[str] = []

    while True:
        prompt = "... " if buffer else "lune> "
        line = _read_line(prompt, stdin, stdout, line_editor)
        if line == "":
            stdout.write("\n")
            return 0

        if buffer:
            if not line.strip():
                source = "".join(buffer)
                buffer.clear()
            else:
                buffer.append(line)
                continue
        else:
            if wants_more(line):
                buffer.append(line)
                continue
            source = line

        try:
            filename = f"<repl:{input_index}>"
            input_index += 1
            source_map.add(filename, source)
            result = session.submit(source, filename)
            if result.kind == "empty":
                continue
            for warning in result.warnings:
                stderr.write(format_diagnostic(warning, source_map, explain_hint=True) + "\n")
            stdout.write(result.message + "\n")
            if result.kind == "quit":
                return 0
        except Exception as exc:
            stderr.write(format_exception(exc, source_map, explain_hint=True) + "\n")


def _declared_names(module: ast.ModuleFile) -> list[str]:
    """Top-level names a module input binds, for the deferral bookkeeping."""
    names: list[str] = []
    for decl in module.declarations:
        if isinstance(decl, ast.LetDecl) and isinstance(decl.pattern, ast.NamePattern):
            names.append(decl.pattern.name)
        elif isinstance(decl, ast.FunctionDecl | ast.VarDecl):
            names.append(decl.name)
    return names


def _is_lazy_top_level(decl: ast.Decl) -> bool:
    """A declaration the evaluator binds without running anything."""
    if isinstance(decl, ast.LetDecl):
        return isinstance(decl.pattern, ast.NamePattern) and not decl.is_strict
    return isinstance(decl, ast.FunctionDecl)


def _describe_binding(name: str, value: object) -> str:
    if not isinstance(value, (Thunk, LazyValue)):
        return f"{name} : value = {preview_value(value)}"
    if value.state == ThunkState.EVALUATED:
        return f"{name} : evaluated = {preview_value(value.value)}"
    if value.state == ThunkState.FAILED:
        error = value.error
        if isinstance(error, DiagnosticError):
            return f"{name} : failed = error[{error.diagnostic.code}] {error.diagnostic.message}"
        return f"{name} : failed = {error}"
    if value.state == ThunkState.EVALUATING:
        return f"{name} : evaluating"
    return f"{name} : unevaluated"


def _unwrap_expression_spans(diagnostic: Diagnostic, filename: str) -> Diagnostic:
    """Map spans off the `let __repl_value = ` wrapper and back onto what the user typed.

    Expression input is parsed wrapped but rendered unwrapped, so spans over the wrapped
    text would otherwise point past the end of the source snippet. The wrapper adds no
    newline, so only columns on the first line move.
    """
    if diagnostic.primary is None and not diagnostic.fixes:
        return diagnostic
    primary = diagnostic.primary
    if primary is not None:
        primary = replace(primary, span=_unwrap_span(primary.span, filename))
    return replace(
        diagnostic,
        primary=primary,
        fixes=[replace(fix, span=_unwrap_span(fix.span, filename)) for fix in diagnostic.fixes],
    )


def _unwrap_span(span: SourceSpan, filename: str) -> SourceSpan:
    if span.filename != filename:
        return span
    offset = len(EXPRESSION_WRAPPER)
    start_column = span.start_column - offset if span.start_line == 1 else span.start_column
    end_column = span.end_column - offset if span.end_line == 1 else span.end_column
    return replace(
        span,
        start_column=max(start_column, 1),
        end_column=max(end_column, 1),
    )


def _ensure_trailing_newline(source: str) -> str:
    return source if source.endswith("\n") else source + "\n"


def wants_more(line: str) -> bool:
    """True when `line` opens a block and the REPL should keep reading.

    Public because the terminal loop is not the only REPL front end: the
    browser playground drives `ReplSession` directly and needs the same
    continuation rule, and two copies of it would drift.
    """
    stripped = line.rstrip()
    return stripped.endswith(":") or stripped.endswith("=") or stripped.endswith("->")


def _configure_line_editor(stdin: TextIO, stdout: TextIO) -> bool:
    if stdin is not sys.stdin or stdout is not sys.stdout:
        return False
    if not getattr(stdin, "isatty", lambda: False)() or not getattr(stdout, "isatty", lambda: False)():
        return False
    try:
        import atexit
        import os
        import readline
    except ImportError:
        return True

    history_file = os.path.expanduser("~/.lune_history")
    try:
        readline.read_history_file(history_file)
    except FileNotFoundError:
        pass
    except OSError:
        pass
    try:
        readline.set_history_length(1000)
    except AttributeError:
        pass

    def save_history() -> None:
        try:
            readline.write_history_file(history_file)
        except OSError:
            pass

    atexit.register(save_history)
    return True


def _read_line(prompt: str, stdin: TextIO, stdout: TextIO, line_editor: bool) -> str:
    if line_editor:
        try:
            return input(prompt) + "\n"
        except EOFError:
            return ""
    stdout.write(prompt)
    stdout.flush()
    return stdin.readline()


def _clone_type_env(env: TypeEnv) -> TypeEnv:
    clone = TypeEnv(env.parent)
    clone.values = dict(env.values)
    clone.constructors = dict(env.constructors)
    clone.types = dict(env.types)
    clone.records = dict(env.records)
    clone.warnings = list(env.warnings)
    return clone
