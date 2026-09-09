# Appendix B: Standard Library Reference

All 41 names in the prelude. No `import` is needed: they are visible from the start, in every file and in the REPL.

To know what the implementation in front of you actually has, the surest thing is to ask the REPL.

```console
lune> :env
```

Each entry gives a type signature, a one-line description and an example. Those that work on lists also say **whether they can be used on an infinite list**, which is the distinction that matters most in practice in Lune (chapter 8).

> **The "infinite" column** — ○ means it comes back when applied to an endless list such as `naturalsFrom(1)`; × means it tries to reach the end and does not come back. These marks are not guesses: each function was actually applied to an infinite list.

A `[T]` in a type is a type variable (any type at all).

## B.1 Option — "there might be a value"

| Name | Type | Meaning |
| --- | --- | --- |
| `Some` | `[T] T -> Option[T]` | build the "there is a value" form |
| `None` | `Option[T]` | the "there is no value" form |
| `isSome` | `[T] Option[T] -> Bool` | is it a `Some`? |
| `isNone` | `[T] Option[T] -> Bool` | is it a `None`? |
| `getOrElse` | `[T] Option[T] -> T -> T` | take the contents; the second argument if `None` |
| `optionMap` | `[T, U] Option[T] -> (T -> U) -> Option[U]` | apply a function to the contents only |

```text
lune> Some(3)
Some(3) : Option[Int]
lune> getOrElse(Some(3), 0)
3 : Int
lune> getOrElse(None, 0)
0 : Int
lune> optionMap(Some(3), fn n: Int -> n * 2)
Some(6) : Option[Int]
```

`Option` is chapter 5; choosing between it and `null` is chapter 7.

## B.2 Result — "success or failure"

| Name | Type | Meaning |
| --- | --- | --- |
| `Ok` | `[T, E] T -> Result[T, E]` | build the success form |
| `Err` | `[T, E] E -> Result[T, E]` | build the failure form; it can carry a reason |
| `isOk` | `[T, E] Result[T, E] -> Bool` | is it a success? |
| `isErr` | `[T, E] Result[T, E] -> Bool` | is it a failure? |
| `unwrapOr` | `[T, E] Result[T, E] -> T -> T` | the contents on success, the second argument on failure |
| `resultMap` | `[T, U, E] Result[T, E] -> (T -> U) -> Result[U, E]` | apply a function only on success |

```text
lune> Err("boom")
Err("boom") : Result[T, String]
lune> unwrapOr(Ok(3), 0)
3 : Int
lune> unwrapOr(Err("boom"), 0)
0 : Int
lune> resultMap(Ok(3), fn n: Int -> n * 2)
Ok(6) : Result[Int, E]
```

Unlike `Option`, `Err` **can carry the reason for the failure**. Used in chapter 5 and in the ledger of chapter 13.

## B.3 List — the basics

| Name | Type | Meaning | Infinite |
| --- | --- | --- | --- |
| `Nil` | `List[T]` | the empty list | — |
| `Cons` | `[T] T -> List[T] -> List[T]` | prepend one element | ○ |
| `head` | `[T] List[T] -> Option[T]` | the first element; `None` when empty | ○ |
| `tail` | `[T] List[T] -> Option[List[T]]` | everything but the first; `None` when empty | ○ |
| `isEmpty` | `[T] List[T] -> Bool` | is it empty? | ○ |
| `length` | `Any -> Int` | the number of elements (works on strings too) | **×** |
| `range` | `Int -> Int -> List[Int]` | `range(a, b)` is a up to but not including b | — |
| `map` | `[T, U] List[T] -> (T -> U) -> List[U]` | apply a function to each element | ○ |
| `filter` | `[T] List[T] -> (T -> Bool) -> List[T]` | keep the elements satisfying a condition | ○ |
| `fold` | `[T, U] List[T] -> U -> (U -> T -> U) -> U` | collapse it, from an initial value | **×** |
| `take` | `[T] List[T] -> Int -> List[T]` | the first n | ○ |
| `drop` | `[T] List[T] -> Int -> List[T]` | discard the first n | ○ |
| `takeWhile` | `[T] List[T] -> (T -> Bool) -> List[T]` | take while the condition holds | ○ |
| `dropWhile` | `[T] List[T] -> (T -> Bool) -> List[T]` | discard while the condition holds | ○ |
| `zip` | `[T, U] List[T] -> List[U] -> List[Tuple[T, U]]` | pair two lists; stops with the shorter | ○ |
| `zipWith` | `[T, U, V] List[T] -> List[U] -> (T -> U -> V) -> List[V]` | pair them and apply a function | ○ |

