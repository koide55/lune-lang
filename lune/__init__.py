"""Lune — the Lazy and Native programming language.

Pure-Python reference implementation: lexer, layout, parser, type checker,
lazy evaluator, diagnostics (en/ja), formatter, fixer and REPL. Depends only
on the standard library.

`__version__` is the single source of truth for the release number:
`pyproject.toml` reads it via hatchling, and `lune --version` / the REPL banner
print it.
"""

__version__ = "0.1.0"

