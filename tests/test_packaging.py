"""Checks on what the package will look like on PyPI.

CI already builds the distributions and installs the wheel. What it cannot see
is the project page: the README becomes the long description, and PyPI renders
it out of the repository, where relative links have nothing to point at.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import lune

try:
    import tomllib  # 3.11+; the interpreter itself still supports 3.10
except ModuleNotFoundError:  # pragma: no cover - depends on the running version
    tomllib = None

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"\]\(([^)\s]+)\)")

needs_tomllib = unittest.skipIf(tomllib is None, "tomllib needs Python 3.11+")


def pyproject() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


class ReadmeTests(unittest.TestCase):
    def test_no_relative_links(self) -> None:
        """The README is the PyPI description; relative links 404 there.

        GitHub resolves them, so this is invisible until someone opens the
        project page — by which time the release is already published.
        """
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        relative = [
            target
            for target in LINK.findall(readme)
            if not target.startswith(("http://", "https://", "#", "mailto:"))
        ]
        self.assertEqual(relative, [], "use absolute https://github.com/... URLs in README.md")

    @needs_tomllib
    def test_the_readme_is_the_described_file(self) -> None:
        self.assertEqual(pyproject()["project"]["readme"], "README.md")


@needs_tomllib
class MetadataTests(unittest.TestCase):
    def test_the_version_has_a_single_source(self) -> None:
        project = pyproject()["project"]
        self.assertEqual(project["dynamic"], ["version"])
        self.assertNotIn("version", project)

    def test_the_distribution_name_is_the_available_one(self) -> None:
        """`lune` on PyPI is taken by an unrelated package (checked 2026-09-08)."""
        self.assertEqual(pyproject()["project"]["name"], "lune-lang")

    def test_sdist_patterns_are_anchored(self) -> None:
        """Unanchored patterns match at any depth.

        `lune` pulled in bin/lune and `README.md` pulled in every nested one,
        so the sdist carried files from directories it never meant to ship.
        """
        include = pyproject()["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
        for pattern in include:
            with self.subTest(pattern=pattern):
                self.assertTrue(pattern.startswith("/"), f"{pattern} is not anchored")


class PublishWorkflowTests(unittest.TestCase):
    WORKFLOW = ROOT / ".github" / "workflows" / "publish.yml"

    def test_it_publishes_without_a_stored_token(self) -> None:
        """Trusted publishing: no API token exists to leak or rotate."""
        workflow = self.WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("id-token: write", workflow)
        self.assertIn("pypa/gh-action-pypi-publish", workflow)
        self.assertNotIn("secrets.", workflow)

    def test_the_release_procedure_names_this_workflow(self) -> None:
        """PyPI's trusted publisher is configured against the file name."""
        procedure = (ROOT / "documents" / "RELEASING.md").read_text(encoding="utf-8")
        self.assertIn("publish.yml", procedure)
        self.assertIn(lune.__version__, procedure, "the worked example uses the current version")


if __name__ == "__main__":
    unittest.main()
