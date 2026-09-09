# Chapter 12: The REPL, Formatting and Checking

Chapter 11 was about the conversation with diagnostics. This chapter is about the tools themselves — the REPL's commands, the canonical formatter `lune fmt`, the CLI's checking flags, and a recipe for lining them up in CI.

One thing worth saying first. Every Lune tool is **a tool for checking your answer**. Unsure of a type? `:type`. Suspicious about the order of evaluation? `:trace`. Arguing about formatting? `fmt`. Get into the habit of asking the machine instead of thinking it through in your head, and Lune becomes a remarkably straightforward language.

## 12.1 Every REPL command

`:help` tells you all of them.

```text
lune> :help
commands: :help, :quit, :q, :env, :type NAME, :thunks [NAME], :trace [on|off], :lang [en|ja], :explain CODE [en|ja]
```

| Command | What it does | Learned in |
| --- | --- | --- |
| `:help` | this list | — |
| `:quit` / `:q` | quit | chapter 1 |
| `:env` | list every name in scope, with its type | this chapter |
| `:type NAME` | give the type of a name | this chapter |
| `:thunks [NAME]` | show a binding's evaluation state without evaluating it | chapter 4 |
| `:trace [on\|off]` | turn the running commentary on forcing on and off | chapter 4 |
| `:lang [en\|ja]` | switch the diagnostic language | chapter 1 |
| `:explain CODE` | explain a diagnostic code | chapter 11 |

Multi-line input continues when a line ends in `=`, `:` or `->` (the `...` prompt) and finishes at a blank line — the behaviour you have used since chapter 1.

Started in a terminal, readline-style line editing and history (the up and down arrows) work as well. Where the environment supports it, history is kept in `~/.lune_history`, so an experiment from a previous session can be called back.

`import` works in the REPL too: modules are resolved from the directory you started in, plus any `--module-path` (chapter 10).

## 12.2 :type and :env — asking the types

`:type` may be the most-used tool in this book. It works on your own functions and on the prelude's alike.

```text
lune> def add(a: Int, b: Int): Int =
...     a + b
...
ok
lune> :type add
add : Int -> Int -> Int
```

Ask it about a record constructor and the answer includes the field names.

```text
lune> :type User
User : (name: String, age: Int) -> User
```

Chapter 6 taught that records must be built with named fields; here that fact is written into the type itself.

`:env` lists **every** name in scope. It includes the prelude, so the list is long, but the interesting part is seeing your own definitions mixed in at the end.

```text
lune> let x = 40
ok
lune> :env
Cons : [T] T -> List[T] -> List[T]
Err : [T, E] E -> Result[T, E]
...
take : [T] List[T] -> Int -> List[T]
takeWhile : [T] List[T] -> (T -> Bool) -> List[T]
tick : () -> Int
x : Int
zip : [T] List[T] -> List[U] -> List[Tuple[T, U]]
```

It is a quick index for "what was in the prelude again?" (the formal list is appendix B).

Ask about a name it does not know and you are told off, naturally.

```text,diagnostic
lune> :type nosuch
error[TYP0003]: undefined name: nosuch
   = help: run `lune explain TYP0003` for a detailed explanation
```

(An aside: undefined names have a code of their own, `TYP0001`, so `TYP0003` here is a small oversight in the implementation. Consistency of diagnostic codes is the sort of thing that ought to be guarded by a test, too.)

## 12.3 lune fmt — the formatter that ends the argument

Two spaces or four? A space around `fn a x -> a+x`? Lune reduces the time spent on that kind of argument to zero. **There is one canonical form**, and `lune fmt` moves code to it.

Here is a messy file, `messy.lune`:

```lune
module messy



let   nums = [ 1,2 ,3 ]

# sum them up
def total( xs : List[Int] ) : Int =
      fold( xs, 0, fn a x -> a+x )

let answer=total(nums)
```

```console
$ lune fmt messy.lune
module messy

let nums = [1, 2, 3]

# sum them up
def total(xs: List[Int]): Int =
    fold(xs, 0, fn a x -> a + x)

let answer = total(nums)
```

