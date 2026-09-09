# Chapter 9: Writing Imperatively — var, while, for and IO

Did you notice? In eight chapters you have **never once modified a variable**. The temperature table, the infinite list of primes, the rock-paper-scissors judgement — all of it was written by naming values and combining them in expressions.

Even so, there are moments when you want to turn a counter, or update a running result. Lune's answer is pragmatic: **imperative code is a good tool as long as it is used in small doses.** This chapter covers the mutable binding `var`, the loops `while` and `for`, and `IO:`, the place where output goes. The watchword is: **keep the commands inside a block and hand a value back out.**

## 9.1 The block idiom — an island of commands

First, look at where Lune puts imperative code. Here is `counter.lune`:

```lune
module counter

# var and while live inside a block; the last expression is its result.
let answer =
    var i = 0
    var total = 0
    while i < 5:
        total = total + i
        i = i + 1
    total
```

```console
$ lune --eval answer counter.lune
10
```

Inside the block, variables are reassigned and a loop turns. But **from outside, `answer` is simply an `Int`**. It is the same shape as the block `let` of chapter 2, with the final expression `total` as the value of the whole block. The imperative process is sealed on its island, and outside the island it is the world of expressions as before. As long as you keep this shape, imperative code does not contaminate the rest of the program.

And as an inhabitant of chapter 4, one remark: this `let answer = ...` is lazy too. Until somebody uses `answer`, the loop does not turn even once.

## 9.2 var — a strict mutable binding

A binding that can be reassigned is made with `var`.

```lune
var count = 0
count = count + 1
```

There are two differences from `let`. It is **mutable**, and it is **strict** (the right-hand side is evaluated at the moment of binding). `tick()` from chapter 4 confirms it.

```text
lune> var t = tick()
ok
lune> tickCount()
1 : Int
```

The counter advanced on the binding alone — with `let` it would still be 0. A variable whose value changes cannot be reasoned about if you also cannot say when it is evaluated, so remember that `var` is not lazy.

| | `let` | `var` |
| --- | --- | --- |
| reassignment | no (immutable) | yes |
| evaluation | lazy (not computed until used) | strict (computed at the binding) |

Only a name can be assigned to. Besides `i = i + 1`, the compound assignments `+= -= *= /= //= %=` are available (`i += 1` means exactly `i = i + 1`). One pitfall: `/` is always true division, so `x /= 2` on an `Int` variable is a type error (the result would be a `Double`). To divide an integer and stay in integers, use floor division, `x //= 2` (`//` is in §2.2).

That "no" is a check, not an intention. Assigning to a `let` reports `TYP0013`.

```text
lune> let a = 1
ok
lune> a = 2
error[TYP0013]: cannot assign to `a`: it is bound with `let` and is immutable
  --> <repl:2>:1:1
  |
1 | a = 2
  | ^ this binding cannot be assigned to
   = hint: declare it with `var a = ...` if it has to change
   = help: run `lune explain TYP0013` for a detailed explanation
lune> a
1 : Int
```

Files are no different. Running `lune --check` on `letassign.lune` reports the same `TYP0013`, pointing at the assignment.

`let` is not the only immutable thing. **Function parameters**, **`for` variables** and names bound by a pattern cannot be assigned to either. The only binding that may change is a `var`. The check looks at the nearest binding, so a `let x` inside a block stays immutable even when an outer `var x` exists.

## 9.3 while — the smallest loop

`while condition:` repeats a block while the `Bool` condition holds. `counter.lune` in §9.1 is all there is to it — the condition is evaluated **every time round**, and the whole `while` expression is always `Unit`. In other words `while` is not a tool for producing a value but a tool for reassigning a `var`.

There is no `break` or `continue`. To leave early, weave the condition into the loop condition (as in `while i < 5 && not(done):`). When that starts to get tiresome, it is usually a sign that the code **wants to be recursion or a `fold`** (chapters 3 and 8).

