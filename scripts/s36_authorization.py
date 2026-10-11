"""Prove that the authorized Sprint 36 card differs from the registered, unauthorized card only by the authorization.

    python scripts/s36_authorization.py [--check]

The unauthorized card and its builder are read from Git history (the registration head ``ORIGINAL_COMMIT``); the
authorized card is the committed ``evaluation/s36-tactical-live-1/manifest.json``, which must rebuild byte-identically.
Both cards are flattened to JSON paths and compared value by value. The only differences allowed are:

* ``screen.authorized``: ``false`` to ``true``;
* ``status``: the clause ``NO SESSION AUTHORIZED`` replaced by ``SESSION BUDGET AUTHORIZED BY THE OWNER``;
* ``screen.frozen_files["scripts/build_s36_card.py"]``: the builder's own pinned digest (the builder necessarily changes),
  which must equal the digest of the original builder before and of the current builder after.

The builder itself must equal the original builder with exactly the declared edits applied, each matching once. Any
other difference, a missing path or a changed game, schedule, policy digest, rule digest, threshold, reference or
budget is a problem. Writes ``evaluation/s36-tactical-live-1/authorization.json`` (identities and the allowlisted
differences only); ``--check`` fails unless the stored file is byte-identical to a fresh comparison.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import manifest as mf  # noqa: E402

ORIGINAL_COMMIT = "45e25220b0efa47f39f539b5bb474194bd3737b1"
ORIGINAL_DIGEST = "73166e0ea51ca21e183cc11c38903ec4a6b1da05f82937673945bad868fbef26"
CARD_PATH = "evaluation/s36-tactical-live-1/manifest.json"
BUILDER_PATH = "scripts/build_s36_card.py"
OUT = REPO_ROOT / "evaluation" / "s36-tactical-live-1" / "authorization.json"
OLD_CLAUSE = "NO SESSION AUTHORIZED"
NEW_CLAUSE = "SESSION BUDGET AUTHORIZED BY THE OWNER"
ALLOWED = (("screen", "authorized"), ("status",), ("screen", "frozen_files", BUILDER_PATH))
BUILDER_EDITS = (
    ('"""Build, or check, the Sprint 36 live card (``docs/SPRINT36_TACTICAL_RECOVERY.md`` section 19). A PROPOSAL.\n',
     '"""Build, or check, the Sprint 36 live card (``docs/SPRINT36_TACTICAL_RECOVERY.md`` section 19). AUTHORIZED.\n'),
    ("``--check`` fails unless the committed card is byte-identical to a fresh build.\n\"\"\"\n",
     "``--check`` fails unless the committed card is byte-identical to a fresh build.\n\n"
     "Authorization (owner, 2026-10-11, UTC+8): at most 51 sessions after 2845, under this card's frozen schedule and\n"
     "rules. Only ``authorized``, the status text and, through this file's own frozen digest, the card's pin of this\n"
     "builder differ from the unauthorized card ``73166e0e...`` (``scripts/s36_authorization.py``).\n\"\"\"\n"),
    ('NOT A CONFIRMATION - NOT ELIGIBLE FOR PROMOTION - ' + OLD_CLAUSE + '"',
     'NOT A CONFIRMATION - NOT ELIGIBLE FOR PROMOTION - ' + NEW_CLAUSE + '"'),
    ('"authorized": False}', '"authorized": True}'),
)


def git_show(commit: str, path: str) -> bytes:
    return subprocess.run(["git", "-C", str(REPO_ROOT), "show", f"{commit}:{path}"], capture_output=True,
                          check=True).stdout


