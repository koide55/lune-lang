# Chapter 1: A Gentle Tour

There has only ever been one way to pick up a new programming language: write programs in it. In this chapter you will write Lune programs, run them, and break them. The precise rules can wait for later chapters; first, one lap around the whole language.

One thing about the manner of this book, before we start. **Do not be afraid of errors.** Lune's compiler treats an error not as a notice of failure but as teaching material. In the second half of this chapter we will cause errors on purpose and let the compiler teach us.

## 1.1 Calculating in the REPL

Lune has a REPL — an interactive session. Type an expression and it evaluates it on the spot and hands back the result. That is where we begin.

```console
$ lune
Lune v0.1.0 REPL. Type :help or :quit.
lune>
```

> **On notation** — shell commands are shown after `$`, and REPL input after `lune>`. The `lune` command means `./bin/lune` in the repository (put it on your `PATH`, or `alias lune=./bin/lune`, and you can type exactly what the book types). If you installed with `pip install lune-lang`, `lune` is already on your `PATH`.
>
> One more. This book prints the compiler's diagnostics in **English**, which is what Lune prints by default. To see them in Japanese instead, set `LUNE_LANG=ja` or pass `--lang ja` (inside the REPL, `:lang ja`).

Type some numbers.

```text
lune> 1 + 2
3 : Int
lune> 40 + 2
42 : Int
```

Results are shown as `value : type`. `3` is the value, `Int` is the type. Every expression in Lune has a type, and the REPL always tells you what it is.

Strings are written with `"` and joined with `+`.

```text
lune> "hello, " + "world"
"hello, world" : String
```

To leave the REPL, `:quit` (or `:q`).

```text
lune> :quit
bye
```

`:help` lists the commands. The REPL is the best laboratory you have for the whole of this book. Whenever a question comes up, type it in and find out.

## 1.2 Naming values with let

`let` gives a value a name.

```text
lune> let x = 41
ok
lune> x + 1
42 : Int
```

To a declaration the REPL answers only `ok`. Notice that no value is printed. That is not laziness on the REPL's part — well, it is, but deliberately: **a Lune `let` has not computed anything at the moment it gives the name**.

> **Coming attraction: the computation has not happened yet** — the REPL's `:thunks` command lets you look at whether a binding has been evaluated, without evaluating it.
>
> ```text
> lune> let y = 1 + 1
> ok
> lune> :thunks y
> y : unevaluated
> lune> y
> 2 : Int
> lune> :thunks y
> y : evaluated = 2
> ```
>
> `1 + 1` was computed at the moment `y` was used, and not before. This is **lazy evaluation** — the heart of Lune's design, and the subject of chapter 4. For now, remember only that `let` writes down a promise to compute, and read on.

## 1.3 Writing a program to a file

The REPL is a laboratory, but programs are written to files. Create `hello.lune` in your editor.

```lune
module hello

def greet(name: String): String =
    "hello, " + name

let main = println(greet("world"))
```

Reading from the top:

- `module hello` — declares that this file is the module `hello`. A Lune source file always starts with this declaration.
- `def greet(name: String): String = ...` — a function definition. The parameter `name` has type `String` and so does the result. The body is indented.
- `let main = println(greet("world"))` — a top-level binding. `println` is a built-in that prints a value.

First, check the types without running anything.

```console
$ lune --check hello.lune
type check OK
```

Now run it. The execution model of Lune v0.1 is "**pick one top-level binding and evaluate it**". Pass the name of the binding to `--eval`.

```console
$ lune --eval main hello.lune
hello, world
()
```

Two lines. The first is what `println` printed. The second, `()`, is the value of `main` itself — the `Unit` value that `println` returns (`--eval` prints the value of the binding it evaluated, last).

`println` prints a `String` **exactly as it is**: no quotes, and escapes such as `"a\nb"` come out as real newlines. Values that are not strings are printed in Lune's standard display form (`show` form). To print a string in quoted `show` form, write `println(show(value))`. Chapter 2 sorts out the display rules.

## 1.4 if is an expression

