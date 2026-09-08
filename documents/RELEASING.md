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
python3 -m build && python3 -m twine check dist/*    # 配布物とメタデータ
```

`twine check` は README が PyPI で描画できるかまで見る。

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

## 試し撃ち（TestPyPI）

本番の前に通しで試したいときは、Actions から `Publish to PyPI` を
**workflow_dispatch** で起動し、`repository` に `testpypi` を選ぶ。

```sh
pip install --index-url https://test.pypi.org/simple/ lune-lang
```

## 公開後

- `README.md` の「pip で入れる」から「**PyPI への公開はまだ**です」の一文を消し、
  `pip install lune-lang` を第一の入れ方にする
- `pip install lune-lang` を真っさらな環境で1回試す

## 注意

- **PyPI の版番号は再利用できない。** 一度上げた番号には二度と別の中身を載せられない
  （yank しても番号は空かない）。試すなら TestPyPI で。
- README は PyPI の紹介文そのものになる。**相対リンクは PyPI では 404 になる**ので、
  README のリンクはすべて絶対 URL にしてある（`tests/test_packaging.py` が強制する）。
