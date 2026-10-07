"""Sprint 21 direct-fire adjudication-semantics audit (``docs/SPRINT21_DIRECT_FIRE_SEMANTICS.md``). Offline only.

    python scripts/s21_semantics.py freeze [--check] [--protocol-only]
    python scripts/s21_semantics.py smoke
    python scripts/s21_semantics.py run [--check]

``freeze`` writes ``protocol.json`` (the registered rules, the K4 probability-law evidence, the target classes the
sufficiency rule requires, the disposition order and the normalised SHA-256 of every frozen source; it can be written
and checked anywhere) and ``inputs.json`` (the inventory of every existing private capture or record with the reason it
is used or not, and the SHA-256 of every file of the frozen corpus; it needs the private files, so the evaluation server
writes it).

``smoke`` is the pre-freeze run of the loader and the pairing on the real corpus: it prints integrity counts and the
pairing status counts only, no K2, K4, K5 or K6 figure.

``run`` refuses unless every pinned file and frozen source matches; it builds the private factual rows, the public
aggregates ``coverage.json``, ``k2.json``, ``k4.json``, ``k5.json``, ``k6.json``, ``semantics.json`` and
``disposition.json`` (checked by the sanitizer) and the private rows ``local/diagnostics/s21/rows-private.json.gz``.
``--check`` rebuilds and compares instead of writing. It runs on the evaluation server, where the private inputs are.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import json
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

OUT = REPO_ROOT / "evaluation" / "s21-direct-fire-semantics"
PROTOCOL = OUT / "protocol.json"
INPUTS = OUT / "inputs.json"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "s21"
LOCAL_EVAL = REPO_ROOT / "local" / "evaluation"
S20_REPLAY = REPO_ROOT / "evaluation" / "s20-t11-replay" / "replay.json"
SCHEMA_PROTOCOL = "miaosuan-s21-protocol/1"
SCHEMA_INPUTS = "miaosuan-s21-inputs/1"
SCHEMA_RESULTS = "miaosuan-s21-results/1"
SOURCES = ("src/miaosuan_agent/evaluation/s21_semantics.py", "scripts/s21_semantics.py")
#: Capture compact-file suffixes of the full-step observer family (``evaluation/residual516.Capture`` and its
#: subclasses) and the matching window files.
COMPACT_SUFFIXES = {".capture.json": ".windows.pkl", ".diagnostic.json": ".windows.pkl", ".timeline.json": ".timeline.pkl"}
#: Folders not opened, and why (section 5).
NOT_OPENED = {"baseline-v2-target-ownership-prevalence-1": "registered stop of the prevalence study: its data stay "
                                                           "unexamined"}
V2 = "baseline-v2-candidate-shoot-target-reservation"
INERT = "inert-v0"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def normalised(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def policy_class(policy: str) -> str:
    """Public policy labels, as Sprint 18 uses them (candidate identities stay out of public files)."""
    if policy == V2:
        return "baseline-v2"
    if policy == INERT:
        return "inert control"
    if policy.startswith("baseline-"):
        return "earlier baselines"
    return "exploratory and tactical candidates"


# ------------------------------------------------------------------------------------------------
# protocol

def protocol() -> Dict[str, Any]:
    from miaosuan_agent.evaluation import s21_semantics as sm
    replay = json.loads(S20_REPLAY.read_text(encoding="utf-8"))
    return {
        "schema": SCHEMA_PROTOCOL, "study_id": sm.STUDY_ID, "engine_sessions": 0,
        "usable_capture_rule": "a capture of the full-step observer family whose window file holds a pre-step snapshot "
                               "(the all-seeing state and the observation of every shooting seat) for every step, whose "
                               "step log holds the pre-execution copies of the submitted actions, the engine's feedback "
                               "and the step's new judge records, and which keeps the final post-step state",
        "pairing": {"accepted": "exactly one shoot echo with the same seat, unit, target and weapon, without error",
                    "paired": "an accepted shot with exactly one direct-fire record of the step naming its unit, target "
                              "and weapon, claimed by no other accepted shot",
                    "ambiguous": "an accepted shot with more than one such record: excluded and counted",
                    "integrity_failures": list(sm.INTEGRITY_FAILURES) + [
                        "a record claimed by two accepted shots", "a paired record whose cur_step is not the step's",
                        "a paired record whose colours disagree with the shooter's and target's",
                        "a shooter or target absent from the pre-step state", "a shooting seat's observation missing",
                        "a missing snapshot or final state", "a step's removed units disagreeing with its snapshots",
                        "an unpaired record that is not a same-hex engagement", "a judge record of another type"]},
        "target_classes": list(sm.TARGET_CLASSES), "class_by_type": {f"type_{k}": v for k, v in sm.CLASS_BY_TYPE.items()},
        "required_classes": sm.required_classes(replay["HH"]["pooled"]),
        "required_classes_source": "evaluation/s20-t11-replay/replay.json, HH pooled target class pairs of root and "
                                   "induced changed shots, both sides",
        "k2": {"statuses": [sm.K2_SUPPORTED, sm.K2_REFUTED, sm.K2_UNRESOLVED], "subgroups": list(sm.SUBGROUPS),
               "rule": "supported only if every paired shot with both levels has listed == judged, the paired rows cover "
                       "two or more ele_diff values (unless the corpus has only one), and no source contradicts it"},
        "k4": {"mapping_statuses": [sm.MAPPING_SUPPORTED, sm.MAPPING_CONTRADICTED, sm.MAPPING_UNTESTED],
               "probability_statuses": [sm.K4P_SUPPORTED, sm.K4P_UNRESOLVED],
               "probability_evidence": [{**e, "quotes": [list(q) for q in e["quotes"]]} for e in sm.K4_PROBABILITY_EVIDENCE],
               "probability_status_at_registration": sm.k4_probability_status(),
               "tables": {"personnel_by_random_number": {sm.labelled("random_value", k): list(v)
                                                         for k, v in sm.PERSONNEL_RESULT.items()},
                          "vehicle_columns_by_shooter_count": {sm.labelled("count", k): list(v)
                                                               for k, v in sm.VEHICLE_COLUMNS.items()},
                          "vehicle_by_random_number": {sm.labelled("random_value", k): list(v)
                                                       for k, v in sm.VEHICLE_RESULT.items()},
                          "air_by_random_number": {sm.labelled("random_value", k): list(v) for k, v in sm.AIR_RESULT.items()},
                          "vehicle_correction_bins_low_high_by_armor_0_to_4": [list(b[:2]) + [list(b[2])]
                                                                               for b in sm.VEHICLE_CORRECTION_BINS],
                          "personnel_correction": "modified random number <= 0: -1; 1 to 7: 0; >= 8: +1",
                          "infantry_light_weapon": sm.INFANTRY_LIGHT_WEAPON},
               "snapshot": {"path": sm.SNAPSHOT, "files_sha256": dict(sm.SNAPSHOT_FILES_SHA256)}},
        "k5": {"relations": sorted(sm.RELATIONS), "short_relations": sorted(sm.SHORT_RELATIONS),
               "statuses": [sm.K5_IDENTIFIED, sm.K5_UNDERIDENTIFIED, sm.K5_NO_FIT, sm.K5_UNTESTED]},
        "k6": {"statuses": [sm.K6_SUPPORTED, sm.K6_REFUTED, sm.K6_UNTESTED]},
        "dispositions_first_match": list(sm.DISPOSITIONS), "t11_completions": list(sm.T11_COMPLETIONS),
        "hh_changed_shots": sm.HH_CHANGED_SHOTS,
        "sources": {p: normalised(REPO_ROOT / p) for p in SOURCES},
        "s20_replay_sha256": sha256(S20_REPLAY),
    }


# ------------------------------------------------------------------------------------------------
# inventory and inputs (section 5)

def captures() -> List[Tuple[str, Path, Path]]:
    out = []
    for folder in sorted(p for p in LOCAL_EVAL.iterdir() if p.is_dir()):
        if folder.name in NOT_OPENED or not (folder / "capture").is_dir():
            continue
        for path in sorted((folder / "capture").iterdir()):
            for suffix, wsuffix in COMPACT_SUFFIXES.items():
                if path.name.endswith(suffix):
                    out.append((folder.name, path, path.with_name(path.name[: -len(suffix)] + wsuffix)))
    return out


def capture_facts(folder: str, compact_path: Path, windows_path: Path) -> Dict[str, Any]:
    """Structural facts of one capture and whether it meets the usable-capture rule (no semantic value is read)."""
    game = compact_path.name.split(".capture.json")[0].split(".diagnostic.json")[0].split(".timeline.json")[0]
    record_path = LOCAL_EVAL / folder / "games" / f"{game}.json"
    compact = json.loads(compact_path.read_text(encoding="utf-8"))
    steps = compact.get("steps") or []
    record = json.loads(record_path.read_text(encoding="utf-8")) if record_path.exists() else {}
    shots = sum((b.get("action") or {}).get("type") == 2 for s in steps for b in s.get("batch") or ())
    judged = sum(len(s.get("judge_new") or ()) for s in steps)
    facts: Dict[str, Any] = {"folder": folder, "game": game, "steps": len(steps), "shoot_actions": shots,
                             "judge_records": judged, "engine_version": record.get("engine_version"),
                             "session": record.get("session"), "scenario_id": record.get("scenario_id"),
                             "condition": record.get("condition"),
                             "policy_classes": sorted({policy_class(s["policy"]) for s in record.get("seats") or ()})}
    reasons = []
    if not record_path.exists():
        reasons.append("no game record")
    if not all("submitted" in s and "feedback" in s and "judge_new" in s for s in steps) or not steps:
        reasons.append("the step log lacks pre-execution copies, feedback or judge records")
    if not windows_path.exists():
        reasons.append("no window file")
    else:
        with windows_path.open("rb") as handle:
            windows = pickle.load(handle)
        samples = windows.get("samples") or []
        ks = [s.get("k") for s in samples]
        facts["snapshots"] = len(samples)
        if ks != list(range(len(steps))):
            reasons.append("pre-step snapshots do not cover every step")
        if not windows.get("final"):
            reasons.append("no final post-step state")
        shooting = {b["seat"] for s in steps for b in s.get("batch") or () if (b.get("action") or {}).get("type") == 2}
        kept = set()
        for s in samples:
            kept |= {int(k) for k in (s.get("seats") or {})}
        if not shooting <= kept:
            reasons.append("a shooting seat's observation is not kept")
    facts["usable"] = not reasons
    facts["reasons_not_usable"] = reasons
    if not reasons:
        facts["files"] = {kind: {"path": p.relative_to(REPO_ROOT).as_posix(), "sha256": sha256(p)}
                          for kind, p in (("record", record_path), ("compact", compact_path), ("windows", windows_path))}
    return facts


OTHER_SOURCES = {
    "local/replay-corpus": "seat observations and actions of the replay corpus: no engine feedback, so acceptance cannot "
                           "be established independently of the judge record",
    "explore and confirmation captures": "the exploratory capture keeps only indirect-fire judgements and the "
                                         "confirmation capture keeps no judge record",
    "game records": "game records hold aggregates only, no per-shot judge record",
    "BOKE-2026": "not used",
}


def inventory() -> Dict[str, Any]:
    entries = [capture_facts(f, c, w) for f, c, w in captures()]
    folders = sorted(p.name for p in LOCAL_EVAL.iterdir() if p.is_dir())
    explore = sorted(f for f in folders if f not in NOT_OPENED and (LOCAL_EVAL / f / "capture").is_dir()
                     and any((LOCAL_EVAL / f / "capture").glob("*.explore.json"))
                     and not any(e["folder"] == f for e in entries))
    records_only = sorted(f for f in folders if not (LOCAL_EVAL / f / "capture").is_dir())
    return {"captures": entries, "explore_or_confirmation_only_folders": explore, "records_only_folders": records_only,
            "not_opened": dict(NOT_OPENED), "other_sources": dict(OTHER_SOURCES)}


def inputs() -> Dict[str, Any]:
    from miaosuan_agent.evaluation import s21_semantics as sm
    inv = inventory()
    corpus = [e for e in inv["captures"] if e["usable"]]
    public_inventory = []
    for e in inv["captures"]:
        public_inventory.append({k: e.get(k) for k in ("folder", "game", "steps", "snapshots", "shoot_actions",
                                                       "judge_records", "engine_version", "session", "scenario_id",
                                                       "condition", "policy_classes", "usable", "reasons_not_usable")})
    return {"schema": SCHEMA_INPUTS, "study_id": sm.STUDY_ID,
            "corpus": [{"folder": e["folder"], "game": e["game"], "files": e["files"]} for e in corpus],
            "inventory": public_inventory,
            "explore_or_confirmation_only_folders": inv["explore_or_confirmation_only_folders"],
            "records_only_folders": inv["records_only_folders"], "not_opened": inv["not_opened"],
            "other_sources": inv["other_sources"],
            "s20_replay": {"path": "evaluation/s20-t11-replay/replay.json", "sha256": sha256(S20_REPLAY)}}


def input_problems(committed: Mapping[str, Any], proto: Mapping[str, Any]) -> List[str]:
    problems = []
    for entry in committed["corpus"]:
        for f in entry["files"].values():
            p = REPO_ROOT / f["path"]
            if not p.exists() or sha256(p) != f["sha256"]:
                problems.append(f["path"])
    for path, digest in proto["sources"].items():
        if normalised(REPO_ROOT / path) != digest:
            problems.append(path)
    if sha256(S20_REPLAY) != committed["s20_replay"]["sha256"] or sha256(S20_REPLAY) != proto["s20_replay_sha256"]:
        problems.append(committed["s20_replay"]["path"])
    return problems


# ------------------------------------------------------------------------------------------------
# loading the frozen corpus (sections 7 and 8)

UNIT_FIELDS = ("obj_id", "color", "type", "sub_type", "blood", "max_blood", "keep", "stack", "armor", "cur_hex",
               "close_combat", "on_board", "launcher", "car", "in_fort", "fort", "fort_passengers", "move_path", "speed",
               "lose_control")


def units(state: Mapping[str, Any]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for where in ("operators", "passengers"):
        for u in state.get(where) or ():
            if isinstance(u, Mapping) and isinstance(u.get("obj_id"), int):
                out[u["obj_id"]] = {**{k: u.get(k) for k in UNIT_FIELDS}, "where": where}
    return out


def _related(u: Mapping[str, Any]) -> List[int]:
    return [v for v in (u.get("launcher"), u.get("car")) if isinstance(v, int) and not isinstance(v, bool) and v > 0]


class Corpus:
    """The private factual rows of the frozen corpus."""

    def __init__(self) -> None:
        self.shots: List[Dict[str, Any]] = []
        self.records: List[Dict[str, Any]] = []
        self.removals: List[Dict[str, Any]] = []
        self.fort_occupants: List[Dict[str, Any]] = []
        self.problems: List[Tuple[str, str]] = []
        self.other_type_records = 0
        self.private_values: set = set()
        self.games: List[Dict[str, Any]] = []

    def problem(self, kind: str, detail: str) -> None:
        from miaosuan_agent.evaluation import s21_semantics as sm
        if kind not in sm.PROBLEM_KINDS:
            raise ValueError(f"unregistered problem kind: {kind}")
        self.problems.append((kind, detail))

    def load_game(self, entry: Mapping[str, Any]) -> None:
        from miaosuan_agent.evaluation import s21_semantics as sm
        files = {k: REPO_ROOT / v["path"] for k, v in entry["files"].items()}
        record = json.loads(files["record"].read_text(encoding="utf-8"))
        compact = json.loads(files["compact"].read_text(encoding="utf-8"))
        with files["windows"].open("rb") as handle:
            windows = pickle.load(handle)
        steps = compact["steps"]
        samples = sorted(windows.get("samples") or [], key=lambda s: s["k"])
        final = windows.get("final")
        game = entry["game"]
        tag = f"{entry['folder']}/{game}"
        if [s["k"] for s in samples] != list(range(len(steps))) or not final or final.get("k") != len(steps):
            self.problem("missing_snapshot_or_final_state", tag)
            return
        cache: Dict[int, Dict[int, Dict[str, Any]]] = {}

        def state(k: int) -> Dict[int, Dict[str, Any]]:
            if k not in cache:
                raw = samples[k]["global"] if k < len(steps) else final["global"]
                cache[k] = units(pickle.loads(raw))
            return cache[k]

        counts = collections.Counter()
        for k, step in enumerate(steps):
            submitted = step.get("submitted") or []
            judge = [r for r in step.get("judge_new") or () if isinstance(r, Mapping)]
            direct = [r for r in judge if r.get("type") == sm.DIRECT_FIRE_TYPE]
            self.other_type_records += len(judge) - len(direct)
            if len(judge) != len(direct):
                self.problem("judge_record_of_another_type", f"{tag} k{k}")
            if not direct and not step.get("gone") and not any(
                    (e.get("action") or {}).get("type") == sm.SHOOT for e in submitted):
                continue
            pre, post = state(k), state(k + 1)
            for u in pre.values():
                self.private_values.add(u["obj_id"])
                if isinstance(u.get("cur_hex"), int):
                    self.private_values.add(u["cur_hex"])
            gone = set(pre) - set(post)
            if set(step.get("gone") or ()) != gone:
                self.problem("removed_units_disagree_with_snapshots", f"{tag} k{k}")
            pairing = sm.pair_step(submitted, step.get("feedback") or [], direct)
            for kind, detail in pairing["problems"]:
                self.problem(kind, f"{tag} k{k} {detail}")
            seats = samples[k].get("seats") or {}
            for shot in pairing["shots"]:
                counts[shot["status"]] += 1
                shooter, target = pre.get(shot["obj_id"]), pre.get(shot["target"])
                row = {"source": entry["folder"], "game": game, "k": k, "cur_step": step.get("cur_step"),
                       "seat": shot["seat"], "faction": shot["faction"], "status": shot["status"],
                       "shooter_class": sm.unit_class(shooter), "target_class": sm.unit_class(target),
                       "shooter": shooter, "target": target, "weapon": shot["weapon"]}
                if shooter is None or target is None:
                    self.problem("shooter_or_target_not_in_pre_state", f"{tag} k{k}")
                if shot["status"] == sm.PAIRED:
                    rec = direct[shot["records"][0]]
                    seat_snap = seats.get(shot["seat"], seats.get(str(shot["seat"])))
                    if seat_snap is None:
                        self.problem("shooting_seat_observation_missing", f"{tag} k{k}")
                        status, level = "missing", None
                    else:
                        observation = pickle.loads(seat_snap["observation"])
                        status, level = sm.listed_level(observation.get("valid_actions") or {}, shot["obj_id"],
                                                        shot["target"], shot["weapon"])
                    if rec.get("cur_step") != step.get("cur_step"):
                        self.problem("paired_record_cur_step_differs", f"{tag} k{k}")
                    if rec.get("attack_color") != shot["faction"] or (target and rec.get("target_color") != target.get("color")):
                        self.problem("paired_record_colours_disagree", f"{tag} k{k}")
                    row.update({"listed_status": status, "listed": level, "judged": rec.get("att_level"),
                                "ele_diff": rec.get("ele_diff"), "att_obj_blood": rec.get("att_obj_blood"),
                                "record_index": shot["records"][0]})
                self.shots.append(row)
            per_target = collections.Counter(r.get("target_obj_id") for r in direct)
            lethal_targets = set()
            for i, rec in enumerate(direct):
                t = pre.get(rec.get("target_obj_id"))
                if t is not None and isinstance(t.get("blood"), int) and isinstance(rec.get("damage"), int) \
                        and rec["damage"] >= t["blood"] and rec.get("target_obj_id") in gone:
                    lethal_targets.add(rec.get("target_obj_id"))
            for i, rec in enumerate(direct):
                status = pairing["record_status"][i]
                attacker, target = pre.get(rec.get("att_obj_id")), pre.get(rec.get("target_obj_id"))
                if status == sm.RECORD_UNMATCHED:
                    a_post, t_post = post.get(rec.get("att_obj_id")), post.get(rec.get("target_obj_id"))
                    same_hex = rec.get("distance") == 0 or bool(attacker and attacker.get("close_combat")) or (
                        attacker and target and attacker.get("cur_hex") == target.get("cur_hex")) or (
                        a_post and t_post and a_post.get("cur_hex") == t_post.get("cur_hex"))
                    status = sm.RECORD_SAME_HEX if same_hex else sm.RECORD_UNEXPLAINED
                    if status == sm.RECORD_UNEXPLAINED:
                        self.problem("unpaired_record_not_same_hex", f"{tag} k{k}")
                if rec.get("cur_step") != step.get("cur_step"):
                    counts["record_cur_step_differs"] += 1
                tid = rec.get("target_obj_id")
                after = post.get(tid)
                linked = bool(target) and any(r in gone and r in lethal_targets for r in _related(target))
                self.records.append({
                    "source": entry["folder"], "game": game, "k": k, "status": status, "record": dict(rec),
                    "attacker": attacker, "target": target, "target_class": sm.unit_class(target),
                    "present_after": after is not None, "blood_after": after.get("blood") if after else None,
                    "records_on_target_in_step": per_target[tid], "linked_removal": linked})
                if target and target.get("type") == 4:
                    occupants = [u for u in pre.values() if u.get("fort") == tid or u["obj_id"] in (target.get("fort_passengers") or ())]
                    for u in occupants:
                        u_after = post.get(u["obj_id"])
                        self.fort_occupants.append({
                            "class": sm.unit_class(u), "own_record": any(r.get("target_obj_id") == u["obj_id"] for r in direct),
                            "removed": u_after is None,
                            "blood_lost": (u_after is not None and isinstance(u.get("blood"), int)
                                           and isinstance(u_after.get("blood"), int) and u_after["blood"] < u["blood"]),
                            "fort_removed": after is None})
            recorded = {r.get("target_obj_id") for r in direct}
            for obj in sorted(gone - recorded):
                u = pre[obj]
                self.removals.append({"source": entry["folder"], "game": game, "k": k, "class": sm.unit_class(u),
                                      "on_board": u.get("where") == "passengers",
                                      "linked_to_removed_unit_with_record": any(r in gone and r in recorded for r in _related(u)),
                                      "unit": u})
        self.games.append({"source": entry["folder"], "game": game, "steps": len(steps),
                           "policy_classes": sorted({policy_class(s["policy"]) for s in record["seats"]}),
                           "shot_status": dict(counts)})


def load_corpus(committed: Mapping[str, Any]) -> Corpus:
    corpus = Corpus()
    for entry in committed["corpus"]:
        corpus.load_game(entry)
    return corpus


# ------------------------------------------------------------------------------------------------
# analysis rows and public aggregates

def record_rows(corpus: Corpus) -> List[Dict[str, Any]]:
    """K4 and K5 rows: every direct-fire record whose target is in the pre-step state."""
    from miaosuan_agent.evaluation import s21_semantics as sm
    rows = []
    for r in corpus.records:
        rec, target = r["record"], r["target"]
        if target is None:
            continue
        table, kind, value = sm.raw_cell(r["target_class"], rec.get("wp_id"), rec.get("att_level"), rec.get("random1"),
                                         rec.get("att_obj_blood"))
        full = sm.is_int(rec.get("ori_damage"))
        rows.append({"record": rec, "table": table, "kind": kind, "value": value,
                     "observed": rec.get("ori_damage") if full else rec.get("damage"),
                     "compared_field": "ori_damage" if full else "damage", "target_class": r["target_class"],
                     "target_blood_before": target.get("blood"), "target_suppressed_before": target.get("keep"),
                     "target_armor": target.get("armor"),
                     "correction_table": sm.correction_table(r["target_class"], rec.get("wp_id")) if full else None,
                     "status": r["status"]})
    return rows


def k6_rows(corpus: Corpus) -> List[Dict[str, Any]]:
    from miaosuan_agent.evaluation import s21_semantics as sm
    rows = []
    for r in corpus.records:
        t, rec = r["target"], r["record"]
        if t is None or r["records_on_target_in_step"] != 1 or not sm.is_int(t.get("blood")) or not sm.is_int(rec.get("damage")):
            continue
        rows.append({"class": r["target_class"], "blood_before": t["blood"], "damage": rec["damage"],
                     "present_after": r["present_after"], "blood_after": r["blood_after"],
                     "linked_removal": r["linked_removal"]})
    return rows


def coverage(corpus: Corpus) -> Dict[str, Any]:
    from miaosuan_agent.evaluation import s21_semantics as sm
    by_source: Dict[str, Dict[str, Any]] = {}
    for g in corpus.games:
        block = by_source.setdefault(g["source"], {"games": 0, "steps": 0, "shots_by_status": collections.Counter(),
                                                   "records_by_status": collections.Counter()})
        block["games"] += 1
        block["steps"] += g["steps"]
    for s in corpus.shots:
        by_source[s["source"]]["shots_by_status"][s["status"]] += 1
    for r in corpus.records:
        by_source[r["source"]]["records_by_status"][r["status"]] += 1
    by_class: Dict[str, Dict[str, int]] = {}
    for c in sm.TARGET_CLASSES:
        shots = [s for s in corpus.shots if s["target_class"] == c]
        recs = [r for r in corpus.records if r["target_class"] == c]
        by_class[c] = {"submitted_shots": len(shots), "paired_shots": sum(s["status"] == sm.PAIRED for s in shots),
                       "ambiguous_shots": sum(s["status"] == sm.AMBIGUOUS for s in shots),
                       "refused_shots": sum(s["status"] == sm.REFUSED for s in shots),
                       "judge_records": len(recs), "records_with_one_record_on_the_target_in_step":
                           sum(r["records_on_target_in_step"] == 1 for r in recs)}
    paired = [s for s in corpus.shots if s["status"] == sm.PAIRED]
    att_blood_equal = sum(s.get("att_obj_blood") == (s["shooter"] or {}).get("blood") for s in paired)
    problem_kinds = collections.Counter(kind for kind, _ in corpus.problems)
    return {
        "games": len(corpus.games), "integrity_problems": len(corpus.problems),
        "integrity_problems_by_kind": dict(sorted(problem_kinds.items())),
        "judge_records_of_another_type": corpus.other_type_records,
        "shots_by_status": dict(sorted(collections.Counter(s["status"] for s in corpus.shots).items())),
        "records_by_status": dict(sorted(collections.Counter(r["status"] for r in corpus.records).items())),
        "records_target_not_in_pre_state": sum(r["target"] is None for r in corpus.records),
        "listed_level_status_of_paired_shots": dict(sorted(collections.Counter(s.get("listed_status") for s in paired).items())),
        "paired_record_att_obj_blood_equal_to_shooter_blood_before": [att_blood_equal, len(paired)],
        "by_source": {k: {**v, "shots_by_status": dict(sorted(v["shots_by_status"].items())),
                          "records_by_status": dict(sorted(v["records_by_status"].items()))}
                      for k, v in sorted(by_source.items())},
        "by_target_class": by_class,
    }


def analyse(corpus: Corpus) -> Dict[str, Dict[str, Any]]:
    from miaosuan_agent.evaluation import s21_semantics as sm
    proto = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    required = proto["required_classes"]
    cov = coverage(corpus)
    integrity_ok = not corpus.problems and cov["games"] == len(json.loads(INPUTS.read_text(encoding="utf-8"))["corpus"])
    paired = [s for s in corpus.shots if s["status"] == sm.PAIRED]
    k2_rows = [{"listed": s.get("listed"), "judged": s.get("judged"), "ele_diff": s.get("ele_diff"),
                "att_obj_blood": s.get("att_obj_blood"), "weapon": s.get("weapon"),
                "shooter_class": s["shooter_class"], "target_class": s["target_class"]} for s in paired]
    corpus_ele = {r["record"].get("ele_diff") for r in corpus.records}
    k2 = sm.k2_summary(k2_rows, corpus_ele)
    rows = record_rows(corpus)
    k4p = sm.k4_probability_status()
    k4 = {"support": sm.k4_support(rows), "mapping": sm.k4_mapping(rows),
          "mapping_paired_shots_only": sm.k4_mapping([r for r in rows if r["status"] == sm.RECORD_PAIRED]),
          "correction_mapping": sm.correction_mapping(rows),
          "probability_law": {"status": k4p, "evidence": [{k: e[k] for k in ("id", "route", "status")}
                                                         for e in sm.K4_PROBABILITY_EVIDENCE],
                              "evidence_text": "protocol.json, k4.probability_evidence"}}
    k5 = {c: sm.k5_class([r for r in rows if r["target_class"] == c]) for c in sm.TARGET_CLASSES}
    k5_paired = {c: sm.k5_class([r for r in rows if r["target_class"] == c and r["status"] == sm.RECORD_PAIRED])["status"]
                 for c in sm.TARGET_CLASSES}
    six = k6_rows(corpus)
    k6 = {"by_class": {c: sm.k6_class([r for r in six if r["class"] == c]) for c in sm.TARGET_CLASSES},
          "removals_without_own_record": {
              c: {"removed": sum(r["class"] == c for r in corpus.removals),
                  "on_board": sum(r["class"] == c and r["on_board"] for r in corpus.removals),
                  "linked_to_a_removed_unit_with_a_record": sum(r["class"] == c and r["linked_to_removed_unit_with_record"]
                                                                for r in corpus.removals)}
              for c in sm.TARGET_CLASSES},
          "fortification_occupants": {
              "occupant_steps": len(corpus.fort_occupants),
              "with_own_record": sum(o["own_record"] for o in corpus.fort_occupants),
              "removed": sum(o["removed"] for o in corpus.fort_occupants),
              "blood_lost": sum(o["blood_lost"] for o in corpus.fort_occupants),
              "removed_or_blood_lost_without_own_record": sum((o["removed"] or o["blood_lost"]) and not o["own_record"]
                                                              for o in corpus.fort_occupants),
              "by_class": label_free_counts([o["class"] for o in corpus.fort_occupants])}}
    sufficiency = {c: {"k2": k2["by_target_class"][c], "k4_probability": k4p, "k5": k5[c]["status"],
                       "k6": k6["by_class"][c]["status"],
                       **sm.class_sufficiency(k2["by_target_class"][c], k4p, k5[c]["status"], k6["by_class"][c]["status"])}
                   for c in sm.TARGET_CLASSES}
    disp = sm.disposition(integrity_ok, sufficiency, required)
    return {"coverage.json": {**cov, "integrity_ok": integrity_ok},
            "k2.json": k2, "k4.json": k4, "k5.json": {"by_class": k5, "paired_shots_only_status": k5_paired}, "k6.json": k6,
            "semantics.json": {"required_classes": required, "by_class": sufficiency,
                               "p_kill_now_calculator": "not constructed: the semantics are not resolved"
                               if disp["disposition"] != sm.DISPOSITIONS[2] else "to be frozen under section 15"},
            "disposition.json": {**disp, "integrity_ok": integrity_ok, "engine_sessions": 0,
                                 "t11_completion": None if disp["disposition"] != sm.DISPOSITIONS[2] else "pending"}}


def label_free_counts(values: Sequence[str]) -> Dict[str, int]:
    return dict(sorted(collections.Counter(values).items()))


def build(committed: Mapping[str, Any]) -> Tuple[Dict[str, str], bytes]:
    from miaosuan_agent.evaluation import s21_semantics as sm
    corpus = load_corpus(committed)
    public = analyse(corpus)
    head = {"schema": SCHEMA_RESULTS, "study_id": sm.STUDY_ID, "protocol_sha256": sha256(PROTOCOL),
            "inputs_sha256": sha256(INPUTS)}
    public = {name: {**head, **data} for name, data in public.items()}
    for name, data in public.items():
        problems = sm.public_problems(data, corpus.private_values)
        if problems:
            raise SystemExit(f"privacy problems in {name}: {problems[:10]}")
    texts = {name: dump(data) for name, data in public.items()}
    private = {"shots": corpus.shots, "records": corpus.records, "removals": corpus.removals,
               "fort_occupants": corpus.fort_occupants, "problems": corpus.problems, "games": corpus.games}
    blob = gzip.compress(json.dumps(private, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8"), mtime=0)
    return texts, blob


def smoke(committed: Mapping[str, Any]) -> int:
    corpus = load_corpus(committed)
    cov = coverage(corpus)
    for key in ("games", "integrity_problems", "integrity_problems_by_kind", "judge_records_of_another_type",
                "shots_by_status", "records_by_status", "records_target_not_in_pre_state",
                "listed_level_status_of_paired_shots"):
        print(key, cov[key])
    for kind, detail in corpus.problems[:20]:
        print("PROBLEM", kind, detail)
    return 0


def run(check: bool) -> int:
    proto = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    committed = json.loads(INPUTS.read_text(encoding="utf-8"))
    problems = input_problems(committed, proto)
    if problems:
        print("inputs or frozen sources differ from their pins; refusing to run:", problems[:5])
        return 1
    texts, blob = build(committed)
    if check:
        same = all((OUT / name).exists() and (OUT / name).read_text(encoding="utf-8") == text
                   for name, text in texts.items())
        same &= (PRIVATE / "rows-private.json.gz").exists() and (PRIVATE / "rows-private.json.gz").read_bytes() == blob
        print("audit identical" if same else "MISMATCH")
        return 0 if same else 1
    for name, text in texts.items():
        (OUT / name).write_text(text, encoding="utf-8", newline="\n")
    PRIVATE.mkdir(parents=True, exist_ok=True)
    (PRIVATE / "rows-private.json.gz").write_bytes(blob)
    print("wrote", ", ".join(sorted(texts)))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run")
    p.add_argument("--check", action="store_true")
    sub.add_parser("smoke")
    p = sub.add_parser("freeze")
    p.add_argument("--check", action="store_true")
    p.add_argument("--protocol-only", action="store_true", help="write or check protocol.json alone (no private data)")
    args = parser.parse_args()
    if args.command == "freeze":
        texts = {PROTOCOL: dump(protocol())}
        if not args.protocol_only:
            texts[INPUTS] = dump(inputs())
        if args.check:
            same = all(p.exists() and p.read_text(encoding="utf-8") == t for p, t in texts.items())
            print(("identical: " + ", ".join(p.name for p in texts)) if same else "MISMATCH")
            return 0 if same else 1
        OUT.mkdir(parents=True, exist_ok=True)
        for p, t in texts.items():
            p.write_text(t, encoding="utf-8", newline="\n")
        print("wrote", ", ".join(p.name for p in texts))
        return 0
    if args.command == "smoke":
        return smoke(inputs())
    return run(args.check)


if __name__ == "__main__":
    sys.exit(main())