## 9.4 for — walking a list

When all you want is to do something to every element of a list, `for` is more concise. Here is `fortotal.lune`:

```lune
module fortotal

let pairs = [(1, 10), (2, 20)]

# A for pattern may be any irrefutable one, as in a let.
let total =
    var result = 0
    for (left, right) in pairs:
        result = result + left + right
    result
```

```console
$ lune --eval total fortotal.lune
33
```

The form is `for pattern in list:`, and the pattern follows the same rule as in a `let` (chapter 5): an **irrefutable** pattern such as a tuple can destructure, and a pattern that could fail is rejected.

```text,diagnostic
lune> for Some(x) in [Some(1), Some(2)]:
...     println(x)
...
error[TYP0008]: refutable pattern in for binding: Some(x)
  --> <repl:1>:1:5
  |
1 | for Some(x) in [Some(1), Some(2)]:
  |     ^^^^ this pattern can fail to match
   = hint: the pattern does not cover None
   = hint: use `match` to handle all cases of Option[Int]
   = help: run `lune explain TYP0008` for a detailed explanation
```

Only a `List[T]` can be walked. Passing something else, as `badfor.lune` does, has a diagnostic of its own.

```text,diagnostic
error[TYP0006]: for iterable must be List, got Int
  --> badfor.lune:5:14
  |
5 |     for x in 42:
  |              ^^ iterable must be List[T]
   = help: run `lune explain TYP0006` for a detailed explanation
```

`for` is `Unit` as well. And since it advances by forcing the spine one step at a time, **a `for` over an infinite list does not come back** — think of it as one of the consuming tools of chapter 8.

## 9.5 IO — output and laziness

We have used `println` many times, but output has a trap of its own in a lazy world. Watch.

```text
lune> let p = println("hi")
ok
lune> p
hi
() : Unit
```

The `let` line printed **nothing**. `println("hi")` was wrapped in a thunk and ran only when `p` was used. In a lazy world, then, *when* output happens is decided by *when* a value is needed — an awkward property for a program that wants characters on the screen in a particular order.

So output is **collected into an `IO:` block**. Here is `io.lune`:

```lune
module io

# Collect output in an IO block, which runs top to bottom.
def report(): Unit =
    IO:
        println("one")
        println("two")

let run = report()
```

```console
$ lune --eval run io.lune
one
two
()
```

The statements in an `IO:` block run **top to bottom** when the block runs. It is also a declaration that "the side effects whose order matters are here", and a marker for the reader. (In v0.1, `IO:` is that placement convention rather than strict effect tracking in the type system; the future specification plans to strengthen it.)

As a matter of style, remember: **computation in pure functions, output inside IO**. Split the decision logic into a function returning a `String` and pour it through a `for` inside `IO:` — exercise 9-2 (FizzBuzz) is practice at that separation.

## 9.6 raise / throw — the last resort

There is an expression for raising a runtime error yourself.

```text,diagnostic
lune> let bad = raise "failed"
ok
lune> bad
error[RUN0006]: failed
   = help: run `lune explain RUN0006` for a detailed explanation
```

`raise expr` (and its synonym `throw`) raises a runtime error when evaluated. As ever, `let` is lazy, so binding it does nothing and using it sets it off — think of it as your own version of `crash()` and you will be about right.

And an important caution: **there is no `try`/`catch`**. There is no way to catch a raised error inside the program. Express recoverable failure with the tools that **return failure as a value**: a monomorphic result type or `Result` from chapter 5, or `T?` from chapter 7. `raise` is for the genuinely exceptional case where stopping the program is the correct response.

## Summary

