# Lune Python 相互運用仕様 (設計案)

Version: 0.1 (2026-10-21) — 第 1 段階 (§11) を実装済み  
Related: `LANGUAGE_SPEC.md` §14・§21, `MODULE_LOADING_SPEC.md`, `TYPE_CHECKER_SPEC.md`, `LAZY_EVALUATION_SPEC.md`, `ERROR_DIAGNOSTICS_SPEC.md`, `STRATEGY.md` §4, `LANGUAGE_FUTURE_SPEC.md` §8

この文書は、Lune から Python のライブラリ（NumPy など）を呼び出す仕組みを定める。第 1 段階（§11）は `lune/pyinterop.py` を中心に実装済みで、テストは `tests/test_pyinterop.py` にある。第 2 段階以降は未実装である。

## 1. 目的

Lune の処理系は Pure Python で書かれている。これまでこの事実は「Pyodide でブラウザ内で動く」という配布上の武器として使ってきた（`STRATEGY.md` §4 A）。本仕様は同じ事実を**言語機能**として使う: Lune プログラムから、ホストである Python のライブラリ群（NumPy、SciPy、pandas、scikit-learn など AI・データ処理系のエコシステム）を呼び出せるようにする。

目標:

- `import python.numpy as np` の一行で Python モジュールを使える。
- NumPy の典型的な書き方（`np.array(xs)`、`a * 2`、`np.sum(m, axis = 0)`、`m[0, 1]`）がそのまま書ける。
- **型検査は Python の世界との境界を見えるようにする**。Python 由来の値は専用の型 `Py` を持ち、Lune の型に戻るときは必ず明示的な変換を通る。
- 失敗は Lune の診断として出る。Python のトレースバックや例外の repr がそのまま利用者に漏れることはない（issue #94 の方針を継承）。
- Playground（Pyodide）でも、インストールなしで NumPy が動く。

非目標（この版では扱わない）:

- Python のクラスを Lune で継承・定義すること。
- Python 側の型ヒント（`.pyi`）から Lune の静的型を生成すること（§12 の将来課題）。
- Python のオブジェクトを書き換える構文（`a[0] = 1`、属性代入）。
- 非同期（`async`/`await`）。

### 1.1 なぜ穴を開けるのか

Lune の値の世界に Python の意味論を持ち込むのは、これまでの方針（issue #94）に反する。それでも入れるのは、得るものの方が大きいからである。

- **エコシステム。** 個人開発の言語がライブラリの量で既存言語と競うことはできない（`STRATEGY.md` §2）。ホストが Python であることを使えば、その競争をせずに NumPy 以降の資産をまるごと使える。
- **速度。** Lune は Python の上で木を辿って評価する言語なので、Python よりさらに遅い。重い計算を NumPy（中身は C）に任せれば、Lune 自体が遅くても計算は速い。Python が遅いことも Lune が遅いことも、計算を C に寄せれば問題でなくなる。

ただし速くなるのは計算が Python 側に移ってからである。Lune のリストを Python に渡す変換は Lune の評価器が 1 セルずつ辿るので、Lune の速度のままになる（§8.1）。**データは最初から Python 側で作り（`np.arange`、`np.loadtxt`、`np.random.default_rng`）、Lune ⇄ Python の境界を越える回数と量を減らす**のが、この機能の正しい使い方である。

### 1.2 設計原則

> **Python は `Py` 型の内側でだけ Python の意味論で動く。境界を越えるのは、明示的な変換だけである。**

Lune はこれまで「ホスト言語の意味論を漏らさない」ことを徹底してきた（`if 1` を Python の truthiness で通さない、`1 == 1.0` を偽にする、など）。相互運用はこの方針に穴を開ける機能なので、穴の位置を型で示す。利用者は `Py` 型の値を見たら「ここから先は Python のルールだ」と分かり、型検査器は `Py` が Lune の世界に紛れ込もうとした地点で止めて、どう変換すればよいかを教える。これは「コンパイラが教える」という Lune の軸（`STRATEGY.md` §1）を相互運用にも延長したものである。

## 2. 全体像

