"""The registered Sprint 16 mechanism capture (``docs/SPRINT16_MECHANISM_CAPTURE.md``): every frozen rule.

Three exclusive engine sessions of the frozen ``t9-batch-capacity-v3`` against the inert control, one game per adverse
configuration, under Sprint 12's full-step observers (unchanged). Not a score screen, not a candidate evaluation, not a
confirmation: no engine action comes from anything but frozen v3, and nothing is promoted. The delayed rules are
evaluated only afterwards, as analysis-side shadows (:mod:`.s16_shadow`), on the recorded v3 observations.

This module fixes, before session 2791: the identities, the card and its pins, the session budget and the ledger audit;
which per-game stops are structural; the risk windows; the first shadow divergence and its classification per
configuration; the 2120531121 C3 reservation certificate; the replacement restoration (R3) and recourse (R4) measures;
the disposition; and the public sanitization. Nothing here reads an engine, a capture or the ledger by itself; callers
pass the data in.

Evidence boundary. A shadow and frozen v3 produce the same world only until the first decision at which the shadow's
emitted actions differ from v3's (the FIRST SHADOW DIVERGENCE). States strictly before it are on-policy for the shadow;
the state at it is valid for judging the proposed first action; every later recorded state is a v3 state, OFF-POLICY
for the shadow. The registered classification rests on the first divergence only.
"""

from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from ..decision import INERT_ID
from . import exploratory as xp
from . import manifest as mf
from . import s12_screen as sc

STUDY_ID = "s16-mechanism-capture"
CARD_ID = "s16-v3-mechanism-capture-1"
SCHEMA = "miaosuan-s16-mechanism/1"
V3_ID, V3_DIGEST = sc.V3_ID, sc.V3_DIGEST
V2_ID, V2_DIGEST = sc.V2_ID, sc.V2_DIGEST
RUNTIME = "baseline-v1-runtime-r2"
LEDGER_BASE_SESSION = 2790
SESSION_CEILING = 3
WORKERS = 1
#: (position, scenario, condition, red, blue): Sprint 10's seat and inert-control semantics (C2 = v3 red against the
#: inert blue control, C3 = the inert red control against v3 blue), in the owner's order.
SCHEDULE = ((1, "1930331196", "C3", INERT_ID, V3_ID), (2, "1930331196", "C2", V3_ID, INERT_ID),
            (3, "2120531121", "C3", INERT_ID, V3_ID))
EXPECTED_SESSIONS = (2791, 2792, 2793)
FIRE_CONFIGS = ("1930331196 C3", "1930331196 C2")
RESERVATION_CONFIG = "2120531121 C3"
CONFIGS = FIRE_CONFIGS + (RESERVATION_CONFIG,)
SHOOT, MOVE = 2, 1

#: Every threshold and anchor, fixed before session 2791.
RULES: Dict[str, Any] = {
    "max_step": 2880,
    "capacity": 4,
    # firing decisions of Sprint 10's frozen baseline-v2 captures (sessions 2776 and 2778): reference anchors that
    # every 1930331196 risk window includes
    "historical_fire_anchors": {"1930331196 C3": [742, 804, 841, 876], "1930331196 C2": [611]},
    # baseline-v2's first ownership of the missed 80-point objective in Sprint 10's capture (session 2774); reported,
    # the 2120531121 window itself is the observed v3 first ownership
    "historical_capture_anchor": {"2120531121 C3": 564},
    # R3 replacement: distinct reference units (T9-v1's post-opening redirected units on the four Sprint 12 primary
    # games, per seat) and the restored units required, ceil(0.5 x reference)
    "reference_units": {"H1": 15, "H2": 26},
    "restoration_required": {"H1": 8, "H2": 13},
    # R4 replacement: cross-objective redirects per memory episode
    "recourse_per_episode_max": 1,
}
STRUCTURAL_STOPS = ("S1", "S2", "S3", "S4", "S6", "S7")
CLASSES = {
    "1930331196 C3": {"safe": "C3_PREFIX_SAFE", "bad": "C3_FIRST_DIVERGENCE_UNSAFE", "ambiguous": "C3_PREFIX_AMBIGUOUS"},
    "1930331196 C2": {"safe": "C2_PREFIX_SAFE", "bad": "C2_FIRST_DIVERGENCE_UNSAFE", "ambiguous": "C2_PREFIX_AMBIGUOUS"},
    "2120531121 C3": {"safe": "C3_212_PREFIX_SAFE", "bad": "C3_212_FIRST_DIVERGENCE_BAD_RESERVATION",
                      "ambiguous": "C3_212_PREFIX_AMBIGUOUS"},
}
NO_TRIGGER = "NO_TRIGGER_OBSERVED"
DISPOSITIONS = ("CAPTURE_INVALID", "MECHANISM_REFUTED", "MECHANISM_AMBIGUOUS", "MECHANISM_PREFIX_SUPPORTED")

