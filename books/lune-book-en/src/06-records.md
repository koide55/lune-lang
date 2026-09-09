# Chapter 6: Records

A tuple (chapter 2) bundles values, but only the person who wrote `(36, "Ada")` knows whether the 36 is an age or a squad number. When you want to bundle values **with names**, you want a **record**. Where the ADT of chapter 5 expresses "exactly one of these" (a sum), a record expresses "all of these at once" (a product), with names.

## 6.1 Declaring and building — building by name

```lune
record User:
    name: String
    age: Int
```

Just list the field names and their types. Building one **always names the fields**.

```text
lune> let ada = User(name = "Ada", age = 36)
ok
lune> ada
{ name = "Ada", age = 36 } : User
```

The display is `{ field = value }` too. Passing by position is not allowed.

```text,diagnostic
lune> User("Ada", 36)
error[REC0006]: User requires named record fields
  --> <repl:4>:1:6
  |
1 | User("Ada", 36)
  |      ^^^^^ use field = value
   = help: run `lune explain REC0006` for a detailed explanation
```

This is the opposite of an ADT constructor, which takes its fields by position (chapter 5). Records tend to grow fields, and as long as the types match, neither machine nor human can tell what the 36 in `User("Ada", 36)` is — hence the design decision to insist on names. In return, every mistake around building is reported by name: `REC0003` when a field is missing, `REC0005` when the name is not declared, `REC0004` when the same name is given twice.

## 6.2 Field access and laziness

Read a field with `.`.

```text
lune> ada.name
"Ada" : String
lune> ada.age + 1
37 : Int
```

did-you-mean covers typos here too. From `typofield.lune`:

```console
$ lune --check typofield.lune
```

```text,diagnostic
error[REC0002]: unknown record field: User.nmae
  --> typofield.lune:9:12
  |
9 | let oops = ada.nmae
  |            ^^^ field is not declared by this record
   = hint: did you mean `name`?
   = help: run `lune explain REC0002` for a detailed explanation
```

And after chapter 4 you can guess the rest — **fields are lazy too**.

```text
lune> let ghost = User(name = "Ghost", age = crash())
ok
lune> ghost.name
"Ghost" : String
lune> :thunks ghost
ghost : evaluated = { name = "Ghost", age = <thunk> }
```

`name` was read quite happily with a landmine sitting in `age`. In the `:thunks` preview, the untouched field is still showing as `<thunk>`.

Put `strict` on a field you want evaluated at construction.

```text
lune> record Tagged:
...     strict tag: Int
...     note: String
...
ok
lune> let t = Tagged(tag = crash(), note = "n")
ok
lune> t.note
error[RUN0006]: crash() was evaluated
   = help: run `lune explain RUN0006` for a detailed explanation
```

Reading `note` set off the mine in `tag`. The record is constructed the moment `t` is first forced, and that is when strict fields are evaluated. "Never let a record holding an invalid value exist" — the design tool promised in chapter 4.

## 6.3 Generic records

Records take type parameters, written as for the ADTs of chapter 5.

```text
lune> record Box[T]:
...     value: T
...
ok
lune> Box(value = 42)
{ value = 42 } : Box[Int]
```

`T = Int` was inferred from the field's value. Functions can take type parameters too (exercise 6-3 builds a `swap` whose types swap with it).

## 6.4 Choosing between tuples, ADTs and records

Three tools for grouping values. To put them side by side:

| Tool | Suits | Example |
| --- | --- | --- |
| tuple | two or three values, here and now, not worth naming | the result of a `zip`, `(quotient, remainder)` |
| record | the same shape used repeatedly; the fields need names | `User`, configuration, a computed summary |
| ADT | there are alternatives, exactly one of which holds | `Shape`, `Option`, a state |

Combining them is the norm. Here is a list of records processed with the tools we have had since chapter 1, in `items.lune`:

```lune
module items

record Item:
    name: String
    price: Int

let items = [Item(name = "pen", price = 120), Item(name = "note", price = 200)]

let total = fold(map(items, fn i: Item -> i.price), 0, fn a x -> a + x)
```

```console
$ lune --eval total items.lune
320
```

"From a list of records, pull out a field with `map` and collapse it with `fold`" — the backbone of a working Lune program.

## 6.5 What is not there yet — update and patterns

