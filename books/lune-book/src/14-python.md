# 第14章 Python の力を借りる

Lune の処理系は Python で書かれています（付録E）。そう聞いて、こう思った人もいるかもしれません — それなら、Python のライブラリも使えるのでは?

使えます。この章では `import python.X` の一行で、NumPy をはじめとする Python のライブラリを Lune から呼ぶ方法を学びます。

ただし、Lune はここで一つの約束を破ります。これまでの章で、Lune は Python の振る舞いを決して持ち込みませんでした（`if 1` は通らず、`1 == 1.0` は偽でした）。Python のライブラリを使うとは、その Python の振る舞いを招き入れることです。そこで Lune は、**Python のルールが通じる範囲を型で区切ります**。その区切りが、この章の主役の `Py` 型です。

## 14.1 import python — 一行で NumPy

```lune
module scores
import python.numpy as np

# 第14章: 計算は NumPy に任せ、結果だけを Lune に持ち帰る。
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

`import python.numpy as np` は、第10章の外部 import の仲間です。`python.` に続く名前が Python のモジュール名になり、`as` で付けた名前（付けなければ末尾の名前）で使えます。`np.array(...)`、`np.mean(...)`、そして配列どうしの引き算や割り算 — NumPy の書き方がそのまま通ります。

NumPy はあらかじめインストールしておく必要があります（`python3 -m pip install numpy`）。インストールの要らない Playground については 14.9節で扱います。

**import は、使われるまで行われません。** `import python.numpy` と書いた時点では、モジュールが存在するかどうかを確かめるだけです。実際に読み込むのは、`np` が初めて使われたときです。第4章の部訓「必要になるまで、やらない」は、モジュールの読み込みにも効いています。

## 14.2 Py 型 — 境界を型で見る

`np.array(...)` の型は何でしょうか。REPL で聞いてみます。

```text
lune> import python.numpy as np
ok
lune> np.arange(3) * 2
[0 2 4] : Py
```

**`Py`** は「Python のオブジェクト」を表す型です。`Py` の値に対しては、メンバーの参照（`np.mean`）、呼び出し（`np.mean(a)`）、添字（`m[1, 2]`）、演算（`a * 2`）が使え、その結果はまた `Py` になります。`Py` の内側では、Python のルールがそのまま働きます。

そのかわり、**`Py` は黙って Lune の型にはなりません。**

```lune
module border
import python.numpy as np

# Py は暗黙には Int にならない。
let scores = np.array([72, 85, 90])

let total: Int = np.sum(scores)
```

```text,diagnostic
error[TYP0003]: let の型注釈: Int が必要ですが、Py が見つかりました
  --> border.lune:7:18
  |
7 | let total: Int = np.sum(scores)
  |                  ^^ この式の型は Py
   = hint: Python の値は `asInt(...)` で Int に変換できます
   = help: 詳しくは `lune explain TYP0003 --lang ja` を実行してください
```

`np.sum` が返すのは Python の整数（正確には NumPy の `int64`）であって、Lune の `Int` ではありません。hint のとおり `asInt(np.sum(scores))` と書けば `Int` になります。境界を越えるところは、必ずソースに見えるようにする — それが `Py` 型の約束です。

変換関数は次のとおりです。

| 関数 | 型 | 受け付けるもの |
| --- | --- | --- |
| `asInt` | `Py -> Int` | 整数（NumPy の整数も）。真偽値は不可 |
| `asDouble` | `Py -> Double` | 実数（整数も） |
| `asString` | `Py -> String` | 文字列 |
| `asBool` | `Py -> Bool` | 真偽値だけ。「真っぽい値」は受け付けない |
| `asList` | `Py -> List[Py]` | 反復できるもの全般（14.4節） |
| `asNullable` | `Py -> Py?` | 何でも。Python の `None` を `null` にする |
| `toPy` | `T -> Py` | Lune の値を `Py` にする（14.3節） |
| `pyStr` | `Py -> String` | Python の `str()` による文字列化 |

変換が失敗すれば実行時エラー（`RUN0006`）です。`asInt(np.array([1, 2]))` は「ndarray は Int に変換できません」と止まります。

### 配列の真偽値という罠

NumPy を使い始めた人がまず踏む罠があります。

```lune
module truth
import python.numpy as np

# 配列の比較は配列。そのままでは条件に使えない。
let scores = np.array([72.0, 85.0, 90.0])

