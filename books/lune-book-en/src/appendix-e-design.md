# Appendix E: The Design of Lune, and What Comes Next

The body of this book has been about how to write. This appendix is about why things were decided that way. A language design usually carries **inconveniences it chose to accept**; leaving those out in the open is this book's last piece of work.

## E.1 Why lazy by default

**"Lazy evaluation is a trap for beginners" is a fair criticism.** When you cannot see when a computation runs, you cannot read the behaviour of a program, and the order of side effects defies intuition. It is no accident that the teaching languages — Racket, Pyret, Hedy — are all strict.

Lune chose lazy by default anyway, and **has decided not to reverse it**. The reason is not that laziness is convenient.

It is that the answer to the criticism was not to hide it but to **make it visible**.

| | The hiding road | The road Lune took |
| --- | --- | --- |
| the timing of evaluation | invisible, so not thought about | see the state with `:thunks`, the moment with `:trace` |
| a circular definition | it hangs (Haskell's `<<loop>>`) | `RUN0005`, reported immediately and with an explanation |
| when you want strictness | the language decides for you | you decide, with `strict` / `!` / `seq` / `force` / `deepForce` |

Chapter 4 is that answer in full. "You do not have to take any of it on faith; all of it can be observed on the spot" was written there because **observability is not the price of the design, it is the design**.

There is a second aim in this. Teaching "evaluation strategy" in a strict language is hard, because the subject sits outside the program. In a lazy-by-default language, the evaluation strategy becomes **something observable inside the program**. The moment you call `tick()` twice and see the counter still at 0 (appendix B), laziness stops being a concept and becomes a phenomenon.

> **The design tension** — "kind to beginners" and "able to teach evaluation strategy" do not usually go together. Lune is a language trying to resolve that tension with diagnostics and observability. Whether it succeeds is answered by how you felt at the end of chapter 4. The strategy in detail is measures D and E in `documents/STRATEGY.md`.

## E.2 Why there is both `null` and `Option`

Chapter 5 taught `Option[T]` and chapter 7 taught `T?`. Two tools for "there might not be a value" looks like fat in a design.

It looks that way, and yet neither could be removed.

**`Option` cannot be removed.** It is not a language feature but **a type anyone can write** given ADTs and pattern matching. It is in fact defined in the prelude as nothing more than `type Option[T] = | Some(value: T) | None`, with no special treatment from the compiler. You cannot take `Option` away from a language that has ADTs — short of forbidding it, somebody will define it.

**`T?` cannot be removed either.** Lune's long-term goals include running on the JVM and calling Java libraries directly (`documents/LANGUAGE_FUTURE_SPEC.md`). And every Java reference can be null. In the future specification's table of Java type correspondences, `T?` is the type matching a **nullable reference** — in other words, **the type for talking to the outside world**. A language without null cannot talk to a world that has it.

So Lune chose **not to abolish `null` but to tame it with types** (chapter 7). Not "a language that removed null" but "a language that makes you write where null may appear, and will not let you use it before checking".

The roles then divide naturally.

| | `T?` | `Option[T]` |
| --- | --- | --- |
| origin | a language feature (with `??`, `?.` and narrowing) | an ADT in the prelude |
| suits | the shape of data: record fields, parameters, results | list processing and higher-order pipelines |
| at the boundary | corresponds to a Java nullable reference | an internal matter for Lune |

The practical rule of thumb is in §7.7. At the boundary, a `match` converts between them.

> **To be honest** — the price of having two is exactly one thing: the reader has to learn which to use. That is a real cost. The table in §7.7 exists to keep that cost down to "look at a table".

## E.3 The limits v0.1 accepted

What was not built is as much a design as what was. The list of what does not work, and the diagnostics you get, is in A.6. Here is the **why**.

### Frozen — the JVM and OO

`class` / `interface` / `extends`, calling Java libraries directly, JVM bytecode generation. They are in the future specification (Phases 2–4 of `LANGUAGE_FUTURE_SPEC.md`), but the decision to **freeze them for now** is explicit (`documents/STRATEGY.md` §5).

The reason is a choice of battlefield, not of capability. Java interoperation is a measure aimed at "get adopted in industry", and that is a fight with poor odds. For teaching, meanwhile, the speed of a Python interpreter is enough. So Lune stepped off the road to becoming a production language and concentrated on being **an introductory functional language whose compiler teaches you in your own tongue**.

That `class` and `new` are syntax errors while still being reserved keywords — that half-way state is the mark of this freeze. The seats are kept for the future; nobody is sitting in them yet.

### Not there yet — `try` / `catch`

There is no tool for throwing failure as an exception. This is a matter of **order** rather than of freezing. The tools that **return failure as a value** — `Result` in chapter 5 and `T?` in chapter 7 — were put in place first, and exceptions overlap with them. Chapter 9's "express recoverable failure as a value; `raise` is for when stopping the program is correct" is the consequence of that design.

### Small things missing

`break` / `continue` (weave it into the loop condition — §9.3), record update and record patterns, mutable record fields, field access on ADTs, `Stream` / `Map` / `Set`. There is no character type either (A.1).

Some of these are not philosophy but simply **not got round to yet**. A.6 lists what happens if you try them; `LANGUAGE_FUTURE_SPEC.md` lists what is wanted.

## E.4 If you want to read the implementation

Lune's implementation is pure Python under `lune/`, about 7,500 lines, with **no external dependencies**. It can be read in a day, which makes it a good subject for a first reading of a language implementation.

The sources are laid out in the order of the checks. The families of diagnostic codes from A.1 (`LXL` → `LAY` → `PRS` → `MOD` → `TYP` → `RUN`) are also the order of the files.

| File | Lines | Role |
| --- | --- | --- |
| `lexer.py` | 294 | text → tokens. `LXL` |
| `layout.py` | 61 | indentation → `INDENT`/`DEDENT`. `LAY` |
| `tokens.py` | 214 | token kinds and the keyword table |
| `parser.py` | 763 | tokens → AST (a Pratt parser). `PRS` |
| `nodes.py` | 405 | the AST definitions; read this for the shape of the whole language |
| `module_loader.py` | 196 | resolving `import`. `MOD` |
| `typechecker.py` | 1597 | type checking and exhaustiveness. `TYP`, `REC`. The largest file |
| `evaluator.py` | 1346 | lazy evaluation and thunks. `RUN` |
| `diagnostics.py` | 124 | the display format of diagnostics (assembling carets and hints) |
| `messages.py` | 358 | the English/Japanese message catalogue |
| `explanations.py` / `explanations_ja.py` | 532 / 430 | the teaching catalogue behind `lune explain` |
| `formatter.py` / `fixer.py` | 490 / 66 | `lune fmt` / `lune fix` |
| `repl.py` | 403 | the REPL. The Playground drives this same `ReplSession` |
| `cli.py` | 279 | the command-line entry point |

**A suggested reading order**: `nodes.py` → `lexer.py` → `parser.py` → `evaluator.py`. Look at the AST first and everything else becomes a matter of "how it is built" and "how it is handled". If lazy evaluation is what interests you, the shortest way in is `Thunk` and `force_value` in `evaluator.py`.

### How to read the specifications

The specifications are in `documents/`. **`LANGUAGE_SPEC.md` is authoritative for v0.1**, with the detailed documents branching off it.

| What you want to know | What to read |
| --- | --- |
| what is usable in v0.1 | `LANGUAGE_SPEC.md` (authoritative) |
| surface syntax, EBNF | `SYNTAX_SPEC.md` / `LEXER_PARSER_SPEC.md` |
| the rules of lazy evaluation | `LAZY_EVALUATION_SPEC.md` |
| the scope of type checking | `TYPE_CHECKER_SPEC.md` / `MATCH_EXHAUSTIVENESS_SPEC.md` |
| the design of diagnostics | `ERROR_DIAGNOSTICS_SPEC.md` / `ERROR_INDEX.md` |
| where it is going | `LANGUAGE_FUTURE_SPEC.md` / `STRATEGY.md` |

> **A caution when reading the specifications** — they are called authoritative, but there are places where the v0.1 implementation has not caught up, and places where the implementation is the one that is right. Two were found while writing appendix A alone (the case where `LXL0004` could never fire, and the character type), and a third while translating chapter 8 (a "known bug" that had already been fixed). **When in doubt, run it through `./bin/lune`.** That is the primary source. Every appendix in this book was written that way.

## E.5 What comes next

`documents/STRATEGY.md` describes where this is going. In summary: do not chase general adoption, concentrate on being an introductory functional language whose compiler teaches you in your own tongue, and keep the JVM/OO road frozen. Lazy by default is not a weakness to be hidden but the distinguishing feature to lead with.

Having read this book, there are a few things you can do.

- **Tell us where you got stuck.** Which diagnostic held you up, which explanation was not enough — those are directly the language's improvements. If a diagnostic was unhelpful, we consider that a bug in the language.
- **Add diagnostics.** The runtime errors collected into the general `RUN0006` have room to be promoted to codes of their own (a work item of measure E in `STRATEGY.md`).
- **Write something.** Even v0.1 can write the programs of chapter 13. When you notice a tool that is missing, that is the next thing to build.

The club motto, once more. **Don't do it until you need to. Once done, never forget it.** It is about lazy evaluation and memoisation — and also about how to build a language.
