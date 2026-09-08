#!/usr/bin/env python3
"""Keep「Playground で開く」links in Markdown in step with the code above them.

The textbook builds its links in the browser (`books/lune-book/theme/playground.js`),
so they cannot go stale. Markdown read on GitHub has no JavaScript, so the
tutorial's links are written into the file — and a link that carries a copy of
the code is exactly the kind of thing that rots the first time the code is
edited. This tool is the answer: the link is generated from the block above it,
and `check` (which the test suite runs) fails if the two have drifted apart.

    tools/playground_links.py check documents/TUTORIAL.md ...   # verify
    tools/playground_links.py write documents/TUTORIAL.md ...   # regenerate

To add a link, write the marker line under a ```lune block and run `write`:

    [▶ Playground で開く](#)

The URL format is the Playground's own share link (`#s=` + base64url of a JSON
state), the same one the share button writes and the book's theme generates.
"""

from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

PLAYGROUND = "https://koide55.github.io/lune-lang/playground/"

# A managed link: the label starts with ▶ and the target is the Playground (or
# the `(#)` placeholder that asks `write` to fill it in).
LINK = re.compile(r"^\[▶ [^\]]+\]\((#|" + re.escape(PLAYGROUND) + r"#s=[\w-]*)\)$", re.M)
LUNE_BLOCK = re.compile(r"^```lune\n(.*?)^```$", re.S | re.M)


def encode(code: str, lang: str) -> str:
    """The URL the Playground reads. Mirrors encodeState() in playground/index.html.

    `b` is left empty on purpose: the Playground picks the binding to evaluate
    with the real parser, which beats guessing from here.
    """
    state = {"c": code, "b": "", "t": False, "l": lang}
    raw = json.dumps(state, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return PLAYGROUND + "#s=" + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode(url: str) -> dict | None:
    if not url.startswith(PLAYGROUND + "#s="):
        return None
    payload = url[len(PLAYGROUND) + 3:]
    payload += "=" * (-len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
    except Exception:
        return None


def language_of(path: Path) -> str:
    return "en" if path.name.endswith("_EN.md") else "ja"


def preceding_block(text: str, position: int) -> str | None:
    """The ```lune block the link at `position` belongs to — the nearest above."""
    blocks = [m for m in LUNE_BLOCK.finditer(text) if m.end() <= position]
    return blocks[-1].group(1) if blocks else None


def check(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    lang = language_of(path)
    problems = []
    for match in LINK.finditer(text):
        line = text[: match.start()].count("\n") + 1
        where = f"{path}:{line}"
        code = preceding_block(text, match.start())
        if code is None:
            problems.append(f"{where}: link with no ```lune block above it")
            continue
        if match.group(1) == "#":
            problems.append(f"{where}: placeholder link — run `tools/playground_links.py write`")
            continue
        state = decode(match.group(1))
        if state is None:
            problems.append(f"{where}: link payload does not decode")
        elif state.get("c") != code:
            problems.append(f"{where}: link no longer matches the code above it")
        elif state.get("l") != lang:
            problems.append(f"{where}: link language is {state.get('l')!r}, expected {lang!r}")
    return problems


def write(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    lang = language_of(path)
    changed = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal changed
        code = preceding_block(text, match.start())
        if code is None:
            return match.group(0)
        label = match.group(0).split("]", 1)[0] + "]"
        new = f"{label}({encode(code, lang)})"
        if new != match.group(0):
            changed += 1
        return new

    updated = LINK.sub(replace, text)
    if updated != text:
        path.write_text(updated, encoding="utf-8")
    return changed


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] not in ("check", "write"):
        print(__doc__, file=sys.stderr)
        return 2
    command, paths = argv[1], [Path(p) for p in argv[2:]]
    if command == "write":
        for path in paths:
            print(f"{path}: {write(path)} 件更新")
        return 0
    problems = [p for path in paths for p in check(path)]
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"\n{len(problems)} 件ずれています。`tools/playground_links.py write` で直せます。", file=sys.stderr)
        return 1
    print(f"OK — {len(paths)} ファイルのリンクは本文と一致しています")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