let verdict = if scores > 70.0 then "pass" else "fail"
```

`scores > 70.0` は「各要素が 70 を超えるか」を並べた配列 `[True True True]` です。Python で `if` にこれを渡すと、実行時に「配列の真偽値はあいまいです」というエラーになります。Lune は**実行する前に**止めます。

```text,diagnostic
error[TYP0003]: if の条件: Bool が必要ですが、Py が見つかりました
   = hint: Python の値は `asBool(...)` で Bool に変換できます
   = hint: 配列の全要素・いずれかの要素を調べるなら `np.all(...)` / `np.any(...)` を使ってください
   = help: 詳しくは `lune explain TYP0003 --lang ja` を実行してください
```

「全員が 70 点を超えたか」なら `np.all(...)`、「誰か一人でも」なら `np.any(...)` で1つの真偽値にし、それを `asBool` で `Bool` にします（演習 14-2）。

## 14.3 Lune から Python へ渡すもの

逆向き — Lune の値を Python に渡す方向 — は自動です。14.1節の `np.array([72.0, 85.0, ...])` では、Lune のリストがそのまま Python のリストになって渡っていました。

| Lune の型 | Python の値 |
| --- | --- |
| `Int` / `Double` / `String` / `Bool` | `int` / `float` / `str` / `bool` |
| `Unit`、`null` | `None` |
| `List[T]`、`Tuple[...]` | `list`、`tuple`（中身も同じ規則で） |
| `Py` | そのオブジェクト自身 |
| `Py` を受け取る関数 | Python から呼べる関数（14.5節） |

こちらを自動にしてよいのは、どの Lune の値にも対応する Python の値が一つに決まるからです。逆に Python の値は、どの Lune の型にすべきかが一つに決まりません（`numpy.int64` は `Int` か `Double` か?）。だから戻る方向だけは明示します。

表にない値 — `Option` やレコード、自分で定義した ADT — は Python に渡せず、型検査で止まります。

引数として渡すときは自動なので、`toPy` を自分で書く場面は多くありません。使うのは、Lune の値に **Python の演算**をさせたいときです。

```text
lune> toPy([1, 2]) * 3
[1, 2, 1, 2, 1, 2] : Py
lune> [1, 2] * 3
error[TYP0003]: *: 数値型が必要ですが、List[Int] が見つかりました
   = help: 詳しくは `lune explain TYP0003 --lang ja` を実行してください
```

Lune のリストに `*` はありませんが、`toPy` で Python のリストにすれば、Python の「リストの繰り返し」になります。

**名前付き引数**は、Python のキーワード引数になります。第13章で、`名前 = 値` が意味を持つのはレコードの構築だけで、関数やコンストラクタに書くと `TYP0012` になると見ました。呼ぶ相手が `Py` のときだけは別です。**添字** `[]` も `Py` の値にだけ使えます。

```lune
module matrix
import python.numpy as np

# 名前付き引数はキーワード引数に、[] は Python の添字になる。
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

Python の `m[:, 0]`（全行の 0 列目）にあたるスライスは、Lune にはまだ構文がないので `pySlice(null, null)` と書きます。

### 標準ライブラリも同じ

NumPy に限らず、Python の標準ライブラリも同じ書き方で使えます。

```lune
module regex
import python.re
import python.json

# 標準ライブラリも同じ書き方で使える。match は Lune のキーワードだが、. の後ろでは名前。
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

`re.match` の `match` は Lune のキーワードですが、`.` の後ろでは名前として読まれます。`re.match` は一致しないと Python の `None` を返すので、`asNullable` で受けると第7章の `null` として扱えます。

## 14.4 Python から戻すもの — 遅延リストとして

`asList` は、Python の「反復できるもの」を Lune のリストにします。このリストは**遅延リスト**です。

```lune
module stream
import python.itertools as it

# Python の無限イテレータも、Lune では遅延リストになる。
let evens = map(asList(it.count(0, 2)), asInt)

let firstFive = take(evens, 5)
```

```console
$ lune --eval firstFive stream.lune
(0 2 4 6 8)
```

`it.count(0, 2)` は 0, 2, 4, … と終わりなく数え続ける Python のイテレータです。`asList` はそれを第8章の無限ストリームと同じ形に包み、要素は**使われたときに一つずつ**取り出されます。`take` が5個で止まるので、プログラムも止まります。

取り出した要素はメモ化されます（第4章）。同じリストを二度たどっても、Python のイテレータが二度進むことはありません。

## 14.5 関数を Python に渡す

Python のライブラリには、関数を受け取るものがたくさんあります。並べ替えの基準を渡す `sorted` の `key`、畳み込みの `functools.reduce`、要素ごとの関数を配列全体に広げる `np.vectorize` などです。Lune の関数は、そのまま渡せます。

```lune
module callbacks
import python.builtins as py
import python.functools as ft
import python.numpy as np

