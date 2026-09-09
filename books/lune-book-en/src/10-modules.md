# Chapter 10: Modules

As a program grows it stops fitting in one file. This chapter covers splitting a Lune program across files — **modules**.

The module system of v0.1 is deliberately small. There is no package management, no public/private control, no namespace access. There is only "split into files and load them". Even so, this minimal set of tools has four rules worth knowing, and getting them wrong produces diagnostics of its own (the `MOD` family, chapter 11).

## 10.1 The module declaration — the file's name tag

The first line you have been copying since chapter 1 finally takes the lead.

```lune
module geometry
```

A Lune source file declares which module it is. And **the declaration must agree with the file's location**: `module geometry` for `geometry.lune`, `module util.text` for `util/text.lune`. A dot corresponds to a directory separator.

```lune
module util.text

def shout(s: String): String =
    s + "!"
```

A module name, then, is the route to the file. When the name tag disagrees with where it sits, the importing side complains (§10.5).

One exception: the **entry file**, the one passed directly to `--eval` or `--check`, is not required to match. (That is how this book has been able to put `module hello` in all sorts of places.)

## 10.2 import — bringing names in

The reading side uses `import`. Here is `main.lune`:

```lune
module main
import geometry
import util.text

let area = circleArea(1.0)

let banner = shout("area")
```

```console
$ lune --eval area main.lune
3.14159
$ lune --eval banner main.lune
"area!"
```

Writing `import geometry` brings the top-level declarations of `geometry.lune` (`def`, `let`, `type`, `record`) **straight into your own environment**. Note that the call is the unqualified `circleArea(...)`, not `geometry.circleArea(...)`.

Qualified calls are not possible in v0.1.

```text,diagnostic
lune> let a = geometry.circleArea(1.0)
error[TYP0001]: undefined name: geometry
   = help: run `lune explain TYP0001` for a detailed explanation
```

There is no value named `geometry` — an import carries the names of the contents and nothing else. The flip side is that **two modules defining the same name will collide**. The defence in v0.1 is not to make names too short (`cartTotal` rather than `total`).

The canonical form puts the `module` declaration and the `import` lines together with no blank line between them (`lune fmt` will arrange them that way; chapter 12).

## 10.3 How to divide a program

How should you split it? Two ideas actually pay off with the tools of v0.1.

**Keep data and its operations together.** Put a record or ADT definition and the functions that work on it in the same module. The `shop/items.lune` of exercise 10-2 has this shape.

```lune
module shop.items

record Item:
    name: String
    price: Int

def priceOf(item: Item): Int =
    item.price

def total(items: List[Item]): Int =
    fold(map(items, priceOf), 0, fn a x -> a + x)
```

**Extract general-purpose tools.** Utilities for strings or numbers, called from everywhere, go somewhere like `util.text`.

There are also divisions that are **better avoided** in v0.1. "Split to hide the implementation" — without public/private control, everything stays visible. "Split apart things that reference each other" — as the next section shows, cycles are forbidden.

## 10.4 Cyclic imports are detected

What happens when `cycle_a` imports `cycle_b` and `cycle_b` imports `cycle_a`?

```console
$ lune --check cycle_a.lune
```

```text,diagnostic
error[MOD0002]: cyclic module import detected: cycle_a.lune -> cycle_b.lune -> cycle_a.lune
  --> cycle_b.lune:2:1
  |
2 | import cycle_a
  | ^^^^^^ this import closes the cycle
   = help: run `lune explain MOD0002` for a detailed explanation
```

The diagnostic shows **the path of the cycle itself** (`cycle_a → cycle_b → cycle_a`) and names the import that closed the loop. You can see at a glance where to cut.

Why forbid it? Lune type-checks and evaluates a module's dependencies **first** (`geometry` before `main`). With a cycle there is no "first". It is the same reasoning that made `let x = x + 1` a `RUN0005` in chapter 4, appearing at the granularity of files.

There are three fixes: extract the common part into a third module, make the dependency point one way only, or put the two back into one file (mutual reference inside a single file is fine).

## 10.5 When a module is not found — the search order

`import foo.bar` looks for `foo/bar.lune`. It looks in three places, in this order.

1. the directory of the entry file
2. the current directory
3. directories added with `--module-path` (which may be repeated)

The third is useful when a shared library lives in a directory of its own. Here is `lib/shared.lune` (`module shared`) used from `usesshared.lune`:

```console
$ lune --check usesshared.lune
error[MOD0001]: module not found: shared
$ lune --module-path lib --check usesshared.lune
type check OK
$ lune --module-path lib --eval answer usesshared.lune
42
```

When it is not found, the diagnostic **tells you where it looked**.

```text,diagnostic
error[MOD0001]: module not found: nothere
  --> missing.lune:2:1
  |
2 | import nothere
  | ^^^^^^ no matching .lune file was found
   = hint: searched: .
   = help: run `lune explain MOD0001` for a detailed explanation
```

(`searched:` really prints absolute paths; the book abbreviates them.)

When the file is found but the name tag differs, the diagnostic is a different one. With `mismatch.lune` containing `module totally.different`:

```text,diagnostic
error[MOD0003]: module declaration mismatch: expected mismatch, got totally.different
  --> mismatch.lune:1:1
  |
1 | module totally.different
  | ^^^^^^ module name does not match the import path
   = hint: change the declaration to `module mismatch` or import it as `totally.different`
   = help: run `lune explain MOD0003` for a detailed explanation
```

