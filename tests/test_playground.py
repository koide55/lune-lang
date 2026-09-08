from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class PlaygroundTests(unittest.TestCase):
    def test_playground_fetches_every_lune_module(self) -> None:
        """playground/index.html hardcodes the module list; it must not go stale.

        (A missing entry surfaces only at runtime in the browser as a
        ModuleNotFoundError — this has happened twice.)
        """
        html = (ROOT / "playground" / "index.html").read_text(encoding="utf-8")
        match = re.search(r"const LUNE_FILES = \[(.*?)\];", html, re.DOTALL)
        assert match is not None, "LUNE_FILES not found in playground/index.html"
        listed = set(re.findall(r'"([\w.]+\.py)"', match.group(1)))
        actual = {path.name for path in (ROOT / "lune").glob("*.py")}
        self.assertEqual(listed, actual)

    def test_playground_uses_relative_paths(self) -> None:
        """GitHub Pages serves the site under a subpath — absolute /lune/ breaks."""
        html = (ROOT / "playground" / "index.html").read_text(encoding="utf-8")
        self.assertIn("fetch(`../lune/${f}`", html)
        self.assertNotIn("fetch(`/lune/", html)

    def test_error_catalog_page_references_both_indexes(self) -> None:
        html = (ROOT / "playground" / "errors.html").read_text(encoding="utf-8")
        self.assertIn("../documents/ERROR_INDEX_JA.md", html)
        self.assertIn("../documents/ERROR_INDEX.md", html)

    def test_landing_page_links_playground_and_catalog(self) -> None:
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="playground/"', html)
        self.assertIn('href="playground/errors.html"', html)

    def test_landing_page_and_readme_link_the_book(self) -> None:
        """The textbook was finished but unreachable: no entry point linked it."""
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="book/"', html)
        self.assertIn('href="book/lune-book.pdf"', html)

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("https://koide55.github.io/lune-lang/book/", readme)

    def test_pages_workflow_builds_the_book_where_the_links_point(self) -> None:
        """`book/` is not in the repo — only the Pages build produces it.

        If the workflow's output paths and the links drift apart, the result is
        a 404 that nothing else in the test suite would notice.
        """
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertIn('--dest-dir "$GITHUB_WORKSPACE/book"', workflow)
        self.assertIn('build_pdf.sh "$GITHUB_WORKSPACE/book/lune-book.pdf"', workflow)

    def test_published_pages_contain_no_mojibake(self) -> None:
        """The landing page once shipped with U+FFFD in the Japanese hero sample.

        Every page GitHub Pages serves is hand-written UTF-8 with Japanese text;
        a replacement character means an editor or paste mangled it.
        """
        for page in (ROOT / "index.html", ROOT / "playground" / "index.html", ROOT / "playground" / "errors.html"):
            with self.subTest(page=page.relative_to(ROOT)):
                raw = page.read_bytes()
                text = raw.decode("utf-8")  # strict: invalid bytes fail here
                self.assertNotIn("\ufffd", text)


if __name__ == "__main__":
    unittest.main()
