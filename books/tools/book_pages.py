#!/usr/bin/env python3
"""目次ページと索引ページを生成し、PDF にしおりを付ける。

`books/tools/build_pdf.sh` から呼ばれる。単体では次のように使う。

    book_pages.py toc                       # 目次を生成（ページ番号なし）
    book_pages.py toc    --pdf FILE         # 目次を生成（ページ番号あり）
    book_pages.py index  --pdf FILE         # 索引を生成（ページ番号あり）
    book_pages.py starts --pdf FILE         # 各章の開始ページを JSON で出す
    book_pages.py bookmarks --pdf FILE      # しおりを注入（pikepdf が要る）

ページ番号は PDF から実測する。mdBook にページの概念はないので、これ以外に
知る方法がない（`build_pdf.sh` が2パス構成になっているのはこのため）。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

BOOKS = Path(__file__).resolve().parent.parent


# --- 版ごとの違い -------------------------------------------------------------
#
# 日本語版と英語版で違うのは、本の場所と、生成するページに書く文字列と、索引語だけ。
# 測り方（PDF から実測する2パス）は共通なので、ここに差分を集めて本体は共有する。

@dataclass(frozen=True)
class Edition:
    book: str                       # books/ の下のディレクトリ名
    toc_title: str
    index_title: str
    cover_label: str                # しおりの先頭項目
    chapter_label: Callable[[int], str]
    heading_re: str                 # 索引で「見出し行」と見なす行
    toc_page_first_line: str        # 目次ページを索引から外すための目印
    toc_note: str
    index_intro: str
    index_outro: str
    concepts: list[tuple[str, list[str]]]


SRC = None                          # 選ばれた版の src（load_edition が入れる）
EDITION = None
TOC_PATH = None
INDEX_PATH = None


def load_edition(name: str) -> None:
    global SRC, EDITION, TOC_PATH, INDEX_PATH
    EDITION = EDITIONS[name]
    SRC = BOOKS / EDITION.book / "src"
    TOC_PATH = SRC / "00-toc.md"
    INDEX_PATH = SRC / "zz-index.md"


# --- SUMMARY.md ---------------------------------------------------------------

def read_summary() -> list[dict]:
    """SUMMARY.md を「部の見出し」と「項目」の並びに読み替える。"""
    entries: list[dict] = []
    for line in (SRC / "SUMMARY.md").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("# ") and line != "# Summary":
            entries.append({"kind": "part", "title": line[2:].strip()})
            continue
        m = re.match(r'^-?\s*\[([^\]]+)\]\(([0-9a-z-]+\.md)\)$', line)
        if not m:
            continue
        title, href = m.group(1), m.group(2)
        # 表紙・目次・索引は目次に載せない（自分自身と前付け）
        if href in {"00-cover.md", "00-toc.md"}:
            continue
        entries.append({"kind": "item", "title": title, "href": href,
                        "numbered": line.startswith("-")})
    return entries


# --- PDF の実測 ---------------------------------------------------------------

def page_texts(pdf: Path) -> list[str]:
    """1ページ1要素のテキスト。pdftotext が要る。"""
    out = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                         capture_output=True, text=True, check=True).stdout
    # pdftotext はページ区切りに \f を入れる
    pages = out.split("\f")
    return pages[:-1] if pages and not pages[-1].strip() else pages


def heading_of(href: str) -> str:
    """その節の h1 見出し（PDF 上の見出し行と照合するため）。"""
    text = (SRC / href).read_text(encoding="utf-8")
    m = re.search(r'^#\s+(.+)$', text, re.M)
    return m.group(1).strip() if m else href


def measure_starts(pdf: Path) -> dict[str, int]:
    """各節が始まるページ番号（1 始まり）。

    判定は「そのページの最初の非空行が h1 見出しと一致すること」。ゆるく
    「ページ内に見出しが含まれるか」で探すと**目次ページが全章のタイトルを
    持っている**ので、どの章も目次のページ番号になってしまう。実際に一度
    そうなった。
    """
    pages = page_texts(pdf)
    # 長い章題は紙面で2行に折り返される（「第9章 命令的に書く — var・while・for・」
    # / 「IO」のように）。先頭2行をつないでから前方一致で見る。
    heads = []
    for p in pages:
        lines = [ln.strip() for ln in p.splitlines() if ln.strip()][:2]
        heads.append(re.sub(r'\s+', '', "".join(lines)))
    starts: dict[str, int] = {}
    for e in read_summary():
        if e["kind"] != "item":
            continue
        needle = re.sub(r'\s+', '', heading_of(e["href"]))
        for i, head in enumerate(heads, start=1):
            if head.startswith(needle):
                starts[e["href"]] = i
                break
    return starts


# --- 目次 ---------------------------------------------------------------------

def emit_toc(starts: dict[str, int] | None) -> str:
    lines = [f"# {EDITION.toc_title}", ""]
    if starts:
        lines += ["| | | |", "| --- | --- | ---: |"]
    else:
        lines += ["| | |", "| --- | --- |"]
    n = 0
    for e in read_summary():
        if e["kind"] == "part":
            cells = [f"**{e['title']}**", "", ""] if starts else [f"**{e['title']}**", ""]
            lines.append("| " + " | ".join(cells) + " |")
            continue
        label = ""
        if e["numbered"]:
            n += 1
            label = EDITION.chapter_label(n)
        link = f"[{e['title']}]({e['href']})"
        if starts:
            page = starts.get(e["href"])
            lines.append(f"| {label} | {link} | {page if page else ''} |")
        else:
            lines.append(f"| {label} | {link} |")
    lines += ["", "<div class=\"toc-note\">", "", EDITION.toc_note, "", "</div>", ""]
    return "\n".join(lines)


# --- 索引 ---------------------------------------------------------------------

# 索引語は人が選ぶ。自動抽出だと「診断」のような頻出語が並んで役に立たないため。
# (見出し語, 探す表記のリスト) の形。表記は完全一致で数える。
CONCEPTS_JA: list[tuple[str, list[str]]] = [
    ("値と型", []),
    ("Int（任意精度）", ["任意精度"]),
    ("Double", ["Double"]),
    ("String", ["String"]),
    ("Bool", ["Bool"]),
    ("Unit", ["Unit"]),
    ("Nothing", ["Nothing"]),
    ("タプル", ["タプル"]),
    ("型注釈", ["型注釈"]),
    ("局所型推論", ["局所型推論", "期待型"]),
    ("型変数", ["型変数"]),
    ("遅延評価", []),
    ("遅延評価", ["遅延評価"]),
    ("サンク", ["サンク"]),
    ("メモ化", ["メモ化"]),
    ("正格", ["strict let", "正格引数"]),
    ("force", ["force"]),
    ("deepForce", ["deepForce"]),
    ("seq", ["seq"]),
    ("無限リスト", ["無限リスト"]),
    ("ストリーム", ["ストリーム"]),
    ("関数", []),
    ("部分適用", ["部分適用"]),
    ("カリー化", ["カリー化"]),
    ("高階関数", ["高階関数"]),
    ("ラムダ", ["ラムダ"]),
    ("パイプライン", ["パイプライン", "|>"]),
    ("再帰", ["再帰関数"]),
    ("データと分岐", []),
    ("代数的データ型", ["代数的データ型", "ADT"]),
    ("パターンマッチ", ["パターンマッチ"]),
    ("網羅性", ["網羅性", "網羅的"]),
    ("反駁不能パターン", ["反駁不能", "反駁可能"]),
    ("レコード", ["レコード"]),
    ("Option", ["Option"]),
    ("Result", ["Result"]),
    ("null 安全", []),
    ("null 安全", ["null 安全"]),
    ("ナローイング", ["ナローイング", "絞り込"]),
    ("null 合体演算子", ["??"]),
    ("セーフナビゲーション", ["?."]),
    ("演算子", []),
    ("床除算", ["床除算", "//"]),
    ("複合代入", ["複合代入"]),
    ("短絡評価", ["短絡"]),
    ("命令的な機能", []),
    ("var", ["var "]),
    ("while", ["while"]),
    ("for", ["for "]),
    ("IO", ["IO:"]),
    ("モジュール", ["モジュール"]),
    ("道具と診断", []),
    ("診断コード", ["診断コード"]),
    ("explain", ["lune explain", ":explain"]),
    ("fmt", ["lune fmt"]),
    ("fix", ["lune fix"]),
    ("REPL", ["REPL"]),
    (":thunks", [":thunks"]),
    (":trace", [":trace"]),
    ("Playground", ["Playground"]),
]


# 英語版。分類は日本語版と同じで、探す表記だけ英語にしてある。
CONCEPTS_EN: list[tuple[str, list[str]]] = [
    ("Values and types", []),
    ("Int (arbitrary precision)", ["arbitrary precision"]),
    ("Double", ["Double"]),
    ("String", ["String"]),
    ("Bool", ["Bool"]),
    ("Unit", ["Unit"]),
    ("Nothing", ["Nothing"]),
    ("tuple", ["tuple"]),
    ("type annotation", ["type annotation"]),
    ("local type inference", ["expected type"]),
    ("type variable", ["type variable", "type parameter"]),
    ("Lazy evaluation", []),
    ("lazy evaluation", ["lazy evaluation"]),
    ("thunk", ["thunk"]),
    ("memoisation", ["memoisation", "memoise"]),
    ("strictness", ["strict let", "strict parameter"]),
    ("force", ["force"]),
    ("deepForce", ["deepForce"]),
    ("seq", ["seq "]),
    ("infinite list", ["infinite list"]),
    ("stream", ["stream"]),
    ("Functions", []),
    ("partial application", ["partial application"]),
    ("currying", ["curried", "currying"]),
    ("higher-order function", ["higher-order"]),
    ("lambda", ["lambda"]),
    ("pipeline", ["pipeline", "|>"]),
    ("recursion", ["recursive function", "recursion"]),
    ("Data and branching", []),
    ("algebraic data type", ["algebraic data type", "ADT"]),
    ("pattern matching", ["pattern matching"]),
    ("exhaustiveness", ["exhaustive"]),
    ("irrefutable pattern", ["irrefutable", "refutable"]),
    ("record", ["record"]),
    ("Option", ["Option"]),
    ("Result", ["Result"]),
    ("Null safety", []),
    ("null safety", ["null safety"]),
    ("narrowing", ["narrow"]),
    ("null coalescing", ["??"]),
    ("safe navigation", ["?."]),
    ("Operators", []),
    ("floor division", ["floor division", "//"]),
    ("compound assignment", ["compound assignment"]),
    ("short-circuiting", ["short-circuit"]),
    ("Imperative features", []),
    ("var", ["var "]),
    ("while", ["while"]),
    ("for", ["for "]),
    ("IO", ["IO:"]),
    ("modules", ["module"]),
    ("Tools and diagnostics", []),
    ("diagnostic code", ["diagnostic code"]),
    ("explain", ["lune explain", ":explain"]),
    ("fmt", ["lune fmt"]),
    ("fix", ["lune fix"]),
    ("REPL", ["REPL"]),
    (":thunks", [":thunks"]),
    (":trace", [":trace"]),
    ("Playground", ["Playground"]),
]


EDITIONS: dict[str, Edition] = {
    "ja": Edition(
        book="lune-book",
        toc_title="目次",
        index_title="索引",
        cover_label="表紙",
        chapter_label=lambda n: f"第{n}章",
        heading_re=r'^\s*(序章|第\d+章|付録[A-E]|\d+\.\d+ |目次|索引)',
        toc_page_first_line="目次",
        toc_note="章の中の節までは載せていません。HTML 版では左の目次から、"
                 "PDF 版ではしおりからたどれます。",
        index_intro="本文と付録に現れる主な用語です。ページ番号は PDF 版のものです"
                    "（HTML 版では上の検索が使えます）。",
        index_outro="付録B（標準ライブラリ）・付録C（診断コード）・"
                    "付録D（CLI と REPL）は、それぞれの一覧そのものが索引として使えます。",
        concepts=CONCEPTS_JA,
    ),
    "en": Edition(
        book="lune-book-en",
        toc_title="Contents",
        index_title="Index",
        cover_label="Cover",
        chapter_label=lambda n: f"Chapter {n}",
        heading_re=r'^\s*(Preface|Chapter \d+|Appendix [A-E]|\d+\.\d+ |Contents|Index)',
        toc_page_first_line="Contents",
        toc_note="Sections within a chapter are not listed. Follow them from the "
                 "sidebar in the HTML edition, or from the bookmarks in the PDF.",
        index_intro="The main terms appearing in the chapters and appendices. The page "
                    "numbers are those of the PDF edition (in HTML, use the search above).",
        index_outro="Appendix B (the standard library), appendix C (the diagnostic codes) "
                    "and appendix D (the CLI and the REPL) are themselves usable as indexes.",
        concepts=CONCEPTS_EN,
    ),
}

MAX_PAGES = 8          # 1 語あたりに載せるページ数の上限
TOO_COMMON = 40        # これより多くのページに出る語は、見出しに出るページだけ載せる


def emit_index(pdf: Path) -> str:
    pages = page_texts(pdf)
    flat = [re.sub(r'[ \t]+', ' ', p) for p in pages]
    # 見出し行（章題・節題）だけを集めたページごとのテキスト
    heads = []
    for p in flat:
        hs = [ln.strip() for ln in p.splitlines()
              if re.match(EDITION.heading_re, ln.strip())]
        heads.append("\n".join(hs))

    # 前付けと索引自身は対象から外す。
    #  - 目次は本文の語を大量に含むので、入れると索引が目次のページで埋まる
    #  - 表紙は副題に「遅延評価」を含むので、その語が p.1 を指してしまう
    #  - 索引以降は索引自身
    starts = measure_starts(pdf)
    skip = {1}                              # 表紙
    idx = starts.get("zz-index.md")
    if idx:
        skip |= set(range(idx, len(flat) + 1))
    for i, p in enumerate(flat, start=1):
        first = next((ln.strip() for ln in p.splitlines() if ln.strip()), "")
        if first == EDITION.toc_page_first_line:
            skip.add(i)

    lines = [f"# {EDITION.index_title}", "", EDITION.index_intro, ""]
    for label, needles in EDITION.concepts:
        if not needles:                    # 分類の見出し
            lines += ["", f"**{label}**", ""]
            continue
        hits = sorted({i for i in range(1, len(flat) + 1)
                       if i not in skip
                       for nd in needles if nd in flat[i - 1]})
        if not hits:
            continue
        if len(hits) > TOO_COMMON:
            in_head = sorted({i for i in range(1, len(flat) + 1)
                              if i not in skip
                              for nd in needles if nd in heads[i - 1]})
            hits = in_head or hits[:MAX_PAGES]
        shown = hits[:MAX_PAGES]
        more = "…" if len(hits) > len(shown) else ""
        lines.append(f"- {label} … {', '.join(str(p) for p in shown)}{more}")
    lines += ["", EDITION.index_outro, ""]
    return "\n".join(lines)


# --- しおり -------------------------------------------------------------------

def inject_bookmarks(pdf: Path, starts: dict[str, int]) -> bool:
    try:
        import pikepdf
    except ImportError:
        return False
    titles = {e["href"]: e["title"] for e in read_summary() if e["kind"] == "item"}
    order = [e["href"] for e in read_summary() if e["kind"] == "item"]
    with pikepdf.open(pdf, allow_overwriting_input=True) as doc:
        with doc.open_outline() as outline:
            outline.root.clear()
            outline.root.append(pikepdf.OutlineItem(EDITION.cover_label, 0))
            for href in order:
                page = starts.get(href)
                if page is None:
                    continue
                outline.root.append(pikepdf.OutlineItem(titles[href], page - 1))
        doc.save()
    return True


# --- CLI ----------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("toc", "index", "starts", "bookmarks"))
    ap.add_argument("--pdf", type=Path)
    ap.add_argument("--edition", choices=tuple(EDITIONS), default="ja",
                    help="どちらの版を対象にするか (既定: ja)")
    args = ap.parse_args(argv)
    load_edition(args.edition)

    if args.command == "toc":
        starts = measure_starts(args.pdf) if args.pdf else None
        TOC_PATH.write_text(emit_toc(starts) + "\n", encoding="utf-8")
        print(f"{TOC_PATH.name}: 生成 ({'ページ番号あり' if starts else 'ページ番号なし'})")
        return 0

    if args.command == "index":
        if not args.pdf:
            ap.error("index には --pdf が要る")
        INDEX_PATH.write_text(emit_index(args.pdf) + "\n", encoding="utf-8")
        print(f"{INDEX_PATH.name}: 生成")
        return 0

    if args.command == "starts":
        if not args.pdf:
            ap.error("starts には --pdf が要る")
        print(json.dumps(measure_starts(args.pdf), ensure_ascii=False, indent=1))
        return 0

    if args.command == "bookmarks":
        if not args.pdf:
            ap.error("bookmarks には --pdf が要る")
        ok = inject_bookmarks(args.pdf, measure_starts(args.pdf))
        print("しおり: 注入" if ok else "しおり: 省略 (pikepdf がない)")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
