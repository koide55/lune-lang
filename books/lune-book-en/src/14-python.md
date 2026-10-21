# Chapter 14: Borrowing Python's Power

Lune's implementation is written in Python (appendix E). Hearing that, you may have wondered: then can't Lune use Python's libraries too?

It can. This chapter shows how a single line, `import python.X`, lets you call Python libraries from Lune — NumPy first among them.

Here, though, Lune breaks a promise. Throughout the earlier chapters Lune never let Python's behaviour in (`if 1` did not pass, and `1 == 1.0` was false). Using a Python library means inviting exactly that behaviour in. So Lune **marks out, in the types, where Python's rules apply**. That boundary is this chapter's protagonist: the `Py` type.

## 14.1 import python — NumPy in one line

```lune
module scores
import python.numpy as np

# Chapter 14: leave the computation to NumPy and bring only the results back to Lune.
let scores = np.array([72.0, 85.0, 90.0, 64.0, 78.0])

let mean = asDouble(np.mean(scores))

let best = asInt(np.argmax(scores))

let normalized = (scores - np.mean(scores)) / np.std(scores)
```

```console
$ lune --eval mean scores.lune
77.8
$ lune --eval best scores.lune
2
$ lune --eval normalized scores.lune
[-0.6292464   0.78113347  1.32358726 -1.49717248  0.02169815]
```

`import python.numpy as np` is a relative of chapter 10's external imports. The name after `python.` is a Python module name, and you use it under the name given with `as` (or, without `as`, under its last component). `np.array(...)`, `np.mean(...)`, subtracting and dividing arrays — NumPy is written exactly as in Python.

NumPy has to be installed beforehand (`python3 -m pip install numpy`). The Playground, which needs no installation, is covered in §14.9.

**The import does not happen until it is used.** Writing `import python.numpy` only checks that the module exists. It is actually loaded when `np` is first used. The club motto from chapter 4, "don't do it until you need to", applies to loading modules too.

## 14.2 The Py type — seeing the boundary in the types

What is the type of `np.array(...)`? Ask the REPL.

```text
lune> import python.numpy as np
ok
lune> np.arange(3) * 2
[0 2 4] : Py
```

**`Py`** is the type of "a Python object". On a `Py` value you can read a member (`np.mean`), call it (`np.mean(a)`), index it (`m[1, 2]`) and apply operators (`a * 2`), and the result is again a `Py`. Inside `Py`, Python's rules apply unchanged.

In return, **a `Py` never silently becomes a Lune type.**

```lune
module border
import python.numpy as np

# A Py never silently becomes an Int.
let scores = np.array([72, 85, 90])

let total: Int = np.sum(scores)
```

```text,diagnostic
error[TYP0003]: let annotation: expected Int, got Py
  --> border.lune:7:18
  |
7 | let total: Int = np.sum(scores)
  |                  ^^ this expression has type Py
   = hint: use `asInt(...)` to convert a Python value to Int
   = help: run `lune explain TYP0003` for a detailed explanation
```

What `np.sum` returns is a Python integer (a NumPy `int64`, to be exact), not a Lune `Int`. As the hint says, `asInt(np.sum(scores))` gives an `Int`. Every place that crosses the boundary has to be visible in the source — that is the promise of the `Py` type.

The conversion functions:

| Function | Type | Accepts |
| --- | --- | --- |
| `asInt` | `Py -> Int` | integers (NumPy's too); not booleans |
| `asDouble` | `Py -> Double` | real numbers (integers too) |
| `asString` | `Py -> String` | strings |
| `asBool` | `Py -> Bool` | booleans only; never "truthy" values |
| `asList` | `Py -> List[Py]` | anything iterable (§14.4) |
| `asNullable` | `Py -> Py?` | anything; Python's `None` becomes `null` |
| `toPy` | `T -> Py` | makes a Lune value a `Py` (§14.3) |
| `pyStr` | `Py -> String` | Python's `str()` |

A failed conversion is a runtime error (`RUN0006`). `asInt(np.array([1, 2]))` stops with "a Python ndarray cannot be converted to Int".

### The trap of an array's truth value

There is a trap that people new to NumPy step into first.

```lune
module truth
import python.numpy as np

# Comparing an array gives an array, which cannot be used as a condition as it is.
let scores = np.array([72.0, 85.0, 90.0])

let verdict = if scores > 70.0 then "pass" else "fail"
```

`scores > 70.0` is an array, `[True True True]`, saying for each element whether it exceeds 70. Hand that to `if` in Python and you get a runtime error: "the truth value of an array is ambiguous". Lune stops it **before the program runs**.

```text,diagnostic
error[TYP0003]: if condition: expected Bool, got Py
   = hint: use `asBool(...)` to convert a Python value to Bool
   = hint: to test all or any elements of an array, use `np.all(...)` or `np.any(...)`
   = help: run `lune explain TYP0003` for a detailed explanation
```

For "did everyone score above 70", reduce it to one truth value with `np.all(...)`; for "did anyone", with `np.any(...)`. Then turn that into a `Bool` with `asBool` (exercise 14-2).

## 14.3 What goes from Lune to Python

The other direction — passing Lune values to Python — is automatic. In §14.1, `np.array([72.0, 85.0, ...])` received the Lune list as a Python list.

| Lune type | Python value |
| --- | --- |
| `Int` / `Double` / `String` / `Bool` | `int` / `float` / `str` / `bool` |
| `Unit`, `null` | `None` |
| `List[T]`, `Tuple[...]` | `list`, `tuple` (contents by the same rules) |
| `Py` | the object itself |
| a function taking `Py` | a function Python can call (§14.5) |

This direction may be automatic because every Lune value has exactly one Python counterpart. A Python value, by contrast, has no single Lune type it should become (is a `numpy.int64` an `Int` or a `Double`?). That is why only the way back is explicit.

Values not in the table — `Option`, records, ADTs of your own — cannot be passed to Python, and the type check stops them.

Since arguments are converted automatically, you rarely write `toPy` yourself. You use it when you want a Lune value to take part in **a Python operation**:

```text
lune> toPy([1, 2]) * 3
[1, 2, 1, 2, 1, 2] : Py
lune> [1, 2] * 3
error[TYP0003]: *: expected numeric type, got List[Int]
   = help: run `lune explain TYP0003` for a detailed explanation
```

A Lune list has no `*`, but turned into a Python list with `toPy`, it gets Python's "repeat the list".

**Named arguments** become Python keyword arguments. In chapter 13 we saw that `name = value` means something only when building a record, and that on a function or constructor it is `TYP0012`. A `Py` callee is the exception. **Indexing** with `[]` likewise works only on `Py` values.

```lune
module matrix
import python.numpy as np

# Named arguments become keyword arguments, and [] becomes Python indexing.
let m = np.arange(6).reshape(2, 3)

let columnSums = np.sum(m, axis = 0)

let corner = asInt(m[1, 2])

let firstColumn = m[pySlice(null, null), 0]
```

```console
$ lune --eval columnSums matrix.lune
[3 5 7]
$ lune --eval corner matrix.lune
5
$ lune --eval firstColumn matrix.lune
[0 3]
```

Lune has no syntax yet for the slice that Python writes `m[:, 0]` (column 0 of every row), so it is written `pySlice(null, null)`.

### The standard library works the same way

Not just NumPy: Python's standard library is used the same way.

```lune
module regex
import python.re
import python.json

# The standard library works the same way. match is a Lune keyword, but after a dot it is a name.
let found = re.match("(\\d+)-(\\d+)", "12-34")

let left = asString(found.group(1))

let person = json.loads("{\"name\": \"Ada\", \"age\": 36}")

let name = asString(person["name"])

let nothing = asNullable(re.match("x", "abc"))
```

```console
$ lune --eval left regex.lune
"12"
$ lune --eval name regex.lune
"Ada"
$ lune --eval nothing regex.lune
null
```

The `match` in `re.match` is a Lune keyword, but after a `.` it is read as a name. When there is no match, `re.match` returns Python's `None`; received with `asNullable`, it becomes chapter 7's `null`.

## 14.4 What comes back from Python — as a lazy list

`asList` turns anything Python can iterate over into a Lune list. That list is a **lazy list**.

```lune
module stream
import python.itertools as it

# Even an infinite Python iterator becomes a lazy list in Lune.
let evens = map(asList(it.count(0, 2)), asInt)

let firstFive = take(evens, 5)
```

```console
$ lune --eval firstFive stream.lune
(0 2 4 6 8)
```

`it.count(0, 2)` is a Python iterator that counts 0, 2, 4, … without end. `asList` wraps it in the same shape as chapter 8's infinite streams, and elements are taken out **one at a time, when they are used**. `take` stops at five, so the program stops too.

The elements taken out are memoised (chapter 4). Walk the same list twice and the Python iterator still advances only once.

## 14.5 Passing functions to Python

Many Python libraries take a function: the `key` that tells `sorted` how to order, `functools.reduce` for folding, `np.vectorize` for spreading a per-element function over a whole array. Lune functions can be passed as they are.

```lune
module callbacks
import python.builtins as py
import python.functools as ft
import python.numpy as np

def lastDigit(x: Py): Int =
    asInt(x) % 10

let xs = [31, 12, 23, 44]

# The lambda's parameter is Py. Python calls it, so no annotation is needed.
let byLast = map(asList(py.sorted(xs, key = fn x -> asInt(x) % 10)), asInt)

let byLastDesc = map(asList(py.sorted(xs, key = lastDigit, reverse = true)), asInt)

let total = asInt(ft.reduce(fn acc x -> asInt(acc) + asInt(x), xs, 0))

let doubled = np.vectorize(fn x -> asDouble(x) * 2.0)(np.arange(4))
```

```console
$ lune --eval byLast callbacks.lune
(31 12 23 44)
$ lune --eval byLastDesc callbacks.lune
(44 23 12 31)
$ lune --eval total callbacks.lune
110
$ lune --eval doubled callbacks.lune
[0. 2. 4. 6.]
```

`python.builtins` is the module holding `sorted`, `len`, `int` and the other functions Python uses without an import.

There is one condition on the functions you pass. **Python calls a function with Python values, so its parameters take `Py`.** `def lastDigit(x: Py)` does that, and a lambda written directly as an argument of a Python call gets `Py` parameters when you leave out the annotations. Try to pass a function that takes an `Int`, and the type check stops you.

```lune
module callback_bad
import python.builtins as py

# A function taking Lune types cannot be called from Python.
def inc(x: Int): Int =
    x + 1

let sorted = py.sorted([3, 1, 2], key = inc)
```

```text,diagnostic
error[TYP0003]: a value of type Int -> Int cannot be passed to Python
  --> callback_bad.lune:8:41
  |
8 | let sorted = py.sorted([3, 1, 2], key = inc)
  |                                         ^^^ this value has no Python counterpart
   = hint: Python calls a function with Py values: declare its parameters as Py, or leave a lambda's unannotated, and convert inside, e.g. `fn x -> asInt(x) + 1`
   = help: run `lune explain TYP0003` for a detailed explanation
```

When a Lune error happens inside such a function, it passes through the Python code in between and arrives as the Lune error it is. Call `crash()` inside a `key` for `sorted`, and what you get is `RUN0006`.

## 14.6 Lazy evaluation and side effects — not always in the order written

From here on come the cautions particular to using Python from Lune. The standard library's `random` is the clearest example.

```lune
module dice
import python.random

# The binding used first receives the first random number.
def lazyDraws(): Tuple[Double, Double] =
    random.seed(42)
    let x = asDouble(random.random())
    let y = asDouble(random.random())
    (y, x)

# strict let evaluates in the order written.
def strictDraws(): Tuple[Double, Double] =
    random.seed(42)
    strict let x = asDouble(random.random())
    strict let y = asDouble(random.random())
    (y, x)

let lazyPair = lazyDraws()

let strictPair = strictDraws()
```

```console
$ lune --eval lazyPair dice.lune
(0.6394267984578837, 0.025010755222666936)
$ lune --eval strictPair dice.lune
(0.025010755222666936, 0.6394267984578837)
```

Written in the same order in Python, `x` gets the first random number (0.639…) and `y` the second (0.025…). `strictPair` agrees. In `lazyPair`, though, they are swapped.

The reason is chapter 4 itself. A `let` only promises a value; the computation happens when the value is used. When `(y, x)` is displayed, `y` is used first, so `y`'s `random.random()` is called first and receives the first random number. In Lune's pure world the order of computation never affected the result, but with **a function that returns a different value each time it is called**, the order changes the result.

There are three remedies.

- Write a call whose result you do not use, like `random.seed(42)`, **as a statement** rather than in a `let`. A statement in a block runs where it is written. Write `let seeded = random.seed(42)` at the top level and, since nothing uses `seeded`, it never runs at all
- Receive the result of a call with side effects in a **`strict let`**
- When you need several random numbers, **draw them in one call** (exercise 14-4). With only one call there is no order to get wrong

### A list passed to Python is a copy

The other caution concerns Python functions that change what they are given.

```lune
module shuffle
import python.random

# A Lune list is copied into a Python list each time it is passed. The copy is what gets shuffled.
let xs = [1, 2, 3, 4, 5]

let result = random.shuffle(xs)

let after = (result, xs)

let picked = map(asList(random.Random(7).sample(xs, 3)), asInt)
```

```console
$ lune --eval after shuffle.lune
(None, (1 2 3 4 5))
$ lune --eval picked shuffle.lune
(3 2 4)
```

`random.shuffle` reorders the list it is given in place and returns Python's `None`. But what got reordered was the **copy** made when the list was passed. Lune's `xs` does not change. A Lune list is a value that cannot be modified, and that holds on the far side of the boundary too. Use functions that return a new list instead (`random.sample`, `sorted`).

`random.Random(7)` creates a random number generator with a fixed seed. Unlike `random.seed`, it does not change any global state, so ordering problems are less likely too.

## 14.7 About speed

Lune runs on Python and is slower still than Python. Does using NumPy make it faster?

**It does — once the computation moves to the Python side.** NumPy's array computations are written in C, and `np.mean(scores)` never goes through Lune's evaluator. Leave the heavy computation to NumPy and Lune's slowness stops mattering.

The **conversion across the boundary, however, runs at Lune's speed.** Write `np.array(range(1, 1000000))` and Lune's evaluator walks a million cells one by one to build a Python list before handing it to NumPy. Write the same array as `np.arange(1, 1000000)` and it is built inside NumPy from the start.

> **Build the data on the Python side from the start** (`np.arange`, `np.loadtxt`, `np.random.default_rng`), and cross the boundary as rarely, and with as little, as you can.

That is the single most important habit when using Python from Lune.

## 14.8 When things fail

### A Python exception — RUN0007

```lune
module broadcast
import python.numpy as np

# Arrays whose shapes do not fit raise a Python exception.
let a = np.array([1, 2, 3])

let b = np.array([1, 2])

let combined = a + b

let typo = np.summ(a)
```

```text,diagnostic
$ lune --eval combined broadcast.lune
error[RUN0007]: Python raised ValueError: operands could not be broadcast together with shapes (3,) (2,)
   = hint: run `lune` with `--py-traceback` to see the full Python traceback
   = help: run `lune explain RUN0007` for a detailed explanation
$ lune --eval typo broadcast.lune
error[RUN0007]: Python raised AttributeError: module 'numpy' has no attribute 'summ'
   = hint: did you mean `sum`?
   = hint: run `lune` with `--py-traceback` to see the full Python traceback
   = help: run `lune explain RUN0007` for a detailed explanation
```

When Python code raises an exception, the result is `RUN0007`. The message is Python's own explanation (arrays of shape `(3,)` and `(2,)` cannot be added). A misspelt attribute gets a "did you mean", just like chapter 1's `TYP0001`. Python's traceback is hidden by default; add `--py-traceback` to see it.

### The module is not found — MOD0004

```text,diagnostic
error[MOD0004]: Python module not found: torch
  --> missing.lune:2:1
  |
2 | import python.torch as torch
  | ^^^^^^ not installed in the Python that runs lune
   = hint: install it with `python3 -m pip install torch` (this is the Python that runs lune)
   = help: run `lune explain MOD0004` for a detailed explanation
```

Where the hint says `python3`, the real output shows the absolute path of the Python executable running lune (shortened here). When "I pip-installed it and it still isn't found", the package has usually gone into a different Python. Reinstall it with the command the hint gives.

To forbid Python imports — say, when running submitted programs on a grading server — pass `--no-python` or set the environment variable `LUNE_PYTHON=off`. Every `python.*` import then becomes `MOD0004`.

## 14.9 In the Playground

The Playground runs Lune on a Python that lives inside the browser (Pyodide). Pyodide comes with NumPy, SciPy, pandas, scikit-learn and more, and when a program contains `import python.numpy`, the package is loaded automatically before it runs. Nothing to install. Try the NumPy preset in the sample menu.

This chapter's code examples carry an **Open in the Playground** link as well. Packages that Pyodide does not have (PyTorch, for example) cannot be used in the Playground; they give `MOD0004`.

> **Break it** — what if you "fixed" §14.2's `truth.lune` with `asBool(scores > 70.0)` instead of `np.all`? The type check passes (`asBool` takes a `Py`). And when it runs? `asBool` does not accept "truthy" values, so given an array it stops with `RUN0006` (a Python ndarray cannot be converted to Bool). Where Python would raise its "ambiguous" error, Lune stops in its own words.

## Summary

| Concept | In one line |
| --- | --- |
| `import python.X as y` | use a Python module; the real import happens on first use |
| The `Py` type | a Python object; members, calls, indexes and operators on it give `Py` too |
| Lune → Python | automatic: numbers, strings, booleans, `null`, lists, tuples, `Py`, functions taking `Py` |
| Python → Lune | explicit: `asInt` `asDouble` `asString` `asBool` `asList` `asNullable` |
| Keyword arguments, indexing | only when the callee or receiver is a `Py` |
| `asList` | turns a Python iterable into a lazy list; it may be infinite |
| Passing functions | parameters take `Py`; a lambda inside a Python call is `Py` without annotations |
| Side effects | happen in the order of use: write a statement, use `strict let`, draw everything in one call |
| Speed | leave computation to Python, and build the data on the Python side |
| Diagnostics | `MOD0004` module not available / `RUN0007` Python exception (`--py-traceback`) |

## Exercises

**Exercise 14-1** (★) Use the standard library's `statistics` to compute, as `Double`s, the median and mean of the Lune list `[3.0, 1.0, 4.0, 1.0, 5.0, 9.0]`.

<details><summary>Answer</summary>

```lune
module ex14_1
import python.statistics as st

# Exercise 14-1: the median and mean of a Lune list, with the standard library's statistics.
let data = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0]

let median = asDouble(st.median(data))

let mean = asDouble(st.mean(data))
```

```console
$ lune --eval median ex14-1.lune
3.5
$ lune --eval mean ex14-1.lune
3.8333333333333335
```

The Lune list goes across as a Python list, and the result comes back as a `Py`, which `asDouble` turns into a `Double`. This one works without NumPy.

</details>

**Exercise 14-2** (★★) Fix §14.2's `truth.lune` so that it means "`"pass"` if everyone scored above 70".

<details><summary>Answer</summary>

```lune
module ex14_2
import python.numpy as np

# Exercise 14-2: an array comparison is an array, so reduce it to one truth value with np.all, then convert to Bool.
let scores = np.array([72.0, 85.0, 90.0])

let verdict = if asBool(np.all(scores > 70.0)) then "pass" else "fail"
```

```console
$ lune --eval verdict ex14-2.lune
"pass"
```

`scores > 70.0` is an array; `np.all(...)` reduces it to one truth value (a NumPy `bool`); `asBool` makes that a Lune `Bool`. For "if anyone", use `np.any`.

</details>

**Exercise 14-3** (★★) Sort `["banana", "fig", "kiwi", "apple"]` by word length, using Python's `sorted` and `len`.

<details><summary>Answer</summary>

```lune
module ex14_3
import python.builtins as py

# Exercise 14-3: sort words by length. The parameter of the lambda given as key is Py.
let words = ["banana", "fig", "kiwi", "apple"]

let byLength = map(asList(py.sorted(words, key = fn w -> py.len(w))), asString)
```

```console
$ lune --eval byLength ex14-3.lune
("fig" "kiwi" "apple" "banana")
```

The lambda `fn w -> py.len(w)` may return a `Py` as it is, since the comparing happens on the Python side. `"kiwi"` and `"apple"` have lengths 4 and 5, and `"banana"` comes last.

</details>

**Exercise 14-4** (★★★) Explain why `x` and `y` were swapped in §14.6's `lazyDraws`, and rewrite it, without `strict let`, so that the two random numbers go into `x` and `y` in the order written.

<details><summary>Answer</summary>

The right-hand side of a `let` is evaluated when it is used, so `y`, used first, called `random.random()` first and received the first random number. With a function whose value changes on every call, the order of the calls decides the result.

Make it a single call and the ordering problem disappears altogether.

```lune
module ex14_4
import python.numpy as np

# Exercise 14-4: draw the random numbers in one call, and the order of forcing no longer matters.
let draws = map(asList(np.random.default_rng(42).random(2)), asDouble)

let x = head(draws)

let y = head(drop(draws, 1))
```

```console
$ lune --eval x ex14-4.lune
Some(0.7739560485559633)
$ lune --eval y ex14-4.lune
Some(0.4388784397520523)
```

Even if `y` is displayed first, both numbers were fixed by the one call to `random(2)`, so the values of `x` and `y` do not change. `np.random.default_rng(42)` creates a generator with a fixed seed, so every run gives the same values.

</details>

---

**More precisely** — the rules of the `Py` type, the conversion tables, when evaluation happens, and the normative diagnostics are in `documents/PYTHON_INTEROP_SPEC.md`. `MOD0004` and `RUN0007` are also explained in `documents/ERROR_INDEX.md`. The code examples of this chapter live in `books/examples-en/ch14/` and are all verified against the real CLI (the NumPy ones in an environment with NumPy installed).
