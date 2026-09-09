# Chapter 7: Null Safety

`null`, standing for the absence of a value, is the king of runtime errors in many languages. Forget a single null check and one day the program simply falls over — a device its own inventor came to call his billion-dollar mistake.

Rather than abolish `null`, Lune chose to **tame it with types**. Places where null may appear are declared with the type `T?`, and the compiler will not let you use such a value before checking it. The role is close to `Option` from chapter 5, but this is the lightweight version, with syntax of its own (`??`, `?.`, narrowing). The end of the chapter sorts out which to use when.

## 7.1 T? — a type that can hold null

Adding `?` to a type lets it hold a value of that type **or `null`**.

```text
lune> let present: Int? = 42
ok
lune> let absent: Int? = null
ok
lune> present
42 : Nullable[Int]
```

The `Nullable[Int]` in the display is the internal name of `Int?` (read it as such). An `Int` value goes where an `Int?` is wanted, but **not the other way round**.

```text,diagnostic
lune> def wantsInt(n: Int): Int =
...     n + 1
...
ok
lune> wantsInt(present)
error[TYP0003]: expected Int, got Nullable[Int]
   = help: run `lune explain TYP0003` for a detailed explanation
```

That is the whole of null safety. A value that might be null cannot be used as an ordinary value **until you have checked**. The rest of this chapter is the ways of checking.

## 7.2 Removing it with match — covering null, and narrowing

The most basic way is `match`. Here is `orzero.lune`:

```lune
module orzero

# A T? holds either a T or null.
let present: Int? = 42

let absent: Int? = null

# Covering null in a match narrows v to Int in the remaining arm.
def orZero(value: Int?): Int =
    match value:
        | null -> 0
        | v -> v
```

```console
$ lune --eval unwrapped orzero.lune
42
$ lune --eval defaulted orzero.lune
0
```

Because the `| null ->` arm has taken null **first**, the `v` of the next arm is **narrowed** to `Int`. That is why `v` can be returned as an `Int` unchanged.

Exhaustiveness checking (chapter 5) counts null as a case. Here is `missingnull.lune`:

```lune
module bad

# A match on Bool? needs more than true and false.
def toInt(b: Bool?): Int =
    match b:
        | true -> 1
        | false -> 0
```

```console
$ lune --check missingnull.lune
```

```text,diagnostic
error[TYP0007]: non-exhaustive match: missing case null
  --> missingnull.lune:5:5
  |
5 |     match b:
  |     ^^^^^ pattern null is not covered
   = hint: add a case for null, or a wildcard case `| _ -> ...`
   = help: run `lune explain TYP0007` for a detailed explanation
```

The classic accident of forgetting a null check has turned into `missing case null` at compile time.

One caution. Catching everything with a name pattern satisfies exhaustiveness but does **not** narrow.

```text,diagnostic
lune> def bad(value: Int?): Int =
...     match value:
...         | v -> v
...
error[TYP0003]: branch: expected Int, got Nullable[Int]
  --> <repl:6>:3:16
  |
3 |         | v -> v
  |                ^ this expression has type Nullable[Int]
   = help: run `lune explain TYP0003` for a detailed explanation
```

`v` becomes an `Int` only when the `null` arm comes before it.

## 7.3 ?? — this one, if there is nothing

"Use a default when it is null" is common enough to have its own operator: the **null-coalescing operator** `??`.

```text
lune> absent ?? 7
7 : Int
lune> present ?? 7
42 : Int
lune> present ?? crash()
42 : Int
```

It returns the left side unless it is null, and the right side when it is. The result type is `Int`, not `Int?` — after coalescing, the possibility of null is gone. Note the third example: when there is a value on the left, **the right side is not even evaluated**. Chapter 4's lazy evaluation, doing its ordinary work here too.

## 7.4 ?. — following a reference safely

"Read `user.name`, but only if `user` is not null" also has syntax of its own: **safe navigation**, `?.`. Here is `nameof.lune`:

```lune
module nameof

record User:
    name: String
    age: Int

# ?. short-circuits to null when the receiver is null, and reads the field
# otherwise.
def nameOf(user: User?): String? =
    user?.name

let someName = nameOf(User(name = "Ada", age = 36))

let noName = nameOf(null)

let fallback = nameOf(null) ?? "(nobody)"
```

```console
$ lune --eval someName nameof.lune
"Ada"
$ lune --eval noName nameof.lune
null
$ lune --eval fallback nameof.lune
"(nobody)"
```

