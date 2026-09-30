"""External, removable instrumentation for attributing decision latency.

No policy source file is edited. :class:`Probe` replaces a fixed list of module and class
attributes with wrappers that call the original object with the same arguments and return its
result unchanged, and restores every attribute on exit, so decisions cannot differ (the tests and
the benchmark compare decision-trace digests with and without the probe). Time is charged to the
innermost active label only (a stack), so routing called inside candidate generation is not
counted twice; ``other`` is the decision's outer time minus all labelled time.

Per decision the probe also records thread and process CPU time, every Python garbage collection
that overlaps the decision (``gc.callbacks``: generation, duration, objects collected), resource
usage deltas where the platform has them (page faults, voluntary and involuntary context
switches), the resident set size, and routing workload: shortest-path requests, memo hits,
Dijkstra runs, nodes settled, and whether a unit's routing could have mattered (move chosen).
"""

from __future__ import annotations

import gc
import importlib
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

try:  # POSIX only; absent on Windows
    import resource
except ImportError:  # pragma: no cover - platform dependent
    resource = None  # type: ignore[assignment]

#: (label, module, attribute path). Names imported into another module are patched there too.
TARGETS: Tuple[Tuple[str, str, str], ...] = (
    ("boundary", "miaosuan_agent.boundary.observation", "Observation.from_raw"),
    ("context", "miaosuan_agent.decision.policy", "build_context"),
    ("engage", "miaosuan_agent.decision.policy", "engage_candidates"),
    ("engage", "miaosuan_agent.experiments.occupy_reservation", "engage_candidates"),
    ("occupy", "miaosuan_agent.decision.policy", "occupy_candidates"),
    ("occupy", "miaosuan_agent.experiments.occupy_reservation", "occupy_candidates"),
    ("move_candidates", "miaosuan_agent.decision.policy", "move_candidates"),
    ("move_candidates", "miaosuan_agent.experiments.occupy_reservation", "move_candidates"),
    ("routing_lookup", "miaosuan_agent.decision.routing", "Router.shortest_paths"),
    ("dijkstra", "miaosuan_agent.decision.routing", "Router._dijkstra"),
    ("ranking", "miaosuan_agent.decision.policy", "best"),
    ("ranking", "miaosuan_agent.experiments.occupy_reservation", "best"),
    ("gate", "miaosuan_agent.decision.gate", "check"),
    ("trace", "miaosuan_agent.decision.policy", "BaselinePolicy._trace"),
    ("trace", "miaosuan_agent.experiments.occupy_reservation", "_with_suppressed"),
)
LABELS = ("boundary", "context", "engage", "occupy", "move_candidates", "routing_lookup", "dijkstra", "ranking",
          "gate", "trace")


def _rusage() -> Optional[Dict[str, int]]:
    if resource is None:
        return None
    who = getattr(resource, "RUSAGE_THREAD", resource.RUSAGE_SELF)
    usage = resource.getrusage(who)
    return {"minor_faults": usage.ru_minflt, "major_faults": usage.ru_majflt,
            "voluntary_switches": usage.ru_nvcsw, "involuntary_switches": usage.ru_nivcsw}


def _rss_kib() -> Optional[int]:
    try:
        with open("/proc/self/statm", encoding="ascii") as handle:
            pages = int(handle.read().split()[1])
        return pages * 4
    except (OSError, ValueError, IndexError):
        return None


