"""Build the platform upload package (``dist/<name>.zip``): one top-level ``ai`` package around a frozen policy.

    python scripts/build_platform_package.py [--name miaosuan-baseline-v2-canary] [--out-dir dist] [--skip-smoke]
    python scripts/build_platform_package.py --replay-corpus     # private: replay real observations (server)

The platform imports ``Agent`` from a package named ``ai`` (a zip holding exactly one top-level folder ``ai`` whose
``agent.py`` defines ``Agent`` with ``setup``, ``step`` and ``reset``). This builder:

* vendors, byte for byte, exactly the project modules the policy imports (the static import closure of
  ``miaosuan_agent.experiments.shoot_reservation``, package ``__init__`` files included) under ``ai/miaosuan_agent``;
  every import inside it is relative, and the closure may import nothing outside the standard library;
* generates ``ai/__init__.py``, ``ai/base_agent.py`` (the three-method interface, written here, no SDK code) and
  ``ai/agent.py`` (``Agent`` delegating to the frozen ``baseline-v2`` agent; an unexpected exception is reported on
  stderr and answered with no action, so one bad step does not stop the agent), and ``ai/PACKAGE.json``;
* writes a deterministic zip (stored entries, sorted, fixed timestamps and permissions), refuses forbidden content
  (SDK, data, caches, tests, git, local paths, secrets) and any layout other than ``ai/``, and refuses 200 MB or more;
* smoke-tests the extracted package in an isolated interpreter (``-I``, no repository on the path): ``from ai import
  Agent``, then a synthetic game whose every action must equal the repository agent's on the same inputs.

``--replay-corpus`` drives the packaged agent and the repository agent through every recorded observation of the
private replay corpus and requires identical actions (it runs where the corpus exists).
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import os
import pickle
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PACKAGE = "miaosuan_agent"
ENTRY = "miaosuan_agent/experiments/shoot_reservation.py"
AGENT_CLASS = "ShootReservationAgent"
POLICY_IDENTITY = "baseline-v2"
POLICY_SOURCE_SHA256 = "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae"
LIMIT_BYTES = 200 * 1024 * 1024
STAMP = (1980, 1, 1, 0, 0, 0)
FORBIDDEN_PARTS = ("__pycache__", ".git", "tests", "local", "Data", "data", ".engine_config")
FORBIDDEN_SUFFIXES = (".pyc", ".pyo", ".zip", ".whl", ".pickle", ".pkl", ".npz", ".so", ".dll", ".exe", ".gz")
FORBIDDEN_TEXT = ("/home/", "C:\\", "F:\\", "D:\\", "192.168.", "BEGIN PRIVATE KEY", "train_env", "land_wargame_sdk")

INIT = '"""The platform package: ``from ai import Agent``."""\n\nfrom .agent import Agent\n\n__all__ = ["Agent"]\n'
BASE = '''"""The platform's agent interface: setup, step and reset (written for this package; no SDK code)."""

from abc import ABC, abstractmethod
from typing import List


class BaseAgent(ABC):
    @abstractmethod
    def setup(self, setup_info: dict) -> None:
        """Called once before a game with the scenario, map data, seat and faction."""

    @abstractmethod
    def step(self, observation: dict) -> List[dict]:
        """Called with each observation; returns the actions of this step."""

    @abstractmethod
    def reset(self) -> None:
        """Called after a game."""
'''
AGENT = '''"""Platform entry point: the frozen {identity} policy (policy source {digest}).

``Agent`` delegates to the project agent unchanged. An observation that violates the project's contract yields no
actions inside the project agent (fail-closed); its error is reported once per distinct message on stderr, so the
platform's logs show it. Any other exception in a step is reported the same way and answered with no action, so a
single bad step does not stop the agent.
"""

import sys
from typing import Any, Dict, List

from .base_agent import BaseAgent
from .{package}.experiments.shoot_reservation import {agent_class}

IDENTITY = "{identity}"
POLICY_SOURCE_SHA256 = "{digest}"


