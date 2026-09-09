# Index

**The index with page numbers is in the PDF edition.** HTML has no such thing as a page,
so in this edition use these three instead.

- **The search above** (the magnifying glass, or the `s` key) — full text search. For
  looking a term up, this is the fastest.
- **The sidebar on the left** — follow the chapters and their sections.
- **The appendices** — each is itself the complete list for one subject.

| What you want to look up | Where to look |
| --- | --- |
| grammar, keywords, operators, types, evaluation rules | [Appendix A: Language Reference Manual](appendix-a-reference.md) |
| the prelude's functions (all 41, with types and examples) | [Appendix B: Standard Library Reference](appendix-b-stdlib.md) |
| the diagnostic codes (all 30) | [Appendix C: The Diagnostic Codes](appendix-c-diagnostics.md) |
| the CLI and REPL commands | [Appendix D: CLI and REPL Command Reference](appendix-d-cli.md) |
| why it is designed this way | [Appendix E: The Design of Lune, and What Comes Next](appendix-e-design.md) |

In the PDF edition (built by `books/tools/build_pdf.sh`), this page is replaced by a list of
terms and page numbers. The index terms are defined as `CONCEPTS_EN` in
`books/tools/book_pages.py`, and the page numbers are measured from the assembled PDF.
