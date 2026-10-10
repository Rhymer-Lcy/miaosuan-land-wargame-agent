"""Sprint 35 full-step observer: Sprint 34's (``evaluation.s34_capture.S34Timeline``) for whichever policy is under test.

A Stage A game has one policy under test (the Sprint 35 candidate or the Sprint 34 control) against ``baseline-v2``; a
Stage B game has the candidate against the inert control. The observer reconstructs every decision of the policy under
test with a fresh instance of that policy (``CoalitionPolicy`` for the candidate, ``CommanderPolicy`` for the control)
from the recorded memory, attributes differences from a shadow ``baseline-v2``, and records the largest canonical JSON
size of the policy's memory (structural stop S9). Read-only: nothing it computes reaches the agents or the engine.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from ..boundary import MoveCosts
from ..coalition.config import CoalitionConfig
from ..coalition.policy import CoalitionPolicy
from ..decision.trace import canonical_json
from ..integrated.config import Config
from .s34_capture import S34Timeline, plain

TIMELINE_SCHEMA = "miaosuan-s35-timeline/1"


class S35Timeline(S34Timeline):
    def __init__(self, policy_id: str, config: Any, costs: MoveCosts, **kwargs: Any) -> None:
        if not isinstance(config, (CoalitionConfig, Config)):
            raise TypeError("the policy under test must be a Sprint 34 or Sprint 35 configuration")
        base = config.base if isinstance(config, CoalitionConfig) else config
        super().__init__(policy_id, base, costs, **kwargs)
        if isinstance(config, CoalitionConfig):
            self.shadow = CoalitionPolicy(costs, config)
        self.checks["memory_bytes_max"] = 0

    def step(self, index: int, before: Any, after: Any, decisions: Sequence[Mapping[str, Any]]) -> None:
        super().step(index, before, after, decisions)
        for d in decisions:
            memory = d.get("memory")
            if d.get("policy") == self.candidate_policy and hasattr(memory, "to_dict"):
                size = len(canonical_json(plain(memory.to_dict())).encode("utf-8"))
                if size > self.checks["memory_bytes_max"]:
                    self.checks["memory_bytes_max"] = size

    def compact(self):
        payload = super().compact()
        payload["schema"] = TIMELINE_SCHEMA
        return payload

    def files(self) -> tuple:
        import pickle
        compact = json.dumps(self.compact(), sort_keys=True, ensure_ascii=False).encode("utf-8")
        windows = pickle.dumps({"schema": TIMELINE_SCHEMA, "samples": self.samples}, protocol=4)
        return compact, windows
