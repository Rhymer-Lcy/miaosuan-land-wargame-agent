"""Explicit type checks used by the boundary. None of them coerces a value."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .errors import ContractError


def require_mapping(value: Any, path: str) -> Mapping[Any, Any]:
    if isinstance(value, Mapping):
        return value
    raise ContractError(path, "a mapping", value)


def require_sequence(value: Any, path: str) -> Sequence[Any]:
    """Accept a list or tuple. Strings and bytes are sequences in Python but never valid here."""
    if isinstance(value, (list, tuple)):
        return value
    raise ContractError(path, "a list or tuple", value)


def require_int(value: Any, path: str) -> int:
    """Accept ``int`` but not ``bool``, which Python treats as an ``int`` subclass."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise ContractError(path, "an int", value)


def require_str(value: Any, path: str) -> str:
    if isinstance(value, str):
        return value
    raise ContractError(path, "a str", value)


def require_bool(value: Any, path: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ContractError(path, "a bool", value)


def require_number(value: Any, path: str) -> float:
    """Accept an int or float (not bool) and return it as float."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    raise ContractError(path, "an int or float", value)
