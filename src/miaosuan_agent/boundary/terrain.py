"""Normalization of the map movement-cost data supplied to agents at setup.

``setup_info["cost_data"]`` (the SDK's ``cost.pickle``) is documented as a three-level list indexed
by movement mode, map row and map column; each cell maps a traversable neighbouring hex to the cost
of entering it. Hexes are four-digit indices, ``row * 100 + column``. The modes are documented as
0 vehicle maneuver, 1 vehicle march, 2 infantry, 3 air. In the observed data costs are ints and
floats and neighbour keys are ints (JSON copies would carry decimal-string keys).

The cost graph alone is not the whole movement contract: the observed graph for map 9601 still
contains edges into roadblock cells, which the rules make impassable to vehicles. Callers combine
:class:`MoveCosts` with the roadblocks reported in each observation.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Dict, Mapping, Tuple

from .checks import require_mapping, require_number, require_sequence
from .errors import ContractError
from .keys import Origin, normalize_int_keyed


class MoveMode(enum.IntEnum):
    """First index of the cost data, as documented."""

    VEHICLE = 0
    VEHICLE_MARCH = 1
    INFANTRY = 2
    AIR = 3


def hex_of(row: int, col: int) -> int:
    return row * 100 + col


@dataclass(frozen=True)
class MoveCosts:
    """Per-mode adjacency with entry costs: ``edges[mode][hex] -> {neighbour hex: cost}``."""

    rows: int
    cols: int
    edges: Tuple[Mapping[int, Mapping[int, float]], ...]

    @classmethod
    def from_raw(cls, raw: Any, origin: Origin = Origin.ENGINE, path: str = "cost_data") -> "MoveCosts":
        modes = require_sequence(raw, path)
        if len(modes) != len(MoveMode):
            raise ContractError(path, f"{len(MoveMode)} movement modes", modes)
        rows = cols = None
        edges = []
        for mode_index, mode_rows in enumerate(modes):
            mode_path = f"{path}[{mode_index}]"
            grid = require_sequence(mode_rows, mode_path)
            if rows is None:
                rows = len(grid)
            if len(grid) != rows or rows == 0:
                raise ContractError(mode_path, f"{rows} rows (as in mode 0)", grid)
            mode_edges: Dict[int, Mapping[int, float]] = {}
            for row_index, row in enumerate(grid):
                row_path = f"{mode_path}[{row_index}]"
                cells = require_sequence(row, row_path)
                if cols is None:
                    cols = len(cells)
                if len(cells) != cols or cols == 0 or cols > 100:
                    raise ContractError(row_path, f"{cols} columns (1 to 100)", cells)
                for col_index, cell in enumerate(cells):
                    cell_path = f"{row_path}[{col_index}]"
                    neighbours: Dict[int, float] = {}
                    for neighbour, cost in normalize_int_keyed(require_mapping(cell, cell_path), origin, cell_path).items():
                        if not (0 <= neighbour // 100 < rows and 0 <= neighbour % 100 < cols) or neighbour < 0:
                            raise ContractError(f"{cell_path}[{neighbour}]", "a neighbour hex inside the map", neighbour)
                        value = require_number(cost, f"{cell_path}[{neighbour}]")
                        if not value > 0:
                            raise ContractError(f"{cell_path}[{neighbour}]", "a positive cost", cost)
                        neighbours[neighbour] = value
                    mode_edges[hex_of(row_index, col_index)] = MappingProxyType(neighbours)
            edges.append(MappingProxyType(mode_edges))
        return cls(rows=rows, cols=cols, edges=tuple(edges))

    def contains(self, hex_: int) -> bool:
        return isinstance(hex_, int) and not isinstance(hex_, bool) and hex_ >= 0 \
            and hex_ // 100 < self.rows and hex_ % 100 < self.cols

    def neighbours(self, mode: MoveMode, hex_: int) -> Mapping[int, float]:
        """Traversable neighbours of ``hex_`` for ``mode`` with their entry costs (empty if none)."""
        return self.edges[MoveMode(mode)].get(hex_, MappingProxyType({}))