Lune's `if` is an **expression**: it produces a value. This is a little different from the statement it is in C or Python.

```text
lune> if 5 > 3 then "big" else "small"
"big" : String
```

Being an expression, its result can be bound with `let` or used as the body of a function. Wherever a value is required, `else` cannot be omitted — without it there would be no value when the condition is false.

For longer bodies there is a block form. The REPL continues the input when a line ends in `=` or `:` (`...` is the continuation prompt; a blank line finishes).

```text
lune> def abs(x: Int): Int =
...     if x < 0:
...         -x
...     else:
...         x
...
ok
lune> abs(-5)
5 : Int
```

## 1.5 Playing with lists — a temperature table

Introductory books on C traditionally start by building a Fahrenheit-to-Celsius table. In tribute, so will this one — but the Lune way, with a **list** instead of a loop.

Lists are written with `[` `]`. They display in Lisp-like `( )` form.

```text
lune> [1, 2, 3]
(1 2 3) : List[Int]
lune> range(0, 5)
(0 1 2 3 4) : List[Int]
```

`range(start, end)` builds the list of integers from `start` up to but not including `end`. The three basic tools for working on lists are `map` (apply a function to every element), `filter` (keep the elements that satisfy a condition) and `fold` (collapse the list into a single value).

```text
lune> map(range(1, 6), fn x -> x * 2)
(2 4 6 8 10) : List[Int]
lune> filter(range(1, 10), fn x -> x % 2 == 0)
(2 4 6 8) : List[Int]
lune> fold([1, 2, 3, 4], 0, fn acc x -> acc + x)
10 : Int
```

`fn x -> x * 2` is a small unnamed function — a lambda. It works without a type on the parameter because the compiler infers it from the type `map` expects (chapter 3).

The tools are in place. Here is the temperature table, in a file `temperature.lune`:

```lune
module temperature

# A table converting 0-300 degrees Fahrenheit to Celsius, in steps of 20.
def toCelsius(f: Int): Double =
    (f - 32) * 5 / 9

let fahrenheits = map(range(0, 16), fn i -> i * 20)

let table = map(fahrenheits, fn f -> (f, toCelsius(f)))
```

`#` starts a comment that runs to the end of the line. `toCelsius` returns `Double` because `/` in Lune **always returns `Double`**. There is no truncating-integer-division trap as in C — in exchange, `Int` and `Double` cannot be added to each other, which chapter 2 covers in detail.

In `fn f -> (f, toCelsius(f))`, the `(f, toCelsius(f))` is a **tuple**: a pair of two values. Run it:

```console
$ lune --eval table temperature.lune
((0, -17.77777777777778) (20, -6.666666666666667) (40, 4.444444444444445) (60, 15.555555555555555) (80, 26.666666666666668) (100, 37.77777777777778) (120, 48.888888888888886) (140, 60.0) (160, 71.11111111111111) (180, 82.22222222222223) (200, 93.33333333333333) (220, 104.44444444444444) (240, 115.55555555555556) (260, 126.66666666666667) (280, 137.77777777777777) (300, 148.88888888888889))
```

The correspondence between Fahrenheit and Celsius, as a list of `(fahrenheit, celsius)` tuples. No loop, no counter variable, no variable holding a partial result. "Take the numbers 0 to 15, multiply by 20 to get the Fahrenheit list, and map each one to a pair with its Celsius value" — the program reads like the specification. That is what writing Lune is normally like.

## 1.6 Your first error — a conversation with the compiler

Now for the part you have been waiting for: **let's get it wrong on purpose**. Change `hello.lune` slightly into `typo.lune`, mistyping `greeting` as `greting`.

```lune
module hello

let greeting = "hello, world"

let main = println(greting)
```

```console
$ lune --check typo.lune
```

```text,diagnostic
error[TYP0001]: undefined name: greting
  --> typo.lune:5:20
  |
5 | let main = println(greting)
  |                    ^^^^^^^ name is not defined
   = hint: did you mean `greeting`?
   = help: run `lune explain TYP0001` for a detailed explanation
```

Dissect it from the top. Every Lune diagnostic has this shape.

