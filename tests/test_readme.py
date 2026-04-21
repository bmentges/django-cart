"""README link integrity — catches dead relative paths and bad anchors.

External http/https URLs are deliberately skipped: this suite stays
offline-clean, and upstream link rot is best caught by a periodic
external link-check CI job rather than a unit test.

Scope:

- ``[text](../path/to/file.md)`` — relative paths resolve somewhere
  in the repo tree.
- ``[text](#section-name)`` — intra-README anchors match a heading
  that GitHub would actually generate.

Both checks strip fenced code blocks first so that sample code in the
README can't accidentally match as a link.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def _strip_code_blocks(text: str) -> str:
    return _FENCE_RE.sub("", text)


def _github_slug(heading: str) -> str:
    """Approximate GitHub's anchor-generation for a heading.

    Matches the subset actually used in this README: lowercase,
    strip inline-code/emphasis markers, drop punctuation except
    hyphens, collapse whitespace into hyphens.
    """
    s = heading.strip().lower()
    s = re.sub(r"[`*_]", "", s)
    s = re.sub(r"[^a-z0-9\s\-]", "", s)
    s = re.sub(r"\s+", "-", s)
    return s


def _heading_anchors(text: str) -> set[str]:
    return {_github_slug(match.group(2)) for match in _HEADING_RE.finditer(text)}


def _iter_links(text: str):
    for match in _LINK_RE.finditer(_strip_code_blocks(text)):
        yield match.group(1), match.group(2)


@pytest.fixture
def readme_text() -> str:
    return (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def test_readme_relative_paths_point_at_files_that_exist(readme_text):
    """Every ``[text](relative/path)`` in the README must resolve to an
    actual file or directory in the repo. Anchor fragments on a path
    (``foo.md#heading``) are allowed but the file part must exist."""
    missing = []
    for _text, target in _iter_links(readme_text):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        # Strip anchor + query fragments, treat the rest as a repo-relative path.
        path_part = target.split("#", 1)[0].split("?", 1)[0]
        if not path_part:
            continue
        resolved = (REPO_ROOT / path_part).resolve()
        if not resolved.exists():
            missing.append(target)

    assert not missing, (
        "README.md references files that don't exist:\n  "
        + "\n  ".join(sorted(missing))
    )


def test_readme_intra_doc_anchors_match_a_heading(readme_text):
    """Every ``[text](#anchor)`` must match a heading GitHub would
    generate an anchor for. Catches TOC drift after section renames."""
    anchors = _heading_anchors(readme_text)
    missing = []
    for _text, target in _iter_links(readme_text):
        if not target.startswith("#"):
            continue
        if target[1:] not in anchors:
            missing.append(target)

    assert not missing, (
        "README.md references #anchors with no matching heading:\n  "
        + "\n  ".join(sorted(set(missing)))
    )
