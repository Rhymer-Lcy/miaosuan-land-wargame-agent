"""Order-independent digests of engine data, for comparing repeated games step by step.

The canonical form keeps types (an int key and a string key stay different, a tuple is not a
list) but sorts every mapping's entries by the canonical form of the key, so two states with the
same content hash equally whatever order the engine built them in. Floats use Python's shortest
round-trip representation; non-finite floats and unknown types are tagged, never dropped.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def _key(item: Any) -> str:
    return json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical(value: Any) -> Any:
    kind = type(value)
    if value is None or kind in (bool, int, str):
        return value
    if kind is float:
        return value if math.isfinite(value) else {"$float": repr(value)}
    if kind is dict:
        entries = [[canonical(k), canonical(v)] for k, v in value.items()]
        entries.sort(key=lambda entry: _key(entry[0]))
        return {"$map": entries}
    if kind is list:
        return [canonical(item) for item in value]
    if kind is tuple:
        return {"$tuple": [canonical(item) for item in value]}
    if hasattr(value, "items") and callable(value.items):
        return canonical(dict(value.items()))
    for method in ("tolist", "item"):
        if hasattr(value, method):
            return {"$" + f"{kind.__module__}.{kind.__qualname__}": canonical(getattr(value, method)())}
    return {"$other": [f"{kind.__module__}.{kind.__qualname__}", repr(value)]}


def value_digest(value: Any) -> str:
    text = json.dumps(canonical(value), separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