```lune
module demo.stats

import python.numpy as np

let xs = [1.5, 2.0, 3.5, 4.0]
let a = np.array(xs)                 # a : Py   (Lune の List[Double] → Python list に自動変換)
let centered = a - np.mean(a)        # Py 同士の演算は Python の演算 (ブロードキャスト)
let total: Double = asDouble(np.sum(centered * centered))
let m = np.arange(6).reshape(2, 3)
let col = np.sum(m, axis = 0)        # 名前付き引数は Python のキーワード引数になる
let corner = asInt(m[1, 2])          # 添字は Py の値にだけ使える

def main(): IO[Unit] =
    IO:
        println(total)
        println(col)                 # [3 5 7]  (Python の str() で表示)
```

## 3. import

### 3.1 構文

既存の外部 import（`java.*` など、`LANGUAGE_SPEC.md` §14）の仕組みに `python.` 接頭辞を加える。構文の追加はない。

```lune
import python.numpy as np        # np を束縛
import python.numpy.linalg as la # la を束縛 (サブモジュール)
import python.math               # 末尾名 math を束縛
```

- `python.` に続くドット区切りの名前を、Python のモジュール名として扱う（`python.numpy.linalg` → `numpy.linalg`）。
- 束縛名の決め方は既存の外部 import と同じ: alias があれば alias、なければ末尾名。
- 束縛された名前の型は `Py`（§4）。`java.*` などの外部 import は従来どおり `Any` のままとし、Python 連携の変更に巻き込まない。

### 3.2 解決の時期 —「必要になるまで、やらない」

| 段階 | 行うこと | 失敗時 |
| --- | --- | --- |
| ロード時（`--check` を含む） | `importlib.util.find_spec` でモジュールが**存在するか**だけを確かめる | `MOD0004`（import 文の位置を指す） |
| 初めて値が force されたとき | `importlib.import_module` で実際に import する | `RUN0007`（import 中に Python 例外） |

実際の import は遅延させる。`torch` のように import だけで数秒かかるモジュールでも、使わない経路では代価を払わない。これは部訓「必要になるまで、やらない」そのものであり、教科書の題材にもなる。一方、モジュールが存在しないことはロード時に検出し、Lune ファイルの `MOD0001` と同じく import 文の位置に診断を出す。

```text
error[MOD0004]: Python モジュールが見つかりません: numpy
  --> demo.lune:3:1
  |
3 | import python.numpy as np
  | ^^^^^^ lune を動かしている Python にはインストールされていない
   = hint: `/usr/local/bin/python3.12 -m pip install numpy` でインストールできます（lune を動かしている Python です）
   = help: 詳しくは `lune explain MOD0004 --lang ja` を実行してください
```

hint には **lune を動かしている Python の実行ファイル**を示す。「pip install したのに見つからない」（別の Python に入れた）は Python 初学者の典型的なつまずきなので、診断で先回りする。

### 3.3 REPL と Playground

- REPL（`repl.py`）は現在外部 import を「opaque なので読み飛ばす」扱いにしている（`repl.py:116`）。`python.*` だけは値環境にも束縛する。
- Playground（Pyodide）では、実行前にソース中の `import python.X` を拾い、`pyodide.loadPackage` で該当パッケージを読み込む。Pyodide には NumPy・SciPy・pandas・scikit-learn・matplotlib が同梱されているので、**ブラウザだけで NumPy を使う Lune** が成立する（PyTorch は Pyodide にないため対象外）。

## 4. `Py` 型

### 4.1 位置づけ

`Py` は新しい基本型で、「Python のオブジェクトへの参照」を表す。静的には**動的型**として振る舞う: `Py` に対する操作は型検査を通り、結果もまた `Py` になる。ただし `Any` と違い、`Py` は Lune の型と暗黙には互換しない。

| 観点 | `Any` | `Py` |
| --- | --- | --- |
| 由来 | `java.*` 外部 import、推論の逃げ道 | `python.*` import と、Python 呼び出しの結果 |
| 他の型への代入 | 何にでも代入できる（検査なし） | **できない**。`asInt` などで変換する |
| メンバー | `() -> Any`（引数なし関数） | `Py`（属性も呼び出しも可） |
| 実行時 | 中身は未定義 | 常に `PyObject` ラッパー（§7.1） |

`Any` を再利用しなかったのは、`Any` が「検査しない」ことを意味するからである。Python 由来の値を `Any` にすると、`let n: Int = np.sum(a)` が型検査を通り、実行時に `numpy.int64` が Lune の `Int` として流れ込む。それは Lune の演算子の型検査（issue #94）を壊す。

### 4.2 `Py` に対する操作の型付け

