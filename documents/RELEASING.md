# リリース手順 — PyPI への公開

配布名は **`lune-lang`**（PyPI の `lune` は別のパッケージが使用中）。版番号の出処は
`lune/__init__.py` の `__version__` ひとつで、パッケージメタデータ・`lune --version`・
REPL のバナーはすべてそこから来る（`LANGUAGE_SPEC.md` §19）。

## 0. 初回だけ — PyPI 側の設定（要 koide の操作）

**API トークンは作らない。** Trusted Publishing（OIDC）を使うので、リポジトリにも
GitHub Secrets にも認証情報を置かない。PyPI が GitHub Actions の身元を直接検証する。

1. <https://pypi.org/account/register/> でアカウントを作る（2要素認証は必須）
2. <https://pypi.org/manage/account/publishing/> で **pending publisher** を追加する

   | 項目 | 値 |
   | --- | --- |
   | PyPI Project Name | `lune-lang` |
   | Owner | `koide55` |
   | Repository name | `lune-lang` |
   | Workflow name | `publish.yml` |
   | Environment name | `pypi` |

3. 練習したい場合は <https://test.pypi.org/> でも同じ設定をし、Environment name を
   `testpypi` にする（下の「試し撃ち」で使う）

まだ誰も `lune-lang` を取っていないことは確認済み（2026-09-08 時点）。pending publisher
を使うと、最初のアップロードと同時にプロジェクトが作られる。

## 1. 出す版を決める

`lune/__init__.py` の `__version__` を上げてコミットする。ここだけを直せばよい。

```sh
grep -n __version__ lune/__init__.py
```

## 2. 手元で確認する

```sh
PYTHONPATH=. python3 -m unittest discover -s tests   # 処理系のテスト
bash books/tools/check_examples.sh                   # 教科書のコード例
```

配布物も手元で組んで確かめたい場合は、次のどちらかで。**`build` と `twine` は標準
ライブラリではなく、Homebrew の python は PEP 668 で `pip install` を拒む**ので、
`python3 -m build` を直接叩くと `No module named build` になる。

```sh
pipx run build && pipx run twine check dist/*        # pipx があるならこれが手軽
```

```sh
python3 -m venv .venv && .venv/bin/pip install build twine   # 初回だけ
.venv/bin/python -m build && .venv/bin/python -m twine check dist/*
```

`twine check` は README が PyPI で描画できるかまで見る。`dist/` は `.gitignore` 済み。

**この手順は省いてもよい。** 同じことを CI の `package` job が PR ごとに、
`publish.yml` がアップロード直前にもう一度やる。手元で確かめるのは、リリース前に
自分の目で見ておきたいときのため。

## 3. タグを打って Release を作る

タグは `v` + 版番号（例 `v0.1.0`）。GitHub の Release を **publish** した時点で
`.github/workflows/publish.yml` が走る。

```sh
git tag v0.1.0 && git push origin v0.1.0
gh release create v0.1.0 --title "Lune v0.1.0" --notes "..."
```

ワークフローは公開の前に次を確かめる。**タグと `__version__` が食い違っていれば止まる**
（リリースページと配布物が別の番号を名乗る事故を防ぐ）。

- sdist と wheel を組み、`twine check` を通す
- チェックアウトの外で wheel を入れ、`lune --eval` / `lune --version` / `lune explain`
  が動くことを確かめる（メッセージカタログや詳解がパッケージに入り損ねていないか）

## 詰まったとき

### `invalid-publisher`（2026-09-09 に実際に出た）

```
Trusted publishing exchange failure:
* `invalid-publisher`: valid token, but no corresponding publisher
```

GitHub 側は正常で、**PyPI 側の pending publisher がまだ無い**（または値が違う）という意味。
`build` job が通って `publish` job だけが落ちているのが目印になる。ログには GitHub が
送った身元情報がそのまま出るので、§0 の表と突き合わせて登録する。

```
* repository:   koide55/lune-lang
* workflow_ref: koide55/lune-lang/.github/workflows/publish.yml@refs/tags/v0.1.0
* environment:  pypi
```

**この失敗で版番号は焼けない。** 何も PyPI に届いていないので、タグを作り直す必要はなく、
登録後に落ちたジョブを再実行すればよい。

```sh
gh run rerun <RUN_ID> --failed
```

### TestPyPI は別サービス

test.pypi.org は PyPI とアカウントも登録も別。片方に登録しても、もう片方では
`invalid-publisher` になる。

## 試し撃ち（TestPyPI）

本番の前に通しで試したいときは、Actions から `Publish to PyPI` を
**workflow_dispatch** で起動し、`repository` に `testpypi` を選ぶ。

```sh
pip install --index-url https://test.pypi.org/simple/ lune-lang
```

## 公開後

**真っさらな環境で 1 回入れて動かす。** 手元のチェックアウトから import してしまうと
確かめたことにならないので、別ディレクトリに venv を作って、そこから叩く。

```sh
cd "$(mktemp -d)" && python3 -m venv v && v/bin/pip install lune-lang
v/bin/python -c 'import lune; print(lune.__file__)'   # site-packages を指すこと
v/bin/lune --version
printf 'let answer = 40 + 2\n' > s.lune && v/bin/lune --eval answer s.lune
printf 'let x = cont\n' > t.lune && LUNE_LANG=ja v/bin/lune --check t.lune
```

最後の 2 つが要点で、**メッセージカタログと詳解がパッケージに入っているか**は、
これでしか分からない（リポジトリの中では手元のファイルが見えてしまう）。

<https://pypi.org/project/lune-lang/> も開いて、README が描画されリンクが生きていることを
見ておく。相対リンクは PyPI では 404 になる（下の「注意」を参照）。

初回（0.1.0、2026-09-09）はこれに加えて README の「pip で入れる」を書き換えた。
2 回目以降は、READMEの版番号に触れている箇所が無ければ、そのまま。

## 注意

- **PyPI の版番号は再利用できない。** 一度上げた番号には二度と別の中身を載せられない
  （yank しても番号は空かない）。試すなら TestPyPI で。
- README は PyPI の紹介文そのものになる。**相対リンクは PyPI では 404 になる**ので、
  README のリンクはすべて絶対 URL にしてある（`tests/test_packaging.py` が強制する）。