Note that the hint offers **the fix in both directions** (change the tag, or change the import). Which one is right is a design decision, so the machine does not choose; it lays out both. A good example of "a hint gives cause and remedy", which chapter 11 covers.

## 10.6 External imports — java.* and std.*

Finally, there are imports that do not point at a Lune file.

```lune
module basics
import java.time.LocalDate

def today(): String =
    LocalDate.now().toString()
```

An import beginning with `java.`, `javax.`, `kotlin.` or `std.` is treated as an **external import** and is not resolved to a file. The type checker merely registers the last name (`LocalDate`) as `Any`, so this definition type-checks — and fails at run time if you actually call it. JVM interoperation is future work (appendix E); v0.1 only accepts the syntax.

Since everything passes as `Any`, external imports are a region where type checking does not protect you. It is wise not to use them in programs written for v0.1.

> **Break it** — produce two of this chapter's `MOD` diagnostics yourself: `MOD0001` (not found) and `MOD0003` (mismatched tag). You can also move from one to the other: keep `import nothere`, create `nothere.lune`, and write `module wrong.name` in it — `MOD0001` becomes `MOD0003`.
>
> ```text,diagnostic
> error[MOD0003]: module declaration mismatch: expected nothere, got wrong.name
>   --> nothere.lune:1:1
>   |
> 1 | module wrong.name
>   | ^^^^^^ module name does not match the import path
>    = hint: change the declaration to `module nothere` or import it as `wrong.name`
>    = help: run `lune explain MOD0003` for a detailed explanation
> ```
>
> You can feel that "find the file" and "check the name tag" are separate stages. Note also that `module something.else` is a syntax error (`PRS0002`) because `else` is a keyword — module names cannot contain keywords.

## Summary

| Concept | In one line |
| --- | --- |
| `module a.b` | the name tag; must match `a/b.lune` (the entry file is exempt) |
| `import a.b` | the other module's top-level declarations enter your environment (used unqualified) |
| namespace access | `a.b.f()` is not supported; watch out for name collisions yourself |
| canonical form | `module` and the `import` lines run together, with no blank line |
| cycles | `MOD0002`; dependencies are evaluated first, so no loops |
| search order | the entry file's directory → the current directory → `--module-path` |
| diagnostics | `MOD0001` not found (with where it looked) / `MOD0003` mismatched tag (hints both ways) |
| external imports | `java.*`, `std.*` and friends are registered as `Any` only; effectively unusable in v0.1 |

## Exercises

**Exercise 10-1** (★) Create a file containing `import nothere` to produce `MOD0001`, then create `nothere.lune` containing `module wrong.name` to turn it into `MOD0003`.

<details><summary>Answer</summary>

Exactly §10.5 and the "Break it" box. `MOD0001`'s hint is where it looked; `MOD0003`'s hint is the two-way choice (fix the tag or fix the import). The change from one diagnostic to the other shows that checking proceeds in the order: resolve the file, then check the name tag.

</details>

**Exercise 10-2** (★★) Move chapter 6's `Item` record and its aggregation into `shop/items.lune` (`module shop.items`), and compute the total from a `main` in another file.

<details><summary>Answer</summary>

```lune
module shop.items

# Exercise 10-2: split the data and its operations out into a module.
record Item:
    name: String
    price: Int

def priceOf(item: Item): Int =
    item.price

def total(items: List[Item]): Int =
    fold(map(items, priceOf), 0, fn a x -> a + x)
```

```lune
module shop_main
import shop.items

# Imported names are used unqualified: Item, priceOf and total alike.
let cart = [Item(name = "pen", price = 120), Item(name = "note", price = 200)]

let sum = total(cart)
```

```console
$ lune --eval sum shop_main.lune
320
```

`record Item` is carried across by the import too, so the using side builds it normally with `Item(name = ..., price = ...)`. Types, functions and values all come across alike: every top-level declaration does.

</details>

**Exercise 10-3** (★★) Put a `module shared` file in a `lib/` directory and load it with `--module-path`. Check what happens without the flag as well.

<details><summary>Answer</summary>

As in §10.5: without the flag, `MOD0001`; with it, it passes. Note that `lib/shared.lune` declares `module shared`, not `module lib.shared` — `--module-path lib` says "start the search at `lib`", so `lib` is not part of the module name.

</details>

**Exercise 10-4** (★★★) Create a cycle between two modules to produce `MOD0002`, then resolve it by extracting the shared part into a third module.

<details><summary>Answer</summary>

`cycle_a` ⇄ `cycle_b` makes the cycle (§10.4). To resolve it, move the definitions both of them need into `common.lune` and have `cycle_a` and `cycle_b` import only `common`. The dependency graph turns from a loop into a tree, so an evaluation order exists again. The diagnostic shows the path (`a -> b -> a`), which is where to start when deciding which edge to cut.

</details>

**Exercise 10-5** (★) A file containing `import java.time.LocalDate` passes the type check. Why? And why is that not safe?

<details><summary>Answer</summary>

An external import merely registers the last name, `LocalDate`, as `Any`, without resolving anything (§10.6). `Any` can be used as anything, so a mistake such as `LocalDate.nonexistentMethod()` slips through the type check and is not found until run time. Type checking does not protect you there — which is why v0.1 programs should avoid external imports.

</details>

---

**More precisely** — the determination of search roots, the test for external imports, and the normative loading order and cycle detection are in `documents/MODULE_LOADING_SPEC.md`. The `MOD` family of diagnostics is also collected in `documents/ERROR_INDEX.md`. The code examples of this chapter live in `books/examples-en/ch10/` and are all verified against the real CLI.
