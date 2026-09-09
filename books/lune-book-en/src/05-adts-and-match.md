# Chapter 5: Algebraic Data Types and Pattern Matching

The types so far — numbers, strings, tuples — were raw material. In this chapter you make **types for your own program**. There are two tools: **algebraic data types** (ADTs), which declare the shape of data, and **`match`**, which takes a shape apart.

Learning these two changes how you write. Instead of checking a value and branching on a flag, you write down every possible shape in the type and let the compiler watch for missing cases. By the end of this chapter you will have seen Lune report a missing case **with a counterexample**.

## 5.1 Expressing a shape as a type

Consider a program about figures. A figure is either a circle or a rectangle. In Lune you write that "either" directly.

```lune
type Shape =
    | Circle(radius: Double)
    | Rect(width: Double, height: Double)
```

A value of type `Shape` is built with one of the **constructors**, `Circle` or `Rect`. No other shape is possible.

```text
lune> Circle(1.0)
Circle(1.0) : Shape
lune> Rect(3.0, 4.0)
Rect(3.0, 4.0) : Shape
```

Fields are declared with names (`radius: Double`). The names are there to make the declaration readable; values are built by position.

Constructors can also have no fields at all — plain alternatives, like the colours of a traffic light.

```lune
type Color =
    | Red
    | Green
    | Blue
```

```text
lune> let g = Green()
ok
lune> g
Green : Color
```

In v0.1, even a field-less constructor is **called** to produce a value (`Green()`). The exceptions are the prelude's `None` and `Nil` (the end of a list, chapter 8), which are registered as values from the start and can be used bare.

> **Terminology** — a type like `Shape`, meaning "exactly one of these", is called a **sum type**. Its counterpart is a product type, meaning "all of these at once", such as a tuple or a record. Types built by combining the two are what "algebraic data type" refers to. Chapter 6 ends with guidance on choosing between them.

## 5.2 match — taking a shape apart

The other side of an ADT is `match`. Here is a proper look at the construct chapter 1 kept hinting at.

```lune
def area(s: Shape): Double =
    match s:
        | Circle(r) -> r * r * 3.14159
        | Rect(w, h) -> w * h
```

`match` examines the **shape** of the subject from the top down and evaluates the arm that first fits. A pattern such as `Circle(r)` both confirms the shape and **extracts** the contents under the name `r`. Checking and destructuring in a single move — that is the pleasure of pattern matching.

`match` is an expression too, so it produces a value. An arm's body can span several lines (indented).

Many kinds of pattern can go in there. All at once:

```text
lune> def sign(n: Int): String =
...     match n:
...         | 0 -> "zero"
...         | x if x < 0 -> "negative"
...         | _ -> "positive"
...
ok
lune> sign(0)
"zero" : String
lune> sign(-5)
"negative" : String
lune> sign(3)
"positive" : String
```

- **literal pattern** `0` — matches exactly that value
- **name pattern** `x` — matches anything and names the value
- **guard** `x if x < 0` — an extra condition on a pattern
- **wildcard** `_` — matches anything, names nothing

Tuples can be taken apart as well.

```text
lune> def where(p: Tuple[Int, Int]): String =
...     match p:
...         | (0, 0) -> "origin"
...         | (x, 0) -> "x-axis"
...         | _ -> "elsewhere"
...
ok
lune> where((3, 0))
"x-axis" : String
```

Guards come into their own together with an ADT such as `Shape`. From `shape.lune`:

```lune
# A guard adds an extra condition to a pattern.
def describe(s: Shape): String =
    match s:
        | Circle(_) -> "circle"
        | Rect(w, h) if w == h -> "square"
        | Rect(_, _) -> "rectangle"
```

```console
$ lune --eval squareness shape.lune
"square"
```

## 5.3 Exhaustiveness — the compiler hands you a counterexample

Here is where Lune shows off. A `match` must be **exhaustive**: not covering every possible shape is a type error. And Lune tells you what is missing with a concrete counterexample (a *witness*).

Forget one case of `Color`:

