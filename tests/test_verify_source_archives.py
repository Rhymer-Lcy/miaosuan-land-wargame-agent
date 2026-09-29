"""Tests for scripts/verify_source_archives.py; they never need the real SDK."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from miaosuan_agent import sdk_provenance as prov

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_source_archives.py"
_spec = importlib.util.spec_from_file_location("verify_source_archives", _SCRIPT)
verify_script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify_script)  # type: ignore[union-attr]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run(archive_dir: Path, require: bool = False) -> tuple[int, list[str]]:
    lines: list[str] = []
    status = verify_script.verify(archive_dir, require=require, out=lines.append)
    return status, lines


class AbsentArchiveTest(unittest.TestCase):
    def test_absent_directory_is_skipped_not_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            status, lines = _run(Path(tmp) / "missing")
        expected = len(prov.ARCHIVE_FILES) + len(prov.NESTED_ARCHIVES) + len(prov.TEXT_MEMBERS)
        self.assertEqual(status, 0)
        self.assertEqual(sum(line.startswith("SKIP ") for line in lines), expected)
        self.assertFalse(any(line.startswith("FAIL") for line in lines))
        self.assertTrue(any("(absent)" in line for line in lines))

    def test_require_turns_absence_into_status_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            status, _ = _run(Path(tmp) / "missing", require=True)
        self.assertEqual(status, 2)


class SyntheticArchiveTest(unittest.TestCase):
    """Replace the recorded manifest with synthetic content to exercise PASS and FAIL paths."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        nested = b"nested archive bytes"
        text = b"print('member')\n"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("inner.zip", nested)
            archive.writestr("pkg/member.py", text)
        self.zip_bytes = buffer.getvalue()
        (self.root / "sdk.zip").write_bytes(self.zip_bytes)
        (self.root / "page.html").write_bytes(b"<html></html>")
        self.patches = [
            mock.patch.object(prov, "SDK_ARCHIVE_NAME", "sdk.zip"),
            mock.patch.object(prov, "ARCHIVE_FILES", {
                "sdk.zip": _sha(self.zip_bytes),
                "page.html": _sha(b"<html></html>"),
            }),
            mock.patch.object(prov, "NESTED_ARCHIVES", {"inner.zip": _sha(nested)}),
            mock.patch.object(prov, "TEXT_MEMBERS", {"pkg/member.py": _sha(text)}),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self) -> None:
        for patch in reversed(self.patches):
            patch.stop()
        self._tmp.cleanup()

    def test_matching_files_pass(self) -> None:
        status, lines = _run(self.root, require=True)
        self.assertEqual(status, 0, lines)
        self.assertEqual(sum(line.startswith("PASS ") for line in lines), 4)

    def test_modified_file_fails(self) -> None:
        (self.root / "page.html").write_bytes(b"<html>changed</html>")
        status, lines = _run(self.root)
        self.assertEqual(status, 1)
        self.assertTrue(any(line.startswith("FAIL sha256 page.html") for line in lines))

    def test_missing_member_fails(self) -> None:
        with mock.patch.object(prov, "TEXT_MEMBERS", {"pkg/absent.py": _sha(b"")}):
            status, lines = _run(self.root)
        self.assertEqual(status, 1)
        self.assertTrue(any("member missing" in line for line in lines))

    def test_corrupt_archive_fails(self) -> None:
        (self.root / "sdk.zip").write_bytes(b"not a zip")
        status, lines = _run(self.root)
        self.assertEqual(status, 1)
        self.assertTrue(any("unreadable archive" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