The extra blank lines became one, the spacing around brackets was tidied, indentation became four spaces, and the `#` comment was kept where it was.

This formatting comes with two guarantees.

**Idempotence** — formatting an already-formatted result changes nothing. It never oscillates, so it is safe to put in CI.

**It does not change meaning** — `fmt` prints the formatted AST and then **re-reads its own output to check that the syntax tree still matches** before handing the result back. If it does not match, it gives up formatting and reports an error. (That is exactly how the nested `let-in` bug mentioned in chapter 2 was caught.) Formatting will never quietly break your program.

There are three modes.

```console
$ lune fmt FILE            # print the formatted result (the file is untouched)
$ lune fmt --write FILE    # format the file in place
$ lune fmt --check FILE    # fail if formatting is needed (for CI)
```

`--check` names the files that differ and exits with 1.

```console
$ lune fmt --check messy.lune
would reformat messy.lune
```

One limitation: a file containing `###` block comments cannot be formatted yet.

```console
$ lune fmt bc.lune
error: bc.lune: lune fmt does not support `###` block comments yet
```

It merely declines to format (and so cannot break anything), which is the safe behaviour, but if `fmt` is in your CI the current practice is to avoid `###` and use a run of `#` instead.

## 12.4 The CLI's checking flags

The main flags of the `lune` command, in the order you meet them.

| Command | What it does |
| --- | --- |
| `lune --repl` | start the REPL |
| `lune --check FILE` | type-check only (no evaluation) |
| `lune --eval NAME FILE` | evaluate the binding NAME and print it |
| `lune --eval NAME --trace FILE` | as above, plus a trace of forcing on stderr (chapter 4) |
| `lune --module-path DIR` | add a module search root (chapter 10, repeatable) |
| `lune --tokens FILE` | print the result of lexing (the token stream) |
| `lune explain CODE` | explain a diagnostic code (chapter 11; `--index` for all) |
| `lune fmt` / `lune fix` | format / auto-fix (§12.3, chapter 11) |
| `--lang en\|ja` | the diagnostic language. The default comes from `LUNE_LANG`; the flag wins |

`--tokens` is not an everyday tool, but it is handy for peering at how layout (indentation) is handled. It shows you the reality behind "indentation is part of the syntax" from chapter 2.

```console
$ lune --tokens geometry.lune
1:1	MODULE	'module'	None
1:8	IDENT	'geometry'	'geometry'
1:16	NEWLINE	''	None
3:1	DEF	'def'	None
3:5	IDENT	'circleArea'	'circleArea'
...
```

Note also the relationship between `--check` and `--eval`. **`--eval` does not type-check** — which is how chapter 4 was able to produce `RUN0005` (a recursive thunk). To check before running, run `--check` first.

Evaluating a binding that does not exist is a runtime error.

```console
$ lune --eval nosuch geometry.lune
error[RUN0006]: undefined variable: nosuch
```

## 12.5 A small CI recipe

Line the tools up and you have a check for the project. Exit codes are uniform — non-zero when something is wrong — so a shell `&&` makes them one pipeline.

```bash
lune fmt --check src/*.lune && lune --check src/main.lune && lune fix --check src/*.lune
```

The three mean:

1. `fmt --check` — is every file in canonical form (has any formatting been missed)?
2. `--check` — does it type-check?
3. `fix --check` — is anything the machine could fix (a typo, say) still there?

The exit code rules, collected:

| Situation | Exit code |
| --- | --- |
| the check passes | 0 |
| **warnings only** (`TYP0009` and the like) | **0** |
| there are errors | 1 |
| `fmt --check` finds a difference | 1 |
| `fix --check` finds something fixable | 1 |

Watch the second row. As chapter 5 showed, warnings alone still count as success. If you do not want warnings slipping past either, one more step is needed: fail when `warning` appears in the output.

```bash
lune --check src/main.lune 2>&1 | tee /tmp/out; ! grep -q warning /tmp/out
```

