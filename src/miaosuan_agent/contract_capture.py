"""Private contract fixtures captured from the real engine.

Observations are derived from SDK scenario data that carries no redistribution license, so
captures are written only under the git-ignored ``local/`` tree (by convention
``local/contract-fixtures/sdk-<version>/<capture-id>/``) and never committed. Each capture holds,
per capture point, the container description and one faithfully encoded observation per slot
(:mod:`miaosuan_agent.typed_json`), a private structural fingerprint per slot, and a manifest
with SHA-256 digests of every file.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping

from . import typed_json
from .boundary import ContractError, Origin, Slot, normalize_state
from .boundary.profile import check_state, summarize
from .boundary.state import SEQUENCE_ORDER
from .fingerprint import Detail, digest, fingerprint

SCHEMA = "miaosuan-contract-capture/1"
SLOT_NAMES = {Slot.RED: "red", Slot.BLUE: "blue", Slot.GLOBAL: "global"}
MANIFEST = "manifest.json"


def _write(path: Path, payload: Any) -> str:
    data = (json.dumps(payload, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def raw_slot(raw_state: Any, slot: Slot) -> Any:
    """The raw observation object of ``slot`` in either accepted container form."""
    if isinstance(raw_state, Mapping):
        return raw_state[slot.value]
    return raw_state[SEQUENCE_ORDER.index(slot)]


class CaptureWriter:
    """Writes one capture directory; refuses to reuse an existing one."""

    def __init__(self, root: Path, metadata: Mapping[str, Any]) -> None:
        self.root = Path(root)
        if self.root.exists():
            raise FileExistsError(f"capture directory {self.root} already exists")
        self.root.mkdir(parents=True)
        self.metadata = dict(metadata)
        self.points: List[str] = []
        self.entries: List[Dict[str, Any]] = []
        self.containers: Dict[str, Dict[str, Any]] = {}
        self.inexact: List[str] = []

    def capture(self, point: str, raw_state: Any) -> None:
        if point in self.points:
            raise ValueError(f"capture point {point!r} already written")
        view = normalize_state(raw_state, Origin.ENGINE, validate=False)
        directory = self.root / point
        directory.mkdir()
        container = {
            "type": type(raw_state).__name__,
            "form": view.form.value,
            "keys": ([{"repr": repr(k), "type": type(k).__name__} for k in raw_state]
                     if isinstance(raw_state, Mapping) else None),
            "length": len(raw_state),
            "profile_deviations": summarize(check_state(raw_state)),
        }
        container_sha = _write(directory / "container.json", container)
        self.containers[point] = {"file": f"{point}/container.json", "sha256": container_sha, **container}
        for slot, name in SLOT_NAMES.items():
            raw = raw_slot(raw_state, slot)
            encoded, inexact = typed_json.encode(raw)
            self.inexact.extend(f"{point}/{name}: {path}" for path in inexact)
            file_sha = _write(directory / f"{name}.typed.json", encoded)
            private = fingerprint(raw, Detail.PRIVATE)
            fingerprint_sha = _write(directory / f"{name}.fingerprint.json", private)
            try:
                time_info = view.observation(slot).time()
                stage, cur_step = time_info.stage, time_info.cur_step
            except ContractError:
                stage = cur_step = None
            self.entries.append({
                "point": point, "slot": name, "file": f"{point}/{name}.typed.json", "sha256": file_sha,
                "fingerprint_file": f"{point}/{name}.fingerprint.json", "fingerprint_file_sha256": fingerprint_sha,
                "fingerprint_private_digest": digest(private),
                "fingerprint_public_digest": digest(fingerprint(raw, Detail.PUBLIC)),
                "stage": stage, "cur_step": cur_step,
            })
        self.points.append(point)

    def finalize(self, extra: Mapping[str, Any]) -> Path:
        manifest = {"schema": SCHEMA, **self.metadata, **dict(extra), "points": self.points,
                    "containers": self.containers, "entries": self.entries, "inexact_values": self.inexact}
        path = self.root / MANIFEST
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        return path


def load_capture(root: Path) -> Dict[str, Any]:
    """Load a capture and verify every file digest; return manifest and decoded raw states by point."""
    root = Path(root)
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise ValueError(f"unsupported capture schema {manifest.get('schema')!r}")
    states: Dict[str, Dict[int, Any]] = {point: {} for point in manifest["points"]}
    slot_values = {name: slot.value for slot, name in SLOT_NAMES.items()}
    for entry in manifest["entries"]:
        for file_key, sha_key in (("file", "sha256"), ("fingerprint_file", "fingerprint_file_sha256")):
            data = (root / entry[file_key]).read_bytes()
            if hashlib.sha256(data).hexdigest() != entry[sha_key]:
                raise ValueError(f"{entry[file_key]} does not match its recorded digest")
        encoded = json.loads((root / entry["file"]).read_text(encoding="utf-8"))
        states[entry["point"]][slot_values[entry["slot"]]] = typed_json.decode(encoded)
    return {"manifest": manifest, "states": states}
