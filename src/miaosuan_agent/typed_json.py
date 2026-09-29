"""Lossless JSON encoding of plain Python data, for private fixtures captured from the engine.

Plain JSON is not faithful to engine data: it turns integer mapping keys into strings and tuples
into lists. This encoding keeps both. Every mapping becomes ``{"$map": [[key, value], ...]}``
and every tuple ``{"$tuple": [...]}``; lists and JSON scalars stay as they are. Because every
mapping is encoded as a tag object, decoding is unambiguous.

Values of any other type, or of a subclass of a supported type, are recorded as
``{"$other": {"type": ..., "repr": ...}}`` and their paths are reported, so a capture can state
precisely where it was not faithful instead of silently converting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Tuple

MAP = "$map"
TUPLE = "$tuple"
OTHER = "$other"
_SCALARS = (bool, int, float, str, type(None))


@dataclass(frozen=True)
class Opaque:
    """Decoded placeholder for a value that could not be encoded faithfully."""

    type: str
    repr: str


def _type_name(value: Any) -> str:
    kind = type(value)
    return f"{kind.__module__}.{kind.__qualname__}"


def encode(value: Any) -> Tuple[Any, List[str]]:
    """Return the encoded value and the paths of every value that was not encoded faithfully."""
    inexact: List[str] = []

    def walk(item: Any, path: str) -> Any:
        kind = type(item)
        if kind in _SCALARS:
            return item
        if kind is dict:
            return {MAP: [[walk(k, f"{path}.<key {k!r}>"), walk(v, f"{path}[{k!r}]")] for k, v in item.items()]}
        if kind is list:
            return [walk(v, f"{path}[{i}]") for i, v in enumerate(item)]
        if kind is tuple:
            return {TUPLE: [walk(v, f"{path}[{i}]") for i, v in enumerate(item)]}
        inexact.append(f"{path}: {_type_name(item)}")
        return {OTHER: {"type": _type_name(item), "repr": repr(item)[:200]}}

    return walk(value, "$"), inexact


def decode(data: Any) -> Any:
    """Invert :func:`encode`. Values recorded as ``$other`` decode to :class:`Opaque`."""
    kind = type(data)
    if kind in _SCALARS:
        return data
    if kind is list:
        return [decode(item) for item in data]
    if kind is dict:
        if len(data) != 1:
            raise ValueError(f"not a typed-JSON tag object: keys {sorted(data)}")
        (tag, payload), = data.items()
        if tag == MAP:
            return {decode(k): decode(v) for k, v in payload}
        if tag == TUPLE:
            return tuple(decode(item) for item in payload)
        if tag == OTHER:
            return Opaque(type=payload["type"], repr=payload["repr"])
        raise ValueError(f"unknown typed-JSON tag {tag!r}")
    raise ValueError(f"unexpected JSON value of type {kind.__name__}")
