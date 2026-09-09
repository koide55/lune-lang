# Chapter 4: Lazy Evaluation — the Heart of Lune

Most programming languages compute in the order you wrote. Write `let x = expensive computation` and the expensive computation runs on that line — this is **strict evaluation**. Lune is different. **A value is not computed until it is needed.** This is **lazy evaluation**, and it lies under every other design decision in the language.

Lazy evaluation is sometimes called a trap for beginners, because you cannot see when the computation runs. Lune's answer was not to hide it but to **make it visible**. This chapter uses two instruments in the REPL, `:thunks` and `:trace`, so that you can watch the moment of evaluation with your own eyes. You do not have to take any of it on faith; all of it can be observed on the spot.

## 4.1 A let is a promise

In chapter 1 we saw the REPL answer nothing but `ok` to a `let`. It prints no value because **there is not a value yet**. Let us confirm that. Here we meet a built-in for observation, `crash()`: a function that always raises a runtime error when evaluated — a landmine.

```text
lune> let boom = crash()
ok
lune> boom
error[RUN0006]: crash() was evaluated
   = help: run `lune explain RUN0006` for a detailed explanation
```

Nothing happened on the line that bound the mine. It went off the moment `boom` was **used**.

`let name = expr` is not an instruction but a promise: "when the value of `name` is needed, compute it with this expression". If a strict language's `let` is a receipt, Lune's is an order slip.

## 4.2 Thunks — what is inside the promise

The container for such a not-yet-computed expression is called a **thunk**. A thunk holds an expression together with its environment, and is in one of three states.

| State | Meaning |
| --- | --- |
| `unevaluated` | not needed even once so far |
| `evaluated = value` | computed; remembers the value |
| `failed = error` | computed and failed; remembers the failure |

The REPL's `:thunks` command looks at the state of a binding **without causing any evaluation**. Let us watch the life of a thunk.

```text
lune> let x = 1 + 1
ok
lune> :thunks x
x : unevaluated
lune> x
2 : Int
lune> :thunks x
x : evaluated = 2
```

`1 + 1` was computed at the instant `x` was referred to. And what became of `boom`?

```text
lune> :thunks boom
boom : failed = error[RUN0006] crash() was evaluated
```

The failure is remembered too. §4.5 makes clear what that is worth.

> **Terminology** — making a thunk evaluate is called **forcing** it. "Force `x`" = "make `x` keep its promise now".

## 4.3 When does evaluation happen — watching with :trace

So when does forcing happen? Type `:trace on` and the REPL narrates every force as it occurs.

```text
lune> :trace on
trace on
lune> let x = 1 + 1
ok
lune> x + 1
force x + 1
  force 1 + 1
  => 2
=> 3
3 : Int
```

Read it like this:

- `force expr` — evaluation of that expression's thunk has begun (indentation is nesting depth)
- `=> value` — the matching force has finished

Notice that the line `let x = 1 + 1` produced **no trace at all**. A declaration causes no forcing. The moment you typed `x + 1`, the whole expression was forced, and inside it the contents of `x`, `1 + 1`, were forced.

Use `x` a second time and a third kind of event appears.

```text
lune> x
force x
  memo 1 + 1 => 2
=> 2
2 : Int
```

`memo` marks "we hit an already-computed value and used it instead of recomputing".

Roughly, **forcing happens wherever a value is looked at**: the operands of arithmetic and comparison, the condition of an `if`, the subject of a `match`, and display in the REPL or when running a file. Appendix A has the exact list, but in practice asking `:trace` is the surest way.

The same trace is available when running a file. Here is `trace_demo.lune`:

```lune
module trace_demo

let x = 1 + 1

let answer = x + x
```

```console
$ lune --eval answer --trace trace_demo.lune
force x + x
  force 1 + 1
  => 2
  memo 1 + 1 => 2
=> 4
4
```

`x` is used twice but computed once; the second time is a `memo`. (The trace goes to stderr, so redirecting separates it from the value.)

## 4.4 Arguments are lazy too — writing your own control structures

It is not only `let` that is lazy. **Function arguments are passed as thunks by default.**