| 式 | 条件 | 型 |
| --- | --- | --- |
| `p.name` | `p : Py` | `Py` |
| `p(args...)` | `p : Py`。引数の個数は問わない。名前付き引数可（§5.2） | `Py` |
| `p[k1, k2, ...]` | `p : Py`。添字は Python に渡せる型（§5.1） | `Py` |
| `a op b`（`+ - * / // % < <= > >= == !=`） | どちらかが `Py`、もう一方が Python に渡せる型 | `Py` |
| `-p`, `+p` | `p : Py` | `Py` |
| `!p`, `p && q`, `if p`, `while p`, match ガード | `p : Py` | **型エラー**（§4.3） |
| `match p` | `p : Py` | **型エラー**（パターンは Lune の値にしか使えない） |
| `for x in p` | `p : Py` | `x : Py`（Python の反復。§6.3） |

`==` / `!=` について: どちらかが `Py` なら Python の `==` に委ねる（NumPy では要素ごとの比較になり、結果は配列）。Lune の構造的等価（PR #43）は Lune の値同士にだけ適用する。

### 4.3 Bool を要求する位置の `Py`

`if a > 0`（`a` が配列）は Python では `ValueError: The truth value of an array ... is ambiguous` になる、NumPy 初学者の定番の罠である。Lune はこれを**型検査の段階で**止める。

```text
error[TYP0003]: if の条件: Bool が必要ですが、Py が見つかりました
   = hint: Python の値は `asBool(...)` で Bool に変換できます
   = hint: 配列の全要素・いずれかの要素を調べるなら `np.all(...)` / `np.any(...)` を使ってください
   = help: 詳しくは `lune explain TYP0003 --lang ja` を実行してください
```

新しいコードは作らず、既存の型不一致コード（`TYP0003`）に `Py` 専用の hint を付ける（`typechecker.python_hints`）。条件式の型不一致には、`Py` に限らず現状ソース位置が付かない。

### 4.4 `Py` から Lune の型への代入

`Py` を Lune の型が期待される位置（注釈付き `let`、関数引数、戻り値）に置くと `TYP0003` になり、期待型に対応する変換関数（§6.1）を hint で示す。逆に、`Py` が期待される位置に Lune の値を置くと `toPy(...)` を示す。

```text
error[TYP0003]: let の型注釈: Int が必要ですが、Py が見つかりました
  --> demo.lune:6:18
  |
6 | let total: Int = np.sum(a)
  |                  ^^ この式の型は Py
   = hint: Python の値は `asInt(...)` で Int に変換できます
   = help: 詳しくは `lune explain TYP0003 --lang ja` を実行してください
```

`asInt(...)` で包む機械適用可能な Fix（`lune fix`）は**付けていない**。呼び出し式の span が callee の部分（上の例の `np`）しか覆っていないため、span から包む範囲を決めると `asInt(np).sum(a)` という誤った修正になる。式全体を覆う span がパーサに入ってから追加する（§11 第 3 段階）。

## 5. Lune → Python（引数の変換）

### 5.1 自動変換される型

Python 呼び出しの引数・添字・演算の相手として Lune の値を渡すと、次の表に従って**自動で**変換する。表にない型（ADT、レコード、`Option` など）を渡すのは型エラー（`TYP0003`、hint で「Python に渡せる型」を列挙）。

| Lune の型 | Python の値 | 備考 |
| --- | --- | --- |
| `Int` | `int` | Lune の `Int` は任意精度なのでそのまま渡る |
| `Double` | `float` | |
| `String` | `str` | |
| `Bool` | `bool` | |
| `Unit` | `None` | |
| `null`（`T?` の null） | `None` | |
| `List[T]`（T が変換可能） | `list` | **全要素を force する**（§8.1） |
| `Tuple[...]` | `tuple` | |
| `Py` | 中身のオブジェクト | 変換なし（同一オブジェクト） |
| 関数 `A -> B` | Python の callable | 第 2 段階（§11）。呼び出し時の引数は `Py` で受ける |

Lune → Python の方向を自動にするのは、`np.array([1.0, 2.0])` を書けないと実用にならないからである。この方向は情報を失わない（Lune の値は Python の値に一意に写る）ので、暗黙でも驚きは少ない。逆方向（§6）は一意に決まらないので明示にする。

### 5.2 名前付き引数

Python のキーワード引数は Lune の既存の名前付き引数構文で書く。