class Agent(BaseAgent):
    def __init__(self) -> None:
        self._agent = {agent_class}()
        self._reported: set = set()

    def _report(self, message: str) -> None:
        if message not in self._reported and len(self._reported) < 50:
            self._reported.add(message)
            print(f"[{{IDENTITY}}] {{message}}", file=sys.stderr, flush=True)

    def setup(self, setup_info: Dict[str, Any]) -> None:
        self._agent.setup(setup_info)

    def step(self, observation: Dict[str, Any]) -> List[Dict[str, Any]]:
        try:
            actions = self._agent.step(observation)
        except Exception as exc:  # noqa: BLE001 - reported, and the agent keeps playing
            self._report(f"step error: {{type(exc).__name__}}: {{exc}}"[:500])
            return []
        trace = self._agent.last_trace
        error = getattr(trace, "error", None)
        if error:
            self._report(f"contract error: {{error}}"[:500])
        return actions

    def reset(self) -> None:
        self._agent.reset()
        self._reported = set()
'''


# ----------------------------------------------------------------------------------------------
# import closure


def _exists(path: Path) -> bool:
    """Case-sensitive existence, also on case-insensitive file systems."""
    return path.parent.is_dir() and path.name in os.listdir(path.parent)


def _module_file(module: str) -> Path:
    path = SRC / Path(*module.split("."))
    if _exists(path) and _exists(path / "__init__.py"):
        return path / "__init__.py"
    if _exists(path.with_suffix(".py")):
        return path.with_suffix(".py")
    raise SystemExit(f"module {module} not found under src/")


def _package_of(relative: str) -> str:
    parts = Path(relative).with_suffix("").parts
    return ".".join(parts[:-1]) if parts[-1] != "__init__" else ".".join(parts[:-1])


def closure(entry: str = ENTRY) -> Tuple[List[str], Set[str]]:
    """Every project file the entry imports (relative paths under src/), and the external top-level modules."""
    files: Set[str] = set()
    external: Set[str] = set()
    pending = [entry]
    while pending:
        relative = pending.pop()
        if relative in files:
            continue
        files.add(relative)
        parts = Path(relative).parts
        for k in range(1, len(parts)):
            init = str(Path(*parts[:k]) / "__init__.py").replace("\\", "/")
            if (SRC / init).exists() and init not in files:
                pending.append(init)
        tree = ast.parse((SRC / relative).read_text(encoding="utf-8"))
        package = _package_of(relative)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top == PACKAGE:
                        raise SystemExit(f"{relative}: absolute import of {alias.name}; only relative imports are vendored")
                    external.add(top)
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0:
                    top = (node.module or "").split(".")[0]
                    if top == PACKAGE:
                        raise SystemExit(f"{relative}: absolute import of {node.module}")
                    if top != "__future__":
                        external.add(top)
                    continue
                base = package.split(".")
                base = base[:len(base) - (node.level - 1)]
                target = ".".join(base + ([node.module] if node.module else []))
                candidates = [target] if node.module else []
                for alias in node.names:
                    candidates.append(f"{target}.{alias.name}")
                for module in candidates:
                    try:
                        found = _module_file(module)
                    except SystemExit:
                        continue
                    pending.append(found.relative_to(SRC).as_posix())
    return sorted(files), external


def check_external(external: Set[str]) -> None:
    allowed = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else set()
    outside = sorted(m for m in external if m not in allowed)
    if outside:
        raise SystemExit(f"the vendored closure imports modules outside the standard library: {outside}")


# ----------------------------------------------------------------------------------------------
# package


def check_policy_source() -> None:
    from miaosuan_agent.evaluation import runtime_remediation as rr
    from miaosuan_agent.evaluation.identity import policy_source_digest
    digest = policy_source_digest(sources=rr.candidate_sources() + ("experiments/shoot_reservation.py",))[0]
    if digest != POLICY_SOURCE_SHA256:
        raise SystemExit(f"the checkout's baseline-v2 policy source is {digest}, not the frozen {POLICY_SOURCE_SHA256}")


def entries() -> Dict[str, bytes]:
    check_policy_source()
    files, external = closure()
    check_external(external)
    payload: Dict[str, bytes] = {
        "ai/__init__.py": INIT.encode("utf-8"),
        "ai/base_agent.py": BASE.encode("utf-8"),
        "ai/agent.py": AGENT.format(identity=POLICY_IDENTITY, digest=POLICY_SOURCE_SHA256, package=PACKAGE,
                                    agent_class=AGENT_CLASS).encode("utf-8"),
    }
    for relative in files:
        payload[f"ai/{relative}"] = (SRC / relative).read_bytes()
    manifest = {"package": "ai", "policy": POLICY_IDENTITY, "policy_source_sha256": POLICY_SOURCE_SHA256,
                "agent_class": f"{PACKAGE}.experiments.shoot_reservation.{AGENT_CLASS}", "python": ">=3.10",
                "third_party": [], "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(payload.items())}}
    payload["ai/PACKAGE.json"] = (json.dumps(manifest, indent=1, sort_keys=True) + "\n").encode("utf-8")
    return payload


def forbidden(name: str, data: bytes) -> List[str]:
    problems = []
    parts = Path(name).parts
    if not name.startswith("ai/"):
        problems.append(f"{name}: outside the top-level ai/ folder")
    for part in parts[1:]:
        if part in FORBIDDEN_PARTS:
            problems.append(f"{name}: forbidden path component {part}")
    if name.endswith(FORBIDDEN_SUFFIXES):
        problems.append(f"{name}: forbidden file type")
    if name.endswith(".json") and name != "ai/PACKAGE.json":
        problems.append(f"{name}: data file")
    text = data.decode("utf-8", errors="replace")
    for needle in FORBIDDEN_TEXT:
        if needle in text:
            problems.append(f"{name}: forbidden text {needle!r}")
    return problems


def write_zip(payload: Dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    directories = sorted({str(Path(name).parent).replace("\\", "/") + "/" for name in payload})
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in directories:
            info = zipfile.ZipInfo(name, STAMP)
            info.create_system = 3  # the same bytes whichever system builds it
            info.external_attr = (0o40755 << 16) | 0x10
            archive.writestr(info, b"")
        for name in sorted(payload):
            info = zipfile.ZipInfo(name, STAMP)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, payload[name])
    return buffer.getvalue()


def verify_zip(data: bytes) -> List[str]:
    problems = []
    if len(data) >= LIMIT_BYTES:
        problems.append(f"archive is {len(data)} bytes, not under 200 MB")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        tops = {name.split("/")[0] for name in names}
        if tops != {"ai"}:
            problems.append(f"top-level entries {sorted(tops)}, expected exactly ai/")
        if "ai/agent.py" not in names or "ai/__init__.py" not in names:
            problems.append("ai/agent.py or ai/__init__.py missing")
        for name in names:
            if not name.endswith("/"):
                problems.extend(forbidden(name, archive.read(name)))
    return problems


# ----------------------------------------------------------------------------------------------
# smoke


SMOKE = r'''
import json, pickle, sys
root, inputs = sys.argv[1], sys.argv[2]
sys.path.insert(0, root)
from ai import Agent
import ai.agent
assert ai.agent.__file__.startswith(root), ai.agent.__file__
assert "miaosuan_agent" not in sys.modules, "the repository package leaked into the isolated interpreter"
data = pickle.load(open(inputs, "rb"))
agents = {}
for seat, setup in data["setups"].items():
    agents[seat] = Agent()
    agents[seat].setup(setup)
