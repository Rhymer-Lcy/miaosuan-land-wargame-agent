"""Identity of the third-party SDK material this project is developed against.

The platform's community SDK carries no license that authorizes redistribution (see
``docs/PROVENANCE.md``), so it is never stored in this repository. This module is the single place
that records the SHA-256 digests identifying a legitimate local copy, and the layout under which a
machine keeps that copy (``local/source-archives/``, which is git-ignored).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import BinaryIO, Mapping

SDK_ARCHIVE_NAME = "land_wargame_sdk.zip"
SDK_ARCHIVE_SHA256 = "ed4c9fc03cb6eb1e64821d2efbc61024d90735e3dc489dc7ffe0515e653ea725"

#: Files expected under ``local/source-archives/``: relative path -> SHA-256. The saved documentation
#: page supplied with the SDK was retired from the local archive on 2026-09-30 (``docs/PROVENANCE.md``).
ARCHIVE_FILES: Mapping[str, str] = {
    SDK_ARCHIVE_NAME: SDK_ARCHIVE_SHA256,
}

DATA_ARCHIVE_MEMBER = "Data.zip"
ENGINE_WHEEL_MEMBER = (
    "land_wargame_train_env-4.1.0-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
)
#: Version of the engine distribution in ``ENGINE_WHEEL_MEMBER`` (from its wheel file name).
ENGINE_VERSION = ENGINE_WHEEL_MEMBER.split("-")[1]

#: Archives nested inside the SDK ZIP: member name -> SHA-256.
NESTED_ARCHIVES: Mapping[str, str] = {
    DATA_ARCHIVE_MEMBER: "0d6130e457faf8a96b495792843023245ae1b204fec140c7b954b2a99d51435e",
    ENGINE_WHEEL_MEMBER: "b74f8d273e93942a7bf61894a84a658f7fdd9fbefb581634bac70b3864e069c6",
}

#: Text members of the SDK ZIP: member name -> SHA-256.
TEXT_MEMBERS: Mapping[str, str] = {
    "ai/__init__.py": "3febf1777f68550ff6b9e3306e4a78055af83a88b9cf96b69e83dd97da688529",
    "ai/agent.py": "7d4213758d28b0f2bd3b6e5835d077b108730f5ef02e0d73703cb17e82d596ad",
    "ai/base_agent.py": "6a14d8a1052623d9d6572908e44ec4c94977a93f0d27958451b0b7cbfb802547",
    "ai/map.py": "ead67e165e20fe19e6e6926f981e926d327d9e022106043dec5242b2af03a630",
    "docs/action_note.json": "186080de8a11df79c0d04ecf44c4c02cc69475352058e2020b84bce551426b52",
    "docs/observation_example.json":
        "ce2b9ddae6f7fa069f3d36235f08f789e080f1992ee9aa26b14e437767d6cffc",
    "docs/observation_note.json":
        "6147b2a1d90dd7c0abf671bc0d27dc741e3bca9b6a10648cfb2a7e9ac7fc66c2",
    "run_offline_games.py": "ed212a471cd214249cf00f1efc6da45afe5f0f7c434c4f33241150c6da1a0384",
}

_CHUNK = 1 << 20


def sha256_stream(stream: BinaryIO) -> str:
    """Return the hex SHA-256 of everything readable from a binary stream."""
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(_CHUNK), b""):
        digest.update(block)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 of a file."""
    with Path(path).open("rb") as handle:
        return sha256_stream(handle)


def default_archive_dir(repo_root: Path) -> Path:
    """Return the conventional location of the local source archives for a checkout."""
    return Path(repo_root) / "local" / "source-archives"