Null receiver, null result; otherwise the field's value. The result is always a `String?`, so catch it at the end with `??` or a `match`. Carry null along with `?.` and land it with `??` — the two are used as a pair.

## 7.5 Narrowing with if

Where a `match` would be more than you need, an `if` condition narrows as well.

```text
lune> def orOne(x: Int?): Int =
...     if x != null then x else 1
...
ok
lune> orOne(absent)
1 : Int
```

In the branch where `x != null` is true, `x` can be used as an `Int` (with `x == null`, the false branch narrows instead). This narrowing works only for the simple forms `x != null` and `x == null`; it does not extend to compound conditions joined with `&&`, or to `elif`. When the condition gets involved, switch to `match`.

## 7.6 Writing a function that returns null

So far we have been on the receiving end of null. On the **returning** end, the straightforward code just works.

```text
lune> def maybeDiv(x: Int, y: Int): Double? =
...     if y == 0 then null else x / y
...
ok
lune> maybeDiv(7, 2)
3.5 : Nullable[Double]
lune> maybeDiv(7, 0)
null : Nullable[Double]
```

Why do the arm returning `null` and the arm returning `Double` meet without complaint? This is the mechanism promised in the look-ahead box of §5.6: the result annotation `Double?` is handed to both branches of the `if` as the **expected type**, and both the `null` arm and the `x / y` arm line up at `Double?` there. The same happens for the arms of a `match`. Here it is as a file, `maybediv.lune`:

```lune
module maybediv

# The expected type Double? reaches both branches of the if, and the null arm
# and the x / y arm meet there.
def maybeDiv(x: Int, y: Int): Double? =
    if y == 0 then null else x / y

let some = maybeDiv(7, 2)

let none = maybeDiv(7, 0)

let fallback = maybeDiv(7, 0) ?? 0.0
```

```console
$ lune --eval some maybediv.lune
3.5
$ lune --eval none maybediv.lune
null
$ lune --eval fallback maybediv.lune
0.0
```

`maybeDiv(7, 0)` raises no division-by-zero error because an `if` does not evaluate the arm it did not choose (chapter 4). Leave the computation that might fail in the else arm and let null carry the other case — the basic shape of a function returning `T?`.

> **This works too** — you can also build the parts in an annotated `let` before branching.
>
> ```lune
> # Building the parts in an annotated let before branching works too.
> # quotient is a thunk, so on the y == 0 side the division never runs.
> def maybeDivLet(x: Int, y: Int): Double? =
>     let quotient: Double? = x / y
>     if y == 0 then null else quotient
> ```
>
> `maybeDivLet(7, 0)` returns `null` as it should. The reason it "passes through" `let quotient: Double? = x / y` without a division-by-zero error is that `quotient` stays a thunk and is never forced — chapter 4 again. Both forms are safe, so the straightforward one, branching first, is normally enough.

Reading a field that may not be there (`?.`), landing on a default (`??`), and this "return null when there is nothing". With those three, null becomes an ordinary tool, guarded by the type system.

## 7.7 Choosing between Option[T] and T?

Why there are two similar tools, and how to choose.

| | `T?` | `Option[T]` |
| --- | --- | --- |
| how "nothing" is written | `null` | `None` |
| dedicated syntax | `??`, `?.`, narrowing in if/match | none (handled with `match` and functions) |
| fits | optional fields, parameters and results | the prelude's list API (`head`/`tail` return it), generic functions |
| nested "nothing" | inexpressible (`null` is one level) | `Some(None)` and `None` are distinct |

The practical rule: **use `T?` when "possibly absent" is part of the shape of your data** (record fields, parameters, results). **Use `Option` inside list processing and higher-order pipelines**, because that is the language the prelude speaks. At the boundary, a `match` converts between them.

> **Break it** — what happens if you swap the two arms of `orZero`, putting `| v -> v` first? Predict, then try.
>
> ```text,diagnostic
> lune> def swapped(value: Int?): Int =
> ...     match value:
> ...         | v -> v
> ...         | null -> 0
> ...
> error[TYP0003]: branch: expected Int, got Nullable[Int]
>   --> <repl:1>:3:16
>   |
> 3 |         | v -> v
>   |                ^ this expression has type Nullable[Int]
>    = help: run `lune explain TYP0003` for a detailed explanation
> ```
>
> Most people predict unreachability (`TYP0009`), but it is caught before that. The leading `v` is still an `Int?`, because null has not been covered yet (the caution in §7.2). The result annotation `Int` reaches it as an expected type (§7.6), and the first arm is named as unable to meet it. Narrowing works only when the null arm comes **first** — the order of the arms reaches all the way into the types.

