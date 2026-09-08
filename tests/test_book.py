"""Structural checks on the textbook.

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
SRC = ROOT / "books" / "lune-book" / "src"

LINK = re.compile(r"\]\(([^)\s]+)\)")
FENCE = re.compile(r"^```.*?^```", re.S | re.M)
INLINE_CODE = re.compile(r"`[^`\n]*`")


def prose(markdown: str) -> str:
    """Drop code so that `def f[T](...)` is not read as a link to `...`."""
    return INLINE_CODE.sub("", FENCE.sub("", markdown))


def pages() -> list[Path]:
    return sorted(p for p in SRC.glob("*.md") if p.name != "SUMMARY.md")


class SummaryTests(unittest.TestCase):
    def test_every_entry_points_at_a_file_that_exists(self) -> None:
        """mdBook CREATES a missing chapter file rather than failing the build.

        So a typo in SUMMARY.md builds green while that chapter quietly
        vanishes from the book — no error, just a page of placeholder text
        where a chapter used to be. Nothing but this check would notice.
        """
        summary = (SRC / "SUMMARY.md").read_text(encoding="utf-8")
        for entry in LINK.findall(summary):
            with self.subTest(entry=entry):
                self.assertTrue((SRC / entry).exists(), f"{entry} is in SUMMARY.md but not on disk")

    def test_every_page_is_reachable_from_the_summary(self) -> None:
        """SUMMARY.md is the table of contents; a page it omits is unreadable."""
        summary = (SRC / "SUMMARY.md").read_text(encoding="utf-8")
        listed = set(LINK.findall(summary))
        for page in pages():
            with self.subTest(page=page.name):
                self.assertIn(page.name, listed)


class PlaygroundLinkTests(unittest.TestCase):
    """The book's "Playground で開く" links carry the code in the URL itself.

    Nothing resolves those links at build time, so a drift between the two
    sides of the format would only show up as a Playground that opens with the
    wrong content — or with the default sample, which looks like it worked.
    """

    THEME = ROOT / "books" / "lune-book" / "theme"

    def test_the_theme_files_are_registered(self) -> None:
        book_toml = (ROOT / "books" / "lune-book" / "book.toml").read_text(encoding="utf-8")
        self.assertIn("theme/playground.css", book_toml)
        self.assertIn('additional-js = ["theme/playground.js"]', book_toml)
        for name in ("playground.js", "playground.css"):
            self.assertTrue((self.THEME / name).exists())

    def test_both_sides_agree_on_the_share_format(self) -> None:
        js = (self.THEME / "playground.js").read_text(encoding="utf-8")
        playground = (ROOT / "playground" / "index.html").read_text(encoding="utf-8")

        self.assertIn('"#s=" + b64', js)  # what the book writes
        self.assertIn('location.hash.match(/^#s=(.+)$/)', playground)  # what reads it

        # The state object's keys, which decodeState picks apart by name.
        self.assertIn('{ c: source, b: "", t: false, l: "ja" }', js)
        for key in ("state.c", "state.b", "state.t", "state.l"):
            self.assertIn(key, playground)

    def test_links_point_at_the_published_playground(self) -> None:
        """A relative path would break in the PDF and in a local mdbook serve."""
        js = (self.THEME / "playground.js").read_text(encoding="utf-8")
        self.assertIn('"https://koide55.github.io/lune-lang/playground/"', js)

    def test_the_links_are_hidden_in_print(self) -> None:
        """print.html runs the script too, and paper links cannot be clicked."""
        css = (self.THEME / "playground.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"@media print \{[^}]*\.playground-open \{ display: none;")


class LinkTests(unittest.TestCase):
    def test_relative_links_resolve(self) -> None:
        """mdBook does not check links; a renamed chapter leaves live 404s."""
        for page in [*pages(), SRC / "SUMMARY.md"]:
            for link in LINK.findall(prose(page.read_text(encoding="utf-8"))):
                if link.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                target = link.split("#", 1)[0]
                if not target:
                    continue
                with self.subTest(page=page.name, link=link):
                    self.assertTrue(
                        (SRC / target).exists() or (ROOT / target).exists(),
                        f"{page.name} links to {target}, which does not exist",
                    )


if __name__ == "__main__":
    unittest.main()
