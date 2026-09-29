"""Documentation and repository-text policy, checked on every public test run.

Rules:

1. every documentation file referenced from Markdown, scripts or source exists;
2. tracked text contains no private infrastructure identifiers (private IPv4 addresses, home
   directories, user@host logins, Windows drive paths);
3. wording that describes the retired per-run engine installation appears only in scopes that
   explicitly record history: the pre-execution audit, the first-probe record, and the History
   section of the installation policy;
4. tracked text files are UTF-8 without BOM, carriage returns or control characters;
5. Markdown code fences are balanced.
"""

from __future__ import annotations

import re
import subprocess
import unicodedata
import unittest
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".md", ".py", ".sh", ".json", ".txt", ".yml", ".yaml", ".toml", ".cfg", ".ini"}
TEXT_NAMES = {".gitignore", ".gitattributes"}

# Built from parts so that this file does not match its own patterns.
PRIVATE_PATTERNS = {
    "private IPv4 address": re.compile(r"\b(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b"),
    "home directory": re.compile("/" + "home/" + r"[A-Za-z0-9_.-]+"),
    "user@host login": re.compile(r"\b[a-z_][a-z0-9_-]*" + "@" + r"(?:\d{1,3}\.){3}\d{1,3}\b"),
    "Windows drive path": re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:" + r"[\\/][^\s`]"),
}
RETIRED_WORDING = re.compile(r"disposable|fresh copy|per[- ]run|throwaway", re.IGNORECASE)
# (file, section heading) pairs where retired wording is history; None means the whole file.
HISTORICAL_SCOPES: Tuple[Tuple[str, Optional[str]], ...] = (
    ("docs/COMPATIBILITY.md", None),     # static audit written before the first execution
    ("docs/ENGINE_SMOKE_TEST.md", None),  # record of the first probe
    ("docs/ENGINE_INSTALL.md", "History"),
)


def tracked_files() -> List[str]:
    listed = subprocess.run(["git", "-C", str(REPO), "ls-files"], capture_output=True, text=True, check=True)
    return [line for line in listed.stdout.splitlines() if line]


def is_text(path: str) -> bool:
    name = Path(path).name
    return Path(path).suffix in TEXT_SUFFIXES or name in TEXT_NAMES


def sections(markdown: str) -> List[Tuple[Optional[str], str]]:
    """Split Markdown into (heading, body) pairs; text before the first heading has heading None."""
    parts: List[Tuple[Optional[str], str]] = []
    heading: Optional[str] = None
    body: List[str] = []
    fence = False
    for line in markdown.splitlines():
        if line.startswith("```"):
            fence = not fence
        match = None if fence else re.match(r"^#{1,6}\s+(.*?)\s*$", line)
        if match:
            parts.append((heading, "\n".join(body)))
            heading, body = match.group(1), []
        else:
            body.append(line)
    parts.append((heading, "\n".join(body)))
    return parts


class DocsPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.files = [path for path in tracked_files() if is_text(path)]
        cls.texts: Dict[str, str] = {path: (REPO / path).read_text(encoding="utf-8") for path in cls.files}

    def test_there_is_something_to_check(self) -> None:
        self.assertGreater(len(self.files), 30)
        self.assertTrue(any(path.startswith("docs/") for path in self.files))

    def test_referenced_documents_exist(self) -> None:
        checked = 0
        for path, text in self.texts.items():
            refs = set(re.findall(r"\bdocs/[A-Z_]+\.md\b", text))
            if path.endswith(".md"):
                refs |= {name for name in re.findall(r"`([A-Z_]+\.md)`", text)}
            for ref in refs:
                candidates = [REPO / ref] if ref.startswith("docs/") else [REPO / "docs" / ref, REPO / ref]
                checked += 1
                with self.subTest(file=path, reference=ref):
                    self.assertTrue(any(candidate.is_file() for candidate in candidates))
        self.assertGreater(checked, 10)

    def test_no_private_infrastructure_identifiers(self) -> None:
        for path, text in self.texts.items():
            for label, pattern in PRIVATE_PATTERNS.items():
                match = pattern.search(text)
                with self.subTest(file=path, pattern=label):
                    self.assertIsNone(match, None if match is None else match.group())

    def test_retired_installation_wording_only_in_historical_scopes(self) -> None:
        for path, text in self.texts.items():
            if not path.endswith(".md"):
                continue
            for heading, body in sections(text):
                allowed = any(path == scope_file and scope_heading in (None, heading)
                              for scope_file, scope_heading in HISTORICAL_SCOPES)
                match = RETIRED_WORDING.search(body)
                with self.subTest(file=path, section=heading):
                    self.assertTrue(allowed or match is None,
                                    f"retired wording {match.group() if match else ''!r} outside a historical scope")

    def test_text_hygiene(self) -> None:
        for path in self.files:
            raw = (REPO / path).read_bytes()
            text = raw.decode("utf-8")
            controls = [hex(ord(c)) for c in text if unicodedata.category(c) == "Cc" and c not in "\n\t"]
            with self.subTest(file=path):
                self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
                self.assertNotIn(b"\r", raw)
                self.assertEqual(controls, [])

    def test_markdown_fences_are_balanced(self) -> None:
        for path, text in self.texts.items():
            if path.endswith(".md"):
                with self.subTest(file=path):
                    self.assertEqual(sum(1 for line in text.splitlines() if line.startswith("```")) % 2, 0)


class PolicyMechanicsTest(unittest.TestCase):
    """The rules themselves must be able to fail."""

    def test_retired_wording_is_detected_case_insensitively(self) -> None:
        self.assertTrue(RETIRED_WORDING.search("First execution must happen in a Disposable environment"))
        self.assertTrue(RETIRED_WORDING.search("installs a fresh copy per-run"))

    def test_sections_ignore_headings_inside_code_fences(self) -> None:
        parsed = sections("intro\n## History\nold\n```\n## not a heading\n```\n## Next\nnew")
        self.assertEqual([heading for heading, _ in parsed], [None, "History", "Next"])

    def test_private_patterns_match_their_targets(self) -> None:
        address = ".".join(["10", "1", "2", "3"])  # assembled so that this file stays clean
        samples = {"private IPv4 address": address, "home directory": "/" + "home/someone/x",
                   "user@host login": "user" + "@" + address, "Windows drive path": "C:" + "/Users/x"}
        for label, sample in samples.items():
            with self.subTest(pattern=label):
                self.assertIsNotNone(PRIVATE_PATTERNS[label].search(sample))


if __name__ == "__main__":
    unittest.main()
