# Appendix A: Language Reference Manual

A normative list for Lune v0.1, readable independently of the main text. This is where you come to check "what was the rule again?"; why it is that way is in the chapters (and in appendix E).

The specifications in `documents/` are authoritative. This appendix draws on them, but the contents of the tables were either extracted mechanically from the implementation or confirmed by running them through the real compiler (see "Where this appendix comes from" at the end).

## A.1 Lexical structure

### Keywords

48 words are reserved. **Many of them are for the future and are syntax errors in v0.1** (see A.6).

```text
IO            abstract      as            catch         class         deepForce
def           elif          else          extends       false         final
finally       fn            for           force         if            implements
import        in            init          interface     internal      lazy
let           match         module        new           null          override
private       protected     public        raise         record        seq
static        strict        super         then          this          throw
throws        true          try           type          var           while
```

`break`, `continue`, `return`, `export` and `use` are **not reserved**. They are treated as ordinary identifiers, so writing one gives "undefined name" (`TYP0001`). See A.6.

### Identifiers

```text
IDENT_START = [A-Za-z_]
IDENT_PART  = [A-Za-z0-9_]
IDENT       = IDENT_START IDENT_PART*
```

A lone `_` is the wildcard pattern; `_name` is an identifier.

### Literals

| Kind | Example | Type |
| --- | --- | --- |
| integer | `42`, `1_000_000` | `Int` (arbitrary precision) |
| floating point | `3.14`, `1e-3` | `Double` |
| string | `"hello"` | `String` |
| character | `'x'` | `String` (see below) |
| boolean | `true`, `false` | `Bool` |
| null | `null` | `Null` |
| unit | `()` | `Unit` |
| list | `[1, 2, 3]` | `List[T]` |
| tuple | `(1, "a")` | `Tuple[Int, String]` |

The `_` in an integer literal is a digit separator and is ignored. The string escapes are `\n` `\r` `\t` `\\` `\"` `\'` `\0`.

> **A character literal does not give a character type** — `'x'` is a token of its own lexically, and anything other than exactly one character inside gives `LXL0002`. But **its type is `String`**. v0.1 has no character type (`Char`) and no standard library functions for characters. `let c: Char = 'x'` is treated exactly as a misspelled type name would be, giving `TYP0003`. `Char` belongs to the future specification (`LANGUAGE_FUTURE_SPEC.md`).

### Comments

```lune
# a line comment

###
a block comment (they do not nest)
###
```

`//` is **not a comment** — it is floor division (§2.2). `/* ... */` is not a comment either.

### Operator table

Highest precedence first. Operators on one line share a precedence.

| Precedence | Operators | Associativity |
| --- | --- | --- |
| 1 | `.` `?.` `()` `[]` | left |
| 2 | unary `!`, unary `-`, unary `+` | right |
| 3 | `*` `/` `//` `%` | left |
| 4 | `+` `-` | left |
| 5 | `::` `++` | right |
| 6 | `==` `!=` `<` `<=` `>` `>=` | non-associative |
| 7 | `&&` | left |
| 8 | `\|\|` | left |
| 9 | `??` | right |
| 10 | `\|>` | left |
| 11 | `=` `+=` `-=` `*=` `/=` `//=` `%=` | right |

**Non-associative** means they cannot be chained. What stops it is the type checker rather than the parser, though: `1 < 2 < 3` parses, and fails when the left operand of the second `<` turns out to be a `Bool` (`<: expected numeric type, got Bool`).

`::` and `++` exist in the parser but are out of practical scope for v0.1's type checking and evaluation.

## A.2 Layout rules

Blocks are expressed by indentation. Only **spaces** may begin a line; a tab gives the lexical error `LXL0004` (tabs are not allowed in indentation). The caret points at the tab itself, so you can see where it crept in.

```text,diagnostic
error[LXL0004]: tabs are not allowed in indentation
  --> tabs.lune:4:1
  |
4 | 	1
  | ^ use spaces for indentation
   = hint: replace tabs with spaces
```

Blank lines and comment-only lines are **not subject to the indentation check** (see the rules below), so a tab in one of those is not reported. Nor are tabs inside strings or after the code on a line.

After lexing, layout processing produces `NEWLINE` / `INDENT` / `DEDENT`.

- Compare the width `n` of the leading whitespace with the top of the indentation stack, `top`.
- `n == top` → emit only `NEWLINE`.
- `n > top` → emit `INDENT` and push `n`.
- `n < top` → emit `DEDENT` until a matching value appears. If none matches, an indentation error (`LAY0001`).
- At end of file, emit `DEDENT` until the stack is empty, then `EOF`.

**No layout tokens are produced inside brackets.** `(` `[` `{` increase the depth by one and `)` `]` `}` decrease it, and while the depth is above zero a physical newline is just whitespace. That is why you may break lines freely inside brackets.

```lune
let xs = [
    1,
    2,
]
```

For constructs that expect a block after `:` (`if`, `while`, `for`, `match`, `record` and so on), the next significant tokens must be `NEWLINE INDENT`. After `=`, either one line or a block is allowed.

