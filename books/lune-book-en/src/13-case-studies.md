# Chapter 13: Building a Program — Case Studies

Every part is now in hand. This chapter writes three small programs **from design to completion**. No new syntax appears; instead we see how the tools learned separately fit together.

All three follow the same procedure: **decide the types → write the skeleton → fill it in guided by the compiler's witnesses → finish with `fmt` and `--check`**. In other words, three real runs of the error-driven development of chapter 11.

## 13.1 Text statistics — one pass with fold and a record

K&R's introduction starts with a program that counts characters. In tribute, let us build statistics about words.

**One caveat first.** v0.1's strings have only `length` and `+` (concatenation), with no tool for splitting a string into words. So the input is a list of already-split words, `List[String]`. Splitting is a job for outside the program — that is the design.

**Decide the types.** The result we want is a triple: the number of words, the total number of characters, and the longest word. We want to carry it with names, so: a record (chapter 6).

```lune
record Stats:
    count: Int
    totalChars: Int
    longest: String
```

**Write the skeleton.** We are collapsing a list into a single value, so `fold` (chapter 8). Which means all we need is a function that makes a new `Stats` from the running `Stats` and the next word. Here is `stats.lune`:

```lune
module stats

record Stats:
    count: Int
    totalChars: Int
    longest: String

let empty = Stats(count = 0, totalChars = 0, longest = "")

def step(s: Stats, w: String): Stats =
    let n = length(w)
    let longer = if n > length(s.longest) then w else s.longest
    Stats(count = s.count + 1, totalChars = s.totalChars + n, longest = longer)

def summarize(words: List[String]): Stats =
    fold(words, empty, step)

def averageLength(s: Stats): Double? =
    if s.count == 0 then null else s.totalChars / s.count

let words = ["the", "quick", "brown", "fox", "jumps"]

let summary = summarize(words)

let average = averageLength(summary)

let emptyAverage = averageLength(summarize([]))
```

```console
$ lune --eval summary stats.lune
{ count = 5, totalChars = 21, longest = "quick" }
$ lune --eval average stats.lune
4.2
$ lune --eval emptyAverage stats.lune
null
```

There are three design decisions in there.

**The list is walked only once.** Computing the three statistics separately would mean three `fold`s; making the accumulator a record does it in one. The running value of a `fold` need not be a number — that is what `fold` is really for.

**The average is a `Double?`.** With zero words there is no average. Returning 0 would be a lie, so it returns `null` (chapter 7). The caller chooses whether to land on `?? 0.0` or to branch with a `match`.

**`step` is its own function.** It could have been a lambda, but giving it a name means it can be tried on its own in the REPL (`step(empty, "hi")`). Name the things you want to test — a practical instinct.

## 13.2 A ledger — ADTs, Result and splitting into modules

Next, something more like real work: record income and expenses and produce a balance.

**Decide the types.** An entry is either income or an expense — a job for a sum type (chapter 5). The data and its operations go into a module together (chapter 10). Here is `ledger/entry.lune`:

```lune
module ledger.entry

type Entry =
    | Income(label: String, amount: Int)
    | Expense(label: String, amount: Int)

def signedAmount(e: Entry): Int =
    match e:
        | Income(_, amount) -> amount
        | Expense(_, amount) -> 0 - amount

def labelOf(e: Entry): String =
    match e:
        | Income(label, _) -> label
        | Expense(label, _) -> label

def validate(e: Entry): Result[Entry, String] =
    if signedAmount(e) == 0 then Err("amount must not be zero: " + labelOf(e)) else Ok(e)
```

This is the heart of the design. We decided **not to carry the sign in the type**. An `Expense` holds a positive `amount`, and `signedAmount` applies the sign. That way the question "do we record expenses as negative?" never arises — a small but essential choice about whether meaning lives in the type or in a function.

`validate` returns failure **as a value** (chapter 5). Nothing is thrown, so the caller cannot ignore the failure. Here is `ledger_main.lune`:

```lune
module ledger_main
import ledger.entry

let entries = [Income("salary", 3000), Expense("rent", 1200), Expense("food", 400)]

let balance = fold(map(entries, signedAmount), 0, fn a x -> a + x)

let expenses = filter(entries, fn e: Entry -> signedAmount(e) < 0)

let rejected = validate(Expense("zero", 0))

let accepted = validate(Income("bonus", 500))
```

```console
$ lune --eval balance ledger_main.lune
1400
$ lune --eval expenses ledger_main.lune
(Expense("rent", 1200) Expense("food", 400))
$ lune --eval rejected ledger_main.lune
Err("amount must not be zero: zero")
$ lune --eval accepted ledger_main.lune
Ok(Income("bonus", 500))
```