| Line | Meaning |
| --- | --- |
| `error[TYP0001]: ...` | severity (error), the **diagnostic code** (TYP0001), and a summary |
| `--> typo.lune:5:20` | the place — file:line:column |
| `5 \| let main = ...` and `^^^^^^^` | the offending source, and a marker under the offending part |
| `= hint: ...` | a suggested fix — here, "did you mean `greeting`?" |
| `= help: run \`lune explain TYP0001\`` | how to find out more |

> **On notation** — the path on the `-->` line is really an absolute path on your machine. The book drops the working directory.

Do what the `help` line says. **Every diagnostic code in Lune comes with an explanation written to teach.**

```console
$ lune explain TYP0001
```

```text
error[TYP0001]: undefined name

A name was used that is not bound in the current scope and is not provided by
the prelude or an import.

Example that triggers it:

    let y = x + 1      # x was never defined

How to fix:
Define or import the name before using it, and check the spelling.
```

What happened, the smallest example that reproduces it, and how to fix it. Get into the habit of reading this every time an error appears and the compiler becomes a private tutor.

A typo like this one is a mechanically applicable fix, so `lune fix` will do it for you.

```console
$ lune fix typo.lune
module hello

let greeting = "hello, world"

let main = println(greeting)
```

It printed the corrected source (`--write` edits the file in place).

This loop — **break it → read the diagnostic → understand it with `explain` → fix it** — is how this book teaches. Every chapter has a **Break it** box for the purpose. Here is the first.

> **Break it** — add an `Int` and a `Bool` in the REPL.
>
> ```text,diagnostic
> lune> 1 + true
> error[TYP0003]: +: expected Int, got Bool
>    = help: run `lune explain TYP0003` for a detailed explanation
> ```
>
> `TYP0003` (type mismatch) is the diagnostic you will meet most often from here on. Read its explanation now with `:explain TYP0003` (inside the REPL, `:explain` stands in for `lune explain`).

## 1.7 A map of what follows

That is one lap. You can already write a Lune program, type-check it, run it, and read and fix an error. The rest of the book walks slowly back over the ground this chapter sprinted across.

- **Chapters 2–3** — values, types and expressions, then functions. Partial application and the pipeline operator `|>` join the toolkit.
- **Chapter 4** — lazy evaluation. The whole of what §1.2 hinted at. This is the main reason to learn Lune.
- **Chapters 5–8** — the tools for giving data a shape: algebraic data types, pattern matching, records, null safety, and infinite lists.
- **Chapters 9–10** — writing imperatively, and splitting a program up.
- **Chapters 11–13** — putting the compiler and the tools to work, and building something larger.

Reading in order is recommended, but once you have read through chapter 4 you can pick and choose.

## Summary

| What you wrote | What it means |
| --- | --- |
| `let name = expr` | a binding (a promise to compute); evaluated when used |
| `def f(x: T): U = body` | a function definition |
| `fn x -> expr` | a lambda (an unnamed function) |
| `if c then a else b` / `if c:` block | a conditional; an expression that produces a value |
| `[1, 2, 3]` | a list; displayed as `(1 2 3)` |
| `(a, b)` | a tuple |
| `module m` | the module declaration; goes at the top of the file |

| Command | What it does |
| --- | --- |
| `lune` | start the REPL |
| `lune --check FILE` | type-check only |
| `lune --eval NAME FILE` | evaluate the binding NAME and print it |
| `lune explain CODE` | explain a diagnostic code |
| `lune fix FILE` | apply the mechanically applicable fixes |
| `export LUNE_LANG=ja` | make Japanese the default diagnostic language (`--lang` wins over it) |
| `:quit` `:help` `:thunks` `:explain` | REPL commands |

## Exercises

**Exercise 1-1** (★) Change the greeting in `hello.lune` to your own name and a greeting you like, and run it. Then change the `+` in the body of `greet` to `-` and see what diagnostic comes out.

<details><summary>Answer</summary>

`"hello, " - name` is a type error.

```text,diagnostic
error[TYP0003]: -: expected numeric type, got String
   = help: run `lune explain TYP0003` for a detailed explanation
```

