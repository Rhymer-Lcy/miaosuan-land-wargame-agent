# Engine refusals: facts first, attribution second

An engine refusal is an entry of the engine's all-seeing `actions` feedback that carries an
`error`. Every refusal recorded so far concerned an action that the project safety gate had
accepted against the start-of-step `valid_actions`. This document fixes how refusals are
recorded and analysed from the variance study onward, and corrects one interpretation in the
earlier results. It changes no policy and no registered artifact.

## The correction

The refusal code 203 was treated as a shooting code: a unit that fires after being destroyed
earlier in the same step. Three places carry that reading.

* The registered taxonomy of the occupation-reservation experiment assigns every code 203 to the
  category "same-step conflict: shooter destroyed earlier in the step", with action type shoot
  (`evaluation/baseline-v1-candidate-occupy-reservation/manifest.json`). Its results count all ten
  suite refusals with code 203 in that category (`results.json`, `refusal_decomposition`). One of
  them was an occupation. The engine's message for code 203 is `CantControlDiedOperator` whether
  the action is a shot or an occupation.
* `docs/EVALUATION.md` gives action "shoot" and the message `CantControlDiedOperator` for the seven
  code-203 refusals of the `baseline-v0` suite, and `docs/BASELINE.md` describes code 203 as a shot
  by a destroyed unit. The `baseline-v0` suite records hold the code only. The action type and the
  message in that table were taken from separate diagnostic games, in which both code-203 refusals
  were shots. The action type of the seven suite refusals is unknown.
* The start-of-step context classifier used for the candidate results (attribution 1,
  `refusal_context` in `src/miaosuan_agent/evaluation/effects.py`) classifies code 203 only on shots.
  It left the occupation unclassified, which was correct, but it still reads the code as
  shooting-specific.

The registered files keep their contents and their digests; the counts they report are unchanged.
The derived analysis is `evaluation/refusal-taxonomy-correction/historical-refusal-facts.json`,
built by `scripts/derive_historical_refusal_facts.py` from the unchanged private game records. It is
checked against the committed results by `tests/test_refusal_history.py`.

## Factual record

The factual class of a refusal is the triple (action type, error code, normalized engine message).
Normalization collapses whitespace, replaces numbers with `N` and keeps 120 characters. The same code
under two action types, or under two messages, forms two classes.

From the variance study onward the harness keeps, privately and for every refusal
(`src/miaosuan_agent/evaluation/refusals.py`, schema `miaosuan-refusal-fact/1`):

* the game and session (record level), the decision index and the engine step;
* the action as echoed by the engine: type, unit, and for a shot its target and weapon;
* the error code, the raw message (up to 200 characters) and the normalized message;
* `passed_project_gate`: whether the echoed action equals, on its identifying fields, an action the
  seat emitted in that step. Only gate-accepted actions are emitted;
* `legal_at_start`: whether the action's type was listed for the unit in the seat's start-of-step
  `valid_actions`, and for a shot whether that listing held the same target and weapon;
* step evidence read from the all-seeing states before and after the step (below);
* the attribution label and its version.

Public results carry only counts by factual class and by attribution label.

## Attribution, version 2

A causal label is assigned only when the factual class matches a rule and the rule's evidence is
present and agrees. "On the map" means listed in `operators`; "present" means listed in `operators`
or `passengers`.

| Factual class | Label | Evidence required |
|---|---|---|
| occupy, 1804, `CantOccupyCauseAlreadyMy` | objective already held by own side at step start | the objective's flag was the own side's at step start |
| occupy, 1804, `CantOccupyCauseAlreadyMy` | same-step duplicate objective occupation | flag not own at step start, at least two own occupations of the objective in the step, flag own after the step |
| shoot, 516, `CantShootToDiedBop` | target no longer alive at resolution | target on the map at step start and present in no unit list after the step |
| any action type, 203, `CantControlDiedOperator` | actor no longer alive at resolution | acting unit on the map at step start and present in no unit list after the step |

Otherwise the label is one of:
* "unclassified: no attribution rule for this factual class";
* "unclassified: evidence missing";
* "unclassified: evidence contradicts the rule";
* "unclassified: evidence could not be gathered".

No label is inferred from the code alone, and a new code, message or action type stays
unclassified until a rule with its own evidence is added under a new version. Recording never ends a
game: a failure while gathering evidence is stored with the refusal.

Attribution 1 (the context classes) is still recorded for continuity. The code-level categories
remain inside the registered candidate manifest. Neither is used for new analysis.

## Historical facts

Engine refusals of the policy under test, as the historical records retain them. "Not retained"
counts refusals whose action type or message the harness of that evaluation did not keep; they are
not filled in from other games.

| Set | Refusals by factual class | Not retained |
|---|---|---|
| `baseline-v0` Gate 1 (2 games) | none | 0 |
| `baseline-v0` suite (64 games) | code 1804: 157, code 516: 23, code 203: 7; action type and message not recorded | 187 |
| `baseline-v0` diagnostics (4 games) | shoot, 203, `CantControlDiedOperator`: 2; shoot, 516, `CantShootToDiedBop`: 7; occupy, 1804: 76, of which 32 retained the message `CantOccupyCauseAlreadyMy` | 44 messages |
| candidate Gate 1, first attempt (2 games) | shoot, 203, `CantControlDiedOperator`: 1 | 0 |
| candidate Gate 1 (2 games) | shoot, 203, `CantControlDiedOperator`: 1 | 0 |
| candidate suite (64 games) | shoot, 203, `CantControlDiedOperator`: 9; occupy, 203, `CantControlDiedOperator`: 1; shoot, 516, `CantShootToDiedBop`: 18 | 0 |

The historical records hold no evidence from after the step, so no historical refusal carries an
attribution-2 label.
