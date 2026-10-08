"""Sprint 24 tactical frontier re-selection (``docs/SPRINT24_TACTICAL_FRONTIER_RESELECTION.md``).

    python scripts/s24_select.py freeze [--check]   pin every public source the study may cite (inputs.json)
    python scripts/s24_select.py run [--check]      verify the pins and every cited evidence value, apply the rule

``run`` reads ``rubric.json`` (registered first), ``experiments.json`` (one next experiment per candidate, with its
evidence items, written before any score) and ``scores.json`` (judgement scores with reasons; the sources of G and
P); it refuses unless every pinned file matches, every keyed evidence value equals its source and every quoted one
occurs verbatim (whitespace normalised) in its document; then it computes G and P, applies the leverage cap, the
interaction cap on I and the cost economy C, and writes ``selection.json`` with the frozen rule
(``evaluation/s24_selection.py``). Every input is a committed public file, so both commands run anywhere.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import s24_selection as sel  # noqa: E402
from miaosuan_agent.evaluation.s12_screen import normalized_sha256, privacy_problems  # noqa: E402

STUDY_ID = "s24-tactical-frontier-reselection"
DIRECTORY = REPO_ROOT / "evaluation" / STUDY_ID
RULES = REPO_ROOT / "src" / "miaosuan_agent" / "evaluation" / "s24_selection.py"
SCHEMA_INPUTS = "miaosuan-s24-inputs/1"
SCHEMA_SELECTION = "miaosuan-s24-selection/1"

# Every public source the study may cite, by short name. Historical documents only: the living frontier and the
# README change after this sprint and are never pinned.
SOURCES = {
    "s1_census": "evaluation/tactical-frontier-1/census.json",
    "s18_rubric": "evaluation/s18-frontier-reset/rubric.json",
    "s18_census": "evaluation/s18-frontier-reset/census.json",
    "s18_admission": "evaluation/s18-frontier-reset/admission.json",
    "s18_experiments": "evaluation/s18-frontier-reset/experiments.json",
    "s18_scores": "evaluation/s18-frontier-reset/scores.json",
    "s18_selection": "evaluation/s18-frontier-reset/selection.json",
    "s19_disposition": "evaluation/s19-t6g-shadow/disposition.json",
    "s19_shadow": "evaluation/s19-t6g-shadow/shadow.json",
    "s20_disposition": "evaluation/s20-t11-replay/disposition.json",
    "s20_replay": "evaluation/s20-t11-replay/replay.json",
    "s21_disposition": "evaluation/s21-direct-fire-semantics/disposition.json",
    "s21_semantics": "evaluation/s21-direct-fire-semantics/semantics.json",
    "s22_disposition": "evaluation/s22-t2-transport-probe/disposition.json",
    "s22_mechanism": "evaluation/s22-t2-transport-probe/mechanism.json",
    "s22_witness": "evaluation/s22-t2-transport-probe/witness.json",
    "s23_disposition": "evaluation/s23-t2-policy-design/disposition.json",
    "s23_episodes": "evaluation/s23-t2-policy-design/episodes.json",
    "s23_prevalence": "evaluation/s23-t2-policy-design/prevalence.json",
    "doc_s18": "docs/SPRINT18_FRONTIER_RESET.md",
    "doc_s19": "docs/SPRINT19_T6G_SHADOW.md",
    "doc_s20": "docs/SPRINT20_T11_REPLAY.md",
    "doc_s21": "docs/SPRINT21_DIRECT_FIRE_SEMANTICS.md",
    "doc_s22": "docs/SPRINT22_T2_TRANSPORT_PROBE.md",
    "doc_s23": "docs/SPRINT23_T2_POLICY_DESIGN.md",
    "doc_ps1": "docs/PS1_DESIGN.md",
    "doc_t7_probe": "docs/T7_MECHANISM_PROBE.md",
    "doc_t1r": "docs/T1R_DIAGNOSIS.md",
}
EXPERIMENT_FIELDS = ("id", "family", "new_family", "hypothesis", "trigger", "action_change", "mechanism",
                     "opportunity", "evidence", "offline_analysis", "engine_step", "next_sessions", "follow_sessions",
                     "engineering", "interaction", "next_offline", "conflict_measured", "risk", "stop",
                     "negative_teaches", "related_closed", "repairs", "depends_on_unidentified", "uses_stopped_data")
EVIDENCE_FIELDS = ("claim", "value", "count_unit", "population", "level", "scenario_sides", "source")
# candidate identity strings of registered policies; none may appear in a Sprint 24 public file
IDENTITIES = ("t2-transport-x1", "t2-transport-p1", "t4-artillery-v1", "t4-artillery-v2", "t4-artillery-v3",
              "t7-idle-concealment", "t9-batch-capacity-v3", "t9-capacity-allocation-v1", "t9-capacity-staging-v2",
              "t9-delayed-post-stage-any-v6", "t9-delayed-post-stage-any-v5", "s16-delayed-shadow-v6",
              "tactic-deployment-split-1")


def load(name: str) -> Any:
    return json.loads((DIRECTORY / name).read_text(encoding="utf-8"))


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def write_or_check(path: Path, text: str, check: bool) -> int:
    if check:
        same = path.exists() and path.read_text(encoding="utf-8") == text
        print(f"{path.name} {'identical' if same else 'MISMATCH'}")
        return 0 if same else 1
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(REPO_ROOT).as_posix()}")
    return 0


def freeze_record() -> Dict[str, Any]:
    pins = {name: {"file": rel, "sha256": normalized_sha256(REPO_ROOT / rel)} for name, rel in sorted(SOURCES.items())}
    return {"schema": SCHEMA_INPUTS, "study_id": STUDY_ID, "sources": pins,
            "rubric_sha256": normalized_sha256(DIRECTORY / "rubric.json"),
            "rules_sha256": normalized_sha256(RULES),
            "note": "every public source the study may cite, pinned before any candidate or score was written; "
                    "run refuses on any difference"}


def pin_problems(record: Mapping[str, Any]) -> List[str]:
    fresh = freeze_record()
    problems = [f"{name}: digest differs" for name, pin in record["sources"].items()
                if fresh["sources"].get(name) != pin]
    problems += [f"{name}: not pinned" for name in fresh["sources"] if name not in record["sources"]]
    for key in ("rubric_sha256", "rules_sha256"):
        if record.get(key) != fresh[key]:
            problems.append(f"{key} differs")
    return problems


def lookup(data: Any, key: Sequence[Any]) -> Any:
    for part in key:
        data = data[part]
    return data


def normalised(text: str) -> str:
    return " ".join(text.split())


def number_in(value: Any, text: str) -> bool:
    """``value`` (an int, or a string such as ``25/30``) occurs in ``text`` as a whole number."""
    forms = {str(value)}
    if isinstance(value, int) and not isinstance(value, bool):
        forms.add(f"{value:,}")
    return any(re.search(r"(?<![\w/])(?<!\d[.,])" + re.escape(form) + r"(?![\w/]|[.,]\d)", text) for form in forms)


def evidence_problems(evidence: Mapping[str, Mapping[str, Any]], rubric: Mapping[str, Any],
                      cache: Dict[str, Any]) -> List[str]:
    """Every evidence item is complete, labelled with a registered level and count unit, and its value is read back
    from the pinned source: a keyed JSON value must be equal, a quoted document passage must occur verbatim (whitespace
    normalised) and contain the value as a whole number."""
    problems: List[str] = []
    for ident, item in sorted(evidence.items()):
        missing = [f for f in EVIDENCE_FIELDS if f not in item]
        if missing:
            problems.append(f"{ident}: missing {missing}")
            continue
        if item["level"] not in rubric["evidence_levels"]:
            problems.append(f"{ident}: unknown level {item['level']!r}")
        if item["count_unit"] not in rubric["count_units"]:
            problems.append(f"{ident}: unknown count unit {item['count_unit']!r}")
        sides = item["scenario_sides"]
        if sides is not None and (not isinstance(sides, int) or isinstance(sides, bool) or sides < 0):
            problems.append(f"{ident}: scenario_sides must be a count or null")
        source = item["source"]
        name = source.get("file") or source.get("doc")
        if name not in SOURCES:
            problems.append(f"{ident}: source {name!r} is not pinned")
            continue
        if "file" in source:
            if name not in cache:
                cache[name] = json.loads((REPO_ROOT / SOURCES[name]).read_text(encoding="utf-8"))
            try:
                found = lookup(cache[name], source["key"])
            except (KeyError, IndexError, TypeError):
                problems.append(f"{ident}: key {source['key']} absent from {name}")
                continue
            if found != item["value"] or type(found) is not type(item["value"]):
                problems.append(f"{ident}: {name} {source['key']} is {found!r}, not {item['value']!r}")
        else:
            if name not in cache:
                cache[name] = normalised((REPO_ROOT / SOURCES[name]).read_text(encoding="utf-8"))
            quote = normalised(source["quote"])
            if quote not in cache[name]:
                problems.append(f"{ident}: quote not found verbatim in {name}")
            elif not number_in(item["value"], quote):
                problems.append(f"{ident}: value {item['value']!r} not in its quote")
    return problems


def experiment_problems(experiments: Mapping[str, Mapping[str, Any]], evidence: Mapping[str, Any],
                        rubric: Mapping[str, Any]) -> List[str]:
    closed = set(rubric["eligibility"]["closed_increments"])
    problems: List[str] = []
    for family, entry in sorted(experiments.items()):
        missing = [f for f in EXPERIMENT_FIELDS if f not in entry]
        if missing:
            problems.append(f"{family}: missing {missing}")
            continue
        if entry["family"] != family:
            problems.append(f"{family}: family field differs")
        for ident in entry["evidence"]:
            if ident not in evidence:
                problems.append(f"{family}: unknown evidence item {ident}")
        for name in list(entry["related_closed"]) + list(entry["repairs"]):
            if name not in closed:
                problems.append(f"{family}: {name!r} is not a registered closed increment")
        for name, statement in entry["related_closed"].items():
            if not isinstance(statement, str) or not statement.strip():
                problems.append(f"{family}: no distinctness statement for {name}")
        for key in ("next_sessions", "follow_sessions"):
            if not isinstance(entry[key], int) or entry[key] < 0:
                problems.append(f"{family}: {key} must be a count")
        if entry["engineering"] not in range(5) or entry["interaction"] not in range(3):
            problems.append(f"{family}: K must be 0 to 4 and X 0 to 2")
    return problems


def candidate_table(experiments: Mapping[str, Mapping[str, Any]], scores: Mapping[str, Mapping[str, Any]],
                    evidence: Mapping[str, Mapping[str, Any]], admission: Mapping[str, Any],
                    rubric: Mapping[str, Any], cache: Dict[str, Any]):
    criteria = rubric["criteria"]
    table: Dict[str, Dict[str, Any]] = {}
    candidates: Dict[str, Dict[str, Any]] = {}
    caps: Dict[str, int] = {}
    if set(scores) != set(experiments):
        raise SystemExit(f"scored and described candidates differ: {sorted(set(scores) ^ set(experiments))}")
    for family, entry in sorted(scores.items()):
        exp = experiments[family]
        sources = {}
        for c in ("G", "P"):
            spec = entry[c]
            name = spec["file"]
            if name not in SOURCES:
                raise SystemExit(f"{family} {c}: source {name} not pinned")
            if name not in cache:
                cache[name] = json.loads((REPO_ROOT / SOURCES[name]).read_text(encoding="utf-8"))
            if spec["key"] is None and not str(spec.get("zero_reason", "")).strip():
                raise SystemExit(f"{family} {c}: a source without a key needs a zero_reason")
            count = lookup(cache[name], spec["key"]) if spec["key"] is not None else 0
            of = spec["of"]
            if not isinstance(count, int) or not isinstance(of, int) or of <= 0 or not 0 <= count <= of:
                raise SystemExit(f"{family} {c}: unusable source {spec}")
            share = count / of
            if c == "G":
                score = sel.level(share, criteria["G"]["thresholds"])
            else:
                if of != criteria["P"]["of"]:
                    raise SystemExit(f"{family} P: the denominator must be the {criteria['P']['of']} H0 scenario-sides")
                score = sel.basis_level(share, criteria["P"]["thresholds"], spec["basis"], criteria["P"]["basis_penalty"])
            sources[c] = {"count": count, "of": of, "share": round(share, 4), "score": score,
                          **({"basis": spec["basis"]} if c == "P" else {})}
        s = {"G": sources["G"]["score"], "P": sources["P"]["score"]}
        reasons = {}
        for c in sel.JUDGED:
            value, reason = entry[c]
            if not isinstance(reason, str) or not reason.strip():
                raise SystemExit(f"{family} {c}: every judgement score needs a reason")
            s[c] = value
            reasons[c] = reason
        stakes = [dict(evidence[i], id=i) for i in entry["stakes"]]
        if not stakes or any(i not in exp["evidence"] for i in entry["stakes"]):
            raise SystemExit(f"{family}: stakes must be evidence items of its experiment")
        cap = sel.leverage_cap(stakes, rubric["leverage_cap"])
        caps[family] = cap
        applied = []
        if s["L"] > cap:
            s["L"] = cap
            applied.append(f"L capped at {cap}")
        if exp["interaction"] == 2 and s["I"] > 3:
            s["I"] = 3
            applied.append("I capped at 3 (X2)")
        s["C"] = sel.cost_economy(exp["next_sessions"], exp["follow_sessions"], exp["engineering"])
        admitted = (not exp["new_family"]) or bool(admission.get(family, {}).get("admitted"))
        candidates[family] = {"family": family, "scores": s, "next_sessions": exp["next_sessions"],
                              "follow_sessions": exp["follow_sessions"], "engineering": exp["engineering"],
                              "interaction": exp["interaction"], "next_offline": exp["next_offline"],
                              "conflict_measured": exp["conflict_measured"], "repairs": exp["repairs"],
                              "depends_on_unidentified": exp["depends_on_unidentified"],
                              "uses_stopped_data": exp["uses_stopped_data"], "admitted": admitted}
        table[family] = {"increment": exp["id"], "scores": s, "G_source": sources["G"], "P_source": sources["P"],
                         "reasons": reasons, "caps_applied": applied, "leverage_cap": cap, "stakes": entry["stakes"],
                         "next_sessions": exp["next_sessions"], "follow_sessions": exp["follow_sessions"],
                         "engineering": exp["engineering"], "interaction": exp["interaction"], "admitted": admitted}
    return table, candidates, caps


def public_problems(data: Any) -> List[str]:
    problems = privacy_problems(data)
    text = json.dumps(data, ensure_ascii=False)
    problems += [f"candidate identity {i!r} in a public file" for i in IDENTITIES if i in text]
    return problems


def build() -> Dict[str, Any]:
    rubric = load("rubric.json")
    record = load("inputs.json")
    problems = pin_problems(record)
    if problems:
        raise SystemExit(f"pinned inputs differ: {problems}")
    exp_file = load("experiments.json")
    score_file = load("scores.json")
    experiments, evidence = exp_file["experiments"], exp_file["evidence"]
    cache: Dict[str, Any] = {}
    problems = experiment_problems(experiments, evidence, rubric) + evidence_problems(evidence, rubric, cache)
    if problems:
        raise SystemExit(f"experiments or evidence fail their checks: {problems}")
    table, candidates, caps = candidate_table(experiments, score_file["candidates"], evidence,
                                              exp_file["admission"], rubric, cache)
    result = sel.select(candidates, rubric, caps)
    by_level: Dict[str, int] = {}
    for item in evidence.values():
        by_level[item["level"]] = by_level.get(item["level"], 0) + 1
    out = {"schema": SCHEMA_SELECTION, "study_id": STUDY_ID, "weights": rubric["weights"],
           "tie_band": rubric["tie_band"], "robust_min_first": rubric["robust_min_first"],
           "inputs_sha256": normalized_sha256(DIRECTORY / "inputs.json"),
           "evidence_checked": {"items": len(evidence),
                                "keyed": sum(1 for e in evidence.values() if "file" in e["source"]),
                                "quoted": sum(1 for e in evidence.values() if "doc" in e["source"]),
                                "by_level": dict(sorted(by_level.items()))},
           "candidates": table, **result,
           "note": "a research prioritisation under the rubric registered before candidates and scores; "
                   "not evidence that any tactic works; nothing is promoted"}
    problems = public_problems(out) + public_problems(exp_file) + public_problems(score_file)
    if problems:
        raise SystemExit(f"public content check failed: {problems[:5]}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("freeze", "run"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.command == "freeze":
        return write_or_check(DIRECTORY / "inputs.json", dump(freeze_record()), args.check)
    return write_or_check(DIRECTORY / "selection.json", dump(build()), args.check)


if __name__ == "__main__":
    sys.exit(main())