```lune
def f(): Int = 1

def g(): Int =
    1
```

Multi-line input in the REPL continues while a line ends in `=`, `:` or `->`, and finishes at a blank line (appendix D).

## A.3 Grammar

Below, `NL` means one or more `NEWLINE`s. The complete EBNF is in §5–§10 of `documents/LEXER_PARSER_SPEC.md`; this is the skeleton drawn from it.

### Files and declarations

```ebnf
file        ::= NL* module_decl? import_decl* top_decl* EOF
module_decl ::= "module" qualified_name NL+
import_decl ::= "import" qualified_name ("as" IDENT)? NL+
qualified_name ::= IDENT ("." IDENT)*

top_decl    ::= function_decl | type_decl | record_decl | let_decl | var_decl

function_decl ::= "def" IDENT type_params? "(" params? ")" (":" type)? "=" body
let_decl      ::= ("strict" "let" | "let") pattern (":" type)? "=" body
var_decl      ::= "var" IDENT (":" type)? "=" body
type_decl     ::= "type" IDENT type_params? "=" NL INDENT constructor+ DEDENT
record_decl   ::= "record" IDENT type_params? ":" NL INDENT field+ DEDENT

constructor   ::= "|" IDENT ("(" ctor_fields? ")")? NL
ctor_fields   ::= ctor_field ("," ctor_field)*
ctor_field    ::= ("strict" | "!")? IDENT ":" type
field         ::= ("strict" | "!")? IDENT ":" type NL
params        ::= param ("," param)*
param         ::= ("strict" | "!")? IDENT ":" type
type_params   ::= "[" IDENT ("," IDENT)* "]"
body          ::= expr | NL INDENT block DEDENT
```

### Expressions

Expressions are parsed with a Pratt parser. The precedences are those in A.1.

```ebnf
expr    ::= assign
assign  ::= pipeline (assign_op assign)?
primary ::= literal | IDENT | "(" expr ")" | list | tuple
          | if_expr | match_expr | lambda | block_expr
          | "lazy" expr | "force" expr | "deepForce" expr
          | "seq" expr expr | "while" expr ":" block | "for" pattern "in" expr ":" block
          | "IO" ":" block | "raise" expr

if_expr    ::= "if" expr ":" NL INDENT block DEDENT elif* else?
             | "if" expr "then" expr "else" expr
match_expr ::= "match" expr ":" NL INDENT match_case+ DEDENT
match_case ::= "|" pattern ("if" expr)? "->" body NL
lambda     ::= "fn" lambda_param* "->" body
list       ::= "[" (expr ("," expr)* ","?)? "]"
tuple      ::= "(" expr "," expr ("," expr)* ")"
```

Building a `record` is a special form of call syntax in which **field names are required** (`User(name = "Ada", age = 36)`). Functions and ADT constructors are called positionally (naming them gives `TYP0012`).

### Patterns

```ebnf
pattern ::= "_"                       # wildcard
          | "null"                    # null
          | IDENT                     # name binding
          | literal                   # literal
          | "(" pattern ("," pattern)+ ")"      # tuple
          | IDENT "(" pattern ("," pattern)* ")" # constructor
          | pattern "|" pattern       # or pattern
          | pattern ":" type          # with a type annotation
```

The pattern of a `let` must be **irrefutable**. `let Some(x) = ...` gives `TYP0008` (use `match`).

## A.4 Types

### Basic types

```text
Bool  Int  Double  String  Unit  Any  Nothing  Null
```

`Int` is arbitrary precision. `Nothing` is the type with no values (the result type of `crash()`).

**That is all of the basic types.** `Long`, `Float` and `Char`, which other languages might lead you to expect, do not exist in v0.1. There is one integer type, `Int` (arbitrary precision, so there is no reason to separate a `Long`), one fractional type, `Double`, and characters are `String`. Writing one in a type annotation is treated exactly as a misspelled type name, giving `TYP0003`.

### Compound types

```text
Option[Int]        Result[Int, String]     List[Int]
Lazy[Int]          IO[String]              Tuple[Int, String]
String?
```

`T?` is `Nullable[T]` in the AST and in type representations.

### Function types

The curried notation is canonical, and `->` is **right-associative**.

```text
Int -> Int
Int -> Int -> Int
```

`(Int, Int) -> Int` is treated as sugar for `Int -> Int -> Int`. A function taking one tuple is written `Tuple[Int, Int] -> Int`.

### Null safety

Both `null` and a non-null `T` can be passed where a `T?` is wanted, but **`null` cannot be passed where a non-null type is wanted, and a `T?` cannot be used as-is where a `T` is required**. The ways to unwrap:

| Means | Written as |
| --- | --- |
| a null pattern in `match` | `\| null -> …`; once covered, later names narrow to non-null |
| null coalescing | `a ?? b` (`b` if `a` is null; short-circuits) |
| safe navigation | `x?.m` (short-circuits to null; the result is nullable) |
| flow narrowing | in the branch of `if x != null:`, `x` is a `T` |

