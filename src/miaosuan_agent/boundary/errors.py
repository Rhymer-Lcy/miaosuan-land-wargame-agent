"""Contract violations detected at the SDK boundary, with bounded diagnostics."""

from __future__ import annotations

from typing import Any, Optional

_MAX_TEXT = 60


class _Missing:
    """Sentinel for a field that is absent, as opposed to present with value ``None``."""

    def __repr__(self) -> str:
        return "<missing>"


MISSING: Any = _Missing()


def describe_value(value: Any) -> str:
    """Describe a value by type and a short preview. Containers are never expanded."""
    if value is MISSING:
        return "nothing (field missing)"
    kind = type(value).__name__
    if value is None or isinstance(value, (bool, int, float, str, bytes)):
        text = repr(value)
        if len(text) > _MAX_TEXT:
            text = text[: _MAX_TEXT - 3] + "..."
        return f"{kind} {text}"
    try:
        return f"{kind} of length {len(value)}"
    except TypeError:
        return kind


class ContractError(ValueError):
    """The value at ``path`` does not have a form the boundary accepts.

    The message names the path, the expected form and the actual type with a bounded preview;
    it never embeds a whole observation.
    """

    def __init__(self, path: str, expected: str, actual: Any, detail: Optional[str] = None) -> None:
        self.path = path or "<root>"
        self.expected = expected
        self.actual = describe_value(actual)
        self.detail = detail
        message = f"{self.path}: expected {expected}, got {self.actual}"
        if detail:
            message += f" ({detail})"
        super().__init__(message)
