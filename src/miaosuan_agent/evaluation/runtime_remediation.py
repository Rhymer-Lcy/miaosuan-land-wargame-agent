"""Registration of the routing remediation: a behaviour-preserving runtime change to baseline-v1.

The candidate may differ from the frozen ``baseline-v1`` only by one added file that replaces the
full-map shortest-path search with a search that stops once every objective the decision reads
is settled. Everything the registration fixes before the candidate is implemented or timed lives
here: identities, the allowed source delta, the behavioural contract, the equivalence and
performance criteria, the replay corpus (pinned by file digest) and the engine diagnostic plan.
Nothing here is imported by a policy.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Mapping

from . import manifest as mf
from .identity import OCCUPY_RESERVATION_SOURCES

SCHEMA = "miaosuan-runtime-remediation-registration/1"
REMEDIATION_ID = "routing-remediation-1"
CANDIDATE_ID = "baseline-v1-routing-bounded-candidate"
PROMOTED_NAME = "baseline-v1-runtime-r1"
CANDIDATE_FILE = "experiments/routing_bounded.py"
PARENT = {
    "identity": "baseline-v1", "code_identity": "baseline-v1-candidate-occupy-reservation",
    "policy_source_sha256": "1d01e48a245273ded0b413ec6248e6aa54bba313ba8d6abbae2a20575544e2e9",
    "golden_trace_chain": "11e12bf0475c04672701bcbb4daa6579c6c3b0238ac90fb8320b2384e61acc66",
    "evaluation_manifest_sha256": "38526b9250d8bce7facdb0f5c6303b5f2040e3939bd2bcedfe1fc2fdb14f103f",
    "evaluation_results_sha256": "ea0ec674e8e51e546684fb75696673e5c81d32d6c9dd7a0d11796a91aeaeda07",
    "variance_study_manifest_sha256": "78109fca78dc8b044b63dcf475c163ca91a6f7f60fe1454a4b126d7ada10f48e",
}
ALLOWED_DELTA = (
    "the candidate's policy sources are baseline-v1's sources, byte-identical, plus the single added file "
    f"src/miaosuan_agent/{CANDIDATE_FILE}; no file of baseline-v1's source set may change",
    "the added file may define only: a router subclass whose shortest-path search stops once every target hex is "
    "settled (or the reachable frontier is exhausted) and whose memo key adds the target set; a policy subclass of "
    "baseline-v1's that uses that router and passes it, once per play-stage decision, the hexes of the objectives "
    "the unchanged tactical context lists; and the matching agent class",
    "the decision trace keeps baseline-v1's content; only its 'policy' field names the candidate",
)
CONTRACT = (
    "move candidates are computed for every controllable unit that lists movement, is not executing a move, has a "
    "documented movement mode, and does not stand on an objective not held by its side; they read the shortest-path "
    "cost and path of exactly the objectives not held by the side (context.objectives), and nothing else",
    "the search is Dijkstra from the unit's hex over the setup-supplied costs of the unit's movement mode "
    "(vehicle, vehicle in march state, infantry, air), with roadblock hexes excluded as neighbours for the two "
    "vehicle modes only; the start hex itself is never checked against roadblocks",
    "entry costs are positive and finite (the boundary rejects anything else); the frontier is a heap of "
    "(cost, hex) pairs, so equal costs pop in ascending hex order; a settled or blocked neighbour is skipped; a "
    "neighbour's cost and predecessor change only on a strictly lower cost; neighbour order is irrelevant",
    "a path is the predecessor chain from the objective back to the start, excluding the start; an objective absent "
    "from the result is unreachable and yields no candidate; if no objective is reachable the unit gets none",
    "the objective chosen is the candidate with the smallest (cost, objective hex), i.e. the cheapest, ties by the "
    "lower hex",
    "results are shared through a first-in-first-out memo of 32 entries keyed by (start hex, mode, roadblock set); "
    "no result depends on the memo",
)
EQUIVALENCE_ARGUMENT = (
    "the bounded search executes exactly the full search's sequence of heap pops and relaxations and stops at a "
    "point of that sequence, so it is a prefix of the full run",
    "once a hex is settled its cost and predecessor never change in the full run (settled neighbours are skipped), "
    "and every hex on its predecessor chain was settled before it; hence costs and paths of settled hexes are equal",
    "the search stops only when every target is settled, so every reachable objective has its final cost and path; "
    "an unreachable objective keeps the search running until the frontier is exhausted, i.e. the full run, so it is "
    "absent in both",
    "the policy reads only objectives, so its candidates, ranks, choices, actions and trace content are equal; the "
    "bounded result exposes settled hexes only, so no tentative value can be read by accident",
)
SEMANTIC_TRACE = ("the decision trace as a dictionary (to_dict) with the key 'policy' removed; every other key, "
                  "including schema, stage, step, seat, units with their candidate counts, rules, ranks, details, no-op "
                  "reasons and validations, excluded units, emitted, rejected, diagnostics and suppressed, must be equal")
EQUIVALENCE_CRITERIA = (
    "E1 baseline-v1 still verifies: policy source digest, golden decision chain, manifests, and byte-identical "
    "regeneration of its results and of the variance study's results",
    "E2 the candidate's source set is baseline-v1's byte-identical plus exactly the registered added file",
    "E3 the public routing tests pass: the characterization of the frozen router, and the candidate against the "
    "frozen full search on hand-made and on generated graphs (fixed seeds)",
    "E4 every non-equivalent mutant of the candidate's search or memo key is killed by the tests; equivalent mutants "
    "are identified, not counted",
    "E5 over every registered replay input, for both agents given the same observation and memory: the emitted "
    "action lists are equal (content and order), the semantic traces are equal, contract errors are equal, and the "
    "observation is left unmodified; unexplained differences: 0",
    "E6 move paths are equal wherever either implementation produces one (reported from E5)",
    "E7 the semantic trace chain of the candidate over the golden decision sequence equals baseline-v1's, and "
    "baseline-v1's own golden chain is unchanged",
    "E8 the registered performance criterion holds",
    "E9 the engine diagnostic: every decision of every diagnostic game compared live with a shadow baseline-v1 agent "
    "on the same observation shows equal actions and semantic traces; no project-gate rejection or contract error "
    "appears that the shadow does not share; the engine's authentication state is unchanged",
    "E10 no tactical rule changed (E2 and E5)",
    "E11 no new legality or contract issue appears (E5 and E9)",
)
PERFORMANCE = {
    "worst_input": "2130511121-seat11-decision1 (the first play decision of the largest scenario; also as captured in "
                   "latdiag-1)",
    "metric": "median wall time of agent.step with a fresh agent (empty memo), repetitions interleaved between "
              "baseline-v1 and the candidate in the same benchmark invocation",
    "criterion": "candidate median <= 0.50 x baseline-v1 median on the worst input (and on its captured twin)",
    "no_regression": "on every other registered state the candidate median <= baseline-v1 median x 1.10 + 0.20 ms",
    "engine": "in the 2130511121 diagnostic games the candidate's first play decision takes <= 0.50 x the shadow "
              "baseline-v1's time for the same observation in the same process",
    "basis": "the latency diagnostic measured about 500 ms, 99% in Dijkstra, and estimated that 15.8% of the settled "
             "nodes are needed; the threshold leaves room for the bounded search's own overhead and for relaxations "
             "that a node count does not show; no platform deadline is assumed",
    "reported": "cold first call, median, p95, p99, max, thread CPU time, wall time, shortest-path requests, searches, "
                "settled nodes, examined edges, retained-work fraction, speedup",
    "repetitions": {"fresh_agent": 200, "memo_warm": 200, "cold_process": 10},
}
ENGINE_PLAN = {
    "games": [
        {"id": "rr-1", "scenario_id": "2130511121", "condition": "C1", "purpose": "both seats run the candidate"},
        {"id": "rr-2", "scenario_id": "2130511121", "condition": "C3", "purpose": "the configuration of the old tail"},
        {"id": "rr-3", "scenario_id": "2010131194", "condition": "C3", "purpose": "small control scenario"},
    ],
    "procedure": "diagnostic sessions of the persistent engine (ledger purpose 'diagnostic'), same isolation as the "
                 "evaluations; every policy seat runs the candidate, and a shadow baseline-v1 agent of the same seat "
                 "decides on the same observation after each decision, outside the candidate's measured window; "
                 "actions and semantic traces are compared for every decision and both decision times recorded",
    "not": "no outcome or score is compared or reported as evidence; no GC setting is changed",
}
PROMOTION = ("promote the candidate to the runtime identity baseline-v1-runtime-r1 only if E1-E11 all hold; it is then "
             "behaviourally equivalent to the tactical baseline-v1 and is not a new tactical baseline",
             "otherwise it is retained as a failed or partial candidate and baseline-v1's runtime stays in use")
FAILURE = ("any unexplained difference in E5 or E9", "any surviving non-equivalent mutant (E4)",
           "the performance criterion missed (E8)", "any change to a baseline-v1 source file (E2)")
OUT_OF_SCOPE = ("garbage collection: the late-game pauses of the shared engine process are a separate runtime issue; "
                "no collection setting, call or threshold is changed",
                "tactics: no rule, order, priority, filter or legality check changes",
                "the shooting-conflict experiment")


def candidate_sources() -> tuple:
    return OCCUPY_RESERVATION_SOURCES + (CANDIDATE_FILE,)


def build(corpus: Mapping[str, Any]) -> Dict[str, Any]:
    registration = {
        "schema": SCHEMA, "remediation_id": REMEDIATION_ID, "parent": dict(PARENT),
        "candidate": {"identity": CANDIDATE_ID, "promoted_name": PROMOTED_NAME,
                      "sources": list(candidate_sources()), "added_file": f"src/miaosuan_agent/{CANDIDATE_FILE}"},
        "allowed_delta": list(ALLOWED_DELTA), "contract": list(CONTRACT),
        "equivalence_argument": list(EQUIVALENCE_ARGUMENT), "semantic_trace": SEMANTIC_TRACE,
        "equivalence_criteria": list(EQUIVALENCE_CRITERIA), "performance": copy.deepcopy(PERFORMANCE),
        "corpus": copy.deepcopy(dict(corpus)), "engine_diagnostic": copy.deepcopy(ENGINE_PLAN),
        "promotion": list(PROMOTION), "failure": list(FAILURE), "out_of_scope": list(OUT_OF_SCOPE),
    }
    registration["corpus_sha256"] = mf.digest(registration["corpus"])
    return registration
