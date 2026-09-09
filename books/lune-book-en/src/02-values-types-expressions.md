# Chapter 2: Values, Types and Expressions

Chapter 1 was a sprint around the language. Part II picks the pieces up one at a time and looks at them. We start with the smallest: values, their types, and the expressions that combine them.

Keep a REPL open for this chapter too. Every Lune expression can be typed straight into it, so whenever you wonder "what is the type of this?", type it and find out.

## 2.1 Literals and the basic types

Lune's literals and the types that go with them:

| Literal | Type | Displayed as |
| --- | --- | --- |
| `42` | `Int` | `42 : Int` |
| `3.14` | `Double` | `3.14 : Double` |
| `"hello"` | `String` | `"hello" : String` |
| `true` / `false` | `Bool` | `true : Bool` |
| `null` | `Null` | `null : Null` |
| `()` | `Unit` | `() : Unit` |
| `(1, "a")` | `Tuple[Int, String]` | `(1, "a") : Tuple[Int, String]` |

A few notes.

**`Int` does not need watching.** In v0.1 `Int` is arbitrary precision, so it never overflows.

```text
lune> 9223372036854775807 + 1
9223372036854775808 : Int
```

Going past the limit of a 64-bit integer is uneventful — in C this is where the number would silently turn negative.

**String escapes.** Inside `"` you can write `\n` (newline) and `\"`. The display form (`show` form) prints them still escaped, so do not be surprised.

```text
lune> "a\nb"
"a\nb" : String
```

That is the REPL's `show` form only. Pass the string to `println` and the raw contents come out, so `\n` becomes a real newline (as in §1.3).

**Single quotes give you a String.** The form `'x'` is accepted, but v0.1 has no separate character type in practice: it is the same `String` as `"x"`.

```text
lune> 'x'
"x" : String
```

**`null` and `()` are different things.** `null` exists solely to represent the absence of a value, and it is the star of null safety (chapter 7). `()` is the single value of type `Unit`, used as the result of functions with no meaningful value to return, such as `println`.

## 2.2 Operators — arithmetic, comparison, logic

The arithmetic operators are `+` `-` `*` `/` `//` `%` and unary `-` (and unary `+`). `*` `/` `//` `%` bind at the same level, more tightly than `+` `-` — mostly what school arithmetic leads you to expect, and `()` overrides it.

```text
lune> 1 + 2 * 3
7 : Int
lune> (1 + 2) * 3
9 : Int
lune> 2 * -3
-6 : Int
```

Division needs care. As chapter 1 mentioned, **`/` always returns `Double`**. Dividing an `Int` by an `Int` still gives a `Double`. For the remainder of an integer division there is `%`, which does give an `Int`.

```text
lune> 7 / 2
3.5 : Double
lune> 7 % 2
1 : Int
```

So what do you use when you want an integer divided by an integer to *be* an integer? **Floor division, `//`**. It keeps the type of its operands.

```text
lune> 7 // 2
3 : Int
lune> 7.0 // 2.0
3.0 : Double
```

`/` and `//` look alike but are **different operators**. Remember that "division" names two things in Lune: `//` to stay in `Int`, `/` to divide as real numbers.

The rounding of `//` has one surprise in it. It rounds **towards negative infinity** (floor), not towards zero.

```text
lune> -7 // 2
-4 : Int
```

If you expected `-3.5` to be "truncated" to `-3`, this is where you trip. The reason it is `-4` is that it keeps `//` and `%` consistent with each other — exercise 13-4 works through why. For now, "`//` is floor" is enough.

All three of `/` `//` `%` raise a runtime error when the right-hand side is 0 (`RUN0006`; chapter 11 covers how to read it).

And **`Int` and `Double` do not mix silently**.

```text
lune> 1 + 2.0
error[TYP0003]: +: expected Int, got Double
   = help: run `lune explain TYP0003` for a detailed explanation
lune> 1 == 1.0
error[TYP0003]: ==: cannot compare Int and Double
   = help: run `lune explain TYP0003` for a detailed explanation
```

Rather than converting implicitly and handing back an answer that is roughly right, Lune asks the writer to decide which world the computation lives in. Line the literals up: `2.0` or `2`.

The comparison operators are `==` `!=` `<` `<=` `>` `>=`. `==` and `!=` work on numbers, strings and booleans. The ordering comparisons are for numbers only.

```text
lune> 3 < 5
true : Bool
lune> "a" == "a"
true : Bool
lune> "a" < "b"
error[TYP0003]: <: expected numeric type, got String
   = help: run `lune explain TYP0003` for a detailed explanation
```

Compound values — tuples, lists, and the algebraic data types of chapter 5 — can be compared with `==` as well. Comparison is **structural**: separately built values are equal when their contents are.

```text
lune> (1, 2) == (1, 2)
true : Bool
lune> (1, 2) == (2, 1)
false : Bool
lune> [1, 2] == [1, 2]
true : Bool
lune> Some(1) == Some(1)
true : Bool
```