def lastDigit(x: Py): Int =
    asInt(x) % 10

let xs = [31, 12, 23, 44]

# ラムダの引数は Py。Python が呼ぶので、注釈は要らない。
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

`python.builtins` は `sorted`・`len`・`int` など、Python で import せずに使える関数の入ったモジュールです。

渡す関数には一つ条件があります。**Python は関数を Python の値で呼ぶので、引数は `Py` で受けます。** `def lastDigit(x: Py)` がそうなっていますし、Python 呼び出しの引数に直接書いたラムダは、注釈を省けば引数が `Py` になります。`Int` を受け取る関数を渡そうとすると、型検査が止めます。

```lune
module callback_bad
import python.builtins as py

# Lune の型を受け取る関数は、Python からは呼べない。
def inc(x: Int): Int =
    x + 1

let sorted = py.sorted([3, 1, 2], key = inc)
```

```text,diagnostic
error[TYP0003]: Int -> Int 型の値は Python に渡せません
  --> callback_bad.lune:8:41
  |
8 | let sorted = py.sorted([3, 1, 2], key = inc)
  |                                         ^^^ Python に対応する値がない
   = hint: Python は関数を Py の値で呼びます。引数は Py と宣言するか、ラムダなら注釈を省き、中で変換してください（例: `fn x -> asInt(x) + 1`）
   = help: 詳しくは `lune explain TYP0003 --lang ja` を実行してください
```

関数の中で Lune のエラーが起きた場合、そのエラーは間にある Python のコードを素通りして、Lune のエラーのまま届きます。`sorted` の `key` の中で `crash()` を呼べば、出るのは `RUN0006` です。

## 14.6 遅延評価と副作用 — 書いた順に起きるとは限らない

ここからは、Python を Lune から使うときに特有の注意点です。標準ライブラリの `random` がいちばん分かりやすい例になります。

```lune
module dice
import python.random

# 先に使われた束縛が、先に乱数を受け取る。
def lazyDraws(): Tuple[Double, Double] =
    random.seed(42)
    let x = asDouble(random.random())
    let y = asDouble(random.random())
    (y, x)

# strict let は書いた順に評価する。
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

Python で同じ順に書けば、`x` が 1 回目の乱数（0.639…）、`y` が 2 回目（0.025…）を受け取ります。`strictPair` はそのとおりです。ところが `lazyPair` では入れ替わっています。

理由は第4章そのものです。`let` は値を約束するだけで、計算は使われたときに行われます。`(y, x)` を表示するとき先に使われるのは `y` なので、`y` の `random.random()` が先に呼ばれ、1 回目の乱数を受け取ります。Lune の純粋な世界では計算の順序は結果に影響しませんでしたが、**呼ぶたびに違う値を返す関数**では順序が結果を変えます。

対策は3つです。

- `random.seed(42)` のように戻り値を使わない呼び出しは、`let` に入れずに**文として**書く。ブロックの文は書いた位置で実行されます。トップレベルに `let seeded = random.seed(42)` と書くと、`seeded` は誰にも使われないので、一度も実行されません
- 副作用のある呼び出しの結果は **`strict let`** で受ける
- 乱数がいくつも要るなら、**一度の呼び出しでまとめて**取る（演習 14-4）。呼び出しが一度なら、順序の問題は起きません

### Python に渡したリストは写し

もう一つは、Python の関数が「渡されたものを書き換える」場合です。

```lune
module shuffle
import python.random

# Lune のリストは渡すたびに Python のリストへ写される。並べ替わるのはその写し。
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

`random.shuffle` は渡されたリストをその場で並べ替え、Python の `None` を返す関数です。しかし並べ替わったのは、渡すときに作られた**写し**です。Lune の `xs` は変わりません。Lune のリストは書き換えられない値で、その性質は境界の向こうでも守られます。新しいリストを返す関数（`random.sample`、`sorted`）を使いましょう。

`random.Random(7)` は、種を固定した乱数生成器を作る書き方です。`random.seed` のように全体の状態を変えないので、順序の問題も起きにくくなります。

## 14.7 速さについて

