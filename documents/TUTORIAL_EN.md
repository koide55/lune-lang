# Lune Tutorial — merged into the book

This tutorial (20 chapters) has been merged into the textbook, *The Lune Programming Language*.

**→ [The Lune Programming Language](https://koide55.github.io/lune-lang/book/en/)**
([single-file PDF](https://koide55.github.io/lune-lang/book/en/lune-book.pdf), sources in [books/](../books/README.md))

**If what you want is one short lap, read just chapter 1 of the book.** An hour gets you as far as writing, running and breaking a program — which is what this tutorial was for.

## Where everything went

| What you read here | Where it is in the book |
| --- | --- |
| 1. First steps | Chapter 1: A Gentle Tour |
| 2–6. Laziness, thunks, memoisation | **Chapter 4: Lazy Evaluation — the Heart of Lune** (watching evaluation with `:thunks` and `:trace`) |
| 7. `fn` and partial application | Chapter 3: Functions |
| 8–9. ADTs and pattern matching | Chapter 5: Algebraic Data Types and Pattern Matching |
| 10. Records | Chapter 6: Records |
| 11. null | Chapter 7: Null Safety |
| 12. The standard library | Appendix B: Standard Library Reference (all 41 names) |
| 13–14. `while` and `for` | Chapter 9: Writing Imperatively |
| 15. Modules | Chapter 10: Modules |
| 16. Type checking and tools | Chapter 12: The REPL, Formatting and Checking |
| 17. Reading errors, learning from errors | Chapter 11: Talking to the Compiler |
| 18. A small program | Chapter 13: Building a Program — Case Studies |
| 19. Exercises | The exercises at the end of every chapter (96 of them, with answers) |
| 20. Current limitations | Appendix A.6: Not supported in v0.1 |

Infinite lists and streams (chapter 8), a worked multi-file program, and the design rationale (appendix E) are new in the book.

## Why it was folded away

Because the same material was being maintained in two places. Before folding it, the two were compared: **there was no language feature, diagnostic code, REPL command or standard library function that the tutorial had and the book did not** (the book touches 34 diagnostics and lists all 41 prelude names). What remained was that the tutorial was in English and that it was short — and the first is now answered by this English edition, the second by "read chapter 1".

This file is kept as a signpost because URLs pointing at it still exist (in the description already published on PyPI, for instance). The content itself remains in the git history.
