"""Run the Playground's own Python driver.

The driver lives inside playground/index.html as a JavaScript template literal,
which put it beyond every test in this suite: it is the one piece of Python in
the project that only ever ran in a browser. It is also where multi-file
support lives — writing each module beside the entry so that `import` resolves
the same way it does on disk — so it is worth executing here rather than only
clicking through Pyodide.

The extraction unescapes the template literal and points `/app` at a temporary
directory; nothing else about the code is changed.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_driver(app_dir: Path) -> dict:
    html = (ROOT / "playground" / "index.html").read_text(encoding="utf-8")
    match = re.search(r"const DRIVER = `(.*?)\n`;", html, re.S)
    assert match, "DRIVER template literal not found in playground/index.html"
    # Undo the JavaScript template literal's escapes (\` \\ \$) so that what we
    # compile is the Python the browser actually runs — `"\\n"` in the file is a
    # newline escape in the Python source, not a literal backslash.
    unescaped = re.sub(r"\\(.)", lambda m: m.group(1) if m.group(1) in "`$\\" else m.group(0), match.group(1), flags=re.S)
    source = unescaped.replace("/app", str(app_dir))
    namespace: dict = {}
    exec(compile(source, "playground/index.html (DRIVER)", "exec"), namespace)
    return namespace


ENTRY_SOURCE = """module main

import geometry

let answer = area(3.0, 4.0)
"""

GEOMETRY = """module geometry

def area(width: Double, height: Double): Double =
    width * height
"""


class DriverModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Path(self.tmp.name)
        self.app.mkdir(exist_ok=True)
        self.driver = load_driver(self.app)
        self.addCleanup(self.tmp.cleanup)

    def modules(self, *pairs: tuple[str, str]) -> str:
        return json.dumps([{"n": name, "c": code} for name, code in pairs])

    def test_an_imported_module_is_written_beside_the_entry(self) -> None:
        out = self.driver["lune_check"](ENTRY_SOURCE, "en", self.modules(("geometry", GEOMETRY)))
        self.assertIn("type check OK", out)
        self.assertTrue((self.app / "geometry.lune").exists())

    def test_the_program_runs_across_both_files(self) -> None:
        out = self.driver["lune_run"](ENTRY_SOURCE, "answer", False, "en", self.modules(("geometry", GEOMETRY)))
        self.assertEqual(out.strip(), "12.0")

    def test_a_dotted_name_becomes_a_subdirectory(self) -> None:
        """`import util.text` resolves to util/text.lune, as it does on disk."""
        entry = 'module main\n\nimport util.text\n\nlet answer = shout("hi")\n'
        module = 'module util.text\n\ndef shout(s: String): String =\n    s + "!"\n'
        out = self.driver["lune_run"](entry, "answer", False, "en", self.modules(("util.text", module)))
        self.assertEqual(out.strip(), '"hi!"')
        self.assertTrue((self.app / "util" / "text.lune").exists())

    def test_a_removed_module_stops_resolving(self) -> None:
        """The trap: a file left behind keeps a deleted tab's module importable.

        The program would then work in the Playground and nowhere else.
        """
        self.driver["lune_check"](ENTRY_SOURCE, "en", self.modules(("geometry", GEOMETRY)))
        out = self.driver["lune_check"](ENTRY_SOURCE, "en", "[]")
        self.assertIn("MOD0001", out)
        self.assertFalse((self.app / "geometry.lune").exists())

    def test_a_single_file_program_still_needs_no_modules(self) -> None:
        """The book's and tutorial's links call this with no module argument."""
        out = self.driver["lune_run"]("let answer = 40 + 2\n", "answer", False, "en")
        self.assertEqual(out.strip(), "42")


    def test_the_multi_file_sample_on_the_page_actually_works(self) -> None:
        """The `import で分ける` preset is the feature's shop window.

        It is offered to someone who has never seen Lune, so it had better
        type-check and produce the number it promises.
        """
        html = (ROOT / "playground" / "index.html").read_text(encoding="utf-8")
        preset = re.search(r"\n  modules: \{(.*?)\n  \},\n\};", html, re.S)
        self.assertIsNotNone(preset, "the `modules` preset is gone from playground/index.html")
        codes = re.findall(r"code: `(.*?)`", preset.group(1), re.S)
        self.assertEqual(len(codes), 2, "expected an entry and one module")
        name = re.search(r'name: "([\w.]+)"', preset.group(1))
        binding = re.search(r'binding: "(\w+)"', preset.group(1))

        out = self.driver["lune_run"](codes[0], binding.group(1), False, "en", self.modules((name.group(1), codes[1])))
        self.assertEqual(out.strip(), "12.0")


class DriverWiringTests(unittest.TestCase):
    def test_the_page_passes_every_file_to_the_driver(self) -> None:
        """Run and check mean the whole program, not the tab on screen."""
        html = (ROOT / "playground" / "index.html").read_text(encoding="utf-8")
        self.assertIn('call("lune_run", entryCode(), $("binding").value, $("trace").checked, $("lang").value, modulesJson())', html)
        self.assertIn('call("lune_check", entryCode(), $("lang").value, modulesJson())', html)


if __name__ == "__main__":
    unittest.main()