#: Files whose normalised SHA-256 the card pins. None may change after the first session: the game entry point and
#: the runner refuse a card whose pins differ from the checkout.
FROZEN_FILES = (
    "src/miaosuan_agent/evaluation/s16_mechanism.py",
    "src/miaosuan_agent/evaluation/s16_shadow.py",
    "src/miaosuan_agent/evaluation/s12_capture.py",
    "src/miaosuan_agent/evaluation/s12_timeline.py",
    "src/miaosuan_agent/evaluation/s12_screen.py",
    "src/miaosuan_agent/evaluation/s13_diagnosis.py",
    "src/miaosuan_agent/evaluation/s14_design.py",
    "src/miaosuan_agent/evaluation/s15_delayed.py",
    "src/miaosuan_agent/evaluation/t9_confirmation.py",
    "src/miaosuan_agent/evaluation/exploratory.py",
    "src/miaosuan_agent/evaluation/residual516.py",
    "src/miaosuan_agent/evaluation/t9_batch_replay.py",
    "src/miaosuan_agent/evaluation/game.py",
    "src/miaosuan_agent/experiments/t9_batch.py",
    "src/miaosuan_agent/experiments/t9_delayed.py",
    "src/miaosuan_agent/experiments/t9_redistribution.py",
    "src/miaosuan_agent/experiments/t9_allocation.py",
    "src/miaosuan_agent/experiments/exploratory_addon.py",
    "scripts/build_s16_card.py",
    "scripts/run_s16_game.py",
    "scripts/run_s16_capture.py",
    "scripts/s16_analysis.py",
    "scripts/run_evaluation.py",
    "scripts/run_s12_stage.py",
    "scripts/s14_design_replay.py",
    "tests/test_s16_shadow.py",
    "tests/test_s16_mechanism.py",
    "tests/test_t9_batch.py",
    "tests/test_s12_proposal_draft.py",
)

TEXTS = {
    "status": "EXPLORATORY TRACK - REGISTERED MECHANISM CAPTURE - NOT A SCORE SCREEN - NOT ELIGIBLE FOR PROMOTION",
    "version": "t9-batch-capacity-v3, frozen, unchanged; Sprint 16 mechanism capture (docs/SPRINT16_MECHANISM_CAPTURE.md)",
    "mechanism": "frozen v3 plays every decision of its seat; the delayed rules exist only as analysis-side shadows "
                 "(s16-delayed-shadow-v6) evaluated afterwards on the recorded observations and never act",
    "controls": "none: the inert control seat; no score is compared and nothing is pooled",
    "configurations": "1930331196 C3, 1930331196 C2, 2120531121 C3 against the inert control, one game each, serially",
    "safety_checks": ["structural stops after every game (S1, S2, S3, S4, S6, S7 of the frozen Sprint 12 checks)",
                      "exactly three sessions after closed session 2790; exclusive diagnostic sessions, one at a time",
                      "every frozen implementation file pinned by digest; any difference refuses the card",
                      "the v3 policy source pinned to 9b2003a7...; baseline-v2's to 7cbaf032..."],
    "intended_observations": ["Sprint 9's T9Capture, Sprint 12's compact v3 capture and full-step timeline with the "
                              "seat-local reconstruction of baseline-v2 and v3 at every decision, all unchanged"],
    "next_step_rule": "none automatic: after the analysis the study returns to the owner",
}


# ------------------------------------------------------------------------------------------------
# Identities, card, budget


def normalized_sha256(path: Path) -> str:
    return sc.normalized_sha256(path)


def frozen_digests(repo: Path) -> Dict[str, str]:
    return {rel: normalized_sha256(repo / rel) for rel in FROZEN_FILES}


def rules_digest() -> str:
    return hashlib.sha256(json.dumps(RULES, sort_keys=True).encode("utf-8")).hexdigest()