```lune
np.sum(m, axis = 0)
np.zeros(3, dtype = "float32")
```

現在、関数呼び出しの名前付き引数は `TYP0012` で拒否している（Lune の関数はカリー化され、位置で束縛するため）。callee の型が `Py` のときだけこれを許し、Python の `**kwargs` として渡す。evaluator の `reject_named_args` も、callee が `PyObject` のときは呼ばない。

### 5.3 添字

`IndexExpr` は既にパーサにある（`parser.py:291`）が、evaluator・型検査器では未対応だった。受け手が `Py` のときに限り有効にする。

- `a[i]` → `a[i]`、`m[i, j]` → `m[(i, j)]`（Python と同じくタプルを渡す）。
- スライス `a[1:3]` は構文がないため、この版では `slice(1, 3)` を返す組み込み `pySlice(start, stop)` で代用する: `m[pySlice(0, 2), 1]`。スライス構文は第 3 段階（§11）。
- `Py` 以外への添字（`list[0]`）は従来どおり未対応のまま。

### 5.4 キーワードと同じ名前のメンバー

`.` と `?.` の直後では、Lune のキーワードも名前として読む（`parser.expect_member_name`）。ドットの後ろから構文が始まることはないので、そこでキーワードとして扱っても名前を禁じる効果しかなかった。Python には Lune のキーワードと同じ名前の属性が珍しくない。

```lune
import python.re

let m = re.match("(\\d+)-(\\d+)", "12-34")   # `match` は Lune のキーワード
let first = asString(m.group(1))             # "12"
```

`type`・`in`・`try`・`lazy`・`force` なども同様に書ける。この規則は受け手の型によらない構文上のものだが、名前として意味を持つのは実際には `Py` のメンバーだけである（レコードのフィールド名にキーワードは使えない）。

## 6. Python → Lune（明示的な変換）

### 6.1 変換関数

prelude に次を追加する。いずれも引数は `Py` に限る（Lune の値に使うと型エラー）。

| 関数 | 型 | 受け付ける Python の値 | 失敗 |
| --- | --- | --- | --- |
| `asInt` | `Py -> Int` | `operator.index` が通るもの（`int`、`numpy.int64` など）。`bool` は不可 | `RUN0006` |
| `asDouble` | `Py -> Double` | `float`、`int`、NumPy の浮動小数・整数スカラー。`bool` は不可 | `RUN0006` |
| `asString` | `Py -> String` | `str` のみ（`str()` による文字列化は `pyStr`） | `RUN0006` |
| `asBool` | `Py -> Bool` | `bool`、`numpy.bool_` のみ。**truthiness では変換しない** | `RUN0006` |
| `asList` | `Py -> List[Py]` | 反復可能なもの全般。**遅延リスト**として返す（§6.3） | `RUN0006` / `RUN0007` |
| `asNullable` | `Py -> Py?` | 何でも。`None` なら `null`、それ以外はそのまま | — |
| `toPy` | `T -> Py`（T は §5.1 の型） | Lune の値を明示的に Python に変換する | — |
| `pyStr` | `Py -> String` | Python の `str()` | `RUN0007` |
| `pySlice` | `Int? -> Int? -> Py` | `slice(start, stop)` | — |

`asBool` が truthiness を使わないのは `require_bool`（`evaluator.py`）と同じ理由である。`asBool(np.array([1, 2]))` は「Bool に変換できない」と Lune の診断で止まり、Python の曖昧性エラーにはならない。

`toPy` は Lune の値に Python の演算を使わせたいとき（`toPy([1, 2]) * 3` で Python のリストの繰り返しを得る、など）にだけ要る。引数位置では自動変換されるので、通常は書かない。

### 6.2 なぜ期待型による自動変換にしないか

`let n: Int = np.sum(a)` を注釈から自動で変換する案は採らない。理由は二つ。

1. evaluator は型情報を見ない。`lune --eval` は型検査を通らずに実行するので、「注釈があれば変換される」挙動は型検査の有無で実行結果が変わることを意味する。
2. 変換は失敗しうる操作であり、失敗地点がソースに見えるべきである。`asInt(...)` と書いてあれば、`RUN0006` がどこで起きたかは一目で分かる。

かわりに §4.4 の hint で、どの関数で変換すればよいかを示す（`lune fix` で自動適用する Fix は第 3 段階）。

### 6.3 反復と遅延