But only values **of the same type** can be compared at all. Tuples of different lengths are different types, so the comparison itself is a type error, contents notwithstanding.

```text
lune> (1, 2) == (1, 2, 3)
error[TYP0003]: ==: cannot compare Tuple[Int, Int] and Tuple[Int, Int, Int]
   = help: run `lune explain TYP0003` for a detailed explanation
```

The logical operators are `&&` (and) and `||` (or); negation is the function `not`. `&&` binds more tightly than `||`. Thanks to lazy evaluation (chapter 4) both **short-circuit** — when the left side settles the answer, the right side is never evaluated.

```text
lune> false && crash()
false : Bool
lune> true || crash()
true : Bool
lune> not(true)
false : Bool
```

Beyond these there are the null-coalescing `??` (chapter 7) and the pipeline `|>` (chapter 3). Appendix A has the full precedence table.

## 2.3 if is an expression — then/else and elif

To recap chapter 1: `if` is an expression that produces a value, and it has a one-line form and a block form.

```text
lune> if 5 > 3 then "big" else "small"
"big" : String
```

Being an expression brings two rules with it. **The condition must be `Bool`**, and **the branches must agree in type**.

```text
lune> if 1 then 2 else 3
error[TYP0003]: if condition: expected Bool, got Int
   = help: run `lune explain TYP0003` for a detailed explanation
lune> if true then 1 else "a"
error[TYP0003]: branch type mismatch: Int vs String
   = help: run `lune explain TYP0003` for a detailed explanation
```

There is no "0 is false" as in C. Write `if x % 2 == 1`, not `if x % 2`.

When there are more branches, the block form takes `elif`. Here is `grade.lune`:

```lune
module grade

# `if` is an expression; the block form adds branches with `elif`.
def grade(score: Int): String =
    if score >= 80:
        "pass"
    elif score >= 60:
        "retry"
    else:
        "fail"

let result = grade(75)
```

```console
$ lune --eval result grade.lune
"retry"
```

However many branches there are, `grade` returns exactly one `String`. The type checker guarantees that every path produces a value — that is the comfort of an expression-oriented language.

## 2.4 let-in — a binding inside an expression

`let` is not only for the top level. When you want a temporary name **inside an expression**, use `let ... in ...`.

```text
lune> let answer = let x = 40 in x + 2
ok
lune> answer
42 : Int
```

What follows `in` is the value of the whole expression, and `x` is visible only within it. When you want more than one name, lining up several `let`s in block form reads better.

```lune
module answers

# Exercise 2-3: a block-form let names the intermediate values of a BMI.
let bmi =
    let h = 1.7
    let w = 62.0
    w / (h * h)
```

```console
$ lune --eval bmi ex2-3.lune
21.453287197231838
```

Put `let`s inside an indented block, and the expression at the end is the value of the block. `lune fmt` treats this shape as canonical.

## 2.5 Type annotations — where to write them and where to leave them out

A `let` can carry a type annotation.

```lune
let y: Int = 42
```

If the annotation and the actual type disagree, that is of course a type error. Here is `annot.lune`:

```lune
module bad

let n: Int = "hello"
```

```console
$ lune --check annot.lune
```

```text,diagnostic
error[TYP0003]: let annotation: expected Int, got String
  --> annot.lune:3:14
  |
3 | let n: Int = "hello"
  |              ^^^^^^^ this expression has type String
   = help: run `lune explain TYP0003` for a detailed explanation
```

So where do you write annotations and where can you leave them out? The rule of thumb for v0.1:

