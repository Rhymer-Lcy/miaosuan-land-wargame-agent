# Baseline identity: baseline-v1

> Since 2026-10-01 the current baseline is `baseline-v2` (`docs/BASELINE_V2.md`), which adds one registered
> change to this policy. The identity recorded here, the policy source and every `baseline-v1` artefact are
> unchanged and still verify.

`baseline-v1` is `baseline-v0` plus exactly one registered change: within one decision step, at most
one occupation command is issued per objective. It was promoted after the registered candidate
experiment passed all eleven acceptance criteria (`docs/EVALUATION_OCCUPY_RESERVATION.md`). It is a
reference point, not a competitor; nothing in it was tuned on outcomes. `baseline-v0`
(`docs/BASELINE.md`) is preserved unchanged and still verifies under its original identity.

## Identity

| Field | Value |
|---|---|
| Identity | `baseline-v1`, the promoted name of the executed candidate `baseline-v1-candidate-occupy-reservation`. The code and every trace keep the candidate name, so no result is attributed to code other than what ran |
| Policy source | SHA-256 `1d01e48a245273ded0b413ec6248e6aa54bba313ba8d6abbae2a20575544e2e9` over `agent.py`, `boundary/`, `decision/`, `experiments/__init__.py` and `experiments/occupy_reservation.py` (`OCCUPY_RESERVATION_SOURCES` in `src/miaosuan_agent/evaluation/identity.py`); unchanged since commit `3def154` |
| Golden decisions | trace chain `11e12bf0475c04672701bcbb4daa6579c6c3b0238ac90fb8320b2384e61acc66` (`tests/test_occupy_reservation.py`) |
| Registration | manifest canonical SHA-256 `38526b9250d8bce7facdb0f5c6303b5f2040e3939bd2bcedfe1fc2fdb14f103f` (amendment 1, commit `1376ca6`, superseding manifest `aff71d57…` of commit `0b4c2cd`); both pushed before the engine sessions they govern |
| Executed | harness commit `1376ca6`; Gate 1 and the 64-game suite in engine sessions 0088 to 0153 |
| Engine | `land_wargame_train_env` 4.1.0 from the persistent installation; SDK archive SHA-256 `ed4c9fc03cb6eb1e64821d2efbc61024d90735e3dc489dc7ffe0515e653ea725` |
| Runtime | CPython 3.10.20 (`miaosuan-runtime`, CPU only); the public tests also pass on CPython 3.12 |
| Configuration | none: no parameters, thresholds or weights |
| Aggregate results | `evaluation/baseline-v1-candidate-occupy-reservation/results.json`, SHA-256 `ea0ec674e8e51e546684fb75696673e5c81d32d6c9dd7a0d11796a91aeaeda07` |
| Evaluation summary | 64 of 64 games completed; no project-gate rejection; no duplicate same-objective occupation emitted; no code-1804 refusal (`baseline-v0`: 157); G4 as registered still fails in 12 of 24 applicable configurations, from shooting and lost-unit conflicts that this change does not address |

Verify the identity of a checkout:

```bash
python -m unittest tests.test_candidate_registration tests.test_occupy_reservation
```

## The one change

Units are processed in `baseline-v0` order with `baseline-v0`'s priority (engage, occupy, move).
The first unit that selects occupation of an objective keeps it for the step; a later unit that
would select occupation of the same objective (keyed by the hex it stands on, the objective's
`coord`) is suppressed and continues down the unchanged hierarchy, which in practice means it does
nothing that step. Each suppression is recorded in the decision trace with reason
`same-step-objective-reserved`; it is a coordination decision, not a legality verdict. The
reservation lives for one step. Everything else is `baseline-v0`, reused by import.

Before registration, both policies decided on 33,702 recorded real start-of-step states: 33,667
were identical and the 35 that differed were all explained by the rule (55 duplicate occupations
suppressed, no other action type changed).

## Known limitations

Carried over from `baseline-v0` except where the change removed them; material now:

* Shooting is uncoordinated: several units may fire at one target in a step (code 516, 18 in the
  suite), and a shot or an occupation by a unit destroyed earlier in the step is refused (code 203,
  10 in the suite; 9 shots and 1 occupation, see `docs/REFUSAL_TAXONOMY.md`). Fire still
  concentrates on the lowest-id target among equal attack levels. `baseline-v2`
  (`docs/BASELINE_V2.md`) allows at most one shot per target in a seat's step.
* A suppressed unit, like any unit standing on an unheld objective, waits there; once every
  objective is held, all units idle. The no-op rate of unit-steps stays above 0.99.

  > Correction (2026-10-01; text only, the identity and every result are unchanged): "all units idle" is
  > inaccurate. Engagement comes first in each unit's priority whatever the objectives' state
  > (`src/miaosuan_agent/decision/policy.py`), so once every objective is held no unit moves or occupies,
  > but a unit with a listed shoot option still shoots. `docs/BASELINE_V2.md` states it correctly.
* Movement ignores enemy positions, minefields and line of sight, never changes movement state and
  cannot be redirected once issued; passengers are never unloaded.
* Rare decisions take 0.4 to 1.1 s in the candidate suite (up to 1.3 s in the `baseline-v0` suite). The
  cause was measured afterwards (`docs/LATENCY_DIAGNOSTIC.md`): route planning at the first play
  decision, and late-game collection pauses of the shared engine process. The routing part is removed,
  with identical decisions, in the runtime `baseline-v1-runtime-r1` (`docs/BASELINE_V1_RUNTIME_R1.md`).
* Outcomes are stochastic once shots are fired, and two repetitions per configuration cannot
  estimate their variance, so no outcome comparison between `baseline-v0` and `baseline-v1` is
  possible from these suites. The variance study (`docs/VARIANCE_STUDY.md`) has since measured
  the variance with ten repetitions per configuration.
