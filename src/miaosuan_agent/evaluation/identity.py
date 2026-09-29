"""The identity of the code that turns a raw observation into emitted actions.

``policy_source_digest`` hashes every source file between the raw observation and the emitted
actions: the agent wrapper, the boundary and the decision package. Files are taken in sorted
relative-path order and line endings are normalized, so a Windows checkout (CRLF) and a Linux
checkout (LF) of the same commit have the same digest.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import List, Tuple

PACKAGE = Path(__file__).resolve().parents[1]
POLICY_SOURCES = ("agent.py", "boundary", "decision")


def policy_source_files(package: Path = PACKAGE) -> List[str]:
    files = []
    for entry in POLICY_SOURCES:
        path = package / entry
        files.extend([path] if path.is_file() else path.rglob("*.py"))
    return sorted(p.relative_to(package).as_posix() for p in files)


def policy_source_digest(package: Path = PACKAGE) -> Tuple[str, List[str]]:
    files = policy_source_files(package)
    digest = hashlib.sha256()
    for relative in files:
        data = (package / relative).read_bytes().replace(b"\r\n", b"\n")
        digest.update(relative.encode("utf-8") + b"\0" + str(len(data)).encode("ascii") + b"\0" + data)
    return digest.hexdigest(), files