| Place | Annotation |
| --- | --- |
| a `let` with an obvious right-hand side | optional (inferred from the right-hand side) |
| the parameters and result of a `def` | write it (a recursive function's result type is required — `TYP0011`) |
| the parameter of a lambda `fn x -> ...` | usually inferred from context (chapter 3) |

Annotations are not only for the machine. Writing `let total: Double = ...` declares your intent to the reader, and the moment the right-hand side is wrong you get the diagnostic above. **When in doubt, write it; when you want to check, use `:type`** — that is the working habit.

## 2.6 Tuples — a group of values of different types

The elements of a list (chapter 8) all share one type. A **tuple** bundles a fixed number of values whose types may differ.

```text
lune> let pair = (1, "a")
ok
lune> pair
(1, "a") : Tuple[Int, String]
```

Values come out of a tuple by **destructuring**. There is no accessor like `.1` — you open it by naming the parts.

```text
lune> let (a, b) = (10, 20)
ok
lune> a
10 : Int
lune> b
20 : Int
```

The temperature table in chapter 1 built a list of `(fahrenheit, celsius)` tuples. Carrying two values together, without ceremony, is what a tuple is for. Once you want the bundled values to have names, you want a record (chapter 6).

> **Break it** — look at the errors from the stages *before* type checking: lexing and layout. Both belong to the `LXL` and `PRS` families of the diagnostic scheme in chapter 11.
>
> Writing `let x = $1` uses a character Lune does not know.
>
> ```text,diagnostic
> error[LXL0001]: unexpected character '$'
>   --> lex.lune:3:9
>   |
> 3 | let x = $1
>   |         ^ unexpected character
>    = help: run `lune explain LXL0001` for a detailed explanation
> ```
>
> Indenting a line for no reason runs into the layout rule.
>
> ```text,diagnostic
> error[PRS0001]: expected top-level declaration, got INDENT
>   --> indent.lune:4:1
>   |
> 4 |   let b = 2
>   | ^ unexpected token
>    = help: run `lune explain PRS0001` for a detailed explanation
> ```
>
> Indentation in Lune is part of the syntax, as it is in Python. Remember that a block only opens after `=` or `:`.

## Summary

| Fact | In one line |
| --- | --- |
| Basic types | `Int` (arbitrary precision) / `Double` / `String` / `Bool` / `Null` / `Unit` / `Tuple[...]` |
| Division | `/` is always `Double`, `//` is floor division and keeps the type, `%` is the remainder |
| Rounding of `//` | towards negative infinity (floor). `-7 // 2` is `-4` |
| `Int` and `Double` | never mix implicitly; line up the literals |
| `==` | compares contents (structural). Only same-type values can be compared |
| `&&` `\|\|` | short-circuit; `&&` binds first |
| `if` | condition is `Bool`, branches agree in type, `elif` for more branches |
| `let ... in` / block `let` | a temporary name inside an expression |
| Type annotations | optional on `let`, written on `def`. Check with `:type` |
| Tuples | `(a, b)` to bundle, `let (x, y) = ...` to open |

## Exercises

**Exercise 2-1** (★) Predict the value and type of each expression, then check in the REPL.

```text
19 / 4
19 // 4
19 % 4
1 + 2 * 3 - 4
2 * -3
true && false || true
```

<details><summary>Answer</summary>

`4.75 : Double` (`/` is always Double), `4 : Int` (`//` is floor division, so the type stays `Int`), `3 : Int`, `3 : Int`, `-6 : Int`, and `true : Bool` (`&&` goes first and gives `false`, then `|| true`).

</details>

**Exercise 2-2** (★) Add a branch to `grade.lune` for "90 or above is `"excellent"`". Check with `grade(95)` that **where** you add the branch changes the result.

<details><summary>Answer</summary>

Put `if score >= 90: "excellent"` **first**. Placed after `elif score >= 80: ...`, a score of 95 is caught by `score >= 80` and comes out as `"pass"`. `if`/`elif` are tried from the top down — the order of the conditions is part of the specification.

</details>

**Exercise 2-3** (★★) Compute the BMI (weight ÷ height²) for a height of 1.7 m and a weight of 62.0 kg, naming the intermediate values with a block-form `let`.

<details><summary>Answer</summary>

```lune
module answers

# Exercise 2-3: a block-form let names the intermediate values of a BMI.
let bmi =
    let h = 1.7
    let w = 62.0
    w / (h * h)
```

```console
$ lune --eval bmi ex2-3.lune
21.453287197231838
```

Change `1.7` to `1` and you get `TYP0003`. Keeping `Int` and `Double` apart catches this kind of unit confusion early.

</details>

**Exercise 2-4** (★★) Using destructuring, build `(2, 1)` by swapping the two values of the tuple `(1, 2)`.

<details><summary>Answer</summary>

```lune
module answers

# Exercise 2-4: swap two values with a destructuring tuple binding.
let (x, y) = (1, 2)

let swapped = (y, x)
```

```console
$ lune --eval swapped ex2-4.lune
(2, 1)
```

No temporary variable is needed. Open it, and bundle it back the other way round.

</details>

**Exercise 2-5** (★★) Predict the result of these three expressions, then check. The third is not like the others — what happens?

```text
(1, 2) == (2, 1)
[1, 2] == [1, 2]
(1, 2) == (1, 2, 3)
```

<details><summary>Answer</summary>

`false : Bool` (the contents are in a different order), `true : Bool` (separately built lists with the same contents are equal — structural equality), and the third is not `true` or `false` but a **type error**.

```text,diagnostic
error[TYP0003]: ==: cannot compare Tuple[Int, Int] and Tuple[Int, Int, Int]
   = help: run `lune explain TYP0003` for a detailed explanation
```

Tuples of different lengths are different types, so asking whether they are equal is not a question that can be asked. `==` answers only between values of one type — the same design as `1 == 1.0`: what cannot be compared is rejected before the program runs.

</details>

---

**More precisely** — literals and types are in `documents/LANGUAGE_SPEC.md` §5–6; the full operator precedence table is in `documents/SYNTAX_SPEC.md` §14 (it includes future entries such as `::` and `++`, so treat `LANGUAGE_SPEC.md` as authoritative for what is implemented); `if` and `let-in` are in `documents/LANGUAGE_SPEC.md` §9. Display rules are in `documents/VALUE_DISPLAY_SPEC.md`. The code examples of this chapter live in `books/examples-en/ch02/` and are all verified against the real CLI.
