"""Verify locally held SDK source archives against the digests recorded in this repository.

The SDK is not redistributable and is never part of the repository, so its absence is normal (for
example on a CI runner). Every expected file that is absent is reported as SKIP; every file that is
present must match its recorded SHA-256. When the SDK ZIP is present, its nested archives and text
members are checked too.

Exit status:
    0  no mismatch (with --require: additionally, nothing was skipped)
    1  at least one mismatch, missing ZIP member or unreadable archive
    2  --require was given and at least one expected file is absent

Usage:
    python scripts/verify_source_archives.py [--archive-dir DIR] [--require]
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path
from typing import Callable, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_provenance as prov  # noqa: E402

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


def verify(archive_dir: Path, require: bool = False, out: Callable[[str], None] = print) -> int:
    """Check ``archive_dir`` against the recorded digests and return the exit status."""
    counts: Dict[str, int] = {PASS: 0, FAIL: 0, SKIP: 0}

    def report(status: str, label: str) -> None:
        counts[status] += 1
        out(f"{status} {label}")

    present = archive_dir.is_dir()
    out(f"archive directory: {archive_dir} ({'present' if present else 'absent'})")

    for rel, expected in prov.ARCHIVE_FILES.items():
        path = archive_dir / rel
        if not path.is_file():
            report(SKIP, f"{rel} (not present)")
            continue
        report(PASS if prov.sha256_file(path) == expected else FAIL, f"sha256 {rel}")

    members = {**prov.NESTED_ARCHIVES, **prov.TEXT_MEMBERS}
    sdk_path = archive_dir / prov.SDK_ARCHIVE_NAME
    if not sdk_path.is_file():
        for member in members:
            report(SKIP, f"{prov.SDK_ARCHIVE_NAME}!/{member} (SDK archive not present)")
    else:
        try:
            with zipfile.ZipFile(sdk_path) as archive:
                for member, expected in members.items():
                    label = f"sha256 {prov.SDK_ARCHIVE_NAME}!/{member}"
                    try:
                        with archive.open(member) as handle:
                            ok = prov.sha256_stream(handle) == expected
                    except KeyError:
                        report(FAIL, f"{label} (member missing)")
                        continue
                    report(PASS if ok else FAIL, label)
        except zipfile.BadZipFile as exc:
            for member in members:
                report(FAIL, f"{prov.SDK_ARCHIVE_NAME}!/{member} (unreadable archive: {exc})")

    expected_total = len(prov.ARCHIVE_FILES) + len(members)
    total = sum(counts.values())
    out(f"SUMMARY passed={counts[PASS]} failed={counts[FAIL]} skipped={counts[SKIP]} "
        f"total={total}/{expected_total}")
    if total != expected_total:
        out("FAIL internal error: check count does not match the recorded manifest")
        return 1
    if counts[FAIL]:
        return 1
    if counts[SKIP]:
        out("NOTE skipped files are expected on machines without the SDK; "
            "see docs/PROVENANCE.md section 5")
        if require:
            return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--archive-dir", type=Path, default=prov.default_archive_dir(REPO_ROOT),
                        help="directory holding the local source archives "
                             "(default: local/source-archives in this checkout)")
    parser.add_argument("--require", action="store_true",
                        help="exit with status 2 if any expected file is absent")
    args = parser.parse_args(argv)
    return verify(args.archive_dir.resolve(), require=args.require)


if __name__ == "__main__":
    sys.exit(main())