`+` works for joining strings, but `-` is for numbers only. Notice how the diagnostic explains it from the operator's point of view: `-` expected a numeric type and got a `String`.

Incidentally, deleting the argument to make it `greet()` is **not** a type error (`lune --check` accepts it). Lune's functions can be given their arguments a few at a time — that is partial application, one of the stars of chapter 3.

</details>

**Exercise 1-2** (★) Build the reverse of `temperature.lune`: a Celsius-to-Fahrenheit table for 0-100 degrees in steps of 20. The formula is `F = C × 9/5 + 32`.

<details><summary>Answer</summary>

```lune
module answers

# Exercise 1-2: Celsius to Fahrenheit, 0-100 degrees in steps of 20.
def toFahrenheit(c: Int): Double =
    c * 9 / 5 + 32.0

let table = map(range(0, 6), fn i -> (i * 20, toFahrenheit(i * 20)))
```

```console
$ lune --eval table ex1-2.lune
((0, 32.0) (20, 68.0) (40, 104.0) (60, 140.0) (80, 176.0) (100, 212.0))
```

There is one trap. Writing `+ 32` gives `TYP0003` (`+: expected Double, got Int`). `c * 9 / 5` is already a `Double` because of the `/`, so what you add has to be written `32.0`. Lune does not silently mix `Int` and `Double`.

</details>

**Exercise 1-3** (★★) For the `fahrenheits` of `temperature.lune`, use `fold` to compute the total, and then combine it with `length` to get the average.

<details><summary>Answer</summary>

```lune
module answers

# Exercise 1-3: fold the Fahrenheit temperatures into a total, then an average.
let fahrenheits = map(range(0, 16), fn i -> i * 20)

let total = fold(fahrenheits, 0, fn acc f -> acc + f)

let average = total / length(fahrenheits)
```

```console
$ lune --eval total ex1-3.lune
2400
$ lune --eval average ex1-3.lune
150.0
```

Learn the shape `fold(list, initial, fn accumulated element -> new accumulated)`. `average` comes out as `150.0` (a `Double`) because `/` always returns one.

</details>

**Exercise 1-4** (★★) From the table in `temperature.lune`, use `filter` to pick out only the Fahrenheit temperatures that are below freezing in Celsius.

<details><summary>Answer</summary>

```lune
module answers

# Exercise 1-4: keep only the Fahrenheit temperatures that are below freezing.
def toCelsius(f: Int): Double =
    (f - 32) * 5 / 9

let fahrenheits = map(range(0, 16), fn i -> i * 20)

let freezing = filter(fahrenheits, fn f -> toCelsius(f) < 0.0)
```

```console
$ lune --eval freezing ex1-4.lune
(0 20)
```

Only 0 and 20 degrees Fahrenheit are below freezing. The right-hand side of the comparison is `0.0` rather than `0` for the same reason as in exercise 1-2.

</details>

**Exercise 1-5** (★) Practice at predicting a diagnostic *before* asking for it. What happens if you pass two arguments, as in `greet("world", "again")`? Predict, then run it, then read `lune explain TYP0005`.

<details><summary>Answer</summary>

```text,diagnostic
error[TYP0005]: expected at most 1 arguments, got 2
  --> arity.lune:6:20
  |
6 | let main = println(greet("world", "again"))
  |                    ^^^^^ wrong number of arguments
   = help: run `lune explain TYP0005` for a detailed explanation
```

Notice the phrase "**at most** 1". Lune's functions can be given their arguments a few at a time (partial application, chapter 3), so too *few* is not necessarily an error, while too *many* certainly is.

</details>

---

**More precisely** — the exact specifications of what appeared in this chapter: syntax and literals in `documents/LANGUAGE_SPEC.md` §5–9, REPL display in `documents/REPL_SPEC.md` and `documents/VALUE_DISPLAY_SPEC.md`, and the diagnostic format in `documents/ERROR_DIAGNOSTICS_SPEC.md`. The code examples of this chapter live in `books/examples-en/ch01/` and are all verified against the real CLI.
