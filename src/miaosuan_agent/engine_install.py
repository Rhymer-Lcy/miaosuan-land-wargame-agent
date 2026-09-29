"""Persistent, provenance-preserving installation of the SDK engine, and its usage ledger.

The engine writes authentication state into its own installed package. A persistent installation
is therefore created once from the verified wheel and afterwards only reused. This module never
interprets, modifies, copies, restores or deletes that state; it hashes it to prove continuity.

Layout of an installation root (git-ignored, for example ``local/engines/sdk-4.1.0/``)::

    install-manifest.json   written once at installation, then made read-only
    site/                   ``pip --target`` installation; the engine may change its state file here
    home/                   persistent HOME for engine processes; never cleared
    usage-ledger.jsonl      append-only record of every engine session
    .session.lock           advisory lock held while a session runs (POSIX)

Guardrails:

* :func:`create_install` refuses an existing destination. There is no reinstall, repair or reset
  operation, because reinstalling would restart the engine's first-use state.
* :func:`open_session` refuses when a package file other than a state file differs from the
  manifest, or when a state file differs from its hash at the end of the previous session (for
  the first session: at installation). Either means something outside a recorded session touched
  the installation, which must be investigated, never repaired by restoring files.
* A session that was opened but never closed (killed or crashed) is closed as ``recovered`` by the
  next :func:`open_session`, with the state recorded as found: the engine may legitimately have
  changed it while that session ran.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import platform
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence

from .sdk_provenance import sha256_file

SCHEMA = "miaosuan-engine-install/1"
MANIFEST = "install-manifest.json"
LEDGER = "usage-ledger.jsonl"
SITE = "site"
HOME = "home"
LOCK = ".session.lock"
#: Engine-owned mutable state, relative to ``site/``. Hashed, never touched.
DEFAULT_STATE_FILES = ("train_env/env/authenticate/.engine_config",)


class InstallError(RuntimeError):
    """The installation is missing, malformed, or an operation on it failed."""


class InstallRefused(InstallError):
    """A guardrail stopped the operation; see the message for what to investigate."""


@dataclass(frozen=True)
class EngineInstall:
    root: Path

    @property
    def site(self) -> Path:
        return self.root / SITE

    @property
    def home(self) -> Path:
        return self.root / HOME

    @property
    def manifest_path(self) -> Path:
        return self.root / MANIFEST

    @property
    def ledger_path(self) -> Path:
        return self.root / LEDGER


@dataclass(frozen=True)
class Integrity:
    changed: List[str]
    missing: List[str]
    added: List[str]

    @property
    def ok(self) -> bool:
        return not self.changed and not self.missing

    def as_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "changed": self.changed, "missing": self.missing, "added": self.added}


def now() -> Dict[str, str]:
    """This host's wall-clock time. It is a label, not a duration source, and may be offset."""
    return {"host_clock_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}


def tree_files(directory: Path, exclude: Iterable[str] = ()) -> Dict[str, str]:
    """Relative path -> SHA-256 for every file below ``directory`` (bytecode caches excluded)."""
    skip = set(exclude)
    result: Dict[str, str] = {}
    for path in sorted(Path(directory).rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            rel = path.relative_to(directory).as_posix()
            if rel not in skip:
                result[rel] = sha256_file(path)
    return result


def tree_digest(files: Mapping[str, str]) -> str:
    lines = "".join(f"{sha}  {rel}\n" for rel, sha in sorted(files.items()))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def pip_target_installer(wheel: Path, target: Path) -> Dict[str, Any]:
    """Install ``wheel`` into ``target`` with the current interpreter's pip, offline, no deps."""
    command = [sys.executable, "-m", "pip", "install", "--no-deps", "--no-index", "--no-compile",
               "--target", str(target), str(wheel)]
    done = subprocess.run(command, capture_output=True, text=True)
    if done.returncode != 0:
        raise InstallError(f"pip install failed ({done.returncode}): {done.stderr.strip()[-2000:]}")
    version = subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True, text=True)
    return {"command": command, "pip_version": version.stdout.strip()}


Installer = Callable[[Path, Path], Mapping[str, Any]]


def create_install(root: Path, wheel: Path, *, wheel_sha256: str, engine_version: str,
                   provenance: Optional[Mapping[str, Any]] = None,
                   state_files: Sequence[str] = DEFAULT_STATE_FILES,
                   installer: Optional[Installer] = None) -> Dict[str, Any]:
    """Create the persistent installation once. Refuses if ``root`` exists in any form."""
    install = EngineInstall(Path(root))
    if install.root.exists():
        raise InstallRefused(
            f"{install.root} already exists. A persistent engine installation is created once and never "
            "replaced: reinstalling would restart the engine's first-use state, so no tool here does it.")
    actual = sha256_file(Path(wheel))
    if actual != wheel_sha256:
        raise InstallError(f"{wheel} has SHA-256 {actual}, expected {wheel_sha256}")
    install.root.mkdir(parents=True)
    details = dict((installer or pip_target_installer)(Path(wheel), install.site))
    files = tree_files(install.site)
    absent = [name for name in state_files if name not in files]
    if absent:
        raise InstallError(f"state files {absent} not found after installation; unexpected package layout")
    manifest = {
        "schema": SCHEMA,
        "engine": {"version": engine_version},
        "source": {"wheel": Path(wheel).name, "wheel_sha256": actual, **dict(provenance or {})},
        "python": {"implementation": platform.python_implementation(), "version": platform.python_version(),
                   "executable": sys.executable},
        "installer": details,
        "installed_at": now(),
        "state_files": list(state_files),
        "state_at_install": {name: files[name] for name in state_files},
        "tree_before_first_import": {"file_count": len(files), "digest": tree_digest(files), "files": files},
    }
    install.home.mkdir()
    install.manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(install.manifest_path, 0o444)
    return manifest


def load_manifest(install: EngineInstall) -> Dict[str, Any]:
    if not install.manifest_path.is_file():
        raise InstallError(f"no installation manifest at {install.manifest_path}; create the installation first")
    manifest = json.loads(install.manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise InstallError(f"unsupported manifest schema {manifest.get('schema')!r}")
    return manifest


def check_integrity(install: EngineInstall, manifest: Mapping[str, Any]) -> Integrity:
    state = set(manifest["state_files"])
    recorded = {k: v for k, v in manifest["tree_before_first_import"]["files"].items() if k not in state}
    current = tree_files(install.site, exclude=state)
    return Integrity(
        changed=sorted(k for k in recorded if k in current and current[k] != recorded[k]),
        missing=sorted(k for k in recorded if k not in current),
        added=sorted(k for k in current if k not in recorded),
    )


def state_hashes(install: EngineInstall, manifest: Mapping[str, Any]) -> Dict[str, Optional[str]]:
    result: Dict[str, Optional[str]] = {}
    for name in manifest["state_files"]:
        path = install.site / name
        result[name] = sha256_file(path) if path.is_file() else None
    return result


def read_ledger(install: EngineInstall) -> List[Dict[str, Any]]:
    if not install.ledger_path.exists():
        return []
    records = []
    for number, line in enumerate(install.ledger_path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise InstallError(f"{install.ledger_path}:{number} is not valid JSON: {exc}") from exc
    return records


def _append(install: EngineInstall, record: Mapping[str, Any]) -> None:
    with install.ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def open_session(install: EngineInstall, purpose: str, harness: Mapping[str, Any],
                 clock: Callable[[], Mapping[str, str]] = now) -> Dict[str, Any]:
    """Check the installation and append a ``session-open`` record; raise InstallRefused otherwise."""
    manifest = load_manifest(install)
    integrity = check_integrity(install, manifest)
    if not integrity.ok:
        raise InstallRefused(f"package files differ from the installation manifest (changed {integrity.changed}, "
                             f"missing {integrity.missing}); investigate before using this installation")
    state = state_hashes(install, manifest)
    home = tree_files(install.home)
    ledger = read_ledger(install)
    last = ledger[-1] if ledger else None
    if last is not None and last.get("event") == "session-open":
        last = {"event": "session-recovered", "session": last["session"], "at": dict(clock()), "state": state,
                "home": home, "integrity": integrity.as_dict(),
                "note": "the previous session was never closed (killed or crashed); state recorded as found"}
        _append(install, last)
    expected, basis = ((manifest["state_at_install"], "installation") if last is None
                       else (last["state"], f"the end of session {last['session']}"))
    if state != expected:
        raise InstallRefused(
            f"the engine state file changed outside a recorded session (compared with {basis}). Investigate; "
            "never restore, reset or replace the state file to make this check pass.")
    opened = [record for record in ledger if record.get("event") == "session-open"]
    record = {"event": "session-open", "session": f"{len(opened) + 1:04d}",
              "kind": "first-use" if not opened else "reuse", "purpose": purpose, "at": dict(clock()),
              "state": state, "home": home, "integrity": integrity.as_dict(), "harness": dict(harness)}
    _append(install, record)
    return record


def close_session(install: EngineInstall, opened: Mapping[str, Any], outcome: Mapping[str, Any],
                  clock: Callable[[], Mapping[str, str]] = now) -> Dict[str, Any]:
    """Append the ``session-close`` record for ``opened``."""
    manifest = load_manifest(install)
    state = state_hashes(install, manifest)
    home = tree_files(install.home)
    record = {"event": "session-close", "session": opened["session"], "at": dict(clock()), "state": state,
              "state_changed": state != opened["state"], "home": home, "home_changed": home != opened["home"],
              "integrity": check_integrity(install, manifest).as_dict(), "outcome": dict(outcome)}
    _append(install, record)
    return record


@dataclass
class Session:
    opened: Dict[str, Any]
    outcome: Dict[str, Any] = field(default_factory=lambda: {"status": "INTERRUPTED"})
    closed: Optional[Dict[str, Any]] = None


@contextmanager
def session(install: EngineInstall, purpose: str, harness: Mapping[str, Any]) -> Iterator[Session]:
    """Hold the installation lock, open a session, and always close it. POSIX only."""
    try:
        import fcntl
    except ImportError as exc:  # pragma: no cover - the engine exists only for Linux
        raise InstallError("engine sessions need POSIX file locking; the SDK engine runs only on Linux") from exc
    install.root.mkdir(parents=True, exist_ok=True)
    with open(install.root / LOCK, "a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise InstallRefused(f"another engine session holds {install.root / LOCK}") from exc
        handle = Session(opened=open_session(install, purpose, harness))
        try:
            yield handle
        except BaseException as exc:
            handle.outcome.setdefault("exception", f"{type(exc).__name__}: {exc}")
            raise
        finally:
            handle.closed = close_session(install, handle.opened, handle.outcome)


def verify(install: EngineInstall) -> Dict[str, Any]:
    """Read-only status: manifest, package integrity, state continuity and ledger summary."""
    manifest = load_manifest(install)
    integrity = check_integrity(install, manifest)
    state = state_hashes(install, manifest)
    ledger = read_ledger(install)
    last = ledger[-1] if ledger else None
    expected = manifest["state_at_install"] if last is None else last.get("state")
    opened = [record for record in ledger if record.get("event") == "session-open"]
    return {
        "root": str(install.root),
        "engine_version": manifest["engine"]["version"],
        "wheel_sha256": manifest["source"]["wheel_sha256"],
        "python": manifest["python"]["version"],
        "installed_at": manifest["installed_at"],
        "tree_digest_before_first_import": manifest["tree_before_first_import"]["digest"],
        "integrity": integrity.as_dict(),
        "state_continuous": state == expected,
        "sessions_opened": len(opened),
        "first_use_session": opened[0]["session"] if opened else None,
        "last_event": None if last is None else {k: last.get(k) for k in ("event", "session", "at")},
        "unclosed_session": bool(last and last.get("event") == "session-open"),
    }