```text
lune> def first(a: Int, b: Int): Int =
...     a
...
ok
lune> first(10, crash())
10 : Int
```

We passed `crash()` and nothing exploded. `b` is never used in the body, so it never got the chance to be forced.

This means more than saving work. **Control structures can be written as ordinary functions.** Here is `myif.lune`:

```lune
module myif

# Arguments are lazy by default, so control structures can be defined by hand.
def myIf(c: Bool, a: Int, b: Int): Int =
    if c then a else b

def myAnd(a: Bool, b: Bool): Bool =
    if a then b else false

let taken = myIf(true, 1, crash())

let skipped = myAnd(false, crash())
```

```console
$ lune --eval taken myif.lune
1
$ lune --eval skipped myif.lune
false
```

`myIf` never evaluates the branch it did not take. `myAnd` never looks at its right operand when the left is `false` — short-circuiting. In a strict language, `&&` and `if` short-circuit only because the language treats them specially, and a user cannot write the same thing as a function. In Lune, `if` and `&&` can in principle be reproduced as plain functions. That the core of the language can stay small is thanks to lazy evaluation.

## 4.5 Memoisation — never computed twice

Let us pin down the `memo` of §4.3. Here is the second instrument, `tick()`: a built-in that increments an internal counter each time it is called and returns the new value. Its partner `tickCount()` reads the counter without incrementing it. Together they are a witness to how many times a computation ran.

```text
lune> let t = tick()
ok
lune> tickCount()
0 : Int
lune> t
1 : Int
lune> t
1 : Int
lune> tickCount()
1 : Int
```

Binding alone leaves the counter at 0. The first use of `t` ran it exactly once, and the second use returned the remembered value. **A thunk is evaluated at most once.**

Failure works the same way. §4.2 said the `failed` state "remembers the failure". Here is the evidence.

```text
lune> let bad = tick() + crash()
ok
lune> tickCount()
0 : Int
lune> bad
error[RUN0006]: crash() was evaluated
   = help: run `lune explain RUN0006` for a detailed explanation
lune> tickCount()
1 : Int
lune> bad
error[RUN0006]: crash() was evaluated
   = help: run `lune explain RUN0006` for a detailed explanation
lune> tickCount()
1 : Int
```

The second `bad` produced the same error, but the counter stayed at 1 — **the failed computation was not re-run**. The remembered failure was re-sent.

Because of this, a Lune binding gives the same result (the same value, or the same failure) however often and whenever it is read. Nothing changes with the timing of the read, which is why laziness does not break the meaning of a program.

## 4.6 Only what you use — what laziness buys

So far we have looked at the *machinery* of laziness. This section is about what the machinery gives you.

Take `range(start, end)` from chapter 1 and call it with a slightly unreasonable width.

```text
lune> let huge = range(1, 100000000)
ok
lune> take(huge, 5)
(1 2 3 4 5) : List[Int]
lune> take(filter(huge, fn x -> x % 7 == 0), 3)
(7 14 21) : List[Int]
```

Five elements out of a hundred-million-element list, then three multiples of seven. **Both come back instantly**, and neither costs any memory.

The trick is the one from §4.1. `range` does not build a hundred million cells and then hand them over; it returns **one cell and a promise to make the rest**. `filter` and `take` have the same shape, so the moment `take(..., 3)` has its third element, every promise beyond it is left unforced. What is never built costs neither time nor memory.

It is not "build a list of a hundred million and then take five". It is "`range` grows exactly as far as taking five requires". **The consumer decides how long the list is.**

Let `tick()` from §4.5 do the counting.

```text
lune> let xs = map(range(1, 100000000), fn x -> tick())
ok
lune> tickCount()
0 : Int
lune> take(xs, 3)
(1 2 3) : List[Int]
lune> tickCount()
3 : Int
```

A `map` over a hundred million elements, evaluated **three** times — and zero times until something asked. In a strict language that expression means a hundred million calls and several gigabytes. Here it meant three calls.

### The boundary — a computation that needs everything still walks everything