Lune は Python の上で動く、Python よりさらに遅い言語です。では NumPy を使うと速くなるのでしょうか。

**なります — 計算が Python の側に移れば。** NumPy の配列計算の中身は C で書かれていて、`np.mean(scores)` は Lune の評価器を通りません。重い計算を NumPy に任せれば、Lune の遅さは問題でなくなります。

ただし、**境界を越える変換は Lune の速さで動きます。** `np.array(range(1, 1000000))` と書くと、Lune の評価器が百万個のセルを一つずつたどって Python のリストを作り、それから NumPy に渡します。同じ配列は `np.arange(1, 1000000)` と書けば、最初から NumPy の中で作られます。

> **データは最初から Python の側で作る**（`np.arange`、`np.loadtxt`、`np.random.default_rng`）。境界を越える回数と量を減らす。

これが、Lune から Python を使うときのいちばん大事なコツです。

## 14.8 失敗したとき

### Python の例外 — RUN0007

```lune
module broadcast
import python.numpy as np

# 形の合わない配列は、Python の例外になる。
let a = np.array([1, 2, 3])

let b = np.array([1, 2])

let combined = a + b

let typo = np.summ(a)
```

```text,diagnostic
$ lune --eval combined broadcast.lune
error[RUN0007]: Python で例外が発生しました: ValueError: operands could not be broadcast together with shapes (3,) (2,)
   = hint: Python のトレースバック全体は `lune --py-traceback` で表示できます
   = help: 詳しくは `lune explain RUN0007 --lang ja` を実行してください
$ lune --eval typo broadcast.lune
error[RUN0007]: Python で例外が発生しました: AttributeError: module 'numpy' has no attribute 'summ'
   = hint: もしかして `sum` ですか?
   = hint: Python のトレースバック全体は `lune --py-traceback` で表示できます
   = help: 詳しくは `lune explain RUN0007 --lang ja` を実行してください
```

Python のコードが例外を投げると、`RUN0007` になります。メッセージは Python 自身の説明です（形 `(3,)` と `(2,)` の配列は足せない）。属性名の綴り違いには、第1章の `TYP0001` と同じく「もしかして」が付きます。Python のトレースバックは既定では隠してあり、`--py-traceback` を付けると表示されます。

### モジュールが見つからない — MOD0004

```text,diagnostic
error[MOD0004]: Python モジュールが見つかりません: torch
  --> missing.lune:2:1
  |
2 | import python.torch as torch
  | ^^^^^^ lune を動かしている Python にはインストールされていない
   = hint: `python3 -m pip install torch` でインストールできます（lune を動かしている Python です）
   = help: 詳しくは `lune explain MOD0004 --lang ja` を実行してください
```

hint に出る `python3` の部分には、実際には lune を動かしている Python の実行ファイルが絶対パスで出ます（紙面では短くしています）。「pip install したのに見つからない」というときは、たいてい別の Python に入れています。hint のとおりのコマンドで入れ直してください。

Python の import を禁止したいとき（たとえば、提出されたプログラムを採点サーバで動かすとき）は、`--no-python` を付けるか、環境変数 `LUNE_PYTHON=off` を設定します。`python.*` の import がすべて `MOD0004` になります。

## 14.9 Playground で

Playground は、ブラウザの中で動く Python（Pyodide）の上で Lune を動かしています。Pyodide には NumPy・SciPy・pandas・scikit-learn などが用意されていて、プログラムに `import python.numpy` があると、実行の前に自動で読み込まれます。インストールは要りません。プリセット「NumPy を使う(Python 連携)」で試せます。

この章のコード例にも「▶ Playground で開く」が付いています。ただし Pyodide にないパッケージ（PyTorch など）は、Playground では使えません（`MOD0004` になります）。

> **壊してみよう** — 14.2節の `truth.lune` を、`np.all` を使わずに `asBool(scores > 70.0)` と直したらどうなるでしょう。型検査は通ります（`asBool` は `Py` を受け取るので）。では実行すると? `asBool` は「真っぽい値」を受け付けないので、配列を渡すと `RUN0006`（ndarray は Bool に変換できません）で止まります。Python なら「あいまい」エラーになるところを、Lune は自分の言葉で止めます。

## まとめ

