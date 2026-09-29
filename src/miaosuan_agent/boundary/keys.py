"""Normalization of integer-valued mapping keys, governed by where the data came from.

The engine returns Python mappings keyed by ``int`` (operator ids, action types, seats, state
slots). JSON cannot represent integer object keys, so the same data after a JSON round trip is
keyed by decimal strings. The caller states the origin explicitly; keys are never guessed from
their form, so a change in the engine's key type is reported instead of silently absorbed.
"""

from __future__ import annotations

import enum
import re
from typing import Any, Dict

from .checks import require_mapping
from .errors import ContractError

# Decimal integers exactly as json.dumps writes int keys: no sign on zero, no leading zeros,
# no whitespace, no plus sign.
_CANONICAL_DECIMAL = re.compile(r"0|-?[1-9][0-9]*")


class Origin(enum.Enum):
    """Where a raw value came from."""

    ENGINE = "engine"  # returned in-process by the SDK engine: integer keys are ints
    JSON = "json"  # deserialized from JSON: integer keys arrive as canonical decimal strings


def is_canonical_decimal(text: str) -> bool:
    return bool(_CANONICAL_DECIMAL.fullmatch(text))


def normalize_int_key(key: Any, origin: Origin, path: str) -> int:
    """Return ``key`` as an int if it has the only form ``origin`` can produce."""
    if origin is Origin.ENGINE:
        if isinstance(key, int) and not isinstance(key, bool):
            return key
        raise ContractError(path, "an int key (in-process engine data)", key)
    if origin is Origin.JSON:
        if isinstance(key, str) and is_canonical_decimal(key):
            return int(key)
        raise ContractError(path, "a canonical decimal string key (JSON data)", key)
    raise TypeError(f"unknown origin {origin!r}")


def normalize_int_keyed(mapping: Any, origin: Origin, path: str) -> Dict[int, Any]:
    """Return a new dict with every key normalized; mixed or invalid key forms raise."""
    source = require_mapping(mapping, path)
    result: Dict[int, Any] = {}
    for key, value in source.items():
        number = normalize_int_key(key, origin, f"{path}[{key!r}]")
        if number in result:
            raise ContractError(path, "unique keys after normalization", key, detail=f"duplicates key {number}")
        result[number] = value
    return result