def config_key(scenario: str, condition: str) -> str:
    return f"{scenario} {condition}"


def game_id(position: int, scenario: str, condition: str) -> str:
    return f"{scenario}.{condition}.{CARD_ID}.p{position:02d}"


def games() -> List[Dict[str, Any]]:
    return [{"game_id": game_id(p, s, c), "scenario_id": s, "condition": c, "red": r, "blue": b, "screen_position": p}
            for p, s, c, r, b in SCHEDULE]


def build_card(shoot_manifest: Mapping[str, Any], shoot_manifest_sha256: str, policies: Sequence[Mapping[str, Any]],
               frozen: Mapping[str, str], shadow: Mapping[str, Any]) -> Dict[str, Any]:
    """The Sprint 16 run card. ``shadow``: the analysis identity, recorded for reference and never executable."""
    by_id = {p["id"]: p for p in policies}
    if sorted(by_id) != sorted((V2_ID, V3_ID)):
        raise ValueError("the card's policies are baseline-v2 and v3 only")
    if by_id[V3_ID]["policy_source"]["sha256"] != V3_DIGEST or by_id[V2_ID]["policy_source"]["sha256"] != V2_DIGEST:
        raise ValueError("a policy source is not the frozen one")
    if sorted(frozen) != sorted(FROZEN_FILES):
        raise ValueError("the frozen file set differs from FROZEN_FILES")
    rows = games()
    budget = {"batch_sessions": len(rows), "ledger_base_session": LEDGER_BASE_SESSION,
              "sprint_session_cap": SESSION_CEILING}
    card = xp.build(CARD_ID, TEXTS, shoot_manifest, shoot_manifest_sha256, policies, V3_ID, rows, RUNTIME, WORKERS,
                    budget)
    for row, game in zip(card["games"], rows):
        row["screen_position"] = game["screen_position"]
    card["screen"] = {"id": STUDY_ID, "stage": "capture", "rules": RULES, "rules_sha256": rules_digest(),
                      "frozen_files": dict(sorted(frozen.items())), "expected_sessions": list(EXPECTED_SESSIONS),
                      "shadow": {**dict(shadow), "executable": False}}
    return card


def card_problems(card: Mapping[str, Any], repo: Path) -> List[str]:
    """Why ``card`` may not be played from this checkout: identity, rules, frozen files, policies, budget, schedule."""
    problems = []
    screen = card.get("screen") or {}
    if card.get("card_id") != CARD_ID or screen.get("id") != STUDY_ID:
        return ["not the Sprint 16 mechanism card"]
    if screen.get("rules") != RULES or screen.get("rules_sha256") != rules_digest():
        problems.append("the card's rules are not the frozen rules")
    current = frozen_digests(repo)
    pinned = screen.get("frozen_files") or {}
    changed = sorted(rel for rel, digest in pinned.items() if current.get(rel) != digest)
    if changed or sorted(pinned) != sorted(FROZEN_FILES):
        problems.append(f"frozen implementation files differ from the card: {changed}")
    policies = card.get("policies") or {}
    if (sorted(policies) != sorted((V2_ID, V3_ID))
            or policies[V3_ID].get("policy_source", {}).get("sha256") != V3_DIGEST
            or policies[V2_ID].get("policy_source", {}).get("sha256") != V2_DIGEST):
        problems.append("policy identities are not the frozen ones")
    budget = card.get("budget") or {}
    if (budget.get("ledger_base_session"), budget.get("sprint_session_cap"), budget.get("batch_sessions")) != (
            LEDGER_BASE_SESSION, SESSION_CEILING, len(SCHEDULE)):
        problems.append("budget is not the registered ceiling")
    planned = [(g.get("game_id"), g.get("scenario_id"), g.get("condition"), g.get("red"), g.get("blue"))
               for g in card.get("games") or ()]
    if planned != [(g["game_id"], g["scenario_id"], g["condition"], g["red"], g["blue"]) for g in games()]:
        problems.append("the games are not the registered schedule")
    if (screen.get("shadow") or {}).get("executable") is not False:
        problems.append("the shadow identity is marked executable")
    return problems


# ------------------------------------------------------------------------------------------------
# Ledger (S1, S2)


