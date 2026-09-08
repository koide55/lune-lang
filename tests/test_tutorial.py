"""The tutorial's Playground links must still match the code above them.

The book generates its links in the browser, so they cannot rot. Markdown read
on GitHub runs no JavaScript, so the tutorial's links carry a copy of the code
in the URL — and a copy is exactly what goes stale the first time the example
is edited. tools/playground_links.py generates them; this keeps them honest.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import playground_links  # noqa: E402

TUTORIALS = [ROOT / "documents" / "TUTORIAL.md", ROOT / "documents" / "TUTORIAL_EN.md"]


class PlaygroundLinkTests(unittest.TestCase):
    def test_links_match_the_code_above_them(self) -> None:
        problems = [p for path in TUTORIALS for p in playground_links.check(path)]
        self.assertEqual(problems, [], "run `tools/playground_links.py write` to regenerate")

    def test_both_tutorials_carry_the_same_links(self) -> None:
        """The two are translations of one another; a link added to one belongs in both."""
        counts = {path.name: len(playground_links.LINK.findall(path.read_text(encoding="utf-8"))) for path in TUTORIALS}
        self.assertEqual(len(set(counts.values())), 1, counts)
        self.assertGreater(min(counts.values()), 0)

    def test_the_encoding_round_trips(self) -> None:
        code = 'let x = 1\nlet answer = "日本語も通る"\n'
        state = playground_links.decode(playground_links.encode(code, "ja"))
        self.assertEqual(state["c"], code)
        self.assertEqual(state["l"], "ja")
        self.assertEqual(state["b"], "")  # empty on purpose: the Playground picks

    def test_drift_is_detected(self) -> None:
        """A test that cannot fail is worthless; make the failure path run."""
        with self.subTest("edited code"):
            good = playground_links.encode("let a = 1\n", "ja")
            text = f"```lune\nlet a = 2\n```\n\n[▶ Playground で開く]({good})\n"
            self.assertTrue(self._problems(text))
        with self.subTest("matching code"):
            text = f"```lune\nlet a = 1\n```\n\n[▶ Playground で開く]({good})\n"
            self.assertFalse(self._problems(text))

    def _problems(self, text: str) -> list[str]:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "TUTORIAL.md"
            path.write_text(text, encoding="utf-8")
            return playground_links.check(path)


if __name__ == "__main__":
    unittest.main()