| Concept | In one line |
| --- | --- |
| the block idiom | seal imperative code in a `let name =` block and return a value from the last expression |
| `var` | mutable and **strict**; only a name can be assigned to |
| `while condition:` | the condition is evaluated each time round; the expression is `Unit`; no break/continue |
| `for pattern in list:` | `List[T]` only (`TYP0006`); the pattern must be irrefutable (`TYP0008`) |
| order of output | collect it in an `IO:` block so laziness cannot shuffle it |
| the separating habit | computation in pure functions, output inside IO |
| `raise` / `throw` | nothing can catch it; return recoverable failure as a value |

## Exercises

**Exercise 9-1** (★) Compute the product of 1 to 10 (10!) with `while`.

<details><summary>Answer</summary>

```lune
module answers

# Exercise 9-1: the product of 1 to 10 (10!) with while.
let product =
    var i = 1
    var acc = 1
    while i <= 10:
        acc = acc * i
        i = i + 1
    acc
```

```console
$ lune --eval product ex9-1.lune
3628800
```

</details>

**Exercise 9-2** (★★) Write FizzBuzz. For 1 to 15, print `Fizz` for multiples of 3, `Buzz` for multiples of 5, `FizzBuzz` for both, and the number otherwise, one per line. Keep the decision and the printing separate.

<details><summary>Answer</summary>

```lune
module answers

# Exercise 9-2: FizzBuzz. The decision is a pure function; the printing is a
# for inside IO.
def fizzbuzz(n: Int): String =
    if n % 15 == 0:
        "FizzBuzz"
    elif n % 3 == 0:
        "Fizz"
    elif n % 5 == 0:
        "Buzz"
    else:
        show(n)

def main(): Unit =
    IO:
        for i in range(1, 16):
            println(fizzbuzz(i))

let run = main()
```

`fizzbuzz` is a pure function, so it can be unit-tested in the REPL (`fizzbuzz(15)` → `"FizzBuzz"`). The needs of output never mix with the decision logic — the separating habit of §9.5.

</details>

**Exercise 9-3** (★★) Define one `let t = tick()` and one `var v = tick()`, and use `tickCount()` to explain the difference in when `let` and `var` evaluate.

<details><summary>Answer</summary>

`tickCount()` straight afterwards is 1 — only the `var` advanced it. The thunk of `let t` is still asleep and becomes 2 the first time `t` is used. It is the same timing as the `strict let` of chapter 4 (`var` = mutable + strict, `strict let` = immutable + strict).

</details>

**Exercise 9-4** (★★★) Rewrite §9.1's `counter.lune` (the sum of 0 to 4) without `var` or a loop. Then argue in your own words which is easier to read.

<details><summary>Answer</summary>

```text
lune> fold(range(0, 5), 0, fn a x -> a + x)
10 : Int
```

One line. Accumulating computations are `fold`'s home ground, and the loop version's four lines (two counters and two updates) carried a responsibility that has now vanished: not mixing up `i` and `total`. On the other hand, control that breaks out partway on a condition is sometimes more natural with `while`. A rule of thumb: **`fold` to walk data once and aggregate, `while` to turn a state machine**.

</details>

**Exercise 9-5** (★, in reverse) Produce `TYP0006` and `TYP0008`, each with the smallest `for` you can write.

<details><summary>Answer</summary>

`for x in 42: println(x)` (TYP0006 — 42 is not a List) and `for Some(x) in [Some(1)]: println(x)` (TYP0008 — `Some(x)` is a pattern that can fail). Both appear in §9.4. Notice too that TYP0008's hints are worded exactly as they were for `let` in chapter 5 — a `for` binding is a relative of a `let`.

</details>

---

**More precisely** — `var` and assignment are in `documents/LANGUAGE_SPEC.md` §7.3; `while` is in `documents/WHILE_LOOP_SPEC.md`; `for`, including the rule for forcing the spine, is in `documents/FOR_LOOP_SPEC.md`; `raise`/`throw` and `IO:` are in `documents/LANGUAGE_SPEC.md` §9.6–9.7. The code examples of this chapter live in `books/examples-en/ch09/` and are all verified against the real CLI.
