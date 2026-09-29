"""Stage and load the SDK's map and scenario inputs from their real on-disk layout.

The SDK's ``Data.zip`` extracts to ``Data/scenarios/<scenario_id>.json`` and
``Data/maps/map_<map_id>/{basic.json, cost.pickle, <map_id>see.npz}``. Scenario files do not name
their map, so callers pass both identifiers explicitly.
"""

from __future__ import annotations

import io
import json
import pickle
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from . import sdk_provenance as prov


class SdkDataError(RuntimeError):
    """Raised when SDK inputs are missing, fail verification or are malformed."""


def scenario_path(data_root: Path, scenario_id: str) -> Path:
    return Path(data_root) / "scenarios" / f"{scenario_id}.json"


def map_paths(data_root: Path, map_id: str) -> Dict[str, Path]:
    directory = Path(data_root) / "maps" / f"map_{map_id}"
    return {
        "basic": directory / "basic.json",
        "cost": directory / "cost.pickle",
        "see": directory / f"{map_id}see.npz",
    }


class _PrimitiveUnpickler(pickle.Unpickler):
    """Unpickler that refuses every global lookup, so loading cannot execute code.

    The SDK's ``cost.pickle`` files contain only dicts, lists and ints, which need no globals.
    """

    def find_class(self, module: str, name: str) -> Any:
        raise SdkDataError(f"refusing to unpickle global {module}.{name}: only primitive data is allowed")


def load_cost(path: Path) -> Any:
    """Load a ``cost.pickle`` file, rejecting anything but primitive containers and scalars."""
    with Path(path).open("rb") as handle:
        return _PrimitiveUnpickler(handle).load()


def load_see(path: Path) -> Any:
    """Load the line-of-sight array stored under key ``data`` in a ``see.npz`` file."""
    import numpy  # imported lazily: the rest of the package does not need numpy

    with numpy.load(Path(path), allow_pickle=False) as archive:
        if "data" not in archive.files:
            raise SdkDataError(f"{path} has no 'data' array (found {archive.files})")
        return archive["data"]


@dataclass(frozen=True)
class ScenarioInputs:
    """Everything ``TrainEnv.setup`` needs besides the player list."""

    scenario_id: str
    map_id: str
    scenario: Dict[str, Any]
    basic: Dict[str, Any]
    cost: Any
    see: Any


def load_inputs(data_root: Path, scenario_id: str, map_id: str) -> ScenarioInputs:
    """Load one scenario and one map, and check that the scenario fits inside the map."""
    paths = {"scenario": scenario_path(data_root, scenario_id), **map_paths(data_root, map_id)}
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise SdkDataError(f"missing SDK input files: {missing}")
    scenario = json.loads(paths["scenario"].read_text(encoding="utf-8"))
    basic = json.loads(paths["basic"].read_text(encoding="utf-8"))
    grid = basic.get("map_data")
    if not isinstance(grid, list) or not grid or not isinstance(grid[0], list):
        raise SdkDataError(f"{paths['basic']} has no two-dimensional 'map_data'")
    rows, cols = len(grid), len(grid[0])
    hexes = [op.get("cur_hex") for op in scenario.get("operators", [])]
    hexes += [city.get("coord") for city in scenario.get("cities", [])]
    outside = [h for h in hexes if not (isinstance(h, int) and 0 <= h // 100 < rows and 0 <= h % 100 < cols)]
    if outside:
        raise SdkDataError(f"scenario {scenario_id} has positions outside map {map_id} ({rows}x{cols}): {outside}")
    return ScenarioInputs(
        scenario_id=str(scenario_id),
        map_id=str(map_id),
        scenario=scenario,
        basic=basic,
        cost=load_cost(paths["cost"]),
        see=load_see(paths["see"]),
    )


def _write_new(path: Path, data: bytes) -> None:
    if path.exists():
        raise SdkDataError(f"refusing to overwrite existing file {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _read_verified_member(sdk_archive: Path, member: str) -> bytes:
    """Read one nested member of the SDK archive after checking the archive and the member digests."""
    sdk_archive = Path(sdk_archive)
    if prov.sha256_file(sdk_archive) != prov.SDK_ARCHIVE_SHA256:
        raise SdkDataError(f"{sdk_archive} does not match the recorded SDK archive digest")
    with zipfile.ZipFile(sdk_archive) as outer:
        blob = outer.read(member)
    if prov.sha256_stream(io.BytesIO(blob)) != prov.NESTED_ARCHIVES[member]:
        raise SdkDataError(f"nested member {member} does not match its recorded digest")
    return blob


def stage_game_data(sdk_archive: Path, dest: Path, scenario_id: str, map_id: str) -> Path:
    """Copy one scenario and one map out of a verified SDK archive; return the ``Data/`` root.

    Only the four files one game needs are written, under ``dest/Data/``. Nothing is overwritten.
    """
    dest = Path(dest)
    members = {"scenario": f"Data/scenarios/{scenario_id}.json"}
    members.update({key: f"Data/maps/map_{map_id}/{path.name}" for key, path in map_paths(Path("."), map_id).items()})
    with zipfile.ZipFile(io.BytesIO(_read_verified_member(sdk_archive, prov.DATA_ARCHIVE_MEMBER))) as inner:
        names = set(inner.namelist())
        absent = [name for name in members.values() if name not in names]
        if absent:
            raise SdkDataError(f"Data.zip lacks {absent}")
        for name in members.values():
            _write_new(dest / name, inner.read(name))
    return dest / "Data"


def extract_engine_wheel(sdk_archive: Path, dest_dir: Path) -> Path:
    """Write the verified engine wheel into ``dest_dir`` and return its path. Nothing is overwritten.

    Used only to create the persistent engine installation (:mod:`miaosuan_agent.engine_install`).
    """
    path = Path(dest_dir) / prov.ENGINE_WHEEL_MEMBER
    _write_new(path, _read_verified_member(sdk_archive, prov.ENGINE_WHEEL_MEMBER))
    return path