`asList(p)` は Python のイテレータを**遅延リスト**に包む。各 cons セルは force されたときに初めて `next()` を呼び、結果をメモ化する（`LazyValue` をそのまま使う）。

```lune
import python.itertools as it

let evens = asList(it.count(0, 2))   # 無限の Python イテレータ
let firstFive = take(5, evens)       # 5 回だけ next() が呼ばれる
```

Python のジェネレータが Lune の遅延リストとしてそのまま流れ、`take` / `takeWhile` などの既存の標準ライブラリがそのまま使える。セルはメモ化されるので、同じセルを二度 force しても `next()` は一度しか呼ばれず、状態を持つイテレータでも Lune の「一度やったことは、忘れない」が成り立つ。

`for x in p`（`p : Py`）は `for x in asList(p)` と同じ意味とする。

## 7. 実行時表現

### 7.1 `PyObject`

evaluator に値の種類を一つ足す。

```python
@dataclass(frozen=True, eq=False)
class PyObject:
    obj: object      # Python のオブジェクト (変換済みでない生の値)
```

- Python 呼び出しの**結果は常に `PyObject` で包む**（`int` や `str` が返っても包む）。静的型が `Py` である値は、実行時にも必ず `PyObject` である。これで型検査の有無にかかわらず evaluator の分岐が一意に決まる。
- `PyObject` は WHNF の葉である（`force_value` / `deep_force` はそれ以上たどらない）。
- `values_equal`（Lune の構造的等価）には現れない。`==` は §4.2 のとおり evaluator の段階で Python の `==` に振り分ける。
- `type_name` は `Py`（診断用には `Py(ndarray)` のように Python の型名を添える）。

### 7.2 評価の振り分け

| evaluator の箇所 | 追加する分岐 |
| --- | --- |
| `eval_member` | 受け手が `PyObject` → `getattr` して `PyObject` で包む |
| `eval_call` / `apply_value` | callee が `PyObject` → 引数を force・変換し、kwargs を組み立てて呼ぶ |
| `eval_binary` / 単項 | どちらかの被演算子が `PyObject` → `operator` モジュールの対応関数に委ねる |
| `IndexExpr`（新規） | 受け手が `PyObject` → `operator.getitem` |
| `eval_for` | 反復対象が `PyObject` → `asList` 相当の遅延リストを走査 |

変換・import・例外の翻訳は新しいモジュール `lune/pyinterop.py` にまとめ、evaluator には振り分けの数行だけを置く。evaluator が肥大化しないようにすることと、Pyodide 側で同じモジュールを差し替え・テストしやすくするためである。

### 7.3 表示

REPL・`println` での表示は Python の `str()` を使う（`[3 5 7]`、`array` 表記ではなく NumPy の print と同じ見た目）。REPL の型行には `: Py` と出る。

```text
lune> np.arange(3) * 2
[0 2 4] : Py
```

`--trace`（遅延評価の可観測化）では `<py ndarray>` のように Python の型名だけを出し、巨大な配列の repr でトレースが埋まらないようにする。

## 8. 評価戦略との整合

### 8.1 Python 呼び出しは正格境界

Python 呼び出しの直前に、引数をすべて force する（リストなら全要素まで deep force して変換する）。Python 側に Lune のサンクを渡しても意味をなさないからである。これは `LANGUAGE_FUTURE_SPEC.md` §8 の「Java メソッド呼び出しは正格評価境界」と同じ扱いである。

この変換は Lune の評価器が 1 セルずつ辿るので、要素数に比例して Lune の速度でかかる。`np.array(range(1, 1000000))` は NumPy の速さを得られない（§1.1）。`np.arange(1, 1000000)` と書けば変換そのものが要らない。

帰結として、**無限リストを Python に渡すと止まらない**。`np.array(naturalsFrom(0))` は変換が終わらない。設計上は防げない（リストの有限性は判定できない）ので、教科書で `take` と組で教える。変換中に要素数がしきい値（例: 10^7）を超えたら警告を一度だけ出す案は、実装時に検討する。

### 8.2 呼び出しの時期

Python 呼び出しそのものは、他の式と同じく**その式が force されたとき**に起きる。`let y = np.sum(a)` は `y` が使われるまで計算されず、一度計算すればメモ化される。

これは NumPy のような純粋な計算には都合がよい（使わない重い計算は走らない）。一方、副作用のある呼び出し（乱数、ファイル、モデルの学習、`print`）は、書いた順ではなく force された順に起きる。標準ライブラリの `random` がいちばん分かりやすい例である。