```text
lune> let xs = [1, 2, 3]
ok
lune> head(xs)
Some(1) : Option[Int]
lune> tail(xs)
Some((2 3)) : Option[List[Int]]
lune> range(1, 5)
(1 2 3 4) : List[Int]
lune> map(xs, fn n: Int -> n * 2)
(2 4 6) : List[Int]
lune> filter(xs, fn n: Int -> n % 2 == 1)
(1 3) : List[Int]
lune> fold(xs, 0, fn a: Int n: Int -> a + n)
6 : Int
lune> zip(xs, ["a", "b"])
((1, "a") (2, "b")) : List[Tuple[Int, String]]
lune> zipWith(xs, xs, fn a: Int b: Int -> a * b)
(1 4 9) : List[Int]
```

**Only `length` and `fold` cannot be used on an infinite list**, because reaching the end is their job. Everything else is safe: `map` or `filter` over an infinite list computes only as much as is later taken out (chapters 4 and 8). `drop` forces only the cells it discards, so it is safe too — but what it returns is still infinite, so keep a `take` in front of any display.

`range` shows `—` in the infinite column (it takes no list), but **the list it returns is lazy**: the spine is built only as far as it is consumed, so `take(range(1, 100000000), 5)` costs the same as `take(range(1, 11), 5)`. The width itself is free (§4.6).

Out-of-range and empty cases return plain values rather than raising.

```text
lune> take([1, 2, 3], 10)
(1 2 3) : List[Int]
lune> drop([1, 2, 3], 10)
() : List[Int]
lune> range(5, 1)
() : List[Int]
lune> head(Nil)
None : Option[T]
```

## B.4 List — building endless lists

| Name | Type | Meaning |
| --- | --- | --- |
| `naturalsFrom` | `Int -> List[Int]` | n, n+1, n+2, … |
| `iterate` | `[T] (T -> T) -> T -> List[T]` | apply a function to a seed over and over |
| `repeat` | `[T] T -> List[T]` | the same value forever |
| `cycle` | `[T] List[T] -> List[T]` | the given list, repeated forever |

```text
lune> take(naturalsFrom(1), 5)
(1 2 3 4 5) : List[Int]
lune> take(iterate(fn n: Int -> n * 2, 1), 5)
(1 2 4 8 16) : List[Int]
lune> take(repeat("x"), 3)
("x" "x" "x") : List[String]
lune> take(cycle([1, 2]), 5)
(1 2 1 2 1) : List[Int]
```

These four are infinite in themselves, so always cut them with `take` or `takeWhile`. Chapter 8.

## B.5 Display and output

| Name | Type | Meaning |
| --- | --- | --- |
| `show` | `Any -> String` | **turn** a value into a string in Lune's display form |
| `print` | `Any -> Unit` | print it (no newline) |
| `println` | `Any -> Unit` | print it with a newline |

```text
lune> show(42)
"42" : String
lune> show([1, 2])
"(1 2)" : String
lune> println("hi")
hi
() : Unit
```

`show` only **returns** a string; it puts nothing on the screen. `print` and `println` do that. `show("hi")` is `"\"hi\""` because turning a string into display form adds the quotes.

## B.6 Small tools

| Name | Type | Meaning |
| --- | --- | --- |
| `id` | `[T] T -> T` | return the argument unchanged |
| `const` | `[T, U] T -> U -> T` | return the first argument, ignoring the second |
| `not` | `Bool -> Bool` | negate a boolean |

```text
lune> id(7)
7 : Int
lune> const(1, 2)
1 : Int
lune> not(true)
false : Bool
```

The second argument of `const` stays lazy and is **never evaluated**. It is a one-line demonstration of chapter 4's "what is not used is not computed".

## B.7 Built-ins for observation

Tools for watching lazy evaluation with your own eyes. They are **not a stable public API** (`STANDARD_LIBRARY_SPEC.md` §8.1 says so explicitly). They exist for teaching and for tests.

| Name | Type | Meaning |
| --- | --- | --- |
| `crash` | `() -> Nothing` | raise a runtime error when evaluated |
| `tick` | `() -> Int` | increment an internal counter and return it |
| `tickCount` | `() -> Int` | the current counter; does not increment it |

`crash` is for demonstrating that nothing happens if it is not evaluated. `tick` counts **how many times something was evaluated**, which is the evidence that `let` is lazy.

```text
lune> let t1 = tick()
ok
lune> let t2 = tick()
ok
lune> tickCount()
0 : Int
```

Two bindings of `tick()` and the counter is still `0`. `let` is lazy, so neither has been called. With `strict let` it would be `2`. Chapter 4.

## B.8 seq and deepForce are not functions

These two are not prelude functions but **syntax of the language** (of the same family as `lazy` and `force`; they do not appear in `:env`).

```lune
seq a b          # evaluate a, then return b
deepForce x      # evaluate x all the way down
```

They are the tools for controlling the order and depth of evaluation, covered in §4.7.

## Where this appendix comes from

The type signatures were taken from the REPL's `:env` — that is, from what the implementation actually has. The descriptions follow `documents/STANDARD_LIBRARY_SPEC.md`. The "infinite" column is the result of applying each function to `naturalsFrom(1)` and seeing whether it came back.