Narrowing applies only to the simple `if x != null` / `if x == null` where `x` is a variable. Narrowing through compound conditions (`&&` and so on), `elif` or `while`, and a `!!` assertion operator, do not exist yet.

### Local type inference

Parameters of a `def` require type annotations. The result type may be omitted (but is **required for a recursive function** — `TYP0011`).

An unannotated lambda parameter takes its type from the context. The contexts are the type annotation of a `let` or `var`, the result annotation of a `def`, and the argument position of a call.

```lune
let inc: Int -> Int = fn x -> x + 1          # x : Int
let doubled = map([1, 2, 3], fn x -> x * 2)  # x : Int
```

Without a context it falls back to `Any` with the warning `TYP0010`.

## A.5 Evaluation

Lune is **lazy by default**.

### What is lazy

- the right-hand side of an ordinary `let`
- ordinary function arguments
- ordinary constructor fields
- ordinary record fields
- the body of `lazy expr`

### Where evaluation happens

- a variable reference
- `force` / `deepForce`
- the first argument of `seq`
- the condition of an `if`, and of a `while`
- the operands a binary operation needs
- the outer constructor of a `match` scrutinee
- comparison against a literal pattern
- strict parameters (`!x: Int` / `strict x: Int`)
- `strict let` (and `!let`, which is the same)
- strict constructor fields and strict record fields

### Memoisation

A thunk memoises **both success and failure**. Forcing a thunk that has failed once produces the same error again (the computation is not repeated).

**Re-entrant evaluation is a runtime error** (`RUN0005`). A value that depends on its own result, such as `let x = x + 1`, comes back to itself the moment it is forced, so it is reported on the spot rather than waited on (§4.7).

Running `--check` on `let x = x + 1` reports `TYP0001` (undefined name `x`) instead, because the `x` on the right is resolved before that `let` enters the environment. `RUN0005` appears when `--eval` actually forces it — an example of the same code producing different diagnostics at the checking and running stages.

The instruments for observing this are `:thunks` (state without evaluation) and `:trace` / `--trace` (a commentary on forcing). See chapter 4 and appendices B and D.

## A.6 Not supported in v0.1

Some things are reserved as keywords but do not work yet. **What comes back is listed alongside**, so that you can look it up from the diagnostic code.

| What you wrote | The diagnostic |
| --- | --- |
| `class` | `PRS0001` expected top-level declaration, got CLASS |
| `interface` | `PRS0001` expected top-level declaration, got INTERFACE |
| `new Foo()` | `TYP0003` unsupported expression: NewExpr |
| `this` / `super` | `TYP0003` unsupported expression: ThisExpr |
| `try` / `catch` / `finally` | `PRS0001` expected expression, got TRY |
| record update `r { x = 2 }` | `PRS0001` (LBRACE) |
| record pattern `R { x }` | `PRS0002` expected ARROW, got LBRACE |
| mutable record field `var x: Int` | `PRS0002` expected IDENT, got VAR |
| annotation `@inline` | `PRS0001` (AT) |
| `throws` | `PRS0002` expected ASSIGN, got THROWS |
| `import a.b.{C, D}` | `PRS0002` expected IDENT, got LBRACE |
| ADT field access `c.v` | `TYP0003` unsupported member access |

**Not even reserved** — `break`, `continue`, `return`, `export` and `use` are not keywords, so they are taken for ordinary identifiers and give `TYP0001` (undefined name). To leave a loop early, weave the condition into the loop condition (§9.3).

Outside the language itself, these are not supported: JVM bytecode generation, calling real Java libraries, `Stream` / `Map` / `Set` / `Promise` / `Iterator`, a package manager, and an LSP server.

What the future is supposed to look like is in `documents/LANGUAGE_FUTURE_SPEC.md`. Why v0.1 was cut at this scope is in appendix E.

## Where this appendix comes from

| Section | Source |
| --- | --- |
| A.1 keywords | generated from `KEYWORDS` in `lune/tokens.py` (48 words) |
| A.1 operator table | §14 of `documents/SYNTAX_SPEC.md`; the infix part cross-checked against `INFIX` in `lune/parser.py` |
| A.1 literals | each literal run through the REPL to confirm its type |
| A.2 layout | §3 of `documents/LEXER_PARSER_SPEC.md` |
| A.3 grammar | the skeleton extracted from the EBNF of §5–§10 of the same |
| A.4 types | §6 and §8 of `documents/LANGUAGE_SPEC.md` |
| A.5 evaluation | §17 of the same |
| A.6 unsupported | §21 of the same. **Every entry was run through `--check` and the diagnostic recorded** |

Writing it turned up two places where the specification and the implementation disagreed. Both have been resolved.

`LXL0004` (tabs in indentation) was fixed **in the implementation** — the diagnostic existed, but the indentation width was measured by counting leading spaces only, which left it impossible to produce.

The type of a character literal was fixed **in the specification**. `LANGUAGE_SPEC.md` listed `Char` as a basic type, but the implementation has neither an expression that produces one nor any function that handles characters. `Char` was removed from v0.1 and became a type of the future specification.
