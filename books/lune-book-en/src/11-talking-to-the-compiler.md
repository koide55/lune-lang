# Chapter 11: Talking to the Compiler

Across the previous chapters you have met nearly thirty diagnostics. You have been told which name was a typo, been handed a counterexample for a missing `match` case, and been stopped at compile time for forgetting about null. This chapter turns that experience into **a system**.

To Lune, a diagnostic is not a notice of failure but half of the language's user interface. Every diagnostic code comes with an explanation written to teach, and a test guarantees that it does. Riding on that design, this chapter's goal is to turn the compiler from a noisy gatekeeper into a tutor sitting next to you.

## 11.1 The anatomy of a diagnostic — six parts

Chapter 1 touched on the structure of a diagnostic; here it is dissected completely. Our specimen is `TYP0008` (chapter 5), which has every part.

```text,diagnostic
error[TYP0008]: refutable pattern in let binding: Some(x)
  --> refutable.lune:3:5
  |
3 | let Some(x) = Some(1)
  |     ^^^^ this pattern can fail to match
   = hint: the pattern does not cover None
   = hint: use `match` to handle all cases of Option[Int]
   = help: run `lune explain TYP0008` for a detailed explanation
```

| Part | Here | Role |
| --- | --- | --- |
| severity | `error` | `error` (the check fails) or `warning` (it passes, but look) |
| code | `TYP0008` | the diagnostic's number — the key to looking it up (§11.3) |
| summary | `refutable pattern in let…` | one line on what is wrong |
| location and source | `--> refutable.lune:3:5` and `^^^^` | where, and which part |
| label | `this pattern can fail to match` | what the `^^^^` is pointing at |
| hint / help | `= hint: ...` ×2 | suggested fixes, and the way to learn more |

The knack is to read **summary → label → hint**. The summary tells you what this is about, the label pins down where, the hint gives the next move. When there are several hints they are ordered **cause → remedy** (here, "does not cover None" is the cause and "use `match`" the remedy).

A `warning` does not stop the check. As `TYP0009` in chapter 5 showed, with only warnings you still get `type check OK` at the end and the check counts as successful. But a warning marks "it runs, but probably not as you intended" — make a habit of not leaving them.

## 11.2 The code scheme — seven families and the stages of checking

The first three letters of a code give its **family**, and the family corresponds directly to a **stage of the compiler**. Source code passes checkpoints in order — layout, lexing, parsing, module resolution, type checking — and only what clears them all is run.

| Family | Stage | Example | Mostly met in |
| --- | --- | --- | --- |
| `LAY` | layout (indentation) | inconsistent indentation | chapter 2 |
| `LXL` | lexing | an unknown character, an unterminated string | chapter 2 |
| `PRS` | parsing | an unexpected token | chapters 2 and 6 |
| `MOD` | module resolution | an import not found, a cycle | chapter 10 |
| `TYP` | type checking | undefined names, type mismatches, exhaustiveness | throughout |
| `REC` | record checking | missing, unknown or duplicate fields | chapter 6 |
| `RUN` | **run time** | division by zero, recursive thunks | chapter 4 |

