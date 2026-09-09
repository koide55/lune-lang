"""Structural checks on the textbook, in both editions.

`books/tools/check_examples.sh` already runs every code example through the
real CLI. These are the checks that do not need the toolchain: that the book
still holds together as a book. They are cheap enough to run with the unit
tests, which is the point — CI builds the book with mdBook, but that is a
minute away and only tells you the build succeeded.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOKS = {
    "ja": ROOT / "books" / "lune-book",
    "en": ROOT / "books" / "lune-book-en",
}
EXAMPLES = {"ja": ROOT / "books" / "examples", "en": ROOT / "books" / "examples-en"}

LINK = re.compile(r"\]\(([^)\s]+)\)")
FENCE = re.compile(r"^```.*?^```", re.S | re.M)
INLINE_CODE = re.compile(r"`[^`\n]*`")


def prose(markdown: str) -> str:
    """Drop code so that `def f[T](...)` is not read as a link to `...`."""
    return INLINE_CODE.sub("", FENCE.sub("", markdown))


def pages(book: Path) -> list[Path]:
    return sorted(p for p in (book / "src").glob("*.md") if p.name != "SUMMARY.md")


class SummaryTests(unittest.TestCase):
    def test_every_entry_points_at_a_file_that_exists(self) -> None:
        """mdBook CREATES a missing chapter file rather than failing the build.

        So a typo in SUMMARY.md builds green while that chapter quietly
        vanishes from the book — no error, just a page of placeholder text
        where a chapter used to be. Nothing but this check would notice.
        """
        for edition, book in BOOKS.items():
            summary = (book / "src" / "SUMMARY.md").read_text(encoding="utf-8")
            for entry in LINK.findall(summary):
                with self.subTest(edition=edition, entry=entry):
                    self.assertTrue(
                        (book / "src" / entry).exists(), f"{entry} is in SUMMARY.md but not on disk"
                    )

    def test_every_page_is_reachable_from_the_summary(self) -> None:
        """SUMMARY.md is the table of contents; a page it omits is unreadable."""
        for edition, book in BOOKS.items():
            summary = (book / "src" / "SUMMARY.md").read_text(encoding="utf-8")
            listed = set(LINK.findall(summary))
            for page in pages(book):
                with self.subTest(edition=edition, page=page.name):
                    self.assertIn(page.name, listed)


class PlaygroundLinkTests(unittest.TestCase):
    """The book's "Open in the Playground" links carry the code in the URL.

    Nothing resolves those links at build time, so a drift between the two
    sides of the format would only show up as a Playground that opens with the
    wrong content — or with the default sample, which looks like it worked.
    """

    def theme(self, edition: str) -> Path:
        return BOOKS[edition] / "theme"

    def test_the_theme_files_are_registered(self) -> None:
        for edition, book in BOOKS.items():
            with self.subTest(edition=edition):
                book_toml = (book / "book.toml").read_text(encoding="utf-8")
                self.assertIn("theme/playground.css", book_toml)
                self.assertIn('additional-js = ["theme/playground.js"]', book_toml)
                for name in ("playground.js", "playground.css"):
                    self.assertTrue((book / "theme" / name).exists())

    def test_both_sides_agree_on_the_share_format(self) -> None:
        playground = (ROOT / "playground" / "index.html").read_text(encoding="utf-8")
        self.assertIn('location.hash.match(/^#s=(.+)$/)', playground)  # what reads it
        for key in ("state.c", "state.b", "state.t", "state.l"):
            self.assertIn(key, playground)

        for edition in BOOKS:
            with self.subTest(edition=edition):
                js = (self.theme(edition) / "playground.js").read_text(encoding="utf-8")
                self.assertIn('"#s=" + b64', js)  # what the book writes
                self.assertIn(f'{{ c: source, b: "", t: false, l: "{edition}" }}', js)

    def test_links_point_at_the_published_playground(self) -> None:
        """A relative path would break in the PDF and in a local mdbook serve."""
        for edition in BOOKS:
            with self.subTest(edition=edition):
                js = (self.theme(edition) / "playground.js").read_text(encoding="utf-8")
                self.assertIn('"https://koide55.github.io/lune-lang/playground/"', js)

    def test_the_links_are_hidden_in_print(self) -> None:
        """print.html runs the script too, and paper links cannot be clicked."""
        for edition in BOOKS:
            with self.subTest(edition=edition):
                css = (self.theme(edition) / "playground.css").read_text(encoding="utf-8")
                self.assertRegex(css, r"@media print \{[^}]*\.playground-open \{ display: none;")


class LinkTests(unittest.TestCase):
    def test_relative_links_resolve(self) -> None:
        """mdBook does not check links; a renamed chapter leaves live 404s."""
        for edition, book in BOOKS.items():
            for page in [*pages(book), book / "src" / "SUMMARY.md"]:
                for link in LINK.findall(prose(page.read_text(encoding="utf-8"))):
                    if link.startswith(("http://", "https://", "mailto:", "#")):
                        continue
                    target = link.split("#", 1)[0]
                    if not target:
                        continue
                    with self.subTest(edition=edition, page=page.name, link=link):
                        self.assertTrue(
                            (book / "src" / target).exists() or (ROOT / target).exists(),
                            f"{page.name} links to {target}, which does not exist",
                        )


class RetiredTutorialTests(unittest.TestCase):
    """The tutorials were merged into the book on 2026-09-09.

    The files stay as signposts because URLs pointing at them are already
    published (the PyPI description among them), but they must not grow back
    into a second copy of the material — maintaining the same content twice
    is what the merge was for.
    """

    TUTORIALS = {
        "documents/TUTORIAL.md": "https://koide55.github.io/lune-lang/book/",
        "documents/TUTORIAL_EN.md": "https://koide55.github.io/lune-lang/book/en/",
    }

    def test_they_point_at_the_book(self) -> None:
        for name, url in self.TUTORIALS.items():
            with self.subTest(file=name):
                text = (ROOT / name).read_text(encoding="utf-8")
                self.assertIn(url, text)

    def test_they_stayed_signposts(self) -> None:
        """A pointer, not a tutorial: no code examples, and short."""
        for name in self.TUTORIALS:
            with self.subTest(file=name):
                text = (ROOT / name).read_text(encoding="utf-8")
                self.assertNotIn("```lune", text)
                self.assertLess(len(text.splitlines()), 60)


class PdfBuildTests(unittest.TestCase):
    """Both editions are built by the same two-pass script."""

    def test_the_script_knows_both_editions(self) -> None:
        script = (ROOT / "books" / "tools" / "build_pdf.sh").read_text(encoding="utf-8")
        self.assertIn("lune-book)    EDITION=ja", script)
        self.assertIn("lune-book-en) EDITION=en", script)

    def test_each_edition_has_a_generated_contents_and_index(self) -> None:
        """Committed without page numbers for HTML; swapped during the PDF build."""
        for edition, book in BOOKS.items():
            for name in ("00-toc.md", "zz-index.md"):
                with self.subTest(edition=edition, page=name):
                    self.assertTrue((book / "src" / name).exists())

    def test_the_pdf_check_string_matches_the_edition(self) -> None:
        """A PDF can be produced and still be unreadable; the check greps the
        text layer, so the string has to be one that edition really contains."""
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertIn("pdf-must-contain: The Lune Programming Language", workflow)
        cover = (BOOKS["en"] / "src" / "00-cover.md").read_text(encoding="utf-8")
        self.assertIn("The Lune Programming Language", cover)


class TranslationTests(unittest.TestCase):
    """The English edition is a translation, not a fork.

    It is being written a chapter at a time, so it is allowed to be shorter —
    but a chapter it does have must line up with the Japanese one, or the two
    editions quietly become different books.
    """

    def test_the_english_edition_translates_existing_chapters(self) -> None:
        ja_pages = {p.name for p in pages(BOOKS["ja"])}
        for page in pages(BOOKS["en"]):
            with self.subTest(page=page.name):
                self.assertIn(page.name, ja_pages, "no Japanese chapter with this name")

    def test_the_english_examples_mirror_the_japanese_ones(self) -> None:
        """Same file names, so books/tools/check_examples.sh can drive both
        editions from one list of assertions."""
        for chapter in sorted(p for p in EXAMPLES["en"].glob("ch*") if p.is_dir()):
            ja_chapter = EXAMPLES["ja"] / chapter.name
            with self.subTest(chapter=chapter.name):
                self.assertTrue(ja_chapter.is_dir(), "no Japanese chapter of examples")
                en_files = {p.relative_to(chapter) for p in chapter.rglob("*.lune")}
                ja_files = {p.relative_to(ja_chapter) for p in ja_chapter.rglob("*.lune")}
                self.assertEqual(en_files, ja_files)

    def test_the_english_edition_is_written_in_english(self) -> None:
        """A sentence half-translated is easy to leave behind and hard to spot.

        The English edition talks *about* `--lang ja`, but never in Japanese.
        """
        japanese = re.compile(r"[ぁ-んァ-ヶ一-龠]")
        for page in pages(BOOKS["en"]) + [BOOKS["en"] / "src" / "SUMMARY.md"]:
            with self.subTest(page=page.name):
                found = japanese.search(page.read_text(encoding="utf-8"))
                self.assertIsNone(found, found and f"untranslated: ...{found.string[max(0, found.start() - 40):found.end() + 40]}...")

    def test_the_english_examples_are_not_in_japanese(self) -> None:
        """Comments have to be translated too; the code itself is the same."""
        japanese = re.compile(r"[ぁ-んァ-ヶ一-龠]")
        for path in sorted(EXAMPLES["en"].rglob("*.lune")):
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIsNone(japanese.search(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