| 概念 | 一言で |
| --- | --- |
| `import python.X as y` | Python のモジュールを使う。実際の import は使われたとき |
| `Py` 型 | Python のオブジェクト。メンバー・呼び出し・添字・演算の結果も `Py` |
| Lune → Python | 自動。数・文字列・真偽値・`null`・リスト・タプル・`Py`・`Py` を受け取る関数 |
| Python → Lune | 明示。`asInt` `asDouble` `asString` `asBool` `asList` `asNullable` |
| キーワード引数・添字 | 呼ぶ相手・受け手が `Py` のときだけ使える |
| `asList` | Python の反復を遅延リストにする。無限でもよい |
| 関数を渡す | 引数は `Py` で受ける。Python 呼び出しの中のラムダは注釈なしで `Py` |
| 副作用 | 使われた順に起きる。文で書く・`strict let`・一度にまとめて取る |
| 速さ | 計算は Python 側に任せる。データも Python 側で作る |
| 診断 | `MOD0004` モジュールが無い / `RUN0007` Python の例外（`--py-traceback`） |

## 演習問題

**演習 14-1**（★） 標準ライブラリの `statistics` を使って、Lune のリスト `[3.0, 1.0, 4.0, 1.0, 5.0, 9.0]` の中央値と平均を `Double` で求めてください。

<details><summary>解答</summary>

```lune
module ex14_1
import python.statistics as st

# 演習 14-1: 標準ライブラリ statistics で、Lune のリストの中央値と平均を求める。
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

Lune のリストはそのまま Python のリストとして渡り、結果は `Py` で返ってくるので `asDouble` で `Double` にします。NumPy が無くても動く例です。

</details>

**演習 14-2**（★★） 14.2節の `truth.lune` を、「全員が 70 点を超えていれば `"pass"`」という意味になるよう直してください。

<details><summary>解答</summary>

```lune
module ex14_2
import python.numpy as np

# 演習 14-2: 配列の比較は配列なので、np.all で1つの真偽値にしてから Bool に変換する。
let scores = np.array([72.0, 85.0, 90.0])

let verdict = if asBool(np.all(scores > 70.0)) then "pass" else "fail"
```

```console
$ lune --eval verdict ex14-2.lune
"pass"
```

`scores > 70.0` は配列、`np.all(...)` はそれを1つの真偽値（NumPy の `bool`）にし、`asBool` が Lune の `Bool` にします。「誰か一人でも」なら `np.any` です。

</details>

**演習 14-3**（★★） `["banana", "fig", "kiwi", "apple"]` を、単語の長さの順に並べ替えてください。Python の `sorted` と `len` を使うこと。

<details><summary>解答</summary>

```lune
module ex14_3
import python.builtins as py

# 演習 14-3: 単語を長さの順に並べる。key に渡すラムダの引数は Py。
let words = ["banana", "fig", "kiwi", "apple"]

let byLength = map(asList(py.sorted(words, key = fn w -> py.len(w))), asString)
```

```console
$ lune --eval byLength ex14-3.lune
("fig" "kiwi" "apple" "banana")
```

ラムダ `fn w -> py.len(w)` の結果は `Py` のままで構いません。`sorted` が比べるのは Python の側だからです。`"kiwi"` と `"apple"` は長さ 4 と 5、`"banana"` が最後です。

</details>

**演習 14-4**（★★★） 14.6節の `lazyDraws` で `x` と `y` が入れ替わった理由を説明し、`strict let` を使わずに、2つの乱数が書いた順に `x`・`y` に入るよう書き直してください。

<details><summary>解答</summary>

`let` の右辺は使われたときに評価されるので、先に使われた `y` が先に `random.random()` を呼び、1 回目の乱数を受け取りました。呼ぶたびに値が変わる関数では、呼ぶ順序が結果を決めます。

呼び出しを一度にすれば、順序の問題そのものが無くなります。

```lune
module ex14_4
import python.numpy as np

# 演習 14-4: 乱数を一度の呼び出しでまとめて取れば、force の順序に左右されない。
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

`y` を先に表示しても、乱数は `random(2)` の一度で2つとも決まっているので、`x` と `y` の値は変わりません。`np.random.default_rng(42)` は種を固定した生成器を作るので、何度実行しても同じ値が出ます。

</details>

---

**より正確には** — `Py` 型の規則、変換の表、評価の時期、診断の規範は `documents/PYTHON_INTEROP_SPEC.md`。`MOD0004` と `RUN0007` の解説は `documents/ERROR_INDEX_JA.md` にもあります。この章のコード例は `books/examples/ch14/` にあり、すべて実際の CLI で検証されています（NumPy を使う例は、NumPy がインストールされた環境で）。