```lune
import python.random

let seeded = random.seed(42)     # 使われないトップレベルの let は一度も実行されない

def main(): Unit =
    random.seed(42)              # 文は書いた位置で実行される
    let x = random.random()
    let y = random.random()
    println(y)                   # 0.6394…  先に使われた y が 1 回目の乱数を受け取る
    println(x)                   # 0.0250…  Python で同じコードを書くと x と y が逆になる
```

`let` を `strict let` にすると、書いた順（x = 0.6394…、y = 0.0250…）に戻る。v0.1 の `IO:` は厳密な effect system ではないので（`LANGUAGE_SPEC.md` §9.7）、この版では次の指針を文書で示すにとどめる。

- 戻り値を使わない呼び出し（`random.seed(42)`）は `let` に入れず、ブロックの文として書く。
- 副作用のある呼び出しの結果は `strict let` で受ける。
- 複数の乱数が要るときは一度の呼び出しでまとめて取る（`np.random.default_rng(42).random(3)`）。呼び出しが一度なら順序の問題は起きない。

これらの振る舞いは `tests/test_pyinterop.py` の `test_side_effects_follow_forcing_order` が固定している。

将来、`IO` を effect として検査する段階で、Python 呼び出しを原則 `IO` 扱いにし、`@pure` で純粋に昇格する（`LANGUAGE_FUTURE_SPEC.md` §2 と同じ方針）。

### 8.3 可変オブジェクト

NumPy 配列は可変であり、`PyObject` は参照である。`a.sort()` のような破壊的メソッドを呼ぶと、同じ配列を指す他の束縛からも変化が見え、しかもその見え方は force の順序に依存する。この版では禁止しない（メソッドが破壊的かどうかは静的に分からない）が、教科書では「`Py` は Lune の不変性の外にある」ことを明示し、`np.sort(a)` のような新しい配列を返す関数を使うよう指導する。破壊的代入の構文（`a[0] = 1`）は提供しない。

逆向きの落とし穴もある。Lune のリストは渡すたびに新しい Python の `list` に変換される（§5.1）ので、渡した先の破壊的な関数はそのコピーを書き換えるだけで、Lune 側の値は変わらない。

```lune
let xs = [3, 1, 2]
let r = random.shuffle(xs)   # r は Python の None、xs は (3 1 2) のまま
```

これは Lune の値が不変であることの帰結で、正しい振る舞いである。ただし何のエラーも出ずに「何も起きない」ので、新しい値を返す関数（`random.sample(xs, 3)`、`py.sorted(xs)`）を使うよう教科書で案内する。どうしても破壊的な関数を使うなら、`toPy(xs)` で作った `Py` の値に対して呼ぶ。

## 9. 診断

新しいコードは二つ。いずれも `explanations.py` / `explanations_ja.py` に詳解を追加する（`tests/test_explanations.py` が強制する）。

| コード | 意味 | 発生時期 |
| --- | --- | --- |
| `MOD0004` | `python.X` の X が、lune を動かしている Python に存在しない | ロード時（`--check` でも出る） |
| `RUN0007` | Python のコードが例外を投げた | 実行時 |

`RUN0007` の表示:

```text
error[RUN0007]: Python で例外が発生しました: ValueError: operands could not be broadcast together with shapes (3,) (2,)
   = hint: Python のトレースバック全体は `lune --py-traceback` で表示できます
   = help: 詳しくは `lune explain RUN0007 --lang ja` を実行してください
```

- 例外の型名と `str(exc)` の 1 行目をメッセージに、2 行目以降を note に出す。トレースバックは既定では隠す（`--py-traceback` で note に添える）。
- 実行時エラーには、Lune の他の実行時エラーと同じくソース位置が付かない（評価器が span を持ち回っていないため）。
- `AttributeError` には、属性名の綴り違いを想定して `dir()` からいちばん近い名前を `did you mean` で示す。
- `KeyboardInterrupt` / `SystemExit` は翻訳せずにそのまま通す。
- Lune の関数を Python に渡した場合（§11）、その中で起きた `LuneRuntimeError` は Python 側を素通りさせて元の診断のまま出す（`RUN0007` で包まない）。

既存コードへの追加:

