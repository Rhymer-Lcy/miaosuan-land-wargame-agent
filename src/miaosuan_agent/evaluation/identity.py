"""The identity of the code that turns a raw observation into emitted actions.

``policy_source_digest`` hashes every source file between the raw observation and the emitted
actions. For ``baseline-v0`` (``POLICY_SOURCES``, frozen) that is the agent wrapper, the boundary
and the decision package; a candidate policy names its own source set, which includes the frozen
one plus explicitly listed files, so adding an unrelated file never changes a registered digest.
Files are taken in sorted relative-path order and line endings are normalized, so a Windows
checkout (CRLF) and a Linux checkout (LF) of the same commit have the same digest.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

PACKAGE = Path(__file__).resolve().parents[1]
#: The source set of ``baseline-v0``. Frozen: changing it would orphan the registered v0 digest.
POLICY_SOURCES = ("agent.py", "boundary", "decision")
#: The source set of ``baseline-v1-candidate-occupy-reservation``: the frozen v0 set plus the two
#: files of the candidate, named individually.
OCCUPY_RESERVATION_SOURCES = POLICY_SOURCES + ("experiments/__init__.py", "experiments/occupy_reservation.py")


def policy_source_files(package: Path = PACKAGE, sources: Sequence[str] = POLICY_SOURCES) -> List[str]:
    files = []
    for entry in sources:
        path = package / entry
        files.extend([path] if path.is_file() else path.rglob("*.py"))
    return sorted(p.relative_to(package).as_posix() for p in files)


def digest_of_files(files: Iterable[str], package: Path = PACKAGE) -> str:
    """The digest of an explicit list of package-relative files (taken in sorted order)."""
    digest = hashlib.sha256()
    for relative in sorted(files):
        data = (package / relative).read_bytes().replace(b"\r\n", b"\n")
        digest.update(relative.encode("utf-8") + b"\0" + str(len(data)).encode("ascii") + b"\0" + data)
    return digest.hexdigest()


def policy_source_digest(package: Path = PACKAGE, sources: Sequence[str] = POLICY_SOURCES) -> Tuple[str, List[str]]:
    files = policy_source_files(package, sources)
    return digest_of_files(files, package), files
