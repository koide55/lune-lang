# Appendix C: The Diagnostic Codes

The complete list of diagnostic codes issued by Lune's compiler and evaluator. Here the book confines itself to being a map: the detailed explanation of each code (what happened, the smallest reproduction, how to fix it) is not copied here but left to `lune explain CODE` (`:explain CODE` in the REPL). The same content is readable in the [diagnostic catalogue](https://koide55.github.io/lune-lang/playground/errors.html) and in `documents/ERROR_INDEX.md` (the Japanese version is `ERROR_INDEX_JA.md`).

```console
$ lune explain TYP0007          # read one code
$ lune explain --index          # list the explanations of every code
```

The first three letters of a code are its **family**, corresponding directly to a stage of the compiler. What the families mean and how to read them is §11.2.

You will never meet a code without an explanation. `test_every_emitted_code_has_an_explanation` in `tests/test_explanations.py` checks that every code the compiler can issue has one, so adding a code without writing its explanation makes the test fail.

## How to read the table

- **Chapters that mention it** — the chapters where the code appears in the text. Chapter 11 is about the machinery of diagnostics itself, so it touches nearly all of them.
- **Working example** — chapters where `books/examples-en/` contains a verified example that actually reproduces the code. Use it as a way in when you want to produce one yourself. A `—` means the book has no example aimed at that code (`LAY0002` and `REC0001`, for instance, take some contriving to produce deliberately).
- Codes issued as warnings say "(warning)" in the meaning column. A warning does not make `--check` fail.

## The list

| Code | Family | Meaning | Chapters that mention it | Working example |
| --- | --- | --- | --- | --- |
| `LAY0001` | layout | inconsistent indentation | 11 | — |
| `LAY0002` | layout | unmatched closing bracket | 11 | — |
| `LXL0001` | lexing | unexpected character | 2, 11 | 2 |
| `LXL0002` | lexing | unterminated string or character literal | 11 | — |
| `LXL0003` | lexing | unterminated block comment | 11 | — |
| `LXL0004` | lexing | tabs are not allowed in indentation | 11 | — |
| `MOD0001` | module resolution | module not found or unreadable | 10, 11 | 10 |
| `MOD0002` | module resolution | cyclic module import | 10, 11 | 10 |
| `MOD0003` | module resolution | module declaration mismatch | 10, 11 | 10 |
| `PRS0001` | parsing | unexpected token | 2, 6, 11 | 2 |
| `PRS0002` | parsing | a particular token was required | 10, 11 | — |
| `REC0001` | record checking | duplicate field in a record declaration | 11 | — |
| `REC0002` | record checking | unknown record field | 6, 11 | 6 |
| `REC0003` | record checking | missing record field | 6, 11 | — |
| `REC0004` | record checking | field given twice in a construction | 6, 11 | — |
| `REC0005` | record checking | a field that was never declared | 6, 11 | — |
| `REC0006` | record checking | records are built with named fields | 6, 11, 13 | — |
| `RUN0005` | run time | recursive thunk evaluation | 3, 4, 10, 11, 12 | 4 |
| `RUN0006` | run time | runtime error | 2, 4, 6, 9, 11, 12 | 4 |
| `TYP0001` | type checking | undefined name | 1, 4, 10, 11, 12 | 1, 4, 11 |
| `TYP0003` | type checking | type mismatch | 1, 2, 7, 8, 11, 12 | 2, 7 |
| `TYP0004` | type checking | value is not callable | 3, 11 | — |
| `TYP0005` | type checking | wrong number of arguments | 1, 3, 11 | 1 |
| `TYP0006` | type checking | the subject of a `for` must be a List | 9, 11 | 9 |
| `TYP0007` | type checking | non-exhaustive match | 5, 7, 11, 13 | 5, 7, 11 |
| `TYP0008` | type checking | a refutable pattern in a binding | 5, 9, 11 | 5 |
| `TYP0009` | type checking | unreachable match case (warning) | 5, 7, 11, 12 | 5 |
| `TYP0010` | type checking | cannot infer a parameter's type (warning) | 3, 11 | — |
| `TYP0011` | type checking | a recursive function needs a result type | 2, 3, 11 | 3 |
| `TYP0012` | type checking | named arguments are not supported here | 11, 13 | — |

## About the gaps in the numbering

You may have noticed that the numbers are not consecutive: `TYP0002` and `RUN0001`–`RUN0004` are missing.

The `RUN` codes were, at the design stage, going to divide runtime errors by kind (`RUN0004` was reserved for "non-exhaustive match at run time"). The implementation abandoned that plan, keeping only the forcing of a recursive thunk as its own `RUN0005` and collecting the rest into the general `RUN0006`. An undefined variable, forcing a failed thunk, a type mismatch in the standard library and a non-exhaustive match at run time are all `RUN0006`. `TYP0002` is simply unused. See `documents/ERROR_DIAGNOSTICS_SPEC.md` for details.

**The gaps will not be filled in.** A number that once meant one thing coming to mean another later would harm readers more than a gap does. An error number is a key for looking things up, not a serial number.

## Where this appendix comes from

The code, family and meaning columns of this table are built from `documents/ERROR_INDEX.md`. That index is itself not hand-written but generated from the compiler's catalogue.

```console
$ ./bin/lune explain --index > documents/ERROR_INDEX.md
```

So this table comes from the catalogue in `lune/explanations.py` — the same primary source as the implementation. When a code is added or changed, regenerate the index and then update this table.
