# Chapter 3: Functions

We have used `def` since chapter 1, but this chapter takes functions head on. There is one goal: to acquire the feeling that **a function is a value**. If a function is a value, it can be put in a variable, passed as an argument, and returned as a result. From here, Lune programs suddenly start to stretch their legs.

## 3.1 def — an anatomy of a definition

A recap, to fix the names of the parts.

```lune
def add(x: Int, y: Int): Int =
    x + y
```

`add` is the function name, `x: Int, y: Int` are the parameters and their types, the second `Int` is the result type, and the indented part after `=` is the body. The body is an expression, and its value is the result (there is no `return` — as chapter 2 showed, everything, `if` included, is an expression).

Write the types of the parameters and the result. There are places in v0.1 where they can be left out, but leaving them out makes inference fall back to `Any` with a warning (`TYP0010`, §3.3), or become an error in a recursive function (`TYP0011`, §3.7). Above all, the type is the function's **sign over the door**.

## 3.2 A function is a value

A defined function can be handled like an integer or a string. It can be bound to another name, for example.

```text
lune> def inc(n: Int): Int =
...     n + 1
...
ok
lune> let renamed = inc
ok
lune> renamed(41)
42 : Int
```

Being a value, it has a type. Function types are written with `->`.

```lune
let inc: Int -> Int = fn x -> x + 1
let addA: Int -> Int -> Int = fn x y -> x + y
let addB: (Int, Int) -> Int = fn x y -> x + y
```

`Int -> Int` is "takes an `Int`, returns an `Int`". Two parameters can be written either `Int -> Int -> Int` or `(Int, Int) -> Int`. Since `->` is right-associative, the first is `Int -> (Int -> Int)` — "takes an `Int` and returns an `Int -> Int`". That reading leads directly into partial application in §3.5.

Ask the REPL for the type of `map`, which we have been using since chapter 1.

```text
lune> :type map
map : [T, U] List[T] -> (T -> U) -> List[U]
```

The leading `[T, U]` declares "for any types `T` and `U`" (generics, chapter 5). Read out loud: "takes a list of `T` and a function from `T` to `U`, and returns a list of `U`". A type signature makes a rather good description of a function.

## 3.3 Lambdas — functions without a name

`fn parameters -> expression` builds a function on the spot.

```lune
fn x -> x + 1          # one parameter
fn x y -> x + y        # two parameters (just list them)
fn -> 42               # no parameters
fn x: Int -> x * 2     # with a type annotation
```

The parameter's type annotation **can be left out when the context makes it clear**. Passing a lambda to `map`, or to `applyTwice` in the next section, tells the compiler what to expect. That is why `map(range(1, 6), fn x -> x * 2)` in chapter 1 produced no warning.

Where there is no context, there is nothing to infer from.

```text
lune> let f = fn x -> x * 2
warning[TYP0010]: cannot infer type of parameter x
  --> <repl:5>:1:12
  |
1 | let f = fn x -> x * 2
  |            ^ parameter type falls back to Any
   = hint: add a type annotation, e.g. `fn x: Int -> ...`
   = help: run `lune explain TYP0010` for a detailed explanation
ok
```

Note that it is a `warning`, not an `error` — the binding is made and `x` falls back to `Any`. It runs, but with thinner protection from the type checker, so the habit is to do what the hint says and write `fn x: Int -> x * 2`.

## 3.4 Higher-order functions

A function that takes or returns a function is called a **higher-order function**. Both are ordinary to write. Here is `hof.lune`:

```lune
module hof

def inc(n: Int): Int =
    n + 1

# A function that takes a function.
def applyTwice(f: Int -> Int, x: Int): Int =
    f(f(x))

# A function that returns a function.
def adder(n: Int): Int -> Int =
    fn x -> x + n

let fortyTwo = applyTwice(inc, 40)

let seven = adder(3)(4)
```

```console
$ lune --eval fortyTwo hof.lune
42
$ lune --eval seven hof.lune
7
```

Playing with it in the REPL:

```text
lune> applyTwice(fn x -> x * 10, 4)
400 : Int
lune> adder(3)(4)
7 : Int
```