Laziness does not make work disappear. It **defers the demand**. When an answer genuinely needs every element, the bill arrives in full.

```text
lune> length(filter(huge, fn x -> x < 10))
```

That took about **seven minutes** here (Ctrl-C is a reasonable response). The answer is `9`. `filter` cannot know that nothing beyond 9 matches without walking to the hundred-millionth element, and `length` counts to the end, so the whole list gets walked. This is not a weakness of the implementation but the **correct consequence** of lazy evaluation: the same expression in Haskell walks just as far.

The condition here, `x < 10`, is monotone over an ascending list, so what we actually meant was "stop when it stops holding". There is a different function for saying that.

```text
lune> takeWhile(huge, fn x -> x < 10)
(1 2 3 4 5 6 7 8 9) : List[Int]
```

`takeWhile` gives up at the first `false`, so the **whole** list comes back at once. `filter` can never finish without looking at everything; `takeWhile` can finish. In a lazy world that distinction shows up as a difference in speed.

For the same reason, do not ask the REPL to display `huge` itself: displaying demands every element. Put a `take` in front of anything you print. This test — **does the answer need every element?** — is treated properly in §8.5, against genuinely infinite lists, because a range wide enough is the same thing in practice.

## 4.7 The strictness toolbox

Lazy by default. But there are moments when you want it computed now, and Lune provides explicit opt-outs, graded by scope.

| Tool | Where you write it | Meaning |
| --- | --- | --- |
| `strict let x = expr` | a binding | evaluate at the moment of binding |
| `strict x: T` (short form `!x`) | a function parameter | evaluate at the moment of the call |
| `strict field: T` | a constructor field | evaluate at the moment of construction |
| `seq a b` | an expression | evaluate `a`, then return `b` |
| `deepForce x` | an expression | evaluate `x` all the way down |
| `lazy expr` / `force expr` | an expression | carry laziness around as the type `Lazy[T]` |

**strict let** — evaluates at binding time. Under `:thunks` it is not even a thunk any more.

```text
lune> strict let s = tick()
ok
lune> tickCount()
1 : Int
lune> :thunks s
s : value = 1
```

**strict parameters** — rewrite §4.4's `first` with strict parameters and even the unused argument is evaluated at the call.

```text
lune> def strictFirst(strict a: Int, strict b: Int): Int =
...     a
...
ok
lune> strictFirst(10, crash())
error[RUN0006]: crash() was evaluated
   = help: run `lune explain RUN0006` for a detailed explanation
```

**strict fields** — constructor fields are normally lazy as well (`Box(crash())` can be built without exploding), but `strict` makes them evaluate at construction.

```lune
module point

# A strict field is evaluated at the moment the value is constructed.
type Point =
    | Point(strict x: Int, strict y: Int)

let p = Point(crash(), 0)
```

```console
$ lune --eval p point.lune
error[RUN0006]: crash() was evaluated
   = help: run `lune explain RUN0006` for a detailed explanation
```

"Never let a `Point` holding an invalid value exist, even for an instant" — this returns in chapters 5 and 6 as a tool for designing data types.

**seq** — `seq a b` evaluates `a` and then returns `b`. Use it when you want to control the order of evaluation and nothing else.

```text
lune> let a = tick()
ok
lune> let answer = seq a 42
ok
lune> answer
42 : Int
lune> :thunks a
a : evaluated = 1
```

The moment `answer` was used, `a` — irrelevant to the value — was dragged along and evaluated.

**deepForce** — forcing normally evaluates only the outside of a value. When you want it evaluated all the way through, use `deepForce`.

```text
lune> let pair = (tick(), tick())
ok
lune> :thunks pair
pair : unevaluated
lune> deepForce pair
(2, 3) : Tuple[Int, Int]
lune> :thunks pair
pair : evaluated = (2, 3)
```

**lazy / force** — "if everything is lazy, why is there a `lazy`?" `lazy expr` is the tool for carrying laziness around **as a type**.

```text
lune> let delayed = lazy (40 + 2)
ok
lune> :type delayed
delayed : Lazy[Int]
lune> force delayed
42 : Int
```