def ledger_audit(ledger: Sequence[Mapping[str, Any]], card: Mapping[str, Any]) -> Dict[str, Any]:
    """Every session opened after 2790 must be the next game of the card in schedule order (session 2790 + n plays
    position n) under the card's digest, opened once and closed with integrity ok, the state chain continuous, at most
    three sessions and none unclosed."""
    order = [g["game_id"] for g in card["games"]]
    digest = mf.digest(card)
    problems: Dict[str, List[str]] = {"S1": [], "S2": []}
    opened: Dict[str, str] = {}
    ended: Dict[str, Mapping[str, Any]] = {}
    seen: Dict[str, str] = {}
    previous = None
    for record in ledger:
        session = record.get("session")
        later = session is not None and int(session) > LEDGER_BASE_SESSION
        if later and record.get("event") == "session-open":
            harness = record.get("harness") or {}
            game = harness.get("game_id")
            position = int(session) - LEDGER_BASE_SESSION
            if game not in order:
                problems["S2"].append(f"session {session} plays a game outside the card")
            elif position > len(order) or order[position - 1] != game:
                problems["S2"].append(f"session {session} is not the card's game in schedule position {position}")
            if harness.get("card") != CARD_ID or harness.get("manifest_sha256") != digest:
                problems["S2"].append(f"session {session} is not under the Sprint 16 card")
            if game in seen:
                problems["S2"].append(f"game opened twice (sessions {seen[game]} and {session})")
            seen[game] = session
            opened[session] = game
            if previous is not None and record.get("state") != previous.get("state"):
                problems["S1"].append(f"session {session} opened with a state other than the previous record's")
        elif later and record.get("event") in ("session-close", "session-recovered"):
            if session in ended:
                problems["S2"].append(f"session {session} ended twice")
            ended[session] = record
            if record.get("event") == "session-recovered":
                problems["S2"].append(f"session {session} was recovered")
            elif not (record.get("integrity") or {}).get("ok"):
                problems["S1"].append(f"session {session} closed with an integrity failure")
        previous = record
    unclosed = sorted(set(opened) - set(ended))
    if unclosed:
        problems["S2"].append(f"unclosed sessions {unclosed}")
    if len(opened) > SESSION_CEILING:
        problems["S2"].append(f"{len(opened)} sessions exceed the ceiling of {SESSION_CEILING}")
    return {"sessions": len(opened), "games": dict(sorted(seen.items())), "unclosed": unclosed, "problems": problems,
            "ok": not any(problems.values())}


def structural_stops(stops: Mapping[str, Sequence[str]]) -> List[str]:
    """The structural stops among a game's Sprint 12 stop findings. S5 and S8 to S14 describe v3's own behaviour and
    are reported, not stops; an add-on error also fails S7, because the frozen observer's consistency check requires
    none."""
    return [code for code in STRUCTURAL_STOPS if stops.get(code)]


# ------------------------------------------------------------------------------------------------
# First shadow divergence and the per-configuration classification