## Summary

| Concept | In one line |
| --- | --- |
| `T?` | a `T` or `null`; displayed as `Nullable[T]` |
| what the type guards | using a `T?` as a `T` gives `TYP0003`; a missing null case gives `TYP0007` |
| `match` | once `\| null ->` is covered, later name patterns narrow to `T` |
| `??` | a default when null; the right side is not evaluated until needed |
| `?.` | short-circuits to null, otherwise reads the field; pairs with `??` |
| `if x != null` | narrows for the simple form only; use `match` when it gets complicated |
| returning null | expected types reach the branches, so plain `if`/`match` works (the mechanism of §5.6) |
| vs `Option` | `T?` for the shape of data, `Option` for lists and higher-order functions |

## Exercises

**Exercise 7-1** (★) Predict the result (value and type), then check. Take `absent: Int? = null` and `present: Int? = 42`.

```text
absent ?? 7
present ?? 7
absent == null
present ?? crash()
```

<details><summary>Answer</summary>

`7 : Int`, `42 : Int`, `true : Bool`, `42 : Int`. The last does not explode because `??` short-circuits. Check also that the type is `Int` and not `Int?`.

</details>

**Exercise 7-2** (★★) Rewrite §7.5's `orOne` with `match` instead of `if`.

<details><summary>Answer</summary>

```text
lune> def orOne(x: Int?): Int =
...     match x:
...         | null -> 1
...         | v -> v
...
ok
lune> orOne(null)
1 : Int
lune> orOne(41)
41 : Int
```

The same skeleton as `orZero`. Both the `if x != null` version and the `match` version are correct; the rule of thumb is `if` for two branches and `match` once there are more.

</details>

**Exercise 7-3** (★★) Following `nameOf`, write `ageOf`, and check that `ageOf(null) ?? 0` gives `0`.

<details><summary>Answer</summary>

```text
lune> def ageOf(user: User?): Int? =
...     user?.age
...
ok
lune> ageOf(User(name = "Ada", age = 36))
36 : Nullable[Int]
lune> ageOf(null) ?? 0
0 : Int
```

Follow the flow of types for "carry with `?.`, land with `??`" — `User? → Int? → Int` — with `:type` as well.

</details>

**Exercise 7-4** (★★★) Write `average(xs: List[Int]): Double?`, the average of a list of integers, with the average of the empty list being `null`. Can you write it without ever dividing by zero?

<details><summary>Answer</summary>

```lune
module answers

# Exercise 7-4: the average of an empty list does not exist. Branching first
# means never touching the division by zero.
def average(xs: List[Int]): Double? =
    if isEmpty(xs) then null else fold(xs, 0, fn a x -> a + x) / length(xs)

let some = average([2, 3, 4])

let none = average([])

let safe = average([]) ?? 0.0
```

```console
$ lune --eval some ex7-4.lune
3.0
$ lune --eval none ex7-4.lune
null
$ lune --eval safe ex7-4.lune
0.0
```

Branch on emptiness **first** and the division is only ever evaluated for a non-empty list. The `null` arm and the computing arm meet at `Double?` as in §7.6. Defining the sum and the division in annotated `let`s before branching also works, since they are discarded while still thunks (the "this works too" box in §7.6).

</details>

**Exercise 7-5** (★, in reverse) Write the smallest code that gets you told off by the type checker for using a possibly-null value without checking it.

<details><summary>Answer</summary>

```lune
let present: Int? = 42

let oops = present + 1
```

gives `error[TYP0003]: +: expected numeric type, got Nullable[Int]`. Passing it to a function (`wantsInt(present)` in §7.1) gives `expected Int, got Nullable[Int]`. The accident that would have been a runtime NullPointerException in another language has been replaced by this one line at compile time — that is what null safety is worth.

</details>

---

**More precisely** — the exact typing and narrowing rules for `T?` are in `documents/LANGUAGE_SPEC.md` §11 (null patterns in `match`) and §9.2 (narrowing in `if`); exhaustiveness with null is in `documents/MATCH_EXHAUSTIVENESS_SPEC.md`; the rule by which an expected type reaches the branches is in `documents/LOCAL_TYPE_INFERENCE_SPEC.md` §5.3. There are further examples in `samples/nullable.lune`. The code examples of this chapter live in `books/examples-en/ch07/` and are all verified against the real CLI.