`Int` and `Lazy[Int]` are different types. Writing `Lazy[T]` as a function's result or a field of a data structure puts "this may not have been computed yet" into the type signature, and whoever receives it has to open it explicitly with `force`. It promotes implicit laziness into a contract.

## 4.8 Bottomless recursion — RUN0005

Here is the notorious trouble spot of lazy evaluation: what happens when you define something in terms of itself?

```lune
module recursive

let x = x + 1
```

To know the value of `x` you need the value of `x` — waiting will not produce an answer. Type checking rejects this straightforward form at the door (the name being defined is not yet in scope on the right-hand side, so it is an undefined name).

```console
$ lune --check recursive.lune
```

```text,diagnostic
error[TYP0001]: undefined name: x
  --> recursive.lune:3:9
  |
3 | let x = x + 1
  |         ^ name is not defined
   = help: run `lune explain TYP0001` for a detailed explanation
```

But a cycle can also slip past the static check and appear only at run time. `--eval` in v0.1 runs without type checking, so this same file can show you. Will it loop forever?

```console
$ lune --eval x recursive.lune
```

```text,diagnostic
error[RUN0005]: recursive thunk evaluation: this value's definition depends on its own result
   = hint: recursive values cannot be computed; use a recursive function (`def`) instead, or break the reference cycle
   = help: run `lune explain RUN0005` for a detailed explanation
```

It will not. **It is detected immediately.** The mechanism is in the thunk states of §4.2: on entering evaluation, a thunk marks itself "being evaluated" internally. If the same thunk is forced again during that evaluation, the definition has come back round to itself — no amount of waiting would help — so `RUN0005` is reported on the spot. `lune explain RUN0005` explains that mechanism as part of the diagnostic.

> **Aside: `<<loop>>`** — Haskell (GHC), the home of lazy evaluation, has a similar detection, but reports it with a curt `<<loop>>`, and sometimes fails to detect it and really does loop. Lune turned the detection into teaching material with a diagnostic code, so that `explain` can also tell you *why* it need not loop forever.

Note that **recursive functions are perfectly fine**.

```text
lune> def fact(n: Int): Int =
...     if n == 0 then 1 else n * fact(n - 1)
...
ok
lune> fact(5)
120 : Int
```

The body of a `def` does not run until it is called, so `fact(n - 1)` does not force the definition of `fact`. It is recursive *values* that cannot exist.

## 4.9 Living with laziness

The tools are all here. To finish, some guidance on when to use what.

**Where laziness pays:**

- **Values that may not be used** — defaults, error messages, one side of a branch. Writing them costs nothing.
- **Your own control structures and short-circuiting logic** (§4.4).
- **Infinite data structures** — the crown jewel. Chapter 8 awaits.

**Where to choose strictness:**

- **Side effects whose order matters** — output that runs "in the order it happened to be needed" is bewildering. Keep IO strict (chapter 9).
- **Measurement and debugging** — when you want to time "this line" and the computation keeps escaping backwards, nail it down with `strict let` or `seq`.
- **Piled-up thunks** — a loop can grow a towering stack of unevaluated computations. We revisit this with `fold` in chapter 8.

And when in doubt, **ask `:thunks` and `:trace`**. The instruments you used in this chapter are the debugging tools you will use in earnest.

> **Break it** — bind an expression that divides by `0` and watch the life of the thunk.
>
> ```text,diagnostic
> lune> let half = 1 / 0
> ok
> lune> half
> error[RUN0006]: division by zero
>    = hint: the right operand of `/` evaluated to 0
>    = help: run `lune explain RUN0006` for a detailed explanation
> lune> :thunks half
> half : failed = error[RUN0006] division by zero
> ```
>
> Nothing at the binding (lazy), a failure on use (force), and the failure remembered (memoisation). The whole chapter in three lines.

## Summary

