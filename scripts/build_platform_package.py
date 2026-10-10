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
import re
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
FORBIDDEN_TEXT = ("BEGIN PRIVATE KEY", "train_env", "land_wargame_sdk")
#: Private infrastructure identifiers, built by concatenation like tests/test_docs_policy.py so this file never
#: matches them itself.
FORBIDDEN_PATTERNS = {
    "home directory": re.compile("/" + "home/" + r"[A-Za-z0-9_.-]+"),
    "Windows drive path": re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:" + r"[\\/][^\s`]"),
    "private IPv4 address": re.compile(r"\b(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b"),
}

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
#: Wrapper variants. ``canary`` is the frozen canary's entry point above (its archive bytes must not change);
#: ``compat1`` wraps the same frozen policy in a transport-compatibility layer and changes no policy file.
VARIANTS = ("canary", "compat1", "compat2")
VARIANT_NAMES = {"canary": "miaosuan-baseline-v2-canary", "compat1": "miaosuan-baseline-v2-compat1",
                 "compat2": "miaosuan-baseline-v2-compat2"}
AGENT_COMPAT1 = '''"""Platform entry point: the frozen __IDENTITY__ policy (policy source __DIGEST__), wrapper compat1.

The policy and every vendored module are the canary's, unchanged. This wrapper adapts only the form of the inputs and
keeps a match able to leave its deployment stage:

* JSON form. A transport through JSON turns every integer mapping key (the neighbour hexes of ``cost_data``, the seats
  of ``role_and_grouping_info``, the unit ids and action types of ``valid_actions``) into a decimal string, which the
  frozen policy rejects: ``setup`` raised, or every step failed its contract and deployment never ended. Mappings whose
  keys are all canonical decimal strings are converted to integer keys, and a decimal-string ``seat`` or ``faction``
  to an int. Input with no such mapping is passed on as the very same object, so on the engine's own form the actions
  are exactly the canary's.
* Start-up safety. An exception in ``setup`` is reported instead of raised. If the policy cannot act because of an
  error (failed setup, a contract error or an exception in a step) while the stage is deployment and the seat has not
  ended its deployment, the wrapper issues the end-of-deployment action (type 333) for the seat, which is what the
  policy itself does at its first deployment step.
* Diagnostics. Once per game, stderr receives the setup_info key names, the types of ``seat`` and ``faction``,
  whether ``cost_data`` is present (without it no unit is ever ordered to move) and the input form; every distinct
  error is reported once. Every line starts with ``[__IDENTITY__/compat1]``. No value of the inputs is printed.
"""

import re
import sys
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .base_agent import BaseAgent
from .__PACKAGE__.experiments.shoot_reservation import __AGENT_CLASS__

IDENTITY = "__IDENTITY__"
WRAPPER = "compat1"
POLICY_SOURCE_SHA256 = "__DIGEST__"
END_DEPLOYMENT = 333
DEPLOYMENT_STAGE = 1
_DECIMAL = re.compile(r"0|-?[1-9][0-9]*")


def _decimal(value: Any) -> bool:
    return isinstance(value, str) and _DECIMAL.fullmatch(value) is not None


def _int_keys(value: Any) -> Tuple[Any, bool]:
    """``value`` with every all-decimal-string-keyed mapping re-keyed by int, and whether anything changed.

    An unchanged value is returned as the same object.
    """
    if isinstance(value, Mapping):
        items = list(value.items())
        rekey = bool(items) and all(_decimal(key) for key, _ in items)
        changed = rekey
        converted = []
        for key, item in items:
            new, sub = _int_keys(item)
            changed = changed or sub
            converted.append((int(key) if rekey else key, new))
        return (dict(converted), True) if changed else (value, False)
    if isinstance(value, (list, tuple)):
        converted = []
        changed = False
        for item in value:
            new, sub = _int_keys(item)
            changed = changed or sub
            converted.append(new)
        if not changed:
            return value, False
        return (converted if isinstance(value, list) else tuple(converted)), True
    return value, False


def _as_int(value: Any) -> Optional[int]:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if _decimal(value):
        return int(value)
    return None


def _type_name(value: Any) -> str:
    return "absent" if value is None else type(value).__name__


class Agent(BaseAgent):
    def __init__(self) -> None:
        self._agent = __AGENT_CLASS__()
        self._reported: set = set()
        self._seat: Optional[int] = None
        self._setup_error: Optional[str] = None
        self._observed = False

    def _report(self, message: str) -> None:
        if message not in self._reported and len(self._reported) < 50:
            self._reported.add(message)
            print(f"[{IDENTITY}/{WRAPPER}] {message}", file=sys.stderr, flush=True)

    def setup(self, setup_info: Dict[str, Any]) -> None:
        self._setup_error = None
        self._observed = False
        self._seat = None
        try:
            keys = sorted(str(key) for key in setup_info) if isinstance(setup_info, Mapping) else []
            get = setup_info.get if isinstance(setup_info, Mapping) else (lambda key: None)
            self._report(f"setup: keys {keys}; seat {_type_name(get('seat'))}; faction {_type_name(get('faction'))}; "
                         f"cost_data {'present' if get('cost_data') is not None else 'ABSENT (units will not move)'}")
            self._seat = _as_int(get("seat"))
            info = setup_info
            changed: Dict[str, Any] = {}
            for name in ("seat", "faction"):
                if not isinstance(get(name), int) and _as_int(get(name)) is not None:
                    changed[name] = _as_int(get(name))
            costs, rekeyed = _int_keys(get("cost_data"))
            if rekeyed:
                changed["cost_data"] = costs
            if changed:
                info = dict(setup_info, **changed)
                self._report(f"setup: converted to integer form: {sorted(changed)}")
            self._agent.setup(info)
        except Exception as exc:  # noqa: BLE001 - reported; the wrapper can still end the deployment
            self._setup_error = f"{type(exc).__name__}: {exc}"[:500]
            self._report(f"setup error: {self._setup_error}")

    def _fallback(self, observation: Any) -> List[Dict[str, Any]]:
        """End the seat's deployment while that is still possible; otherwise no action."""
        try:
            if self._seat is None or _as_int(observation["time"]["stage"]) != DEPLOYMENT_STAGE:
                return []
            seats = observation.get("role_and_grouping_info") or {}
            entry = seats.get(self._seat, seats.get(str(self._seat))) if isinstance(seats, Mapping) else None
            if isinstance(entry, Mapping) and entry.get("end_deployment") is True:
                return []
        except Exception:  # noqa: BLE001 - an unreadable stage means no action
            return []
        self._report("fallback: ending the deployment for the seat after an error")
        return [{"actor": self._seat, "type": END_DEPLOYMENT}]

    def step(self, observation: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self._observed and isinstance(observation, Mapping):
            self._observed = True
            self._report(f"first observation: keys {sorted(str(key) for key in observation)}")
        try:
            converted, rekeyed = _int_keys(observation)
        except Exception as exc:  # noqa: BLE001
            self._report(f"input error: {type(exc).__name__}: {exc}"[:500])
            converted, rekeyed = observation, False
        if rekeyed:
            self._report("observation: JSON form, integer keys converted")
        if self._setup_error is not None:
            return self._fallback(converted)
        try:
            actions = self._agent.step(converted)
        except Exception as exc:  # noqa: BLE001 - reported, and the agent keeps playing
            self._report(f"step error: {type(exc).__name__}: {exc}"[:500])
            return self._fallback(converted)
        trace = self._agent.last_trace
        error = getattr(trace, "error", None)
        if error:
            self._report(f"contract error: {error}"[:500])
            if not actions:
                return self._fallback(converted)
        return actions

    def reset(self) -> None:
        try:
            self._agent.reset()
        except Exception as exc:  # noqa: BLE001
            self._report(f"reset error: {type(exc).__name__}: {exc}"[:500])
        self._reported = set()
        self._seat = None
        self._setup_error = None
        self._observed = False
'''
AGENT_COMPAT2 = r'''"""Platform entry point: the frozen __IDENTITY__ policy (policy source __DIGEST__), wrapper compat2.

The policy and every vendored module are the canary's, unchanged. compat2 is a strict adapter between the online
platform's seat representation and the frozen policy's. It follows an online test match in which the platform passed
``setup_info.seat`` as the string ``"p3"``: compat1's setup failed on it, and the agent returned no action all game.

Seat identity, the only identity translated:

* external seat: ``setup_info["seat"]`` exactly as passed. Accepted: an int (the local engine's form) or ``"p<N>"``
  with N a canonical decimal of at least 1 (the online form). Anything else fails setup.
* internal seat: the int itself, or N for ``"p<N>"``; the frozen policy sees only the internal seat.
* outbound ``actor``: the external seat, verbatim. The platform's documented reference agent stores
  ``self.seat = setup_info["seat"]``, issues ``"actor": self.seat`` and reads
  ``observation["role_and_grouping_info"][self.seat]``. An action whose actor is not the internal seat is dropped.
* ``role_and_grouping_info`` keys: an int, its decimal-string JSON form, ``"p<N>"`` (to N), or the platform's
  non-player entry ``"god"`` (to the reserved internal seat -1, accepted only with faction -1, role -1 and no units).
  Any other key, or two keys for one internal seat, is a contract error for that step. A non-int ``user_id`` (the
  platform sends strings; the policy never reads it) is left out of the internal view only.

Other inputs: mappings whose keys are all decimal strings (a JSON transport) are re-keyed by int, as in compat1,
``cost_data`` included. Nothing else is changed. Input that needs no change reaches the policy as the same object, so
on the local engine's form every action is the canary's.

Status: ``setup()`` ends ``ready`` or ``failed``. A failure is reported with the exception class, the field path
(indices masked) and a category, and is never reported as success. While not ``ready`` a step returns no action,
except the labelled FALLBACK that only ends the seat's deployment when the external seat itself was valid; the same
fallback answers a deployment step that failed its contract. Diagnostics are bounded: the setup result, the first
observation, the first deployment and play decisions, the first MOVE, zero controllable units, a missing router,
distinct errors and invalid outputs; at most 50 lines per game. No input value except the form of the external seat
is printed. Every line starts with ``[__IDENTITY__/compat2]``.
"""

import re
import sys
from collections import Counter
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .base_agent import BaseAgent
from .__PACKAGE__.experiments.shoot_reservation import __AGENT_CLASS__

IDENTITY = "__IDENTITY__"
WRAPPER = "compat2"
POLICY_SOURCE_SHA256 = "__DIGEST__"
END_DEPLOYMENT = 333
MOVE = 1
DEPLOYMENT_STAGE = 1
PLAY_STAGE = 2
NON_PLAYER_KEY = "god"
NON_PLAYER_INTERNAL = -1
MAX_LINES = 50
_DECIMAL = re.compile(r"0|-?[1-9][0-9]*")
_PLAYER = re.compile(r"p([1-9][0-9]*)")
_INDEX = re.compile(r"\[[^\]]*\]")
_DIGITS = re.compile(r"[0-9]+")
_CONTRACT = re.compile(r"^(?P<cls>\w+): (?P<path>.*?): expected (?P<expected>.*?), got ")


class SeatError(ValueError):
    """A seat identifier or seat table the adapter does not accept. The message names a field, never a value."""

    def __init__(self, path: str, expected: str) -> None:
        self.path, self.expected = path, expected
        super().__init__(f"{path}: expected {expected}")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _decimal(value: Any) -> bool:
    return isinstance(value, str) and _DECIMAL.fullmatch(value) is not None


def _int_keys(value: Any) -> Tuple[Any, bool]:
    """``value`` with every all-decimal-string-keyed mapping re-keyed by int, and whether anything changed.

    An unchanged value is returned as the same object.
    """
    if isinstance(value, Mapping):
        items = list(value.items())
        rekey = bool(items) and all(_decimal(key) for key, _ in items)
        changed = rekey
        converted = []
        for key, item in items:
            new, sub = _int_keys(item)
            changed = changed or sub
            converted.append((int(key) if rekey else key, new))
        return (dict(converted), True) if changed else (value, False)
    if isinstance(value, (list, tuple)):
        converted = []
        changed = False
        for item in value:
            new, sub = _int_keys(item)
            changed = changed or sub
            converted.append(new)
        if not changed:
            return value, False
        return (converted if isinstance(value, list) else tuple(converted)), True
    return value, False


def internal_seat(external: Any) -> int:
    """The internal seat of an external seat identifier, or SeatError."""
    if _is_int(external):
        return external
    if isinstance(external, str):
        match = _PLAYER.fullmatch(external)
        if match:
            return int(match.group(1))
    raise SeatError("setup_info.seat", "an int or 'p<N>' with N >= 1")


def seat_form(external: Any) -> str:
    if isinstance(external, str):
        return "'p<N>'" if _PLAYER.fullmatch(external) else "str (unrecognised)"
    return type(external).__name__


def _seat_key(key: Any, entry: Any) -> int:
    path = "role_and_grouping_info"
    if _is_int(key):
        return key
    if isinstance(key, str):
        if _decimal(key):
            return int(key)
        match = _PLAYER.fullmatch(key)
        if match:
            return int(match.group(1))
        if key == NON_PLAYER_KEY:
            if (isinstance(entry, Mapping) and _is_int(entry.get("faction")) and entry.get("faction") == -1
                    and _is_int(entry.get("role")) and entry.get("role") == -1 and not entry.get("operators")):
                return NON_PLAYER_INTERNAL
            raise SeatError(path, "the non-player entry with faction -1, role -1 and no units")
    raise SeatError(path, "seat keys that are ints, 'p<N>' or the non-player entry")


def adapt_seats(observation: Any) -> Tuple[Any, bool]:
    """The observation with its seat table keyed by internal seat, and whether anything changed."""
    if not isinstance(observation, Mapping):
        return observation, False
    table = observation.get("role_and_grouping_info")
    if not isinstance(table, Mapping):
        return observation, False
    adapted: Dict[int, Any] = {}
    changed = False
    for key, entry in table.items():
        internal = _seat_key(key, entry)
        if internal in adapted:
            raise SeatError("role_and_grouping_info", "one key per internal seat (two keys collide)")
        if not (_is_int(key) and key == internal):
            changed = True
        if isinstance(entry, Mapping) and "user_id" in entry and not _is_int(entry["user_id"]):
            entry = {name: value for name, value in entry.items() if name != "user_id"}
            changed = True
        adapted[internal] = entry
    if not changed:
        return observation, False
    out = dict(observation)
    out["role_and_grouping_info"] = adapted
    return out, True


def _key_forms(table: Any) -> List[str]:
    forms: Counter = Counter()
    for key in (table if isinstance(table, Mapping) else ()):
        if _is_int(key):
            forms["int"] += 1
        elif _decimal(key):
            forms["decimal str"] += 1
        elif isinstance(key, str) and _PLAYER.fullmatch(key):
            forms["'p<N>'"] += 1
        elif key == NON_PLAYER_KEY:
            forms["non-player"] += 1
        else:
            forms["other"] += 1
    return [f"{form} x{count}" for form, count in sorted(forms.items())]


def _sanitise_path(path: str) -> str:
    return _INDEX.sub("[*]", path)


def _describe(exc: BaseException) -> Tuple[str, str]:
    """(class and sanitised path, category) of an exception, without any value from the input."""
    path = getattr(exc, "path", None)
    if isinstance(path, str):
        path = _sanitise_path(path)
    else:
        path = "<no field>"
    if "cost_data" in path:
        category = "cost_data"
    elif path.endswith(".seat") or path == "role_and_grouping_info" or "role_and_grouping_info" in path:
        category = "seat"
    elif path.endswith(".faction"):
        category = "faction"
    elif isinstance(exc, (SeatError,)) or type(exc).__name__ == "ContractError":
        category = "contract"
    else:
        category = "internal"
    expected = getattr(exc, "expected", None)
    where = f"{type(exc).__name__} at {path}" + (f": expected {expected}" if isinstance(expected, str) else "")
    return where, category


def _describe_trace_error(error: str) -> str:
    match = _CONTRACT.match(error)
    if match:
        return f"{match.group('cls')} at {_sanitise_path(match.group('path'))}: expected {match.group('expected')}"
    return _DIGITS.sub("N", error.split(":", 1)[0])


class Agent(BaseAgent):
    def __init__(self) -> None:
        self._agent = __AGENT_CLASS__()
        self._clear()

    # -- state and diagnostics ---------------------------------------------------------------------

    def _clear(self) -> None:
        self.status = "uninitialized"
        self._external: Any = None
        self._internal: Optional[int] = None
        self._lines: set = set()
        self._limited = False
        self._once: set = set()

    def _report(self, message: str) -> None:
        if message in self._lines:
            return
        if len(self._lines) >= MAX_LINES:
            if not self._limited:
                self._limited = True
                print(f"[{IDENTITY}/{WRAPPER}] diagnostic limit reached; further lines suppressed",
                      file=sys.stderr, flush=True)
            return
        self._lines.add(message)
        print(f"[{IDENTITY}/{WRAPPER}] {message}", file=sys.stderr, flush=True)

    def _first(self, key: str) -> bool:
        if key in self._once:
            return False
        self._once.add(key)
        return True

    # -- interface ---------------------------------------------------------------------------------

    def setup(self, setup_info: Dict[str, Any]) -> None:
        try:
            self._agent.reset()
        except Exception:  # noqa: BLE001 - a fresh agent has nothing to reset
            pass
        self._clear()
        self.status = "failed"
        try:
            if not isinstance(setup_info, Mapping):
                raise SeatError("setup_info", "a mapping")
            external = setup_info.get("seat")
            form = seat_form(external)
            internal = internal_seat(external)
            faction = setup_info.get("faction")
            if not _is_int(faction) or faction not in (0, 1):
                raise SeatError("setup_info.faction", "0 or 1")
            info = dict(setup_info)
            info["seat"] = internal
            raw_costs = setup_info.get("cost_data")
            if raw_costs is None:
                cost_status = "ABSENT"
            else:
                converted, rekeyed = _int_keys(raw_costs)
                if rekeyed:
                    info["cost_data"] = converted
                cost_status = "present, JSON keys converted" if rekeyed else "present"
            self._external, self._internal = external, internal
            self._agent.setup(info)
            costs = getattr(self._agent, "costs", None)
            router = getattr(getattr(self._agent, "policy", None), "router", None)
            if costs is not None:
                cost_status += f", parsed ({len(costs.edges)} modes, {costs.rows}x{costs.cols} hexes)"
            self.status = "ready"
            self._report(f"setup OK: external seat {form} mapped to the internal seat; faction {faction}; "
                         f"cost_data {cost_status}; movement router {'ready' if router is not None else 'UNAVAILABLE'}; "
                         f"policy {IDENTITY} initialised")
            if router is None:
                self._report("movement router UNAVAILABLE: no MOVE can be generated in this game")
        except Exception as exc:  # noqa: BLE001 - reported as a failure, never as success
            self.status = "failed"
            where, category = _describe(exc)
            self._report(f"SETUP FAILED: {where}; category {category}; the agent is NOT initialised")

    def _seat_entry(self, observation: Any) -> Optional[Mapping]:
        table = observation.get("role_and_grouping_info") if isinstance(observation, Mapping) else None
        if not isinstance(table, Mapping) or self._internal is None:
            return None
        for key, entry in table.items():
            try:
                if _seat_key(key, entry) == self._internal:
                    return entry if isinstance(entry, Mapping) else None
            except SeatError:
                continue
        return None

    def _fallback(self, observation: Any, reason: str) -> List[Dict[str, Any]]:
        """FALLBACK: end the seat's deployment while that is still possible; otherwise no action."""
        if self._external is None or self._internal is None:
            return []
        try:
            stage = observation["time"]["stage"]
            if stage != DEPLOYMENT_STAGE and stage != str(DEPLOYMENT_STAGE):
                return []
            entry = self._seat_entry(observation)
            if entry is not None and entry.get("end_deployment") is True:
                return []
        except Exception:  # noqa: BLE001 - an unreadable stage means no action
            return []
        self._report(f"FALLBACK ({reason}): ending the seat's deployment only; this is not a policy decision")
        return [{"actor": self._external, "type": END_DEPLOYMENT}]

    def _first_observation(self, raw: Any) -> None:
        if not self._first("observation") or not isinstance(raw, Mapping):
            return
        table = raw.get("role_and_grouping_info")
        entry = self._seat_entry(raw)
        if entry is None:
            self._report(f"first observation: seat keys {_key_forms(table)}; NO entry for this seat")
            return
        faction = entry.get("faction")
        consistent = "consistent" if faction == self._agent.faction else "INCONSISTENT"
        units = entry.get("operators")
        count = len(units) if isinstance(units, (list, tuple)) else "unreadable"
        self._report(f"first observation: seat keys {_key_forms(table)}; own entry found; faction {consistent} with "
                     f"setup; {count} units listed for the seat")

    def _observe(self, trace: Any, actions: List[Dict[str, Any]]) -> None:
        stage = getattr(trace, "stage", None)
        types = Counter(int(t) for t, _ in getattr(trace, "emitted", ()) or ())
        if stage == DEPLOYMENT_STAGE and self._first("deployment"):
            self._report(f"first deployment decision: emitted types {dict(sorted(types.items()))}")
        if stage == PLAY_STAGE and self._first("play"):
            units = getattr(trace, "units", ()) or ()
            moves = sum(1 for u in units if getattr(u, "rule", None) == "move")
            reasons = Counter(_DIGITS.sub("N", u.no_op_reason) for u in units if getattr(u, "no_op_reason", None))
            self._report(f"first play decision: {len(units)} controllable units; {moves} MOVE selected; emitted types "
                         f"{dict(sorted(types.items()))}; no-action reasons {dict(sorted(reasons.items()))}")
            if not units:
                self._report("ZERO controllable units for this seat")
        for _, _, reason in getattr(trace, "rejected", ()) or ():
            self._report(f"policy gate rejected an action: {_DIGITS.sub('N', str(reason))}")
        if types.get(MOVE) and self._first("move"):
            self._report(f"first MOVE emitted at step {getattr(trace, 'step', '?')} ({types[MOVE]} in that step)")

    def _outbound(self, actions: List[Any]) -> List[Dict[str, Any]]:
        out = []
        for action in actions:
            if not isinstance(action, Mapping) or not _is_int(action.get("actor")) or action.get("actor") != self._internal:
                self._report("INVALID OUTPUT dropped: an action whose actor is not this seat")
                continue
            converted = dict(action)
            converted["actor"] = self._external
            out.append(converted)
        if out and self._first("format"):
            first = out[0]
            self._report(f"first submitted action: type {first.get('type')}, keys {sorted(first)}, "
                         f"actor {seat_form(first['actor'])}")
        return out

    def step(self, observation: Dict[str, Any]) -> List[Dict[str, Any]]:
        if self.status != "ready":
            if self._first("not-ready"):
                self._report(f"step while {self.status}: no policy decision")
            return self._fallback(observation, f"setup {self.status}")
        try:
            converted, _ = _int_keys(observation)
            adapted, _ = adapt_seats(converted)
        except Exception as exc:  # noqa: BLE001
            where, category = _describe(exc)
            self._report(f"input error: {where}; category {category}")
            return self._fallback(observation, "unreadable input")
        self._first_observation(observation)
        try:
            actions = self._agent.step(adapted)
        except Exception as exc:  # noqa: BLE001 - reported, and the agent keeps playing
            where, category = _describe(exc)
            self._report(f"step error: {where}; category {category}")
            return self._fallback(adapted, "step error")
        trace = self._agent.last_trace
        error = getattr(trace, "error", None)
        if error:
            self._report(f"contract error: {_describe_trace_error(str(error))}")
            if not actions:
                return self._fallback(adapted, "contract error")
        self._observe(trace, actions)
        return self._outbound(actions)

    def reset(self) -> None:
        try:
            self._agent.reset()
        except Exception as exc:  # noqa: BLE001
            self._report(f"reset error: {type(exc).__name__}")
        self._clear()
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


def agent_source(variant: str = "canary") -> str:
    if variant == "canary":
        return AGENT.format(identity=POLICY_IDENTITY, digest=POLICY_SOURCE_SHA256, package=PACKAGE,
                            agent_class=AGENT_CLASS)
    if variant in ("compat1", "compat2"):
        source = AGENT_COMPAT1 if variant == "compat1" else AGENT_COMPAT2
        for marker, value in (("__IDENTITY__", POLICY_IDENTITY), ("__DIGEST__", POLICY_SOURCE_SHA256),
                             ("__PACKAGE__", PACKAGE), ("__AGENT_CLASS__", AGENT_CLASS)):
            source = source.replace(marker, value)
        return source
    raise SystemExit(f"unknown variant {variant!r}; known: {list(VARIANTS)}")


def entries(variant: str = "canary") -> Dict[str, bytes]:
    check_policy_source()
    files, external = closure()
    check_external(external)
    payload: Dict[str, bytes] = {
        "ai/__init__.py": INIT.encode("utf-8"),
        "ai/base_agent.py": BASE.encode("utf-8"),
        "ai/agent.py": agent_source(variant).encode("utf-8"),
    }
    for relative in files:
        payload[f"ai/{relative}"] = (SRC / relative).read_bytes()
    manifest = {"package": "ai", "policy": POLICY_IDENTITY, "policy_source_sha256": POLICY_SOURCE_SHA256,
                "agent_class": f"{PACKAGE}.experiments.shoot_reservation.{AGENT_CLASS}", "python": ">=3.10",
                "third_party": [], "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(payload.items())}}
    if variant != "canary":
        manifest["wrapper"] = variant
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
    for label, pattern in FORBIDDEN_PATTERNS.items():
        if pattern.search(text):
            problems.append(f"{name}: {label}")
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


def _plain(value: Any) -> Any:
    """JSON encoder fallback for the arrays in the setup data (``see_data``)."""
    if hasattr(value, "tolist"):
        return value.tolist()
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")


def json_form(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """The same game as a JSON transport delivers it: setups and observations round-tripped through JSON (integer
    mapping keys become decimal strings); the expected actions stay those of the engine-form inputs."""
    def round_trip(value: Any) -> Any:
        return json.loads(json.dumps(value, default=_plain))
    return {"setups": {seat: round_trip(setup) for seat, setup in inputs["setups"].items()},
            "steps": [(seat, round_trip(observation), expected) for seat, observation, expected in inputs["steps"]]}


#: The non-player seat entry as the online platform delivers it (match evidence: faction -1, role -1, no units).
PLATFORM_NON_PLAYER = {"faction": -1, "role": -1, "operators": [], "user_id": "god", "user_name": "god",
                       "end_deployment": True}


def platform_seat(seat: Any) -> str:
    return f"p{seat}"


def platform_form(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """SYNTHETIC: engine-form inputs re-expressed in the seat representation the online platform used (seat "p<N>",
    seat-table keys "p<N>" plus the non-player "god" entry, string user ids, a string scenario id with a suffix, an
    extra top-level field, JSON keys). Every other value is the engine's. The expected actions are the engine-form
    ones with ``actor`` replaced by the platform seat; nothing else in them changes."""
    def observation(raw: Any) -> Dict[str, Any]:
        ob = json.loads(json.dumps(raw, default=_plain))
        table = {}
        for key, entry in ob["role_and_grouping_info"].items():
            entry = dict(entry)
            if "user_id" in entry:
                entry["user_id"] = str(entry["user_id"])
            table[platform_seat(key)] = entry
        table["god"] = dict(PLATFORM_NON_PLAYER)
        ob["role_and_grouping_info"] = table
        ob["scenario_id"] = f"{ob.get('scenario_id')}-1"
        ob["extra"] = {"global_jam_switch": 0}
        return ob

    def setup(raw: Dict[str, Any]) -> Dict[str, Any]:
        info = json.loads(json.dumps(raw, default=_plain))
        info["seat"] = platform_seat(raw["seat"])
        if "user_id" in info:
            info["user_id"] = str(info["user_id"])
        info["state"] = {}
        return info

    return {"setups": {seat: setup(info) for seat, info in inputs["setups"].items()},
            "steps": [(seat, observation(ob), [dict(a, actor=platform_seat(a["actor"])) for a in expected])
                      for seat, ob, expected in inputs["steps"]]}


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
    parser.add_argument("--variant", choices=VARIANTS, default="canary", help="entry-point wrapper (default: the canary)")
    parser.add_argument("--name", default=None, help="archive name (default: by variant)")
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "dist")
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument("--replay-corpus", action="store_true", help="also replay the private corpus (server)")
    parser.add_argument("--python", default=sys.executable, help="interpreter for the isolated smoke")
    args = parser.parse_args()
    args.name = args.name or VARIANT_NAMES[args.variant]
    payload = entries(args.variant)
    problems = [p for name, content in payload.items() for p in forbidden(name, content)]
    data = write_zip(payload)
    problems += verify_zip(data)
    if problems:
        raise SystemExit("REFUSED:\n" + "\n".join(problems))
    report: Dict[str, Any] = {"name": args.name, "variant": args.variant, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                              "files": len(payload), "policy": POLICY_IDENTITY, "policy_source_sha256": POLICY_SOURCE_SHA256}
    if not args.skip_smoke:
        result = smoke(data, synthetic_inputs(), args.python)
        if result["mismatches"] or not result["steps"]:
            raise SystemExit(f"package smoke: {result}")
        report["smoke"] = result
        if args.variant != "canary":
            result = smoke(data, json_form(synthetic_inputs()), args.python)
            if result["mismatches"] or not result["steps"]:
                raise SystemExit(f"package smoke, JSON form: {result}")
            report["smoke_json_form"] = result
        if args.variant == "compat2":
            result = smoke(data, platform_form(synthetic_inputs()), args.python)
            if result["mismatches"] or not result["steps"]:
                raise SystemExit(f"package smoke, platform form: {result}")
            report["smoke_platform_form"] = result
    if args.replay_corpus:
        forms = (("replay_corpus", lambda game: game),)
        if args.variant != "canary":
            forms += (("replay_corpus_json_form", json_form),)
        if args.variant == "compat2":
            forms += (("replay_corpus_platform_form", platform_form),)
        games = corpus_inputs()
        for label, form in forms:
            totals = {"games": 0, "steps": 0, "mismatches": 0}
            for game in games:
                result = smoke(data, form(game), args.python)
                totals["games"] += 1
                totals["steps"] += result["steps"]
                totals["mismatches"] += result["mismatches"]
            report[label] = totals
            if totals["mismatches"]:
                raise SystemExit(f"{label}: {totals}")
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
