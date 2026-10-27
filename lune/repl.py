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
    forced, and a file accepts `def greet(...): String` written below it.
    The REPL therefore treats its inputs as one module built up over time.
    The binding is evaluated into the environment (as a thunk, or a closure
    for `def`) right away; its *type check* is replayed once the missing
    name arrives. Until then the name has no type, and using it reports the
    original TYP0001 for the missing name.

    The REPL follows the file's rule for what may be used before it is
    defined: a `def` with a return type and a constructor. A missing name
    that turns out to be a `let`, a `var` or a `def` without a return type
    fails the binding with the TYP0001 a file would have given, and the
    binding stays `failed` until something it waits on is defined again.
    """

    name: str
    module: ast.ModuleFile
    missing: str
    diagnostic: Diagnostic
    seq: int
    failed: bool = False


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
        # Inputs are numbered so the session knows the order a file would
        # have. `_late` holds the names a file cannot use above their
        # declaration (`let`, `var`, `def` without a return type) with the
        # input that declared them and which of the three they are.
        self._input_seq = 0
        self._late: dict[str, tuple[int, str]] = {}

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
        prepared: TypeEnv | None = None
        joined: list[PendingBinding] = []
        try:
            self._load_imports(module)
            # Imports are resolved above, so the name must not also be bound to
            # `Any` — that is what hid the real declarations (`process_imports`
            # is how module_loader.check_file draws the same line).
            define_external_imports(module, self.type_env)
            prepared = _clone_type_env(self.type_env)
            check_module_into(module, self.type_env, process_imports=False)
        except LuneTypeError as exc:
            self.type_env = type_snapshot
            pending = self._pending.get(exc.undefined_name or "")
            if is_expr or prepared is None or pending is None or pending.failed:
                if not is_expr and self._can_defer(module, exc):
                    return self._defer(module, exc)
                raise self._with_pending_context(exc) from None
            # The input uses a binding that is still waiting — typically the
            # second half of a mutual recursion. Check it together with what
            # it waits on, as one file would.
            outcome = self._check_with_pending(module, exc, prepared)
            if isinstance(outcome, ReplResult):
                return outcome
            self.type_env, joined = outcome
        except Exception:
            self.type_env = type_snapshot
            raise
        warnings = tuple(self.type_env.warnings[warning_start:])
        del self.type_env.warnings[warning_start:]
        # What this input bound: pending bindings waiting on any of these
        # names get another try.
        bound = set(self.type_env.values.keys() - type_snapshot.values.keys())
        self._input_seq += 1
        for name in _declared_names(module):
            bound.add(name)
            self._record_order(module, name, self._input_seq)
            # A redefinition supersedes whatever was still waiting under that name.
            self._pending.pop(name, None)
        notes: list[str] = []
        for pending in joined:
            if self._pending.pop(pending.name, None) is not None:
                bound.add(pending.name)
                self._record_order(pending.module, pending.name, pending.seq)
                notes.append(t("repl.resolved", name=pending.name, type=repr(self.type_env.lookup_value(pending.name))))

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
        resolved, resolution_diagnostics = self._resolve_pending(bound)
        notes.extend(resolved)
        message = "\n".join([*trace_lines, "ok", *(f"   = note: {note}" for note in notes)])
        return ReplResult("ok", message, warnings=(*warnings, *resolution_diagnostics))

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
        self._input_seq += 1
        notes = []
        for name in _declared_names(module):
            self._late.pop(name, None)
            self._pending[name] = PendingBinding(
                name, module, exc.undefined_name, exc.diagnostic, self._input_seq
            )
            notes.append(t("repl.deferred", missing=exc.undefined_name, name=name))
        # The binding itself is lazy, so evaluating the declaration binds a
        # thunk (or closure) and runs nothing.
        eval_module_into(module, self.eval_env)
        return ReplResult("ok", "\n".join(["ok", *(f"   = note: {note}" for note in notes)]))

    def _check_with_pending(
        self, module: ast.ModuleFile, exc: LuneTypeError, prepared: TypeEnv
    ) -> tuple[TypeEnv, list[PendingBinding]] | ReplResult:
        """Type-check `module` together with the pending inputs it reaches.

        This is the second half of a mutual recursion typed in two inputs.
        Returns the checked environment and the bindings it settled, or the
        result of deferring `module` when the group as a whole still waits on
        an undefined name.
        """
        try:
            return self._check_group([], exc.undefined_name, prepared, module)
        except LuneTypeError as merged_exc:
            missing = merged_exc.undefined_name
            if missing in self._pending and self._pending[missing].failed:
                raise self._with_pending_context(merged_exc) from None
            if missing is not None and missing not in self._pending and missing not in _declared_names(module):
                if self._can_defer(module, merged_exc):
                    return self._defer(module, merged_exc)
                raise self._with_pending_context(exc) from None
            raise

    def _check_group(
        self,
        group: list[PendingBinding],
        missing: str | None,
        base: TypeEnv,
        module: ast.ModuleFile | None = None,
    ) -> tuple[TypeEnv, list[PendingBinding]]:
        """Check pending inputs as one file, following what they wait on.

        Starting from `group`, every pending input reached through `missing`
        (and through each TYP0001 that names another waiting binding) joins,
        and the inputs are checked in the order they were typed, followed by
        `module` if given. That is the file those inputs would make, so
        `isEven` and `isOdd` find each other across inputs, while a `let`
        still cannot be used above its definition. Raises the TYP0001 (or
        other error) the group still has.
        """
        group = list(group)
        while True:
            while missing in self._pending and not self._pending[missing].failed:
                pending = self._pending[missing]
                if any(member.module is pending.module for member in group):
                    break
                group.extend(p for p in self._pending.values() if p.module is pending.module)
                missing = pending.missing
            modules: list[ast.ModuleFile] = []
            for member in sorted(group, key=lambda p: p.seq):
                if not any(seen is member.module for seen in modules):
                    modules.append(member.module)
            tail = list(module.declarations) if module is not None else []
            merged = replace(modules[0] if module is None else module,
                             declarations=[*(decl for m in modules for decl in m.declarations), *tail])
            env = _clone_type_env(base)
            if module is None:
                self._hide_late(env, min(p.seq for p in group), {p.name for p in group})
            try:
                check_module_into(merged, env, process_imports=False)
            except LuneTypeError as exc:
                missing = exc.undefined_name
                pending = self._pending.get(missing or "")
                if pending is not None and not pending.failed and not any(p.name == missing for p in group):
                    continue                      # reaches further pending inputs
                raise
            return env, group

    def _hide_late(self, env: TypeEnv, seq: int, keep: set[str]) -> None:
        """Remove from `env` what a file could not use at input `seq`."""
        for name, (declared_at, _) in self._late.items():
            if declared_at > seq and name not in keep:
                env.values.pop(name, None)

    def _with_pending_context(self, exc: LuneTypeError) -> DiagnosticError:
        """Using a pending name reports *why* it is unusable: the original
        diagnostic for the name it is waiting on, pointing at the input that
        introduced it. A failed binding's diagnostic already says why."""
        pending = self._pending.get(exc.undefined_name or "")
        if pending is None:
            return exc
        if pending.failed:
            return DiagnosticError(pending.diagnostic)
        hint = t("hint.waiting-for", name=pending.name, missing=pending.missing)
        return DiagnosticError(replace(pending.diagnostic, hints=[*pending.diagnostic.hints, hint]))

    def _resolve_pending(self, bound: set[str]) -> tuple[list[str], list[Diagnostic]]:
        """Retry the bindings waiting on a name this input just bound.

        The retry sees the session as a file would at the waiting input's
        position: names a file cannot use above their declaration (`_late`)
        are hidden when they were declared after it, so `let a = b + 1`
        followed by `let b = 2` is the same TYP0001 it is in a file. Runs to
        a fixpoint, because settling one binding binds its names too (`a`
        waits on `f`, which waits on the `g` just defined). Only newly bound
        names trigger a retry, so a binding that fails is reported once, not
        again on every later input.
        """
        notes: list[str] = []
        diagnostics: list[Diagnostic] = []
        progress = True
        while progress:
            progress = False
            for pending in self._unique_pending():
                if pending.missing not in bound:
                    continue
                members = [p for p in self._pending.values() if p.module is pending.module]
                names = [p.name for p in members]
                warning_start = len(self.type_env.warnings)
                try:
                    env, group = self._check_group(members, None, self.type_env)
                except LuneTypeError as exc:
                    missing = exc.undefined_name
                    late = self._late.get(missing or "")
                    if missing is not None and late is not None and late[0] > pending.seq:
                        # Defined, but where a file could not have used it.
                        hint = _late_hint(late[1], pending.name, missing)
                        self._fail(names, missing, replace(exc.diagnostic, hints=[*exc.diagnostic.hints, hint]))
                    elif (
                        missing is not None
                        and missing not in self.type_env.values
                        and (missing not in self._pending or self._pending[missing].failed)
                    ):
                        # Still a forward reference: to a name nobody has
                        # defined yet, or to one whose own check failed. (A
                        # waiting name in the group is an ordering error.)
                        for name in names:
                            self._pending[name].missing = missing
                            self._pending[name].diagnostic = exc.diagnostic
                            self._pending[name].failed = False
                        continue
                    else:
                        hint = t("hint.pending-failed", name=pending.name, missing=pending.missing)
                        self._fail(names, pending.missing, replace(exc.diagnostic, hints=[*exc.diagnostic.hints, hint]))
                    diagnostics.append(self._pending[pending.name].diagnostic)
                    continue
                diagnostics.extend(env.warnings[warning_start:])
                for member in sorted(group, key=lambda p: p.seq):
                    self.type_env.define_value(member.name, env.lookup_value(member.name))
                    self._record_order(member.module, member.name, member.seq)
                    del self._pending[member.name]
                    bound.add(member.name)
                    notes.append(t("repl.resolved", name=member.name, type=repr(self.type_env.lookup_value(member.name))))
                progress = True
                break                             # the pending set changed; rescan
        return notes, diagnostics

    def _record_order(self, module: ast.ModuleFile, name: str, seq: int) -> None:
        kind = _late_kind(module, name)
        if kind is None:
            self._late.pop(name, None)
        else:
            self._late[name] = (seq, kind)

    def _unique_pending(self) -> list[PendingBinding]:
        """One pending binding per input (an input may declare several names)."""
        seen: list[ast.ModuleFile] = []
        result: list[PendingBinding] = []
        for pending in sorted(self._pending.values(), key=lambda p: p.seq):
            if not any(module is pending.module for module in seen):
                seen.append(pending.module)
                result.append(pending)
        return result

    def _fail(self, names: list[str], missing: str, diagnostic: Diagnostic) -> None:
        """Mark an input's bindings failed. They still wait on `missing`, so
        defining it again (as a `def` with a return type, say) retries them."""
        for name in names:
            self._pending[name].missing = missing
            self._pending[name].diagnostic = diagnostic
            self._pending[name].failed = True

    def _pending_label(self, name: str) -> str:
        pending = self._pending[name]
        if pending.failed:
            return f"{name} : ? (failed: {pending.diagnostic.code})"
        return f"{name} : ? (waiting for {pending.missing})"

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
            lines.extend(self._pending_label(key) for key in sorted(self._pending))
            return ReplResult("info", "\n".join(lines))
        if name == ":type":
            if len(parts) != 2:
                return ReplResult("error", "usage: :type NAME")
            if parts[1] in self._pending:
                return ReplResult("info", self._pending_label(parts[1]))
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


def _late_kind(module: ast.ModuleFile, name: str) -> str | None:
    """Why a file could not use `name` above its declaration in `module`.

    None when it could: a `def` with a return type is predeclared, as are
    constructors (`predeclare_decl`). Otherwise "let", "var" or "def".
    """
    for decl in module.declarations:
        if isinstance(decl, ast.FunctionDecl) and decl.name == name:
            return None if decl.return_type is not None else "def"
        if isinstance(decl, ast.LetDecl) and isinstance(decl.pattern, ast.NamePattern) and decl.pattern.name == name:
            return "let"
        if isinstance(decl, ast.VarDecl) and decl.name == name:
            return "var"
    return None


def _late_hint(kind: str, name: str, missing: str) -> str:
    if kind == "let":
        return t("hint.defined-too-late-let", name=name, missing=missing)
    if kind == "var":
        return t("hint.defined-too-late-var", name=name, missing=missing)
    return t("hint.defined-too-late-def", name=name, missing=missing)


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
    clone.mutable = set(env.mutable)
    clone.constructors = dict(env.constructors)
    clone.types = dict(env.types)
    clone.records = dict(env.records)
    clone.warnings = list(env.warnings)
    return clone