| Concept | In one line |
| --- | --- |
| Lazy evaluation | a value is not computed until it is needed |
| Thunk | the container of an unevaluated expression: `unevaluated` / `evaluated` / `failed` |
| Forcing | making a thunk evaluate; happens wherever a value is looked at |
| Memoisation | evaluated at most once; both success and failure are remembered |
| Only what you use | the consumer decides the length; the width of a `range` is free |
| Does it need everything? | if it does, it walks it all (`length`, `fold`, display); if not, `take` / `takeWhile` |
| `:thunks` / `:trace` | look at the state / narrate the forcing. When in doubt, these |
| `strict let` / strict parameters / strict fields | opting out of laziness |
| `seq` / `deepForce` | controlling the order and the depth of evaluation |
| `lazy` / `force` and `Lazy[T]` | making laziness explicit in the type |
| `RUN0005` | a recursive value cannot exist; make it a function |

## Exercises

**Exercise 4-1** (★) Typing the following in order, what does each line print? Predict, then check.

```text
lune> let u = tick()
lune> let v = tick()
lune> v
lune> :thunks
lune> u
```

<details><summary>Answer</summary>

```text
lune> let u = tick()
ok
lune> let v = tick()
ok
lune> v
1 : Int
lune> :thunks
u : unevaluated
v : evaluated = 1
lune> u
2 : Int
```

`u`, defined first, is 2; `v`, defined second, is 1. The counter advances in the order things are **used**, not the order they are **defined**. What decides the order of evaluation is not the layout of the program but demand — the core of lazy evaluation.

</details>

**Exercise 4-2** (★★) Following `myAnd` (§4.4), write `myOr`, which returns `true` without evaluating its right operand when the left one is `true`. You pass when `myOr(true, crash())` does not explode.

<details><summary>Answer</summary>

```lune
module answers

# Exercise 4-2: myOr short-circuits — a true on the left never evaluates the right.
def myOr(a: Bool, b: Bool): Bool =
    if a then true else b

let shortCircuited = myOr(true, crash())
```

```console
$ lune --eval shortCircuited ex4-2.lune
true
```

`if` evaluates only the condition `a`. When the chosen branch is the literal `true`, the thunk for `b` is never even touched.

</details>

**Exercise 4-3** (★★) Define one `let t = tick()` and one `strict let s = tick()`, and use `tickCount()` and `:thunks` to explain the difference.

<details><summary>Answer</summary>

Reading `tickCount()` straight after the definitions gives 1 — only the `strict let` has run. Under `:thunks`, `t : unevaluated` against `s : value = 1`. `s` never went through a thunk; it became a value at the moment of binding. `t` is computed later, the first time it is used.

</details>

**Exercise 4-4** (★★) List elements are lazy as well. So does `length(xs)` succeed for `let xs = [crash(), 1, 2]`? Predict, then check.

<details><summary>Answer</summary>

```text
lune> let xs = [crash(), 1, 2]
ok
lune> length(xs)
3 : Int
```

It succeeds. `length` counts only the **spine** of the list (the chain of cells) and never forces the **elements**. That distinction — evaluate the structure, not the contents — is exactly the mechanism behind the infinite lists of chapter 8.

</details>

**Exercise 4-5** (★★★, in reverse) Produce a real `RUN0005`. Then explain why `--check` on the same file reports `TYP0001` rather than `RUN0005`.

<details><summary>Answer</summary>

The smallest reproduction is a file containing `let x = x + 1`, run with `--eval x` (§4.8). `--check` gives `TYP0001` because the type checker works by the rule that the name being defined is not yet in scope while its right-hand side is checked, so self-reference is rejected at the door as an undefined name. The type checker prevents cycles of names statically; the evaluator detects a cycle that appears at run time with `RUN0005`. Two layers of defence.

</details>

---

**More precisely** — the complete list of thunk state transitions and forcing boundaries is in `documents/LAZY_EVALUATION_SPEC.md`; the display specification for `:thunks` and `:trace` is in `documents/REPL_SPEC.md` §5.1–5.2. `crash`, `tick` and `tickCount` are the observation built-ins of `documents/STANDARD_LIBRARY_SPEC.md` §8.1. The code examples of this chapter live in `books/examples-en/ch04/` and are all verified against the real CLI.
