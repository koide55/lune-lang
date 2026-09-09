# Appendix D: CLI and REPL Command Reference

Every feature of the `lune` command and the REPL. The story of how to use them is in chapter 11 (diagnostics) and chapter 12 (the tools); this is the place to look up "what was that argument again?".

Following the book's convention, `lune` means `./bin/lune` in the repository (or the `lune` installed by `pip install lune-lang`).

## D.1 Startup and modes

```console
$ lune [--lang en|ja] [--module-path DIR]... [MODE] [FILE]
```

The mode is one of the following, and **only one at a time**.

| Form | What it does |
| --- | --- |
| `lune` | with no arguments, start the REPL |
| `lune --repl` | start the REPL explicitly |
| `lune --check FILE` | type-check and stop; do not evaluate |
| `lune --eval NAME FILE` | read the file, evaluate the top-level binding `NAME` and print it |
| `lune --eval NAME --trace FILE` | as above, plus a commentary on forcing to stderr (chapter 4) |
| `lune --tokens FILE` | print the token stream after layout processing (chapter 12) |
| `lune FILE` | with no mode, print the syntax tree (AST) as it is |

The last line is the default, for developers. It is not meant to be read by people, so use `--check` or `--eval` in normal use.

`--eval` evaluates without type-checking. Running ill-typed code with `--eval` means the types of operators and conditions are checked at run time, giving `RUN0006` with a hint suggesting `lune --check`. The safe habit is to pass `--check` first.

## D.2 Global options

| Option | Effect |
| --- | --- |
| `--lang en\|ja` | the language of diagnostics; `--lang=ja` also works |
| `--module-path DIR` | add a module search root; **may be repeated** (chapter 10) |
| `--version` / `-V` | print the version and exit |
| `-h` / `--help` | print usage |

The relationship for the language is: the environment variable `LUNE_LANG` is the default, and the `--lang` flag wins over it.

```console
$ export LUNE_LANG=ja               # Japanese from here on
$ lune --lang en --check f.lune     # English, just this once
```

> **Note** — `--lang` does **not** appear in the list printed by `lune --help`, because it is handled before the other options. Do not forget it exists.

The version is worth quoting in a bug report.

```console
$ lune --version
lune 0.1.0
```

The line the REPL prints at startup carries the same number (`Lune v0.1.0 REPL.`). This book covers the v0.1 series.

## D.3 Subcommands

### `lune explain`

```console
$ lune explain CODE [--lang en|ja]
$ lune explain --index [--lang en|ja]
```

Prints the explanation of a diagnostic code. `--index` prints the explanations of every code, which is exactly what `documents/ERROR_INDEX.md` is (appendix C).

Give it a code it does not know and it tells you which codes it does.

### `lune fmt` / `lune fix`

```console
$ lune fmt [--write|--check] FILE...
$ lune fix [--write|--check] FILE...
```

`fmt` formats; `fix` applies the mechanical fixes suggested by diagnostics (chapters 11 and 12). Their flags work the same way.

| Flag | Behaviour |
| --- | --- |
| none | write the result to standard output; there must be **exactly one** file |
| `--write` / `-w` | rewrite the files in place; several files allowed |
| `--check` | change nothing; exit 1 if a change is needed. For CI |

`--write` and `--check` cannot be combined.

`fmt` has one limitation: a file containing `###` block comments cannot be formatted (§12.3).

## D.4 REPL commands

`:help` prints the complete list.

| Command | What it does |
| --- | --- |
| `:help` | print this list |
| `:quit` / `:q` | quit |
| `:env` | list every visible name with its type |
| `:type NAME` | give the type of a name |
| `:thunks [NAME]` | show a binding's evaluation state without evaluating it (chapter 4) |
| `:trace [on\|off]` | toggle the running commentary on forcing (chapter 4) |
| `:lang [en\|ja]` | switch the diagnostic language |
| `:explain CODE [en\|ja]` | read the explanation of a diagnostic code (chapter 11) |

With no argument, `:thunks` lists the state of every binding.

Multi-line input continues while a line ends in `=`, `:` or `->`, and finishes at a blank line. Started in a terminal, line editing and history (the up and down arrows) work, and the history is kept in `~/.lune_history`.

`import` works here too (chapter 10). The search starts from **the directory you started in**, and `--module-path` adds to it. The names of an imported module stay in the session, so they appear in `:env`.

```console
$ lune --repl
lune> import math
ok
lune> add(1, 2)
3 : Int
```

## D.5 Exit codes

For calling it from a script or from CI.

| Code | Meaning |
| --- | --- |
| `0` | success. **Warnings alone are still 0** — `--check` does not fail on a warning |
| `1` | a check or an evaluation failed, and a diagnostic was printed. Also "would change" from `fmt --check` / `fix --check` |
| `2` | misuse: an unknown flag, a missing argument, `--write` and `--check` together |

The point is that "a diagnostic was reported" (1) and "the command was called wrongly" (2) are separate. When `--check` fails, you can tell whether the problem is in the code or in your script without reading the output.