```text,diagnostic
lune> def label(c: Color): String =
...     match c:
...         | Red -> "warm"
...         | Blue -> "cool"
...
error[TYP0007]: non-exhaustive match: missing case Green
  --> <repl:13>:2:5
  |
2 |     match c:
  |     ^^^^^ pattern Green is not covered
   = hint: add a case for Green, or a wildcard case `| _ -> ...`
   = help: run `lune explain TYP0007` for a detailed explanation
```

"`Green` is missing." You could probably have spotted that one yourself; the real worth of a witness shows when shapes **nest**. Here is `missing.lune`:

```lune
module bad

# The Some(false) case is missing.
def toInt(o: Option[Bool]): Int =
    match o:
        | Some(true) -> 1
        | None -> 0
```

```console
$ lune --check missing.lune
```

```text,diagnostic
error[TYP0007]: non-exhaustive match: missing case Some(false)
  --> missing.lune:5:5
  |
5 |     match o:
  |     ^^^^^ pattern Some(false) is not covered
   = hint: add a case for Some(false), or a wildcard case `| _ -> ...`
   = help: run `lune explain TYP0007` for a detailed explanation
```

You wrote `Some` and you wrote `None` — and still the compiler **synthesises the counterexample** `Some(false)`. At this point exhaustiveness checking is not a supervisor but a tool for finding holes in a specification. It asks, with an example in hand, "did you think about this input?"

Two cautions. First, **an arm with a guard does not count towards exhaustiveness**: the compiler cannot prove that `| x if x < 0 -> ...` covers every negative number. When you use a guard, always leave an unconditional arm to catch what falls through. Second, `| _ -> ...` satisfies exhaustiveness in one stroke, but at a price: **you stop being told when a case is added to the type**. Enumerate when you can enumerate — exercise 5-1 lets you feel the difference.

## 5.4 Unreachable arms, and bindings that can fail

There is a check in the opposite direction as well. An arm that is **already covered and can never be chosen** is a warning. Here is `unreachable.lune`:

```lune
def f(c: Color): Int =
    match c:
        | Red -> 1
        | Red -> 2
        | Green -> 3
```

```console
$ lune --check unreachable.lune
```

```text,diagnostic
warning[TYP0009]: unreachable match case: Red
  --> unreachable.lune:10:9
   |
10 |         | Red -> 2
   |         ^ this case can never match
   = hint: remove this case, or move it before the cases that cover it
   = help: run `lune explain TYP0009` for a detailed explanation
type check OK
```

It is a `warning`, so the check itself passes (note the `type check OK` at the end). Chapter 12 covers how to make CI fail on warnings too.

One more. Patterns can appear in a `let` as well (the destructuring tuple binding of chapter 2). But only a pattern that **cannot fail** — an irrefutable one — may go there. Here is `refutable.lune`:

```lune
module bad

let Some(x) = Some(1)
```

```console
$ lune --check refutable.lune
```

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

Even though the right-hand side is plainly `Some(1)`. A value of type `Option[Int]` might be `None`, and as long as "might" is there, a `let` cannot receive it. As the hint says, open such a value with `match`. Tuple patterns are allowed in a `let` because a tuple has no other shape.

## 5.5 Generic ADTs — abstracting the container with a type parameter