The lambda `fn x -> x + n` returned by `adder(3)` **remembers** the `n = 3` it was created with. A function that carries the environment of its definition around with it is called a **closure**. It is the same mechanism as the thunk of chapter 4, which is a parcel of "expression plus environment": Lune's world is made of expressions and environments.

## 3.5 Partial application — you may pass only some of the arguments

In the exercises of chapter 1 we met the oddity that calling a one-parameter function with no arguments, `greet()`, is not a type error. This section is the explanation.

In Lune, **a call with too few arguments is not an error; it returns a function waiting for the rest**.

```text
lune> def add(x: Int, y: Int): Int =
...     x + y
...
ok
lune> let plusTen = add(10)
ok
lune> :type plusTen
plusTen : Int -> Int
lune> plusTen(32)
42 : Int
```

Remember reading `add : Int -> Int -> Int` as "give it an `Int` and an `Int -> Int` comes back". `add(10)` just does exactly that. Passing them together as `add(10, 32)` or separately as `add(10)(32)` is the same thing — and that flexibility lets you build "the existing function with some arguments fixed" in one line.

```text
lune> map([1, 2, 3], plusTen)
(11 12 13) : List[Int]
```

Passing too *many*, on the other hand, is still an error (`TYP0005` — and now the phrase "at most 1" makes sense). Arguments passed in a partial application are captured as thunks just like those of an ordinary call: laziness holds consistently inside partial application too.

## 3.6 The pipeline |> — writing the flow of data

When function applications nest, the reading order runs against the execution order. `double(inc(inc(5)))` means "take 5, inc, inc, double", but you have to read it backwards. The **pipeline operator** `|>` fixes that: `x |> f` is sugar for `f(x)`.

```text
lune> 5 |> inc
6 : Int
lune> 5 |> inc |> double
12 : Int
```

Left to right, in the order the data passes through the transformations. And piping into a function of several parameters gives a **partial application**. Here is `pipeline.lune`:

```lune
module pipeline

def inc(n: Int): Int =
    n + 1

def double(n: Int): Int =
    n * 2

def add(x: Int, y: Int): Int =
    x + y

# `x |> f` is sugar for `f(x)`: read left to right, in the order the data flows.
let result = 5 |> inc |> double

# Piping into a function of several parameters gives a partial application.
let addFive = 5 |> add

let eleven = addFive(6)
```

```console
$ lune --eval result pipeline.lune
12
$ lune --eval eleven pipeline.lune
11
```

The pipeline is the syntax for writing a recipe of transformations. It comes into its own in chapter 8, combined with list processing.

## 3.7 Recursion

A function that calls itself — the functional way of writing a loop. Fibonacci is the classic.

```lune
def fib(n: Int): Int =
    if n <= 1 then n else fib(n - 1) + fib(n - 2)
```

```text
lune> fib(10)
55 : Int
```

A recursive function comes with one obligation: **write the result type**. Here is what happens without it, in `norettype.lune`:

```lune
module bad

def fact(n: Int) =
    if n == 0 then 1 else n * fact(n - 1)
```

```console
$ lune --check norettype.lune
```

```text,diagnostic
error[TYP0011]: recursive function requires a return type annotation: fact
  --> norettype.lune:3:1
  |
3 | def fact(n: Int) =
  | ^^^ the function calls itself before its type is known
   = hint: add a return type, e.g. `def fact(...): T = ...`
   = help: run `lune explain TYP0011` for a detailed explanation
```

The diagnostic explains the reason too. `fact(n - 1)` appears before the type of the body has been inferred, so the type checker needs to know the type of `fact` in advance. As chapter 4 shows, only functions may recurse (a recursive *value* gives `RUN0005`), and a recursive function must carry its type on the sign over the door. Those two rules together make recursion safe to use.

One tip on writing them: **write the stopping condition first**. Build the shape `if n == 0 then ... else recursive-call` and only then fill in the recursive side, and infinite recursion becomes harder to write.

> **Break it** — calling something that is not a function has a diagnostic of its own.
>
> ```text,diagnostic
> lune> let x = 42
> ok
> lune> x(1)
> error[TYP0004]: value is not callable: Int
>   --> <repl:7>:1:1
>   |
> 1 | x(1)
>   | ^ this value is not callable
>    = help: run `lune explain TYP0004` for a detailed explanation
> ```
>
> "An `Int` cannot be called" — you usually meet this one after a stray pair of parentheses (the reverse of meaning `f(x)(y)` and writing `f(x, y)`).

