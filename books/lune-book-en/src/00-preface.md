# Preface: Welcome to Lune

A sheet of paper is pinned to the wall of the after-school clubroom:

> **Club motto: don't do it until you need to. Once done, never forget it.**

You join expecting an easy club, and then you are told that the motto is about
evaluation strategy — that is the opening scene in this language's repository.
This book is what comes next.

Everything the club teaches is collected here, so that you can learn it without
coming to the clubroom. The senior members do not appear in these pages, but
**the compiler plays every one of their parts**.

## What Lune is — Lazy and Native

Start with the name.

**Lazy** is the evaluation strategy. A value in Lune is not computed until it is
needed. Writing `let` makes nothing happen; the language waits until the moment
the value is actually used. Once computed, it remembers, and never computes it
again. Exactly the motto.

**Native** is not native code. It is **native language**. Lune's compiler
explains itself in the language you think in.

```console
$ lune --check guide.lune
error[TYP0001]: undefined name: cont
  --> guide.lune:2:13
  |
2 | let total = cont + 5
  |             ^^^^ name is not defined
   = hint: did you mean `count`?
   = help: run `lune explain TYP0001` for a detailed explanation
```

This edition shows English, which is what Lune prints by default. Run
`lune --check --lang ja` and the same compiler says the same thing in Japanese,
down to the hint. That switch is the point of the design: the effort of decoding
an error message in a foreign language should go into learning to program
instead. It is easy to forget that this is a cost at all when the messages
already happen to be in your language.

## The attitude of this book — errors are teaching material

One line from the club president, borrowed just once:

> **In this club, an error is not a failing grade. It is teaching material.**

That is a design decision rather than a nice turn of phrase. Every Lune
diagnostic carries three things: **what happened**, **where it happened**, and
**what to do next**. In the example above, `^^^^` gives the place, `= hint:`
gives the next move, and `= help:` points at a longer explanation.

All 30 diagnostic codes come with one — what it means, the smallest example
that reproduces it, and how to fix it. Type `lune explain TYP0001` to read it.
**An error number is not something to memorise; it is a key to look things up
with.**

So this book produces errors on purpose. Every chapter has a **Break it** box.

> **Break it** — type `1 + true` into the REPL. What comes back?
>
> ```text,diagnostic
> lune> 1 + true
> error[TYP0003]: +: expected Int, got Bool
>    = help: run `lune explain TYP0003` for a detailed explanation
> ```

If you got an error, it worked. **An error means you got it right.**

## How to read this book

**Read it with a REPL open.** This is the one request that matters most.

```console
$ lune
Lune v0.1.0 REPL. Type :help or :quit.
lune>
```

If installing is a nuisance, there is a
[Playground](https://koide55.github.io/lune-lang/playground/) that runs in the
browser — the actual implementation, running inside the page, with nothing to
install. It has a REPL too. Every complete example in this book has an
**Open in the Playground** link under it.

Every output printed in this book was **taken from a real run of the
implementation**. You will get the same thing. If you do not, either this book
is wrong or you have found something interesting.

- **Part I (chapter 1)** — one lap around the language. Rules come later; here
  you write, run, and break things.
- **Part II (chapters 2–10)** — the language itself. Values and types,
  functions, **lazy evaluation (chapter 4)**, algebraic data types and `match`,
  records, null safety, lists and streams, imperative code, modules.
- **Part III (chapters 11–13)** — the compiler and the tools. Reading
  diagnostics, the REPL and the formatter, and case studies that put it
  together.
- **Appendices A–E** — the reference half. Grammar, standard library, the
  diagnostic catalogue, the CLI and REPL, and the design rationale.

In a hurry? Chapter 1 → chapter 4 → chapters 2 and 3 → chapter 5 → chapter 8
still reaches the core of the language. **Chapter 4 (lazy evaluation) is what
this language is for**, so do not skip it: with `:thunks` and `:trace` you get
to watch evaluation happen.

The exercises come with answers, folded up directly beneath each question.
Think first, then open.

## What you need to know already

If you have written variables, functions and conditionals in some programming
language, that is enough. No functional programming experience is required. You
do not need to know what lazy evaluation is — chapter 4 is more fun if you
don't.

---

Have a good club session.

Open the REPL and type `1 + 2`. Chapter 1 starts there.