mismatches, steps = 0, 0
for seat, observation, expected in data["steps"]:
    actions = agents[seat].step(observation)
    steps += 1
    mismatches += json.dumps(actions, sort_keys=True, default=str) != json.dumps(expected, sort_keys=True, default=str)
for agent in agents.values():
    agent.reset()
print(json.dumps({"python": sys.version.split()[0], "steps": steps, "mismatches": mismatches,
                  "ai": ai.agent.IDENTITY, "source": ai.agent.POLICY_SOURCE_SHA256}))
'''


def synthetic_inputs() -> Dict[str, Any]:
    """A synthetic fake-engine game played by the repository agent: setup data, observations and its actions."""
    from miaosuan_agent.evaluation.game import play
    from miaosuan_agent.evaluation.manifest import PLAYERS, GameSpec
    from miaosuan_agent.experiments.shoot_reservation import CANDIDATE_ID, ShootReservationAgent
    from tests.fixtures import fake_engine
    from tests.test_evaluation_game import Inputs

    steps: List[Any] = []

    class Recorder:
        def setup(self, *args: Any) -> None:
            pass

        def step(self, index: int, before: Any, after: Any, decisions: Any) -> None:
            for d in decisions:
                steps.append((d["seat"], dict(d["observation"]), [dict(a) for a in d["actions"]]))

    spec = GameSpec(game_id="package-smoke", scenario_id="999", map_id="99", condition="C1", red=CANDIDATE_ID,
                    blue=CANDIDATE_ID, repetition=1, max_time=40)
    record = play(lambda: fake_engine.FakeEnv(doomed=(7, fake_engine.BLUE_UNIT)), {CANDIDATE_ID: ShootReservationAgent},
                  spec, Inputs, PLAYERS, observer=Recorder())
    if record["status"] != "COMPLETED" or not steps:
        raise SystemExit(f"the synthetic game did not complete: {record['status']} {record.get('failure')}")
    setups = {p["seat"]: {"scenario": Inputs.scenario, "basic_data": Inputs.basic, "cost_data": Inputs.cost,
                          "see_data": Inputs.see, "seat": p["seat"], "faction": p["faction"], "role": p["role"],
                          "user_name": p["user_name"], "user_id": p["user_id"]} for p in PLAYERS}
    return {"setups": setups, "steps": steps}


def smoke(data: bytes, inputs: Dict[str, Any], python: str = sys.executable) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "extract"
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            archive.extractall(root)
        for path in root.rglob("*"):
            if path.is_file():
                path.chmod(0o444)
        pickled = Path(tmp) / "inputs.pkl"
        pickled.write_bytes(pickle.dumps(inputs, protocol=4))
        script = Path(tmp) / "smoke.py"
        script.write_text(SMOKE, encoding="utf-8")
        result = subprocess.run([python, "-I", "-B", str(script), str(root), str(pickled)], capture_output=True,
                                text=True, cwd=tmp, env={"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")})
        if result.returncode != 0:
            raise SystemExit(f"package smoke failed:\n{result.stdout}\n{result.stderr}")
        return json.loads(result.stdout.strip().splitlines()[-1])


def corpus_inputs() -> List[Dict[str, Any]]:
    """Every recorded observation of the private replay corpus, with the repository agent's actions on it."""
    import gzip
    from miaosuan_agent import typed_json
    from miaosuan_agent.experiments.shoot_reservation import ShootReservationAgent

    corpus = json.loads((REPO_ROOT / "evaluation" / "routing-remediation-1" / "corpus.json").read_text(encoding="utf-8"))
    data_root = REPO_ROOT / "local" / "evaluation" / "baseline-v1-variance-study-1" / "data"
    from miaosuan_agent import sdk_data
    games = []
    for entry in corpus["files"]:
        if entry["role"] != "replay corpus game":
            continue
        with gzip.open(REPO_ROOT / entry["path"], "rt", encoding="utf-8") as handle:
            header = json.loads(next(handle))
            rows = [json.loads(line) for line in handle]
        cost = sdk_data.load_inputs(data_root / header["scenario_id"] / "Data", header["scenario_id"], header["map_id"]).cost
        setups, agents, steps = {}, {}, []
        for row in rows:
            seat = row["seat"]
            if seat not in setups:
                setups[seat] = {"seat": seat, "faction": row["faction"], "cost_data": cost}
                agents[seat] = ShootReservationAgent()
                agents[seat].setup(setups[seat])
            observation = typed_json.decode(row["observation"])
            steps.append((seat, observation, agents[seat].step(observation)))
        games.append({"setups": setups, "steps": steps})
    return games


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", default="miaosuan-baseline-v2-canary")
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "dist")
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument("--replay-corpus", action="store_true", help="also replay the private corpus (server)")
    parser.add_argument("--python", default=sys.executable, help="interpreter for the isolated smoke")
    args = parser.parse_args()
    payload = entries()
    problems = [p for name, content in payload.items() for p in forbidden(name, content)]
    data = write_zip(payload)
    problems += verify_zip(data)
    if problems:
        raise SystemExit("REFUSED:\n" + "\n".join(problems))
    report: Dict[str, Any] = {"name": args.name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                              "files": len(payload), "policy": POLICY_IDENTITY, "policy_source_sha256": POLICY_SOURCE_SHA256}
    if not args.skip_smoke:
        result = smoke(data, synthetic_inputs(), args.python)
        if result["mismatches"] or not result["steps"]:
            raise SystemExit(f"package smoke: {result}")
        report["smoke"] = result
    if args.replay_corpus:
        totals = {"games": 0, "steps": 0, "mismatches": 0}
        for game in corpus_inputs():
            result = smoke(data, game, args.python)
            totals["games"] += 1
            totals["steps"] += result["steps"]
            totals["mismatches"] += result["mismatches"]
        report["replay_corpus"] = totals
        if totals["mismatches"]:
            raise SystemExit(f"replay corpus: {totals}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / f"{args.name}.zip").write_bytes(data)
    listing = {"report": report, "files": {name: {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
                                           for name, content in sorted(payload.items())}}
    (args.out_dir / f"{args.name}.manifest.json").write_text(json.dumps(listing, indent=1, sort_keys=True) + "\n",
                                                             encoding="utf-8")
    print(json.dumps(report, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