> **Break it** — format `messy.lune` with `fmt --write` and then run `fmt --check` again. This time it should say nothing (a demonstration of idempotence). While you are there, read the formatted result and count the differences between your own habits and the canonical form.

## Summary

| Tool | In one line |
| --- | --- |
| `:help` | the list of REPL commands; start here when stuck |
| `:type` / `:env` | ask the types / list every name in scope |
| `lune fmt` | format to the canonical form; **idempotent** and **meaning-preserving** (self-checked by re-parsing) |
| the three `fmt` modes | stdout / `--write` / `--check` (CI) |
| `fmt`'s limitation | `###` block comments are unsupported (it declines, safely) |
| `--check` vs `--eval` | `--eval` does not type-check; run `--check` first if you want checking |
| `--tokens` | a window onto lexing and layout |
| the CI recipe | `fmt --check && --check && fix --check`; warnings alone still exit 0 |

## Exercises

**Exercise 12-1** (★) Predict the result of running `fmt` on `messy.lune`, then check. Where were you wrong?

<details><summary>Answer</summary>

As in §12.3. The usual surprises are that runs of blank lines are squeezed to one, the spacing around the brackets and the colons of `def total( xs : List[Int] ) : Int =`, and the spaces appearing in `a+x`. Check too that the `#` comment survives.

</details>

**Exercise 12-2** (★) Use `:env` to confirm that `zipWith` is in the prelude, and what its type is. Does it match your memory of using it in chapter 8?

<details><summary>Answer</summary>

`zipWith : [T, U, V] List[T] -> List[U] -> (T -> U -> V) -> List[V]`. "Takes two lists and a two-argument function, and returns one list" — what you did for the moving average in exercise 8-3, written in the type. `:type zipWith` gives the same answer.

</details>

**Exercise 12-3** (★★) Checking with `:type` as you go, build a "multiply by three" function from `scale(factor, n)` by partial application, and `map` it over a list. Check the type of the partial application itself along the way, as in `:type scale(3)`.

<details><summary>Answer</summary>

```lune
module answers

# Exercise 12-3: tools built by partial application, checked with :type as
# they were assembled.
def scale(factor: Int, n: Int): Int =
    factor * n

let double = scale(2)

let tripled = map([1, 2, 3], scale(3))

let doubled = map([1, 2, 3], double)
```

```console
$ lune --eval tripled ex12-3.lune
(3 6 9)
$ lune --eval doubled ex12-3.lune
(2 4 6)
```

In the REPL, `:type scale` is `Int -> Int -> Int`, and after `let triple = scale(3)`, `:type triple` is `Int -> Int`. The right-associativity of `->` from chapter 3, observed directly.

</details>

**Exercise 12-4** (★★) Run the CI recipe of §12.5 against your own project (the exercise files of this book will do). If you find a file that fails, explain the cause from the diagnostic.

<details><summary>Answer</summary>

Trying it on this book's `books/examples-en/`, the deliberately broken files (`ch02/annot.lune`, `ch11/typos.lune` and so on) are caught. `typos.lune` fails both `--check` and `fix --check`, but for different reasons — the first is "it does not type-check", the second "something fixable is still there". Reading that the same file fails for **two different reasons** is the point.

</details>

**Exercise 12-5** (★, in reverse) Make `lune fmt` give up formatting.

<details><summary>Answer</summary>

Run `fmt` on a file containing a `###` block comment and it gives up with `lune fmt does not support ### block comments yet` (§12.3). The other way to make it give up is a bug in the formatter itself failing the meaning-preservation self-check (`formatter changed the program's meaning (internal bug)`). That one is hard to produce on purpose, but if you find one it is a bug worth reporting — one was in fact found while this book was being written.

</details>

---

**More precisely** — the REPL is specified in `documents/REPL_SPEC.md` (including the display format of `:thunks` and `:trace`); the formatter's guarantees and limitations are in `documents/FORMATTER_SPEC.md`; every CLI flag is in appendix D. The code examples of this chapter live in `books/examples-en/ch12/` and are all verified against the real CLI.
