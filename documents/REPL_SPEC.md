# Lune REPL 仕様

Version: 0.1 draft  
Related: `LANGUAGE_SPEC.md`, `TYPE_CHECKER_SPEC.md`, `LAZY_EVALUATION_SPEC.md`, `ERROR_DIAGNOSTICS_SPEC.md`

## 1. 目的

Lune v0.1 REPL は、lexer/parser/typechecker/evaluator を対話的に試すための開発用 REPL である。

目標:

- 入力ごとに型チェックしてから評価する。
- `let`、`def`、`type` 宣言をセッション内に保持する。
- 式を入力した場合は値と型を表示する。
- 遅延評価の挙動を観察できる。

### 1.1 起動と既定言語

REPL は次のいずれでも起動する。

```sh
lune --repl
lune                # ファイル・サブコマンドなし
lune --lang ja      # グローバル --lang のみ → REPL にフォールバック
```

グローバルフラグ（`--lang`）を取り除いた後に引数が残らない場合、CLI は REPL 起動にフォールバックする。

起動時に版番号を含む1行を stdout に出す。版番号の出処は `lune/__init__.py` の `__version__` ひとつで、`lune --version` と同じ値である（`LANGUAGE_SPEC.md` §19）。

```text
Lune v0.1.0 REPL. Type :help or :quit.
```

### 1.2 import

REPL の `import` はファイルモジュールを実際に読み込む（`MODULE_LOADING_SPEC.md` §11）。探索ルートは**起動時の作業ディレクトリ**と `--module-path` で、REPL には入口ファイルが無いため前者がその役割を担う。

```text
$ lune --repl --module-path lib
lune> import math
ok
lune> add(1, 2)
3 : Int
```

読み込んだモジュールのトップレベル名はセッションに残り、`:env` にも現れる。同じモジュールを二度 `import` しても再登録はしない。解決に失敗すれば `MOD0001`、巡回は `MOD0002`、`module` 宣言名の不一致は `MOD0003` で、いずれもファイルを実行したときと同じ診断である。

診断メッセージの既定言語は次の優先順位で決まる（`ERROR_DIAGNOSTICS_SPEC.md` §4.2）。

1. `--lang en|ja` フラグ
2. 環境変数 `LUNE_LANG`（`en`/`ja`。不正値は `en` に落とす）
3. 既定は `en`

REPL セッションの初期言語もこれに従い、`:lang` コマンドでセッション中に切り替えられる。常に日本語で使うにはシェルの設定に `export LUNE_LANG=ja` を書けばよい。

## 2. セッション状態

REPL セッションは 2 つの環境を保持する。

```text
typeEnv
evalEnv
```

各入力は同じ環境に追加される。たとえば:

```lune
let x = 40
x + 2
```

2 行目は 1 行目の `x` を参照できる。

### 2.1 後から定義される名前（前方参照）

REPL のセッションは「1 入力ずつ書き足していく 1 つのファイル」として扱う。トップレベルの `let` と `def` は遅延束縛なので、ファイルでは `def greet(...): String` より上に `let main = greet("world")` を書ける。REPL でも同じ順で入力できる。

```text
lune> let main = println(greet("world"))
ok
   = note: `greet` is not defined yet; `main` will be checked once it is
lune> :thunks main
main : unevaluated
lune> :type main
main : ? (waiting for greet)
lune> def greet(name: String): String =
...     "hello, " + name
...
ok
   = note: `main` is now checked: Unit
lune> main
hello, world
() : Unit
```

- **待てる入力**: 宣言がすべて遅延束縛（名前パターンの `let` と `def`）で、未定義の名前がセッションにまだ無いとき。束縛そのものはその場で評価環境に入る（thunk か closure なので何も実行されない）。型検査だけを、待っている名前が定義されるまで保留する。
- **待てない入力**: `strict let`・`var`・パターン `let` はその場で評価されるので、式入力と同じく従来どおり `TYP0001` になる。セッションが既に知っている名前に対する型エラーも前方参照ではないので、そのままエラーになる。
- **待っている名前を使う**: 待っている名前を式などで使うと、待っている先の名前についての元の `TYP0001` が、それを書いた入力の位置で表示される。ヒントに「`main` は `greet` の定義を待っています」と出る。何も force されないので、thunk は未評価のまま残る。
- **解決**: 入力が名前を束縛するたびに、その名前を待っていた束縛の型検査をやり直す。解決した束縛が別の束縛の待ち先なら、それも続けて解決する（`a` → `f` → `g` の連鎖は `g` の入力 1 つで片付く）。
- **相互再帰**: 2 つの入力に分けた `isEven` と `isOdd` のように、待っている束縛を使う宣言入力は、待っている入力と合わせて 1 つのファイルとして検査する（待っている側が先、入力した順）。
- **前方参照できる範囲はファイルと同じ**: ファイルで定義より前に使えるのは、戻り値型を書いた `def` とコンストラクタだけである（`LOCAL_TYPE_INFERENCE_SPEC.md`）。待っていた名前が `let`・`var`・戻り値型のない `def` で定義された場合、待っていた束縛はファイルと同じ `TYP0001` で失敗する。やり直しの検査では、待っている入力より後に定義された `let` などは見えない。
- **失敗**: 待ち先が定義されても型検査に失敗した束縛は、その入力の警告としてエラーを 1 度だけ表示する。以後は `? (failed: CODE)` となり、使うとその診断が出る。待ち先の名前を定義し直すと、もう一度検査する。同じ名前を定義し直すと、待っていた束縛は破棄される。
- `:type NAME` と `:env` は、待っている名前を `? (waiting for X)`、失敗した名前を `? (failed: CODE)` と表示する。