- `TYP0003`: `Py` が Lune の型の位置に来たとき・Lune の値を Python に渡せないときの hint（§4.3、§4.4、§5.1）。
- `TYP0012`: callee が `Py` のときは出さない（§5.2）。
- `RUN0006`: `asInt` などの変換失敗。

コード数が 31 → 33 に増えるので、README・Playground の診断カタログ・教科書（付録・本文の「全 N コード」）を更新する。

## 10. 安全性と配布

- **依存は増やさない。** `pyproject.toml` の `dependencies = []` は維持する。NumPy は利用者が自分で入れる。相互運用の仕組み自体は標準ライブラリしか使わない。
- **無効化スイッチ。** `python.*` import は任意の Python コード（`python.os`、`python.subprocess`）を実行できる。採点サーバなどで Lune を動かす場合に備え、`--no-python` フラグ（と環境変数 `LUNE_PYTHON=off`）で `python.*` import を `MOD0004` 相当のエラーにできるようにする。既定は有効。
- **テスト。** 中核のテストは標準ライブラリのモジュール（`python.math`、`python.fractions`、`python.itertools`、`python.statistics`）で書き、CI に NumPy を要求しない。NumPy 固有の振る舞い（ブロードキャスト、`numpy.int64` の `asInt`、配列の `==`）は `pytest.importorskip("numpy")` で別ファイルにする。

## 11. 段階的な実装計画

### 第 1 段階: 最小限の相互運用（MVP） — 実装済み

ここまでで「NumPy で計算して結果を Lune で使う」が成立する。

| ファイル | 変更 |
| --- | --- |
| `lune/module_loader.py` | `python.` を外部 import に加え、`find_spec` による存在確認と `MOD0004` |
| `lune/pyinterop.py`（新規） | `PyObject`、遅延 import、Lune ⇄ Python 変換、例外の翻訳、`as*` 関数 |
| `lune/typechecker.py` | `PY = Type("Py")`、§4.2 の型付け、`Py` 用の hint、`TYP0012` の例外 |
| `lune/evaluator.py` | §7.2 の振り分け、`IndexExpr`、`type_name` / 表示 |
| `lune/repl.py` | `python.*` import の値束縛 |
| `lune/messages.py`、`explanations*.py` | 新しいメッセージ・詳解（日英） |
| `lune/cli.py` | `--py-traceback`、`--no-python` |
| `documents/` | 本仕様の確定、`LANGUAGE_SPEC.md` §6・§14・§21、`ERROR_INDEX*.md` |
| `tests/` | 標準ライブラリによる相互運用テスト、NumPy の任意テスト |

### 第 2 段階: Lune の関数を Python に渡す・Playground

- Lune の関数を Python の callable に変換する（`scipy.optimize.minimize(f, x0)`、`sorted(xs, key = f)`）。Python から受け取る引数は `PyObject` で包んで渡し、戻り値は §5.1 で変換する。callable の静的型は `Py -> ... -> T`（T は Python に渡せる型）に限る。
- Playground で `import python.X` から `loadPackage` を自動で行う。
- 教科書に「Python の力を借りる」章（または付録）を追加する。

### 第 3 段階: 書き心地

- 添字のスライス構文 `a[1:3]`、`m[:, 0]`（受け手が `Py` のときのみ）。
- §4.4 の `asInt(...)` などで包む機械適用可能な Fix（呼び出し式全体を覆う span が前提）。
- 行列積の演算子 `@`（`@` は将来仕様でアノテーションに使う予定なので、字句上の衝突を検討してから）。
- 型付きラッパー: Lune 側に型の付いた宣言を書き、`Py` を経由せずに使えるようにする。

  ```lune
  extern python "numpy.mean" def mean(xs: List[Double]): Double
  ```

  `.pyi` から自動生成する案もあるが、NumPy の型ヒントは Lune の型に落ちないものが多いので、手書きの宣言を先にする。

## 12. 未決事項

- `Py` の表記: `Py` / `PyObject` / `Python`。短さと、型エラーの文中での読みやすさから `Py` を推す。
- 変換関数の名前: `asInt` 系を prelude に置くか、`Py.int(...)` のように名前空間に置くか。Lune には現在 qualified access がない（`LANGUAGE_SPEC.md` §14）ので、この版では prelude に置く。
- 無限リストを Python に渡したときの警告しきい値（§8.1）。
- `println(p)` を `str()` にするか `repr()` にするか（§7.3 は `str()` を推す）。