Two things follow from the table. First, **the earlier the family, the earlier it catches you** — while an `LXL` error stands, the conversation about types has not even begun. Second, only `RUN` is at run time. A `RUN` diagnostic can appear even after `--check` passes (chapter 4's `crash()`, or division by zero): type checking guards a great deal, but not everything.

There are 31 codes in all today. Appendix C has the list, and the full catalogue of explanations is `documents/ERROR_INDEX.md`.

## 11.3 explain — an error number is for looking up

There are three doors to a diagnostic's explanation.

```console
$ lune explain TYP0007        # from the shell
```

```text
lune> :explain TYP0007        # from inside the REPL
```

And to read them all at once, `lune explain --index` — which is what `ERROR_INDEX.md` actually is (the file is the output of that command, saved; a test fails when it goes stale).

Each explanation has three parts — what happened, the smallest example that reproduces it, and how to fix it — as you read for `TYP0001` in chapter 1 and `RUN0005` in chapter 4. Ask about a code that does not exist and you get the list of codes you can ask about.

```text
$ lune explain ZZZ9999
error: no explanation for diagnostic code 'ZZZ9999'
available codes: LAY0001, LAY0002, LXL0001, LXL0002, LXL0003, LXL0004, MOD0001, MOD0002, MOD0003, PRS0001, PRS0002, REC0001, REC0002, REC0003, REC0004, REC0005, REC0006, RUN0005, RUN0006, TYP0001, TYP0003, TYP0004, TYP0005, TYP0006, TYP0007, TYP0008, TYP0009, TYP0010, TYP0011, TYP0012, TYP0013
```

"An error number is not to be memorised; it is **the key to looking it up**" — that is how to use the code scheme.

## 11.4 Errors a machine can fix — did-you-mean and lune fix

Some diagnostics have exactly one obvious fix. Typos are the archetype. Here is `typos.lune`, with two planted deliberately:

```lune
module stats

let values = [3, 1, 4, 1, 5]

let total = fold(valeus, 0, fn a x -> a + x)

let count = lenght(values)
```

```console
$ lune --check typos.lune
```

```text,diagnostic
error[TYP0001]: undefined name: valeus
  --> typos.lune:5:18
  |
5 | let total = fold(valeus, 0, fn a x -> a + x)
  |                  ^^^^^^ name is not defined
   = hint: did you mean `values`?
   = help: run `lune explain TYP0001` for a detailed explanation
```

`--check` reports only the first, but `lune fix` **applies the hints mechanically, re-checks the result**, and repeats until nothing fixable remains.

```console
$ lune fix typos.lune
module stats

let values = [3, 1, 4, 1, 5]

let total = fold(values, 0, fn a x -> a + x)

let count = length(values)
```

Both `valeus` and `lenght` were fixed in one go. `--write` edits the file in place; `--check` turns it into a CI check that fails when anything fixable is left.

```console
$ lune fix --check typos.lune
typos.lune: 2 auto-fixable issue(s)
```

`fix`, on the other hand, **does not touch what it cannot decide**. Run it on chapter 2's `annot.lune` (`let n: Int = "hello"`) and the source comes back unchanged. Whether the `Int` or the `"hello"` should change is a design decision, and a machine cannot make it. Remember that line: **if the hint is unique it is the machine's job; if judgement is required it is yours**.

## 11.5 Error-driven development — writing by following the witness

To finish, here is the development style this book has been promising all along, in one pass: **write the skeleton first, and ask the compiler what is missing**.

The subject is rock-paper-scissors. We judge whether `a` beats `b`. Start with the type and the one case we are sure of.

```text,diagnostic
lune> type Hand =
...     | Rock
...     | Paper
...     | Scissors
...
ok
lune> def beats(a: Hand, b: Hand): Bool =
...     match (a, b):
...         | (Rock, Scissors) -> true
...
error[TYP0007]: non-exhaustive match: missing case (Paper, Rock)
  --> <repl:2>:2:5
  |
2 |     match (a, b):
  |     ^^^^^ pattern (Paper, Rock) is not covered
   = hint: add a case for (Paper, Rock), or a wildcard case `| _ -> ...`
   = help: run `lune explain TYP0007` for a detailed explanation
```

The compiler has brought us **the next winning case to write**: `(Paper, Rock)` — paper beats rock. Do as it says and write all the winning cases.

```text,diagnostic
lune> def beats(a: Hand, b: Hand): Bool =
...     match (a, b):
...         | (Rock, Scissors) -> true
...         | (Paper, Rock) -> true
...         | (Scissors, Paper) -> true
...
error[TYP0007]: non-exhaustive match: missing case (Rock, Rock)
  --> <repl:2>:2:5
  |
2 |     match (a, b):
  |     ^^^^^ pattern (Rock, Rock) is not covered
   = hint: add a case for (Rock, Rock), or a wildcard case `| _ -> ...`
   = help: run `lune explain TYP0007` for a detailed explanation
```

This time it is `(Rock, Rock)` — we are being told that **draws exist**. Everything that is not a win is not a win, so catch it with a wildcard.

```text
lune> def beats(a: Hand, b: Hand): Bool =
...     match (a, b):
...         | (Rock, Scissors) -> true
...         | (Paper, Rock) -> true
...         | (Scissors, Paper) -> true
...         | _ -> false
...
ok
lune> beats(Rock(), Scissors())
true : Bool
lune> beats(Scissors(), Rock())
false : Bool
```

Look back at what happened. We did not remember a single one of the gaps in the specification — paper's win, the existence of draws — **by ourselves**. The compiler brought each of them, in the form of a concrete counterexample. A diagnostic is not something to read but **a TODO list to work through**. That is error-driven development.

The more of the types you write first, the better the questions the compiler asks. Enumerate the shapes with an ADT, build the skeleton with `match`, run `--check`. When the gaps are filled, finish with `fix` and `fmt`. That cycle is the basic rhythm of writing Lune.

> **Break it** — delete `| _ -> false` from `rps.lune`, run `--check` to see the witness, and then cover the cases by **enumerating the three draws and the three losses** instead of using a wildcard. Both styles have a virtue: the wildcard is shorter, while the enumeration protects you when a case is added to `Hand` (the lesson of exercise 5-1).

## Summary

| Concept | In one line |
| --- | --- |
| the parts of a diagnostic | severity / code / summary / location + label / hint / help; read summary → label → hint |
| the order of hints | cause → remedy |
| seven families | LAY, LXL, PRS, MOD, TYP, REC before running; only RUN at run time |
| `lune explain` / `:explain` / `--index` | all 31 codes have an explanation; the number is a key for looking up |
| `lune fix` | when the hint is unique, the machine fixes it (repeatedly); `--write` / `--check` |
| where fix stops | it does not touch fixes a machine cannot decide |
| error-driven development | skeleton → `--check` → work through the witnesses as a TODO list |

## Exercises

**Exercise 11-1** (★) About the specimen in §11.1 (`TYP0008`): which hint states the cause and which the remedy? And why does `--check` come back as a failure (a non-zero exit)?

<details><summary>Answer</summary>

The cause is the first ("the pattern does not cover None") and the remedy the second ("use `match` to handle all cases"). It fails because the severity is `error`. With only warnings (`TYP0009` and the like) the check succeeds and prints `type check OK`.

</details>

**Exercise 11-2** (★★) Predict what `lune fix` does to `typos.lune` and to chapter 2's `annot.lune`, then check.

<details><summary>Answer</summary>

`typos.lune` comes back as complete source with both typos fixed. `annot.lune` comes back **unchanged** — `TYP0003` has no unique, mechanically applicable hint. With `fix --check`, the former fails (non-zero exit) with "2 auto-fixable issue(s)" and the latter succeeds, having nothing to fix.

</details>

**Exercise 11-3** (★★) Using `beats` as a building block, write `judge(a, b)`, returning the three values `"win"` / `"lose"` / `"draw"`.

<details><summary>Answer</summary>

```lune
def judge(a: Hand, b: Hand): String =
    if beats(a, b):
        "win"
    elif beats(b, a):
        "lose"
    else:
        "draw"
```

```console
$ lune --eval tied ex11-3.lune
"draw"
```

The **rule** for who wins is written in exactly one place, `beats`, and `judge` merely asks it twice. Not writing the rule twice is the point.

</details>

**Exercise 11-4** (★★★, in reverse, comprehensive) Write the smallest code that produces a diagnostic from each of the five families `LXL`, `PRS`, `TYP`, `REC` and `RUN` (bonus points for a code this book has not yet shown you).

<details><summary>Answer</summary>

For example `let x = $1` (LXL0001), `let a = (1` (a `PRS` code — an unclosed parenthesis), `1 + true` (TYP0003), `User(name = "X", name = "Y", age = 1)` (REC0004, chapter 6), and evaluating a binding containing `1 / 0` with `--eval` (RUN0006). A bonus: ending a file with an unclosed `###` gives `LXL0003` (unterminated block comment). Check your finds against the index of all 31 codes (appendix C / `ERROR_INDEX.md`).

</details>

**Exercise 11-5** (★) Skim the output of `lune explain --index`, find a diagnostic code this book has not shown you, and read its explanation.

<details><summary>Answer</summary>

`MOD0002` (a cyclic import), for instance, has not appeared yet — that is chapter 10's treat. `LAY0002` (an unmatched closing bracket) and `REC0001` (a duplicated field in a record declaration) also take some contriving to produce on purpose.

</details>

---

**More precisely** — the normative diagnostic model and display format are in `documents/ERROR_DIAGNOSTICS_SPEC.md`; the catalogue of every code is `documents/ERROR_INDEX.md` (regenerated with `lune explain --index`); the rules for applying fixes are in `documents/ERROR_DIAGNOSTICS_SPEC.md` §9.5. The code examples of this chapter live in `books/examples-en/ch11/` and are all verified against the real CLI.