## 3. 入力の分類

REPL は入力を次の順で解釈する。

1. 宣言またはモジュール断片としてパースする。
2. 失敗した場合、式として扱い `let __repl_value = expr` に包んでパースする。

式入力は内部的にトップレベル `let` として評価されるが、表示上は式の値として扱う。

## 4. 表示

宣言入力:

```text
ok
```

式入力:

```text
value : Type
```

値の表示形式は `VALUE_DISPLAY_SPEC.md` に従う。代表例:

```text
lune> "Ada"
"Ada" : String
lune> [1, 2, 3]
(1 2 3) : List[Int]
```

例:

```text
lune> 1 + 2
3 : Int
```

## 5. コマンド

v0.1 でサポートするコマンド:

```text
:help
:quit
:q
:env
:type NAME
:thunks [NAME]
:trace [on|off]
:lang [en|ja]
:explain CODE [en|ja]
```

- `:help`: コマンド一覧を表示する。
- `:quit` / `:q`: REPL を終了する。
- `:env`: 現在のトップレベル名と型を表示する。型検査を保留している名前は末尾に `? (waiting for X)` / `? (failed: CODE)` で並ぶ（§2.1）。
- `:type NAME`: 指定名の型を表示する。保留中の名前は `:env` と同じ形で表示する。
- `:thunks [NAME]`: 遅延束縛（thunk）の評価状態を、**評価を一切起こさずに**表示する。NAME を省略すると全 thunk を定義順に一覧する。
- `:trace [on|off]`: 遅延評価トレースの有効/無効を切り替える（引数なしで現在の状態を表示）。有効な間、式の評価で**いつ・どの thunk が force されたか**を入れ子の深さ付きで表示する（§5.2）。
- `:lang [en|ja]`: 診断メッセージと `:explain` の言語を切り替える（引数なしで現在の言語を表示）。
- `:explain CODE [en|ja]`: 診断コードの詳解を表示する（`lune explain CODE` と同じ内容、`ERROR_DIAGNOSTICS_SPEC.md` §4.1）。言語を省略すると英語。`ja` で日本語の詳解を表示する。

### 5.1 `:thunks` の表示

各束縛は次のいずれかの状態で表示される（`LAZY_EVALUATION_SPEC.md` の thunk 状態に対応）。

```text
x   : unevaluated                    # まだ一度も force されていない
x   : evaluated = 2                  # メモ化済み（値を表示）
x   : failed = division by zero      # 失敗もメモ化される
v   : value = 7                      # thunk ではない（:thunks NAME 指定時のみ）
```

値の表示は専用の非強制プレビューを使う。値の中の未評価部分は `<thunk>` と表示されるため、無限ストリームでも安全で、**どこまで評価が進んだか**がそのまま見える。

```text
lune> let nat = naturalsFrom(1)
ok
lune> head(nat)
Some(1) : Option[Int]
lune> :thunks nat
nat : evaluated = Cons(1, <thunk>)
```

### 5.2 `:trace` の表示

トレースが有効な間、式の評価は次のイベントを入れ子の深さ付きで表示する。

```text
force <式>       # thunk の評価に入った
=> <値>          # その評価が完了した（対応する force と同じ深さ）
memo <式> => <値> # force がメモ化済みの結果に当たった（再評価なし）
```

式は正準フォーマッタで一行に整形し、値は §5.1 と同じ非強制プレビューで表示する。宣言（`let` など）は遅延されるため、トレースには何も現れない — それ自体が遅延評価の教材になる。

```text
lune> :trace on
trace on
lune> let x = 1 + 1
ok                       # 宣言では何も評価されない
lune> x + 1
force x + 1
  force 1 + 1
  => 2
=> 3
3 : Int
lune> x
force x
  memo 1 + 1 => 2        # 2 回目はメモ化された値を再利用
=> 2
2 : Int
```

CLI では `lune --eval NAME --trace FILE` で同じトレースを stderr に出力する。

## 6. 複数行入力

v0.1 の対話 REPL は簡易的な複数行入力をサポートする。

- 入力行が `:`、`=`、`->` で終わる場合、継続プロンプトへ移る。
- 継続中は空行で入力を確定する。

例:

```text
lune> def add(x: Int, y: Int): Int =
...     x + y
...
ok
```

## 7. 行編集と履歴

端末上で `--repl` を起動した場合、REPL は readline 互換の行編集を有効にする。

想定する操作:

- 左右矢印によるカーソル移動。
- 上下矢印による履歴移動。
- Backspace / Delete。
- `Ctrl-A` / `Ctrl-E` など readline の基本操作。

履歴は可能なら `~/.lune_history` に保存する。

標準入力が pipe やテスト用 stream の場合、行編集は有効化せず、従来どおり 1 行ずつ読み込む。

## 8. エラー

型エラー、構文エラー、実行時エラーは REPL を終了させない。エラーメッセージを表示し、次の入力へ進む。

エラー表示形式は `ERROR_DIAGNOSTICS_SPEC.md` に従う。REPL 入力は `<repl:N>` という仮想ファイル名で表示する。

v0.1 ではエラー時の環境ロールバックを完全保証する。入力を型チェックしてから評価するため、型チェック失敗時は評価環境を変更しない。例外は §2.1 の待てる入力で、型検査を保留したまま遅延束縛を評価環境に入れる（何も実行しない）。評価失敗時は、その入力による部分的な変更が残る場合がある。将来、評価環境のトランザクション化を検討する。

## 9. 制限

- ファイル読み込みコマンドは未実装。
- 行編集と履歴保存は Python の readline 環境に依存する。
- 補完は未実装。
- 複数行入力の完了判定は簡易的である。