"`map` to signed amounts and `fold` them" — chapter 6's aggregation pattern, working unchanged. Pulling out the expenses with `filter` is the same idea.

**Experience the benefit of witnesses here.** Add a third case to `Entry` — a `Transfer`, say — and `TYP0007` appears in both `signedAmount` and `labelOf`. The compiler points out, exhaustively, that you have not decided what sign a transfer has. That is what chapter 11 taught, and it is what a design robust to changing requirements actually means.

> **A note on v0.1** — ADT constructors are called with **positional** arguments (`Income("salary", 3000)`). Writing them by name, as `Income(label = "salary", amount = 3000)`, is rejected with `TYP0012`. Constructors can be partially applied (chapter 3), so `Income(amount = 3000)` would mean "a partial application with the first argument unfilled", leaving nothing for the names to correspond to. **It is records that require names**, and there positional arguments give `REC0006` instead (chapter 6) — the two are exactly mirror images.

## 13.3 A laboratory of sequences — infinite lists and counting evaluations

The last is a comprehensive exercise in lazy evaluation. We build the Collatz sequence (halve an even number; treble an odd one and add one; continue until it reaches 1) as an infinite list.

Writing "halve if even" needs care about **which** division. `/` always returns a `Double`, so `n / 2` is not an `Int`. To divide and stay in integers, use floor division `//` (§2.2).

```text
lune> 7 // 2
3 : Int
lune> 7 / 2
3.5 : Double
```

Here is `collatz.lune`:

```lune
module collatz

# `//` is integer floor division. `/` always returns a Double, so staying in
# Int means `//`.
def next(n: Int): Int =
    if n % 2 == 0 then n // 2 else 3 * n + 1

let fromSix = take(iterate(next, 6), 9)

let fromSeven = takeWhile(iterate(next, 7), fn n: Int -> n != 1)
```

```console
$ lune --eval fromSix collatz.lune
(6 3 10 5 16 8 4 2 1)
$ lune --eval fromSeven collatz.lune
(7 22 11 34 17 52 26 13 40 20 10 5 16 8 4 2)
```

`iterate(next, 6)` is "the infinite Collatz sequence starting from 6" (chapter 8). How much of it to look at is the caller's decision — nine with `take`, or "up to just before 1" with `takeWhile`. Separating the definition of a sequence from how much of it you use, once again.

And finally, let us confirm **with a number** that laziness really is doing its work. Prepare an "expensive" computation with a `tick()` (chapter 4) inside, and measure how many times it runs when two elements are taken from a five-element list. Here is `counted.lune`:

```lune
module counted

# An "expensive" computation with a tick() in it: the counter records how
# many times it was called.
def costly(n: Int): Int =
    seq tick() (n * 2)

let doubled = map([1, 2, 3, 4, 5], costly)

# Take just the first two, and evaluate them all the way down.
let firstTwo = deepForce take(doubled, 2)

# How many times costly ran while doing so.
let cost = seq firstTwo tickCount()
```

```console
$ lune --eval firstTwo counted.lune
(2 4)
$ lune --eval cost counted.lune
2
```

**We mapped over five elements and `costly` ran twice.** A strict language would run it five times and then throw three results away. The benefit of laziness, tracked since chapter 4, finally appears as a number.

Notice also why `deepForce` is needed. `take(doubled, 2)` alone materialises only the spine (the chain of `Cons` cells), leaving the elements as thunks — with `:thunks` you can see it stop at `Cons(<thunk>, <thunk>)`, the same view as in chapter 8. That you can choose *how far* to evaluate is itself an expression of Lune's design.

## 13.4 What the three cases have in common

Put side by side, a common pattern emerges.

1. **Turn the shape into a type** (record or ADT — product or sum).
2. **Write with immutable transformations** (`map` / `filter` / `fold`; if an imperative part is needed, seal it in a block).
3. **Express "nothing" and "failed" as values** (`T?` / `Result` / a monomorphic result type).
4. **Let the compiler watch for gaps** (exhaustiveness in `match`, filling in guided by witnesses).
5. **Build your own instrument to check with** (as `costly` and `tick()` do — confirm with a number, not with "it should be fast").

And every one of the programs was formatted with `lune fmt` and passed through `lune --check` before being called finished (the CI recipe of chapter 12).

## Exercises

**Exercise 13-1** (★★) Add "the shortest word" to `Stats`, without breaking on an empty list.

<details><summary>Answer</summary>

Initialising it to `""` would make the shortest always the empty string, so express "not yet any" with `null` (chapter 7).

```lune
record Stats:
    count: Int
    totalChars: Int
    longest: String
    shortest: String?