## Summary

| Concept | In one line |
| --- | --- |
| `def f(x: T): U = body` | a function definition; the type is the sign over the door, and a recursive function must have a result type |
| Function types | `Int -> Int`; `->` is right-associative, matching how partial application reads |
| `fn x -> expr` | a lambda; the annotation is optional with context, `TYP0010` without |
| Higher-order functions | take or return functions; a returned lambda remembers its environment (a closure) |
| Partial application | a call with too few arguments is a function waiting for the rest |
| `x \|> f` | sugar for `f(x)`; into a multi-parameter function it is a partial application |
| `:type f` | the habit of checking a function's type |

## Exercises

**Exercise 3-1** (★) Rewrite `double(inc(inc(5)))` as a pipeline (`inc` and `double` as in the text).

<details><summary>Answer</summary>

```text
lune> 5 |> inc |> inc |> double
14 : Int
```

`double(inc(inc(5)))` is `14 : Int` as well. Same computation, but the piped version reads in the order it runs: 5 → +1 → +1 → ×2.

</details>

**Exercise 3-2** (★★) Write `compose`, which composes two functions: `compose(f, g)` returns a single function that applies `g` and then `f`.

<details><summary>Answer</summary>

```lune
module answers

# Exercise 3-2: function composition. compose(f, g) is "g, then f".
def compose(f: Int -> Int, g: Int -> Int): Int -> Int =
    fn x -> f(g(x))

def inc(n: Int): Int =
    n + 1

def double(n: Int): Int =
    n * 2

let incThenDouble = compose(double, inc)

let answer = incThenDouble(5)
```

```console
$ lune --eval answer ex3-2.lune
12
```

The returned lambda remembers `f` and `g` — this is practice with closures (§3.4) as much as with composition.

</details>

**Exercise 3-3** (★★) Write `fib` yourself and check `fib(10)`. Then delete the result type `: Int`, predict which diagnostic you will get, and run `--check`.

<details><summary>Answer</summary>

```lune
module answers

# Exercise 3-3: Fibonacci by recursion. The result type Int is required (TYP0011).
def fib(n: Int): Int =
    if n <= 1 then n else fib(n - 1) + fib(n - 2)

let answer = fib(10)
```

```console
$ lune --eval answer ex3-3.lune
55
```

Deleting the result type gives `TYP0011`, the same diagnostic as in §3.7.

</details>

**Exercise 3-4** (★★★) Generalise `applyTwice` into `applyN(f, n, x)`, which applies the function `f` to `x` `n` times. You have it right when `applyN(double, 3, 1)` is `8`.

<details><summary>Answer</summary>

```lune
module answers

# Exercise 3-4: applyTwice generalised — apply f n times.
def applyN(f: Int -> Int, n: Int, x: Int): Int =
    if n == 0 then x else applyN(f, n - 1, f(x))

def double(n: Int): Int =
    n * 2

let answer = applyN(double, 3, 1)
```

```console
$ lune --eval answer ex3-4.lune
8
```

Higher-order functions and recursion together. Write the stopping condition first (`n == 0` returns `x` unchanged), so that the recursive side reads as "apply once, and count down".

</details>

**Exercise 3-5** (★, in reverse) Write the smallest piece of code that produces `TYP0004` (value is not callable).

<details><summary>Answer</summary>

The smallest is `42(1)` (`error[TYP0004]: value is not callable: Int`). Any non-function value — a number, a string, a tuple — with `(...)` after it will do. Conversely, if you can explain why too *few* arguments, as in `greet()`, is neither `TYP0004` nor `TYP0005`, you have graduated from this chapter.

</details>

---

**More precisely** — function definitions, lambdas and partial application are in `documents/LANGUAGE_SPEC.md` §8; the syntax of function types is in `documents/FUNCTION_TYPE_SPEC.md`; how partial application relates to laziness is in `documents/LAZY_EVALUATION_SPEC.md` §7; type inference for lambdas is in `documents/LOCAL_TYPE_INFERENCE_SPEC.md`. The code examples of this chapter live in `books/examples-en/ch03/` and are all verified against the real CLI.