class Probe:
    """Install with ``with probe.installed():``; measure one decision with ``with probe.decision():``."""

    def __init__(self, clock: Callable[[], float] = time.perf_counter, keep: bool = True) -> None:
        """``keep=False`` does not retain decision records (the caller stores each one), so the probe itself
        does not grow the heap that the garbage collector must traverse."""
        self.clock = clock
        self.keep = keep
        self._stack: List[Tuple[str, float]] = []
        self._current: Optional[Dict[str, Any]] = None
        self._gc_start: Optional[Tuple[float, int]] = None
        self._decision_events: List[Tuple[float, float, int]] = []
        #: Every collection of the oldest generation, inside a decision or not (few; the rest are counted).
        self.full_collections: List[Dict[str, Any]] = []
        self.collections_outside_decisions: Dict[str, int] = {}
        self.decisions: List[Dict[str, Any]] = []

    # -- labelled time -------------------------------------------------------------------------
    def _enter(self, label: str) -> None:
        now = self.clock()
        if self._stack and self._current is not None:
            outer, since = self._stack[-1]
            self._current["components"][outer] += now - since
        self._stack.append((label, now))

    def _exit(self) -> None:
        now = self.clock()
        label, since = self._stack.pop()
        if self._current is not None:
            self._current["components"][label] += now - since
        if self._stack:
            self._stack[-1] = (self._stack[-1][0], now)

    def _wrap(self, label: str, original: Callable[..., Any]) -> Callable[..., Any]:
        probe = self

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if probe._current is None:
                return original(*args, **kwargs)
            routing = probe._current["routing"]
            before = (routing["requests"], routing["dijkstra_runs"])
            probe._enter(label)
            try:
                result = original(*args, **kwargs)
            finally:
                probe._exit()
            if label == "move_candidates":
                routing["per_unit"].append({"obj_id": getattr(args[0], "obj_id", None),
                                            "requests": routing["requests"] - before[0],
                                            "dijkstra_runs": routing["dijkstra_runs"] - before[1]})
            if label == "dijkstra":
                probe._current["routing"]["dijkstra_runs"] += 1
                probe._current["routing"]["nodes_settled"] += len(result.cost)
            elif label == "routing_lookup":
                probe._current["routing"]["requests"] += 1
                key = (args[1], int(args[2]), args[3] if len(args) > 3 else kwargs.get("blocked", frozenset()))
                probe._current["routing"]["keys"].append(hash(key))
            elif label == "move_candidates":
                probe._current["routing"]["move_candidate_calls"] += 1
                probe._current["routing"]["move_candidates_nonempty"] += bool(result[0])
            return result

        wrapper.__wrapped__ = original  # type: ignore[attr-defined]
        return wrapper

    @contextmanager
    def installed(self) -> Iterator["Probe"]:
        saved: List[Tuple[Any, str, Any]] = []
        try:
            for label, module_name, path in TARGETS:
                owner: Any = importlib.import_module(module_name)
                parts = path.split(".")
                for part in parts[:-1]:
                    owner = getattr(owner, part)
                name = parts[-1]
                raw = owner.__dict__[name] if isinstance(owner, type) else getattr(owner, name)
                if isinstance(raw, classmethod):
                    replacement: Any = classmethod(self._wrap(label, raw.__func__))
                else:
                    replacement = self._wrap(label, raw)
                saved.append((owner, name, raw))
                setattr(owner, name, replacement)
            gc.callbacks.append(self._gc_callback)
            yield self
        finally:
            if self._gc_callback in gc.callbacks:
                gc.callbacks.remove(self._gc_callback)
            for owner, name, raw in reversed(saved):
                setattr(owner, name, raw)

    # -- garbage collection -------------------------------------------------------------------
    def _gc_callback(self, phase: str, info: Dict[str, Any]) -> None:
        now = self.clock()
        if phase == "start":
            self._gc_start = (now, info.get("generation", -1))
            return
        if self._gc_start is None:
            return
        start, generation = self._gc_start
        self._gc_start = None
        inside = self._current is not None
        if inside:
            self._decision_events.append((start, now, generation))
        else:
            key = str(generation)
            self.collections_outside_decisions[key] = self.collections_outside_decisions.get(key, 0) + 1
        if generation == 2:
            self.full_collections.append({"start": start, "seconds": now - start, "collected": info.get("collected"),
                                          "in_decision": dict(self._current["meta"]) if inside else None})

    # -- one decision ---------------------------------------------------------------------------
    @contextmanager
    def decision(self, meta: Optional[Dict[str, Any]] = None) -> Iterator[Dict[str, Any]]:
        record: Dict[str, Any] = {"meta": dict(meta or {}),
                                  "components": {label: 0.0 for label in LABELS + ("other",)},
                                  "routing": {"requests": 0, "dijkstra_runs": 0, "nodes_settled": 0,
                                              "move_candidate_calls": 0, "move_candidates_nonempty": 0, "keys": [],
                                              "per_unit": []}}
        usage_before, rss_before = _rusage(), _rss_kib()
        self._decision_events = []
        counts_before = gc.get_count()
        thread_before, process_before = time.thread_time(), time.process_time()
        start = self.clock()
        self._current = record
        self._stack = [("other", start)]
        try:
            yield record
        finally:
            end = self.clock()
            label, since = self._stack.pop() if self._stack else ("other", end)
            record["components"][label] += end - since
            self._stack, self._current = [], None
            events, self._decision_events = self._decision_events, []
            record["wall"] = end - start
            record["thread_cpu"] = time.thread_time() - thread_before
            record["process_cpu"] = time.process_time() - process_before
            usage_after = _rusage()
            record["rusage"] = None if usage_before is None or usage_after is None else {
                k: usage_after[k] - usage_before[k] for k in usage_before}
            rss_after = _rss_kib()
            record["rss_kib"] = rss_after
            record["rss_delta_kib"] = None if rss_before is None or rss_after is None else rss_after - rss_before
            record["gc"] = {"collections": len(events), "seconds": sum(stop - begin for begin, stop, _ in events),
                            "by_generation": _by_generation(events), "counts_before": list(counts_before),
                            "full_seconds": sum(stop - begin for begin, stop, g in events if g == 2)}
            keys = record["routing"].pop("keys")
            record["routing"]["distinct_keys"] = len(set(keys))
            if self.keep:
                self.decisions.append(record)


def _by_generation(events: List[Tuple[float, float, int]]) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for _, _, generation in events:
        result[str(generation)] = result.get(str(generation), 0) + 1
    return result


def accounting(record: Dict[str, Any]) -> Dict[str, float]:
    """Labelled time, unattributed time and the ratio of labelled to outer time for one decision."""
    labelled = sum(v for k, v in record["components"].items() if k != "other")
    other = record["components"].get("other", 0.0)
    wall = record["wall"]
    return {"wall": wall, "labelled": labelled, "other": other,
            "sum_error": abs(labelled + other - wall), "labelled_share": labelled / wall if wall else 0.0}
