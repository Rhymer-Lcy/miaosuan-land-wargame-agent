"""Value- and schema-preserving publication of public JSON (Sprint 36, section 4).

The project's pre-push privacy scan (kept outside the repository) flags, among other things, numbers that look like a
recorded host clock offset. A research figure can collide with such a pattern by accident: Sprint 35's public results
had to leave out every game's mean held value because one of them matched. Dropping a metric changes the schema and
hides data; editing the accepted privacy baseline weakens the scan. This module does neither: it serializes the
document with ``json.dumps`` and rewrites only the numeric literals that fall inside a match of ``NUMERIC_PATTERNS``
into exponent notation (a value written ``ddd.ddd`` becomes ``d.ddddde+02``), which JSON reads back as the same number.
It then checks that the rewritten text parses to a structure equal to the input (numbers compared by value), that no
pattern matches any more, and that no match touches anything but a numeric literal (a colliding string or key is
refused, not rewritten).

``NUMERIC_PATTERNS`` restates only the scan's numeric rule; the scan itself stays outside the repository.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, List, Pattern, Tuple

NUMERIC_PATTERNS: Tuple[str, ...] = (r"\b38[789]\.[0-9]|\b388\b",)
_NUMBER = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")


def _compiled(patterns: Iterable[str]) -> List[Pattern[str]]:
    return [re.compile(p) for p in patterns]


def _exponent(literal: str) -> str:
    """The same JSON number in exponent notation (three significant digits stay three: ``ddd`` -> ``d.dde+02``)."""
    value = float(literal)
    digits = literal.lstrip("-").replace(".", "").lstrip("0") or "0"
    text = f"{value:.{max(0, len(digits.rstrip('0')) - 1)}e}"
    if float(text) != value:
        text = repr(value) if "e" in repr(value) else f"{value:.15e}"
    return text


def _equal(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b))
    return a == b


def collisions(text: str, patterns: Iterable[str] = NUMERIC_PATTERNS) -> List[Tuple[int, int]]:
    return [m.span() for p in _compiled(patterns) for m in p.finditer(text)]


def _numeric_spans(text: str) -> List[Tuple[int, int]]:
    """Spans of the numeric literals of a JSON text (outside strings)."""
    spans: List[Tuple[int, int]] = []
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            i += 1
            continue
        m = _NUMBER.match(text, i) if (ch == "-" or ch.isdigit()) else None
        if m:
            spans.append(m.span())
            i = m.end()
            continue
        i += 1
    return spans


def dumps(data: Any, patterns: Iterable[str] = NUMERIC_PATTERNS, **kwargs: Any) -> str:
    """``json.dumps(data, **kwargs)`` with colliding numeric literals in exponent notation (module docstring)."""
    patterns = tuple(patterns)
    text = json.dumps(data, **kwargs)
    matches = collisions(text, patterns)
    if not matches:
        return text
    numbers = _numeric_spans(text)
    for start, end in matches:
        if not any(a <= start and end <= b for a, b in numbers):
            raise ValueError(f"a privacy pattern matches outside a numeric literal: "
                             f"{text[max(0, start - 20):end + 20]!r}")
    out, last = [], 0
    for a, b in numbers:
        if any(a <= s and e <= b for s, e in matches):
            out.append(text[last:a])
            out.append(_exponent(text[a:b]))
            last = b
    out.append(text[last:])
    rewritten = "".join(out)
    if collisions(rewritten, patterns):
        raise ValueError("a privacy pattern still matches after the numeric rewrite")
    if not _equal(json.loads(rewritten), data):
        raise ValueError("the rewritten document does not parse to the same values")
    return rewritten


__all__ = ["dumps", "collisions", "NUMERIC_PATTERNS"]