def pickShortest(current: String?, w: String): String =
    if current == null:
        w
    elif length(w) < length(current):
        w
    else:
        current
```

```console
$ lune --eval summary ex13-1.lune
{ count = 5, totalChars = 21, longest = "quick", shortest = "the" }
```

After the first line of `pickShortest` checks `current == null`, `current` is narrowed to `String`, so `length(current)` can be written (the narrowing of chapter 7). Note also that the one-line form `if ... then ... elif` does not exist — `elif` belongs to the block form only.

</details>

**Exercise 13-2** (★★) Add `Transfer(label: String, amount: Int)` to `Entry` (a transfer between accounts, which does not affect the balance). Observe what the compiler demands.

<details><summary>Answer</summary>

Adding one line to the `type` produces `TYP0007` (non-exhaustive match) in **both** `signedAmount` and `labelOf`. Adding `| Transfer(_, _) -> 0` (no effect on the balance) and `| Transfer(label, _) -> label` makes it pass.

Change a type in one place and the compiler lists every place affected — this is why the wildcard `_ -> ...` is worth avoiding (exercise 5-1). Had it been written with a wildcard, `Transfer` might quietly have been treated as an expense.

</details>

**Exercise 13-3** (★★) What does `cost` become if `take(doubled, 2)` in `counted.lune` becomes `take(doubled, 5)`? And what if `deepForce` is removed? Predict, then check.

<details><summary>Answer</summary>

It becomes `5` (all five elements are evaluated). Without `deepForce`, `cost` is `0` — `take` materialises only the spine and never touches the elements' thunks. The chapter 8 lesson that "having a list" and "having computed its contents" are different things, confirmed with a number.

</details>

**Exercise 13-4** (★★★) `-7 // 2` is `-4`, not `-3`. Explain why, together with the value of `-7 % 2`. Predict first, check in the REPL, then answer.

<details><summary>Answer</summary>

Start by looking at both values.

```text
lune> -7 // 2
-4 : Int
lune> -7 % 2
1 : Int
```

`//` rounds **towards negative infinity** (floor), not towards zero (truncation). `-7 / 2` is `-3.5`, and the floor of that is `-4`.

Why not `-3`? Because `//` and `%` are not two unrelated operations: they **have to add up as a pair**. Whatever the signs, quotient and remainder are tied by this identity.

```text
a == (a // b) * b + (a % b)
```

Check it:

```text
lune> (-7 // 2) * 2 + (-7 % 2)
-7 : Int
```

Suppose `//` truncated towards zero and returned `-3`. The `%` side (`1`) is unchanged, so:

```text
lune> (-3) * 2 + (-7 % 2)
-5 : Int
```

which is not `-7`. Choosing `-3` makes `//` and `%` contradict each other, and they stop deserving the names quotient and remainder. Once `%` is defined to return a remainder matching the sign of the divisor (`-7 % 2` is `1`, not `-1`), `//` must be floor. Neither can be decided by looking at it alone — which is the point of this exercise.

Only positive numbers appear in the Collatz sequence, so writing `next` never exposes the difference. It starts to matter the moment you divide a negative number. The rounding direction is specified in §9.1 of `documents/LANGUAGE_SPEC.md`.

</details>

**Exercise 13-5** (★★★, comprehensive) Pick one of the three case studies and extend it. For example: add a filter for "words of n characters or more" to the text statistics; add a monthly summary to the ledger (a `record Month` combined with `filter`); or write a function giving the number of steps a Collatz sequence takes to reach 1.

<details><summary>Answer</summary>

Taking the third: the number of steps is the `length` of the `takeWhile` result, plus one.

```text
lune> length(takeWhile(iterate(next, 7), fn n: Int -> n != 1)) + 1
17 : Int
```

`length` is being used on an infinite list, but `takeWhile` has made it finite first, so it terminates (§8.5). "Transform while infinite, make it finite, then consume" — whether you keep that order is the test of whether lazy evaluation is under your control.

</details>

---

**More precisely** — this chapter uses no new features. The specifications each section rests on: records in `documents/RECORD_FIELD_SPEC.md`, ADTs and `match` in `documents/MATCH_EXHAUSTIVENESS_SPEC.md`, lists and the lazy combinators in `documents/STANDARD_LIBRARY_SPEC.md` §6, and `seq`/`deepForce` in `documents/LAZY_EVALUATION_SPEC.md` §9–10. The code examples of this chapter live in `books/examples-en/ch13/` and are all verified against the real CLI.
