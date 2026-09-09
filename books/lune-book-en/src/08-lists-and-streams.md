# Chapter 8: Lists and Streams

This is the chapter where the lazy evaluation of chapter 4 turns into data structure design. The first half relearns properly the lists we have used since chapter 1. In the second half those same lists become **infinite** — with no new type involved. A Lune list is born able to be infinite.

## 8.1 What a list really is — Cons and Nil

`[1, 2, 3]` is sugar. A list is really an ordinary ADT defined in the prelude: two constructors, writable with the tools of chapter 5.

```text
lune> :type Cons
Cons : [T] T -> List[T] -> List[T]
lune> :type Nil
Nil : List[T]
lune> Cons(1, Cons(2, Nil))
(1 2) : List[Int]
```

`Nil` is the empty list and `Cons(head, rest)` is "a first value, and the rest of the list". `[1, 2]` means `Cons(1, Cons(2, Nil))` (`Nil`, like the prelude's `None`, is registered as a value).

Now recall chapter 4: **constructor fields are lazy by default**. So the "rest" of a `Cons` is a thunk, not computed until needed. That single fact carries the whole second half of this chapter.

## 8.2 The basic tools — opening, counting, transforming

First, opening. `head` and `tail` **return an `Option`**.

```text
lune> head([1, 2, 3])
Some(1) : Option[Int]
lune> head([])
None : Option[T]
lune> tail([1, 2, 3])
Some((2 3)) : Option[List[Int]]
lune> isEmpty([])
true : Bool
```

An empty list has no first element. Returning a "might not be there" answer as an `Option` is exactly the design of chapter 5. That said, the best way to open a list is not to peel an `Option` but to **destructure it directly with `match`**, as §8.6 does.

The transforming tools are the familiar `map` / `filter` / `fold`, plus `take` / `drop` / `range` / `length`. Here are their types by way of revision — note that all of them take the list first and the tool second.

| Function | Type (in outline) | In a phrase |
| --- | --- | --- |
| `map(xs, f)` | `List[T] -> (T -> U) -> List[U]` | `f` over every element |
| `filter(xs, p)` | `List[T] -> (T -> Bool) -> List[T]` | only the elements where `p` holds |
| `fold(xs, init, f)` | `List[T] -> U -> ((U, T) -> U) -> U` | collapse it |
| `take(xs, n)` / `drop(xs, n)` | | take / discard the first `n` |
| `head` / `tail` | | return an `Option` |
| `length` / `isEmpty` / `range` | | length / emptiness / a range of integers |

## 8.3 The tail is lazy — a list can be infinite

To the point. The tail of a `Cons` is a thunk. Which means the computation of "the rest of the list" **is allowed never to finish**. The prelude has functions that build exactly such lists.

```lune
naturalsFrom(n)   # [n, n+1, n+2, ...]
iterate(f, x)     # [x, f(x), f(f(x)), ...]
repeat(x)         # [x, x, x, ...]
cycle(xs)         # xs, repeated forever
```

Let us look inside an infinite list with `:thunks`, which is safe here because it causes no evaluation.

```text
lune> let nat = naturalsFrom(1)
ok
lune> :thunks nat
nat : unevaluated
lune> head(nat)
Some(1) : Option[Int]
lune> :thunks nat
nat : evaluated = Cons(1, <thunk>)
lune> take(nat, 5)
(1 2 3 4 5) : List[Int]
lune> :thunks nat
nat : evaluated = Cons(1, Cons(2, Cons(3, Cons(…))))
```

`Cons(1, <thunk>)` — only the leading 1 has been computed and all the rest is still a promise. Asking for five with `take` advanced the evaluation by exactly that much. **An infinite list is a sequence that materialises only as far as it is needed**, and `:thunks` shows you how far that is. The instruments of chapter 4 have their finest hour here.

Combined with `take`, an infinite list is handled like any other value. Here is `infinite.lune`:

```lune
module infinite

# The tail of a List is lazy. That is how a list can be infinite.
let firstFive = take(naturalsFrom(1), 5)

let powersOfTwo = take(iterate(fn x: Int -> x * 2, 1), 6)

let threeSevens = take(repeat(7), 3)

let pattern = take(cycle([1, 2, 3]), 7)
```

```console
$ lune --eval powersOfTwo infinite.lune
(1 2 4 8 16 32)
$ lune --eval pattern infinite.lune
(1 2 3 1 2 3 1)
```

## 8.4 Lazy combinators — transforming while still infinite

`map` and `filter` preserve the laziness of the tail, so an **infinite list can be transformed and stay infinite**. Harvest as much as you need with `take` at the end.

```text
lune> take(map(naturalsFrom(1), fn n: Int -> n * n), 5)
(1 4 9 16 25) : List[Int]
lune> takeWhile(naturalsFrom(1), fn x -> x < 4)
(1 2 3) : List[Int]
lune> take(dropWhile(naturalsFrom(1), fn x -> x < 10), 3)
(10 11 12) : List[Int]
lune> take(zip(naturalsFrom(1), cycle(["a", "b"])), 4)
((1, "a") (2, "b") (3, "a") (4, "b")) : List[Tuple[Int, String]]
lune> take(zipWith(naturalsFrom(1), naturalsFrom(10), fn a: Int b: Int -> a + b), 3)
(11 13 15) : List[Int]
```

- `takeWhile` / `dropWhile` — take or discard while the condition holds
- `zip(a, b)` — pair two lists into a list of tuples (stopping with the shorter one)
- `zipWith(a, b, f)` — pair them and combine with `f`

Zipping two infinite lists is fine as well. The result is another infinite list, and only what you use gets computed.

## 8.5 Operations that do not stop — the consuming functions

Some tools, however, **consume the list to the end**: `fold` and `length`. Used on an infinite list, the end never arrives, so they **do not stop**.

```text
lune> length(naturalsFrom(1))
```

The prompt does not come back (interrupt with Ctrl-C). Note that it is not an error — counting one by one forever is a perfectly correct computation that happens never to finish. The same goes for displaying an infinite list in full: `take` some of it before printing.

Telling them apart is simple: **does producing the answer require every element?** `take`, `map`, `filter`, `takeWhile`, `zip` do not (they preserve laziness). `fold` and `length` do. `drop(xs, n)` forces only the `n` cells it discards, so it is safe on an infinite list — `take(drop(naturalsFrom(1), 5), 3)` gives `(6 7 8)` — but the list it hands back is still infinite, so keep a `take` in front of the display. `filter` has a trap of its own: if no element ever satisfies the condition again, it keeps running while looking for the next one.

## 8.6 Worked examples — thinking in infinite lists

**The Fibonacci sequence.** Read it as "keep advancing the state `(a, b)` to `(b, a+b)`", which is what `iterate` is for. Here is `fib.lune`:

```lune
module fib

# Advance the state (a, b) by one step: (0,1) -> (1,1) -> (1,2) -> (2,3) -> ...
def step(p: Tuple[Int, Int]): Tuple[Int, Int] =
    match p:
        | (a, b) -> (b, a + b)

def fst(p: Tuple[Int, Int]): Int =
    let (a, _) = p
    a

# The Fibonacci sequence itself, as an infinite list.
let fibs = map(iterate(step, (0, 1)), fst)

let first10 = take(fibs, 10)
```

```console
$ lune --eval first10 fib.lune
(0 1 1 2 3 5 8 13 21 34)
```

`fibs` is not a name for "ten Fibonacci numbers" but for **the Fibonacci sequence itself**. How many to use is decided later, by whoever uses it. Separating production from consumption is the real design benefit of infinite lists.

**The sieve of Eratosthenes.** An infinite list of primes. Here is `primes.lune`:

```lune
module primes

# The sieve of Eratosthenes. Take the head p as a prime, strain the multiples
# of p out of the rest, and leave the continuation to be computed on demand.
def sieve(xs: List[Int]): List[Int] =
    match xs:
        | Cons(p, rest) -> Cons(p, sieve(filter(rest, fn n: Int -> n % p != 0)))
        | Nil -> Nil

let primes = sieve(naturalsFrom(2))

let first10 = take(primes, 10)
```

```console
$ lune --eval first10 primes.lune
(2 3 5 7 11 13 17 19 23 29)
```

Three lines with a lot packed into them.

- The list is destructured straight into `Cons(p, rest)` with `match` (more direct than `head`/`tail`).
- The second argument of the returned `Cons` — the recursive call `sieve(...)` — **goes into a lazy field**, so the endless recursion does not run away. The next prime is strained out only when somebody asks for it.
- The bare `Nil` on the right of `| Nil -> Nil` would have an undetermined type argument on its own (like `None : Option[T]` in §5.6). Here the result annotation `List[Int]` reaches the arm as an expected type and settles `T = Int`.

> **Break it** — get the argument order of `take` wrong and the type tells you immediately.
>
> ```text,diagnostic
> lune> take(5, naturalsFrom(1))
> error[TYP0003]: expected List[T], got Int
>    = help: run `lune explain TYP0003` for a detailed explanation
> ```
>
> List first, count second. Remember the convention from the table in §8.2: list functions take the list as their first argument.

## Summary

| Concept | In one line |
| --- | --- |
| `Cons` / `Nil` | what a list really is; `[1, 2]` is `Cons(1, Cons(2, Nil))` |
| a lazy tail | the "rest" is a thunk, which is how a list can be infinite |
| `head` / `tail` | return an `Option`; to destructure, use `match` on `Cons(x, rest)` |
| `naturalsFrom` / `iterate` / `repeat` / `cycle` | four ways to build an infinite list |
| laziness-preserving tools | `take` / `map` / `filter` / `takeWhile` / `dropWhile` / `zip` / `zipWith` |
| consuming tools | `fold` / `length` — not for infinite lists |
| observing | `:thunks` shows how far a list has materialised, without evaluating it |

## Exercises

**Exercise 8-1** (★) Predict the results, then check.

```text
take(cycle([1, 2]), 5)
takeWhile(naturalsFrom(1), fn x -> x < 4)
take(zip(naturalsFrom(1), cycle(["a", "b"])), 4)
```

<details><summary>Answer</summary>

`(1 2 1 2 1)`, `(1 2 3)`, `((1, "a") (2, "b") (3, "a") (4, "b"))`. The third zips an infinite sequence of numbers with an infinite alternating pattern — neither ends, but only four were asked for, so only four were computed.

</details>

**Exercise 8-2** (★★) Build the infinite list of squares (1, 4, 9, 16, ...) and take the first five **even** ones.

<details><summary>Answer</summary>

```lune
module answers

# Exercise 8-2: five even numbers from the infinite list of squares.
let squares = map(naturalsFrom(1), fn n: Int -> n * n)

let evenSquares = take(filter(squares, fn s: Int -> s % 2 == 0), 5)
```

```console
$ lune --eval evenSquares ex8-2.lune
(4 16 36 64 100)
```

`map` → `filter` → `take`: two transformations applied while still infinite, then the harvest.

</details>

**Exercise 8-3** (★★) For the sensor readings `[1, 4, 7, 10]`, compute the average of each neighbouring pair (a moving average), `(2.5 5.5 8.5)`. Hint: shift the list by one and `zipWith` it against itself.

<details><summary>Answer</summary>

```lune
module answers

# Exercise 8-3: the average of each neighbouring pair (a moving average).
# Shift the list by one and zip it with itself.
let readings = [1, 4, 7, 10]

let smoothed = zipWith(readings, drop(readings, 1), fn a: Int b: Int -> (a + b) / 2)
```

```console
$ lune --eval smoothed ex8-3.lune
(2.5 5.5 8.5)
```

`zipWith` stops with the shorter side (the dropped one), so there is no edge case to write.

</details>

**Exercise 8-4** (★★★) Build the infinite list of Lucas numbers (2, 1, 3, 4, 7, ... — the same recurrence as Fibonacci, starting from `(2, 1)`) and take the first ten.

<details><summary>Answer</summary>

```lune
module answers

# Exercise 8-4: the Lucas numbers. The same recurrence as Fibonacci, with the
# seed changed to (2, 1).
def step(p: Tuple[Int, Int]): Tuple[Int, Int] =
    match p:
        | (a, b) -> (b, a + b)

def fst(p: Tuple[Int, Int]): Int =
    let (a, _) = p
    a

let lucas = map(iterate(step, (2, 1)), fst)

let first10 = take(lucas, 10)
```

```console
$ lune --eval first10 ex8-4.lune
(2 1 3 4 7 11 18 29 47 76)
```

The only difference from `fib.lune` is the seed of `iterate`. Once you see the correspondence "recurrence = the `step` function, sequence = `iterate`", the shape works for any recurrence.

</details>

**Exercise 8-5** (★, in reverse) Write an expression that does not stop. You need not run it (if you do, have Ctrl-C ready). Explain why it does not stop, in the words of §8.5.

<details><summary>Answer</summary>

For example `length(naturalsFrom(1))`, `fold(repeat(1), 0, fn a x -> a + x)`, or `takeWhile(naturalsFrom(1), fn x -> x > 0)` (the condition is true forever). Each needs every element to produce its answer. A slightly meaner example is `head(filter(naturalsFrom(1), fn x -> x < 0))` — `filter` itself preserves laziness, but the first element is never found.

</details>

---

**More precisely** — the lazy field of `Cons` and the laziness of each function (how far it forces) are documented per function in `documents/STANDARD_LIBRARY_SPEC.md` §6. Even the fact that `take(list, 0)` does not evaluate `list` is specified. The code examples of this chapter live in `books/examples-en/ch08/` and are all verified against the real CLI.