v0.1's records are missing two features that neighbouring languages have.

There is no **record update** (a "copy with one part changed", as in `{ ada | age = 37 }`), so a new value is built by writing every field. There is no **record pattern** either, so a record cannot be destructured in a `match`.

```text,diagnostic
lune> match ada:
...     | { name = n } -> n
...
error[PRS0001]: expected pattern, got LBRACE
  --> <repl:12>:2:7
  |
2 |     | { name = n } -> n
  |       ^ unexpected token
   = help: run `lune explain PRS0001` for a detailed explanation
```

Read what you need out of a record with `.`, and branch with `if`/`match` on the field's value. Both features are in the future specification (appendix E).

> **Break it** — produce the record-building diagnostics `REC0003` (missing field), `REC0004` (the same field twice) and `REC0005` (unknown field) one at a time with `User`. Check that each is reported by name, on the construction expression. Of the code families in chapter 11, `REC` has its home ground in this chapter.

## Summary

| Concept | In one line |
| --- | --- |
| `record R:` plus field declarations | a named product; building requires `R(field = value)` |
| `r.field` | reading a field; a typo gives `REC0002` plus did-you-mean |
| laziness of fields | lazy by default; `strict field: T` evaluates at construction |
| `record Box[T]:` | a generic record |
| choosing | ad-hoc group → tuple / named product → record / one of several → ADT |
| not supported | record update, record patterns (read with `.`) |

## Exercises

**Exercise 6-1** (★) Break the construction of `User` in three ways to produce `REC0003`, `REC0005` and `REC0006` (predict first which break gives which code).

<details><summary>Answer</summary>

`User(name = "X")` → `REC0003` (`age` is missing), `User(name = "X", years = 1)` → `REC0005` (`years` is not a declared name), `User("X", 36)` → `REC0006` (built without names). While you are there, `User(name = "X", name = "Y", age = 1)` gives `REC0004`.

</details>

**Exercise 6-2** (★★) From the items of `items.lune`, build a list of **just the names** of those costing 150 or more.

<details><summary>Answer</summary>

```lune
module answers

# Exercise 6-2: take just the names of the items costing 150 or more.
record Item:
    name: String
    price: Int

let items = [Item(name = "pen", price = 120), Item(name = "note", price = 200)]

let pricey = map(filter(items, fn i: Item -> i.price >= 150), fn i: Item -> i.name)
```

```console
$ lune --eval pricey ex6-2.lune
("note")
```

Narrow with `filter`, then pull out with `map`. The other order (names first) throws the price away and leaves nothing to filter on — the order of a pipeline is decided by how long each piece of information has to live.

</details>

**Exercise 6-3** (★★) Write a generic record `Pair[A, B]` (`first: A`, `second: B`) and a `swap` that exchanges the two. Note that the result type of `swap` is `Pair[B, A]`.

<details><summary>Answer</summary>

```lune
module answers

# Exercise 6-3: a generic record, and a swap whose types swap with it.
record Pair[A, B]:
    first: A
    second: B

def swap[A, B](p: Pair[A, B]): Pair[B, A] =
    Pair(first = p.second, second = p.first)

let swapped = swap(Pair(first = 1, second = "a"))
```

```console
$ lune --eval swapped ex6-3.lune
{ first = "a", second = 1 }
```

The type arguments of `Pair(first = p.second, ...)` are inferred from the values passed, so nothing needs writing on the construction side.

</details>

**Exercise 6-4** (★★★) Build both §6.2's `Tagged` (with a strict `tag`) and an identical record without `strict`, put `crash()` in `tag` for each, and explain the difference in behaviour, using `:thunks` as well.

<details><summary>Answer</summary>

Without `strict`, `l.note` returns `"n"` and `:thunks l` shows `{ tag = <thunk>, note = ... }` — the mine is harmless until touched. With `strict`, `t.note` already gives `RUN0006`, because forcing `t` runs the record's construction and construction evaluates the strict fields. The chapter 4 principle, "lazy by default plus explicit strictness", appears here directly as a data design tool.

</details>

---

**More precisely** — the syntax, typing and laziness rules of records are in `documents/RECORD_FIELD_SPEC.md` (which states in §7 and §6 that update and patterns are future work). The code examples of this chapter live in `books/examples-en/ch06/` and are all verified against the real CLI.