def normalised_sha256(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def flatten(value: Any, prefix: Tuple[Any, ...] = ()) -> Dict[Tuple[Any, ...], Any]:
    """Every leaf by its path; lists keep their indices and length, so order and count are compared too."""
    if isinstance(value, Mapping):
        out: Dict[Tuple[Any, ...], Any] = {prefix + ("{}",): sorted(value)}
        for key, item in value.items():
            out.update(flatten(item, prefix + (key,)))
        return out
    if isinstance(value, list):
        out = {prefix + ("[]",): len(value)}
        for index, item in enumerate(value):
            out.update(flatten(item, prefix + (index,)))
        return out
    return {prefix: value}


def apply_edits(text: str) -> Tuple[str, List[str]]:
    problems = []
    for old, new in BUILDER_EDITS:
        if text.count(old) != 1:
            problems.append(f"a declared builder edit matches {text.count(old)} times, not once")
            continue
        text = text.replace(old, new)
    return text, problems


def compare(original: Mapping[str, Any], new: Mapping[str, Any], original_builder: bytes,
            current_builder: bytes) -> Tuple[List[str], List[Dict[str, Any]]]:
    problems: List[str] = []
    if mf.digest(original) != ORIGINAL_DIGEST:
        problems.append("the original card is not the registered unauthorized card")
    a, b = flatten(original), flatten(new)
    differing = sorted((p for p in set(a) | set(b) if a.get(p, KeyError) != b.get(p, KeyError)), key=repr)
    unexpected = [p for p in differing if p not in ALLOWED]
    if unexpected:
        problems.append(f"differences outside the authorization: {[list(p) for p in unexpected[:10]]}")
    if sorted(differing, key=repr) != sorted(ALLOWED, key=repr):
        problems.append(f"the differing paths are {[list(p) for p in differing]}, not exactly the allowlist")
    if a.get(("screen", "authorized")) is not False or b.get(("screen", "authorized")) is not True:
        problems.append("authorized is not false before and true after")
    status = a.get(("status",))
    if not isinstance(status, str) or status.count(OLD_CLAUSE) != 1 \
            or b.get(("status",)) != status.replace(OLD_CLAUSE, NEW_CLAUSE):
        problems.append("the status text changed beyond the authorization clause")
    pin = ("screen", "frozen_files", BUILDER_PATH)
    if a.get(pin) != normalised_sha256(original_builder):
        problems.append("the original card does not pin the original builder")
    if b.get(pin) != normalised_sha256(current_builder):
        problems.append("the authorized card does not pin the current builder")
    edited, edit_problems = apply_edits(original_builder.replace(b"\r\n", b"\n").decode("utf-8"))
    problems += edit_problems
    if edited.encode("utf-8") != current_builder.replace(b"\r\n", b"\n"):
        problems.append("the builder differs from the original beyond the declared edits")
    changes = [{"path": list(p), "before": a.get(p), "after": b.get(p)} for p in differing if p in ALLOWED]
    return problems, changes


def result(card_text: str) -> Dict[str, Any]:
    original = json.loads(git_show(ORIGINAL_COMMIT, CARD_PATH).decode("utf-8"))
    new = json.loads(card_text)
    original_builder = git_show(ORIGINAL_COMMIT, BUILDER_PATH)
    current_builder = (REPO_ROOT / BUILDER_PATH).read_bytes()
    problems, changes = compare(original, new, original_builder, current_builder)
    return {"schema": "miaosuan-s36-authorization/1", "card": new.get("card_id"),
            "original": {"commit": ORIGINAL_COMMIT, "card_sha256_canonical": mf.digest(original),
                         "builder_sha256_normalised": normalised_sha256(original_builder)},
            "authorized": {"card_sha256_canonical": mf.digest(new),
                           "builder_sha256_normalised": normalised_sha256(current_builder)},
            "compared_paths": len(set(flatten(original)) | set(flatten(new))),
            "games": len(new.get("games", [])), "allowed_paths": [list(p) for p in ALLOWED],
            "changes": changes, "builder_edits": len(BUILDER_EDITS), "problems": problems}


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def load_builder() -> Any:
    spec = importlib.util.spec_from_file_location("s36auth_build", REPO_ROOT / "scripts" / "build_s36_card.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    cards = load_builder()
    card_text = (REPO_ROOT / CARD_PATH).read_text(encoding="utf-8")
    if cards.dump(cards.build()) != card_text:
        print(f"MISMATCH: {CARD_PATH} does not rebuild byte-identically", file=sys.stderr)
        return 1
    data = result(card_text)
    text = dump(data)
    ok = not data["problems"]
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print(f"{'OK' if same and ok else 'MISMATCH'} {OUT.relative_to(REPO_ROOT).as_posix()} problems={data['problems']}")
        return 0 if same and ok else 1
    if not ok:
        print(f"REFUSED: {data['problems']}", file=sys.stderr)
        return 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()}: {data['original']['card_sha256_canonical']} -> "
          f"{data['authorized']['card_sha256_canonical']}, {len(data['changes'])} allowlisted differences of "
          f"{data['compared_paths']} paths, {data['games']} games")
    return 0


if __name__ == "__main__":
    sys.exit(main())