Defining `Option` yourself looks like this (and this is in fact the structure of the prelude's definition):

```lune
type Option[T] =
    | Some(value: T)
    | None

def getOrElse[T](option: Option[T], defaultValue: T): T =
    match option:
        | Some(value) -> value
        | None -> defaultValue
```

`[T]` means "for any type `T`" — one definition serves `Option[Int]` and `Option[String]` alike. The function takes a type parameter too, `def getOrElse[T](...)`, and promises in the type that the contents and the default are of the same type. It is the same mechanism as `map : [T, U] List[T] -> (T -> U) -> List[U]` from chapter 3.

## 5.6 Using Option and Result

The prelude comes with `Option[T]` (a value or nothing) and `Result[T, E]` (success or failure). These four are the basic tools.

```text
lune> getOrElse(Some(42), 0)
42 : Int
lune> getOrElse(None, 7)
7 : Int
lune> optionMap(Some(2), fn x -> x + 1)
Some(3) : Option[Int]
lune> unwrapOr(Err("boom"), 0)
0 : Int
lune> resultMap(Ok(20), fn x -> x * 2)
Ok(40) : Result[Int, E]
```

`optionMap` transforms what is there and leaves `None` alone; `unwrapOr` gives the contents on success and a default on failure. Instead of throwing an exception, **carry the failure as a value** — the standard functional approach to error handling, used in earnest in the chapter 13 case studies.

Let us return one from a function of our own. Integer division cannot divide by 0, so wrap the result in `Option[Double]`, a type that carries failure as a value.

```text
lune> def maybeDiv(x: Int, y: Int): Option[Double] =
...     if y == 0 then None else Some(x / y)
...
ok
lune> maybeDiv(1, 2)
Some(0.5) : Option[Double]
lune> maybeDiv(1, 0)
None : Option[Double]
```

Unremarkable code, but the type checker has quietly done something good. `None` on its own does not know what type its contents would be. Typed bare, you can see the type argument left undetermined:

```text
lune> None
None : Option[T]
```

The `E` left over in `resultMap(Ok(20), ...)` above is the same thing — `Ok(20)` reveals only the success side. So how did the `None` inside `maybeDiv` become an `Option[Double]`? The result annotation `Option[Double]` is handed to both branches of the `if` as the **expected type**, and settles the undetermined `T` there. Expected types flow from a `let` annotation too.

```text
lune> let nothing: Option[Double] = None
ok
lune> nothing
None : Option[Double]
```

They are handed to the arms of a `match` as well. To return division by zero as a failure with a reason, use `Result`. From `maybediv.lune`:

```lune
# Each arm of a match gets the expected type too, fixing Err's T and Ok's E.
def safeDiv(x: Int, y: Int): Result[Double, String] =
    match y:
        | 0 -> Err("div by zero")
        | _ -> Ok(x / y)
```

```console
$ lune --eval ratio maybediv.lune
Ok(4.5)
```

`Err("div by zero")` reveals only the failure side and `Ok(x / y)` only the success side, but the expected type `Result[Double, String]` fills in the rest.

> **Looking ahead: the same holds for nullable types** — this mechanism, where an expected type is handed to the branches and they meet in the middle, works for the nullable type `T?` of chapter 7 as well.
>
> ```lune
> # Looking ahead (chapter 7): branches meet the same way for a nullable type.
> def nullDiv(x: Int, y: Int): Double? =
>     if y == 0 then null else x / y
> ```
>
> The `null` branch and the `Double` branch meet at `Double?` and the function type-checks. Chapter 7 sorts out when to use `Option` and when to use `T?`.

## Summary

| Concept | In one line |
| --- | --- |
| `type T = \| A(...) \| B(...)` | a sum type; a value is always exactly one constructor |
| field-less constructors | call them to make a value, `Green()` (only the prelude's `None` / `Nil` are bare values) |
| `match` | an expression that checks a shape and destructures it at once |
| patterns | literal / name / `_` / tuple / constructor / guard `if` |
| `TYP0007` | a missing case, reported **with a counterexample** |
| `TYP0009` | an unreachable arm (a warning) |
| `TYP0008` | a pattern that can fail may not go in a `let` |
| `type Option[T] = ...` | a generic ADT; the function side takes `def f[T](...)` |
| `Option` / `Result` | from the prelude: `getOrElse` / `optionMap` / `unwrapOr` / `resultMap` |
| expected types | a result or `let` annotation reaches the branches and fixes the type arguments of `None` / `Err(...)` |

## Exercises

**Exercise 5-1** (★) Add `Yellow` to the `Color` of the text (leaving `label` as it is). Predict the diagnostic, run `--check`, and then consider how it would differ if exhaustiveness had been satisfied with `| _ -> ...`.

<details><summary>Answer</summary>

`label` reports `error[TYP0007]: non-exhaustive match: missing case Yellow`. The moment a case is added to the type, the compiler finds **every place that matches on that type** — this is why "enumerate rather than `_` when you can enumerate". Had the code said `| _ -> "unknown"`, `Yellow` would quietly become `"unknown"` and nobody would notice.

</details>

**Exercise 5-2** (★★) Write a traffic light colour `Light` (Red / Yellow / Green) and a `next` that returns the next colour, in the order red → green → yellow → red.

<details><summary>Answer</summary>

```lune
module answers

# Exercise 5-2: the next colour of a traffic light. Exhaustiveness checking
# guarantees that every colour has been considered.
type Light =
    | Red
    | Yellow
    | Green

def next(light: Light): Light =
    match light:
        | Red -> Green()
        | Green -> Yellow()
        | Yellow -> Red()

let afterRed = next(Red())

let afterTwo = next(next(Red()))
```

```console
$ lune --eval afterTwo ex5-2.lune
Yellow
```

Bare `Red` in a pattern, `Red()` when building a value. Deleting one arm to produce `TYP0007` makes a good revision exercise.

</details>

**Exercise 5-3** (★★) Build something that checks an integer and returns the value when it is 0 or above, and a reason when it is negative. The prelude's `Result[Int, String]` would do, but define a result type of your own (without type parameters) here. This is practice at feeling the ADT's advantage: constructor names can be the words of your own domain.

<details><summary>Answer</summary>

```lune
module answers

# Exercise 5-3: put the result of a check into the type, information and all,
# for both success and failure.
type Checked =
    | Valid(value: Int)
    | Invalid(reason: String)

def check(n: Int): Checked =
    if n >= 0 then Valid(n) else Invalid("negative")

def report(c: Checked): String =
    match c:
        | Valid(v) -> "ok: " + show(v)
        | Invalid(reason) -> "rejected: " + reason

let good = report(check(5))

let bad = report(check(-3))
```

```console
$ lune --eval bad ex5-3.lune
"rejected: negative"
```

When there is information worth carrying on both success and failure, express it in a type rather than with a `Bool` or a special value such as `-1`. It is the most practical pattern in ADT design. With the mechanism of §5.6 the `Result[Int, String]` version works just as well, but with a type of your own the **words of your domain**, `Valid` and `Invalid`, appear in the arms of the `match` and in the diagnostics.

</details>

**Exercise 5-4** (★★★) Without using the prelude, write your own `MyOption[T]` and `myGetOrElse`, and check that both `MySome(42)` and `MyNone()` work.

<details><summary>Answer</summary>

```lune
module answers

# Exercise 5-4: build a generic container by hand — the same structure as the
# prelude's Option.
type MyOption[T] =
    | MySome(value: T)
    | MyNone

def myGetOrElse[T](option: MyOption[T], defaultValue: T): T =
    match option:
        | MySome(value) -> value
        | MyNone -> defaultValue

let some = myGetOrElse(MySome(42), 0)

let none = myGetOrElse(MyNone(), 0)

# Fixing type arguments from the expected type (§5.6) works for a generic ADT
# of your own too.
let empty: MyOption[Int] = MyNone()
```

```console
$ lune --eval some ex5-4.lune
42
$ lune --eval none ex5-4.lune
0
```

Two ways of settling a type argument are on display. The `T = Int` of `MySome(42)` comes **from the argument**, while the `T` of `MyNone()` is settled by unification with the other argument, `0`. And since the expected-type mechanism of §5.6 applies to your own generic ADTs, an annotation can settle it too, as in `let empty: MyOption[Int] = MyNone()`.

</details>

**Exercise 5-5** (★, in reverse) Write the smallest code that produces `TYP0008` (a refutable pattern), and explain what each of the diagnostic's two hints is telling you.

<details><summary>Answer</summary>

`let Some(x) = Some(1)` (§5.4). The first hint, "the pattern does not cover None", says **why** it can fail, naming the shape left uncovered. The second, "use `match` to handle all cases", says **what to do instead**. Reading a diagnostic as cause → remedy is a rehearsal for chapter 11.

</details>

---

**More precisely** — the syntax of ADTs and `match` is in `documents/LANGUAGE_SPEC.md` §10–11; the algorithm for exhaustiveness checking and witnesses is in `documents/MATCH_EXHAUSTIVENESS_SPEC.md`; the full API of `Option` and `Result` is in `documents/STANDARD_LIBRARY_SPEC.md` §4–5; the rules by which an expected type fixes a constructor's type arguments are in `documents/LOCAL_TYPE_INFERENCE_SPEC.md` §5.3 and §5.6. Note that the specification describes OR patterns (`| 0 | 1 ->`), which v0.1 does not implement. The code examples of this chapter live in `books/examples-en/ch05/` and are all verified against the real CLI.