def plain(actions: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return [{str(k): v for k, v in dict(a).items()} for a in actions]


def diverges(v3_actions: Sequence[Mapping[str, Any]], shadow_actions: Sequence[Mapping[str, Any]]) -> bool:
    """A decision is a divergence when the emitted action lists differ (content or order)."""
    return plain(v3_actions) != plain(shadow_actions)


def changed_units(v3_actions: Sequence[Mapping[str, Any]], shadow_actions: Sequence[Mapping[str, Any]]) -> List[Any]:
    """Units whose emitted actions differ between v3 and the shadow (an action present in one list only included)."""
    def by_unit(actions):
        out: Dict[Any, List[Dict[str, Any]]] = collections.defaultdict(list)
        for action in plain(actions):
            out[action.get("obj_id")].append(action)
        return out
    a, b = by_unit(v3_actions), by_unit(shadow_actions)
    return sorted((u for u in set(a) | set(b) if a.get(u) != b.get(u)), key=str)


def fire_window_end(config: str, observed: Mapping[Any, Sequence[int]], rules: Mapping[str, Any] = RULES) -> int:
    """The last decision of a 1930331196 risk window: the latest of the historical firing anchors and of every decision
    at which an own ground unit of the v3 seat had a direct-fire action listed or ordered in the new game."""
    decisions = list(rules["historical_fire_anchors"][config])
    for values in observed.values():
        decisions.extend(values)
    return max(decisions)


def reservation_window_end(first_own_decision: Optional[int], last_decision: int) -> int:
    """The last decision of the 2120531121 C3 risk window: v3's first ownership of the problem objective in the new
    game, or the last decision if v3 never owns it."""
    return last_decision if first_own_decision is None else first_own_decision


def protected_reasons(unit: Any, k: int, window_end: int, historical: Mapping[Any, int],
                      observed: Mapping[Any, Sequence[int]]) -> List[str]:
    """Why changing ``unit``'s action at decision ``k`` touches a firing role: a historical shooter whose firing
    decision is not before ``k``, or a unit with a direct-fire listing or order at some decision from ``k`` to the end
    of the window in the new game (a fire opportunity at ``k`` itself included)."""
    reasons = []
    if unit in historical and k <= historical[unit]:
        reasons.append("historical shooter before its firing decision")
    if any(k <= d <= window_end for d in observed.get(unit, ())):
        reasons.append("fire opportunity in the new game from this decision to the end of the window")
    return reasons


def classify_fire(config: str, fsd: Optional[Mapping[str, Any]], window_end: int, historical: Mapping[Any, int],
                  observed: Mapping[Any, Sequence[int]]) -> Dict[str, Any]:
    """1930331196 C3 and C2. ``fsd``: None (no divergence in the whole game) or {"k", "ordinal", "changed"} (the first
    divergence, its ordinal among decisions with an own ground move, the units whose actions differ)."""
    names = CLASSES[config]
    if fsd is None:
        return {"class": names["safe"], "sublabel": NO_TRIGGER, "window_end": window_end, "reasons": []}
    k = fsd["k"]
    if k > window_end:
        return {"class": names["safe"], "sublabel": "first divergence after the risk window", "window_end": window_end,
                "reasons": []}
    reasons = []
    if fsd["ordinal"] == 1:
        reasons.append("divergence at the opening decision (Sprint 14's harmful opening-redirect topology)")
    for unit in fsd["changed"]:
        reasons.extend(f"changed unit: {r}" for r in protected_reasons(unit, k, window_end, historical, observed))
    if reasons:
        return {"class": names["bad"], "sublabel": "first divergence inside the risk window", "window_end": window_end,
                "reasons": sorted(set(reasons))}
    return {"class": names["ambiguous"], "sublabel": "first divergence inside the risk window on a unit with no firing "
            "role: the world diverges before the window ends", "window_end": window_end, "reasons": []}


RESERVATION_CLAUSES = ("v3 selection not kept", "dominated by a faster selectable claimant",
                       "cannot arrive before the end", "fills the problem objective's last place needed by v3's capture")


def reservation_flags(row: Mapping[str, Any]) -> List[str]:
    """The bad-reservation clauses one first-divergence redirect meets (``row`` from the certificate)."""
    flags = []
    if row["v3_selection_not_kept"]:
        flags.append(RESERVATION_CLAUSES[0])
    if row["dominated"]:
        flags.append(RESERVATION_CLAUSES[1])
    if row["unreachable"]:
        flags.append(RESERVATION_CLAUSES[2])
    if row["to_problem_objective"] and row["consumes_last_place"] and row["before_first_ownership"] \
            and row["capturer_without_place"]:
        flags.append(RESERVATION_CLAUSES[3])
    return flags


def ownership_facts(k: int, first_own: Optional[int], holders_at_divergence: Iterable[Any],
                    capturers: Iterable[Any]) -> Dict[str, bool]:
    """The two facts of the fourth reservation clause that the v3 trajectory supplies after the divergence: the
    divergence comes before v3's first ownership of the problem objective (always, if v3 never owns it), and some unit
    standing on it at that first ownership held no place there (standing, counted mover or stage-1 selection) at the
    divergence. They identify which places v3's capture used; they are never read as the shadow's own future."""
    return {"before_first_ownership": first_own is None or k < first_own,
            "capturer_without_place": bool(set(capturers) - set(holders_at_divergence))}


def classify_reservation(fsd: Optional[Mapping[str, Any]], window_end: int,
                         rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """2120531121 C3. ``rows``: the certificate rows of the first divergence's redirects."""
    names = CLASSES[RESERVATION_CONFIG]
    if fsd is None:
        return {"class": names["safe"], "sublabel": NO_TRIGGER, "window_end": window_end, "reasons": []}
    if fsd["k"] > window_end:
        return {"class": names["safe"], "sublabel": "first divergence after the risk window", "window_end": window_end,
                "reasons": []}
    reasons = []
    if fsd["ordinal"] == 1:
        reasons.append("divergence at the opening decision")
    for row in rows:
        reasons.extend(reservation_flags(row))
    if reasons:
        return {"class": names["bad"], "sublabel": "first divergence inside the risk window", "window_end": window_end,
                "reasons": sorted(set(reasons))}
    return {"class": names["ambiguous"], "sublabel": "first divergence inside the risk window, no bad-reservation "
            "clause: the world diverges before v3's capture", "window_end": window_end, "reasons": []}


def dominated(redirect_free_flow: Optional[int], destination_claimants: Sequence[Mapping[str, Any]]) -> bool:
    """A redirect is dominated when a claimant of the same destination at the same decision that can arrive before
    the end, with a strictly shorter free-flow time, is not given a place there."""
    if redirect_free_flow is None:
        return True
    return any(c["feasible"] and not c["placed"] and c["free_flow"] is not None and c["free_flow"] < redirect_free_flow
               for c in destination_claimants)


# ------------------------------------------------------------------------------------------------
# Disposition


def disposition(problems: Sequence[str], classes: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """First match: CAPTURE_INVALID (any capture, reconstruction, integrity or fidelity problem, or a configuration
    without a valid game), MECHANISM_REFUTED (a first divergence recreates a diagnosed adverse mechanism in some
    configuration), MECHANISM_AMBIGUOUS (some configuration's first divergence is inside its risk window without being
    that mechanism), else MECHANISM_PREFIX_SUPPORTED. ``classes``: the target shadow's classification per configuration."""
    if problems or sorted(classes) != sorted(CONFIGS):
        missing = sorted(set(CONFIGS) - set(classes))
        return {"disposition": DISPOSITIONS[0], "problems": list(problems)[:20], "configurations_missing": missing}
    bad = sorted(c for c, row in classes.items() if row["class"] == CLASSES[c]["bad"])
    if bad:
        return {"disposition": DISPOSITIONS[1], "configurations": bad}
    unclear = sorted(c for c, row in classes.items() if row["class"] == CLASSES[c]["ambiguous"])
    if unclear:
        return {"disposition": DISPOSITIONS[2], "configurations": unclear}
    if any(row["class"] != CLASSES[c]["safe"] for c, row in classes.items()):
        raise ValueError("an unknown class")
    return {"disposition": DISPOSITIONS[3], "no_trigger_observed": sorted(
        c for c, row in classes.items() if row.get("sublabel") == NO_TRIGGER)}


# ------------------------------------------------------------------------------------------------
# R3 replacement: distinct-unit restoration (historical primary corpus)


def restoration(reference: Mapping[str, Set[Tuple[str, Any]]], redirected: Mapping[str, Set[Tuple[str, Any]]],
                rules: Mapping[str, Any] = RULES) -> Dict[str, Any]:
    """Per seat, the reference units (game, unit) T9-v1 redirects after the opening, the restored ones (reference units
    the shadow redirects at least once after the opening; repeats of one unit count once) and the frozen requirement."""
    seats = {}
    for seat in ("H1", "H2"):
        ref = set(reference.get(seat, ()))
        restored = ref & set(redirected.get(seat, ()))
        seats[seat] = {"reference_units": len(ref), "restored_units": len(restored),
                       "required": rules["restoration_required"][seat],
                       "pass": len(restored) >= rules["restoration_required"][seat]}
    fidelity = {seat: seats[seat]["reference_units"] == rules["reference_units"][seat] for seat in seats}
    return {"seats": seats, "reference_reproduced": fidelity, "pass": all(s["pass"] for s in seats.values())}


# ------------------------------------------------------------------------------------------------
# R4 replacement: bounded recourse per memory episode, tracked independently of the shadow's memory


class EpisodeTracker:
    """Episodes of one shadow on one recorded stream, from the observation and v3's stage-1 allocation only (never the
    shadow's memory): an episode of a unit is a run of overflow observations at one source; it ends when the unit is
    absent, has a path ending on an objective, stands on an objective its side does not hold, its source is held by
    its side, it is given a place or claims while it cannot arrive, or overflows at another source (which starts a new
    episode). Every redirect the shadow emits is charged to the unit's open episode."""

    def __init__(self) -> None:
        self.open: Dict[Any, Dict[str, Any]] = {}
        self.closed: List[Dict[str, Any]] = []
        self.outside = 0

    def _close(self, unit: Any) -> None:
        self.closed.append(self.open.pop(unit))

    def before(self, units: Mapping[Any, Tuple[Any, Tuple[Any, ...]]], flags: Mapping[Any, Any], faction: int) -> None:
        """``units``: own ground unit -> (hex, path); ``flags``: objective -> flag, both at this decision."""
        for unit in sorted(self.open, key=str):
            position = units.get(unit)
            episode = self.open[unit]
            if position is None:
                self._close(unit)
                continue
            hex_, path = position
            if path and path[-1] in flags:
                self._close(unit)
            elif not path and hex_ in flags and flags[hex_] != faction:
                self._close(unit)
            elif flags.get(episode["source"]) == faction:
                self._close(unit)

    def after(self, k: int, claimants: Mapping[Any, Tuple[Any, bool, bool]], redirected: Mapping[Any, Any]) -> None:
        """``claimants``: unit -> (own objective, can arrive (overflow-eligible status), given a place by stage 1);
        ``redirected``: unit -> destination of this decision's shadow redirects."""
        for unit in sorted(claimants, key=str):
            source, feasible, placed = claimants[unit]
            if placed or not feasible:
                if unit in self.open:
                    self._close(unit)
                continue
            if unit in self.open and self.open[unit]["source"] != source:
                self._close(unit)
            if unit not in self.open:
                self.open[unit] = {"unit": unit, "source": source, "start": k, "redirects": []}
        for unit, destination in sorted(redirected.items(), key=lambda item: str(item[0])):
            if unit not in self.open:
                self.outside += 1
                continue
            self.open[unit]["redirects"].append((k, self.open[unit]["source"], destination))

    def episodes(self) -> List[Dict[str, Any]]:
        return self.closed + list(self.open.values())


def oscillations(history: Sequence[Tuple[int, Any, Any, Any]]) -> int:
    """Redirects (decision, unit, from, to) that send a unit back to an objective it was earlier redirected away from,
    from the objective it was then redirected to (A to B, later B to A), across episodes (Sprint 15's definition).
    Within one episode the source is fixed, so an oscillation there needs two redirects in one episode, which the
    per-episode limit already forbids."""
    seen: Dict[Any, List[Tuple[Any, Any]]] = collections.defaultdict(list)
    count = 0
    for _, unit, source, target in sorted(history, key=lambda r: (r[0], str(r[1]))):
        if any(s == target and t == source for s, t in seen[unit]):
            count += 1
        seen[unit].append((source, target))
    return count


def recourse(trackers: Iterable[EpisodeTracker], rules: Mapping[str, Any] = RULES) -> Dict[str, Any]:
    """Bounded recourse per episode over several streams (one tracker per stream): at most the limit of redirects per
    episode, at most one destination per episode, no redirect outside an episode. Reported, not gated: redirects per
    unit over a whole stream (a unit may enter several episodes) and oscillations across episodes."""
    episodes, outside, per_unit, oscillating = [], 0, collections.Counter(), 0
    for index, tracker in enumerate(trackers):
        mine = tracker.episodes()
        episodes.extend(mine)
        outside += tracker.outside
        history = []
        for e in mine:
            per_unit[(index, e["unit"])] += len(e["redirects"])
            history.extend((k, e["unit"], source, target) for k, source, target in e["redirects"])
        oscillating += oscillations(history)
    counts = [len(e["redirects"]) for e in episodes]
    multi = sum(1 for e in episodes if len({r[2] for r in e["redirects"]}) > 1)
    worst = max(counts, default=0)
    totals = [n for n in per_unit.values() if n]
    return {"episodes": len(episodes), "episodes_with_a_redirect": sum(1 for n in counts if n),
            "max_redirects_per_episode": worst, "limit": rules["recourse_per_episode_max"],
            "episodes_over_limit": sum(1 for n in counts if n > rules["recourse_per_episode_max"]),
            "multi_destination_episodes": multi, "redirects_outside_episodes": outside,
            "redirects_per_unit": dict(sorted(collections.Counter(totals).items())),
            "oscillations_across_episodes": oscillating,
            "pass": worst <= rules["recourse_per_episode_max"] and multi == 0 and outside == 0}


# ------------------------------------------------------------------------------------------------
# Public sanitization


def public_check(value: Any, private_values: Iterable[Any] = ()) -> List[str]:
    """Forbidden keys at any depth and any private value (unit ids, hexes) as a number, key or word."""
    return sc.privacy_problems(value, private_values)


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
