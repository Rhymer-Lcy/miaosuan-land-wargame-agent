"""Structural fingerprints of observations: shape and types, without scenario content.

A fingerprint keeps what an interface contract is made of and drops what a scenario is made of:

* mappings keyed by field names are *records*; their field names are kept;
* mappings keyed by ints or decimal strings are *keyed* (ids, seats, action types); only the key
  kind and the merged shape of their values are kept, never the keys themselves;
* lists keep an ``empty`` flag and the merged shape of their items, not their length;
* scalars keep only their type, except at the few paths in ``VALUE_PATHS`` whose values are
  interface facts (the stage and the end-of-deployment flags).

``Detail.PUBLIC`` additionally reduces unit records to a field count, so a public fingerprint does
not reproduce the SDK's unit data model. ``Detail.PRIVATE`` keeps every field name and is meant
for comparisons stored under the git-ignored ``local/`` tree.
"""

from __future__ import annotations

import enum
import hashlib
import json
from typing import Any, Dict, List, Mapping

from .boundary.keys import is_canonical_decimal


class Detail(enum.Enum):
    PUBLIC = "public"
    PRIVATE = "private"


VALUE_PATHS = frozenset({"time.stage", "role_and_grouping_info.*.end_deployment"})
REDACTED_RECORD_PATHS = frozenset({"operators.[]", "passengers.[]"})


def _join(path: str, part: str) -> str:
    return f"{path}.{part}" if path else part


def _key_kind(key: Any) -> str:
    if isinstance(key, bool):
        return "bool"
    if isinstance(key, int):
        return "int"
    if isinstance(key, str):
        return "numeric-str" if is_canonical_decimal(key) else "str"
    return type(key).__name__


def _scalar_kind(value: Any) -> str:
    if value is None:
        return "none"
    for kind, name in ((bool, "bool"), (int, "int"), (float, "float"), (str, "str")):
        if isinstance(value, kind):
            return name if type(value) is kind else f"{name}-subclass:{type(value).__name__}"
    return f"other:{type(value).__name__}"


def _canonical(node: Any) -> str:
    return json.dumps(node, sort_keys=True, separators=(",", ":"))


def _flags(node: Mapping[str, Any]) -> set:
    value = node["empty"]
    return set(value) if isinstance(value, list) else {value}


def _merge(nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge the fingerprints of sibling values into one description of their common shape."""
    unique = {_canonical(node): node for node in nodes}
    if len(unique) == 1:
        return next(iter(unique.values()))
    group = list(unique.values())
    kinds = {node["kind"] for node in group}
    if len(kinds) == 1:
        kind = next(iter(kinds))
        if kind == "record" and all("fields" in node for node in group):
            names = sorted({name for node in group for name in node["fields"]})
            optional = sorted(name for name in names
                              if not all(name in node["fields"] for node in group)
                              or any(name in node.get("optional", ()) for node in group))
            merged: Dict[str, Any] = {
                "kind": "record",
                "fields": {name: _merge([node["fields"][name] for node in group if name in node["fields"]])
                           for name in names},
            }
            if optional:
                merged["optional"] = optional
            return merged
        if kind in ("list", "tuple", "keyed"):
            member = "values" if kind == "keyed" else "items"
            empties = sorted(set().union(*(_flags(node) for node in group)))
            merged = {"kind": kind, "empty": empties[0] if len(empties) == 1 else empties}
            if kind == "keyed":
                merged["key_kinds"] = sorted({k for node in group for k in node["key_kinds"]})
            members = [node[member] for node in group if member in node]
            if members:
                merged[member] = _merge(members)
            return merged
        if all(set(node) <= {"kind", "value", "values"} for node in group):
            values: set = set()
            for node in group:
                values.update(node["values"] if "values" in node else ([node["value"]] if "value" in node else []))
            merged = {"kind": kind}
            if values:
                merged["values"] = sorted(values, key=repr)
            return merged
    return {"kind": "union", "options": [unique[key] for key in sorted(unique)]}


def fingerprint(value: Any, detail: Detail = Detail.PUBLIC, path: str = "") -> Dict[str, Any]:
    """Return the structural fingerprint of ``value`` (see the module docstring)."""
    if isinstance(value, Mapping):
        keys = list(value)
        if keys and all(isinstance(k, str) and not is_canonical_decimal(k) for k in keys):
            if detail is Detail.PUBLIC and path in REDACTED_RECORD_PATHS:
                return {"kind": "record", "field_count": len(keys)}
            return {"kind": "record",
                    "fields": {k: fingerprint(value[k], detail, _join(path, k)) for k in sorted(keys)}}
        node: Dict[str, Any] = {"kind": "keyed", "key_kinds": sorted({_key_kind(k) for k in keys}),
                                "empty": not keys}
        if keys:
            node["values"] = _merge([fingerprint(value[k], detail, _join(path, "*")) for k in keys])
        return node
    if isinstance(value, (list, tuple)):
        node = {"kind": "tuple" if isinstance(value, tuple) else "list", "empty": not value}
        if value:
            node["items"] = _merge([fingerprint(item, detail, _join(path, "[]")) for item in value])
        return node
    node = {"kind": _scalar_kind(value)}
    if path in VALUE_PATHS:
        node["value"] = value
    return node


def digest(node: Mapping[str, Any]) -> str:
    """SHA-256 of the canonical JSON of a fingerprint."""
    return hashlib.sha256(_canonical(node).encode("utf-8")).hexdigest()
