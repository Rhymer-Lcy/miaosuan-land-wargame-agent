# Baseline identity: baseline-v2

`baseline-v2` is `baseline-v1` plus exactly one registered change: within one seat's decision step, at most one
emitted shoot action targets the same enemy object. It was promoted after the registered two-group experiment
passed all ten promotion criteria (`docs/EVALUATION_SHOOT_RESERVATION.md`). It runs on the runtime
`baseline-v1-runtime-r1` (`docs/BASELINE_V1_RUNTIME_R1.md`), which keeps its name, and makes the same decisions on
`baseline-v1-runtime-r2` (`docs/BASELINE_V1_RUNTIME_R2.md`), the same code with NumPy's OpenBLAS pool limited to one
thread. It is a reference point, not a
competitor; nothing in it was tuned on outcomes. `baseline-v1` (`docs/BASELINE_V1.md`) is preserved unchanged and
still verifies under its own identity.

## Identity

| Field | Value |
|---|---|
| Identity | `baseline-v2`, the promoted name of the executed candidate `baseline-v2-candidate-shoot-target-reservation`. The code and every trace keep the candidate name, so no result is attributed to code other than what ran |
| Parent | `baseline-v1`: policy source `1d01e48a245273ded0b413ec6248e6aa54bba313ba8d6abbae2a20575544e2e9`, golden decision chain `11e12bf0475c04672701bcbb4daa6579c6c3b0238ac90fb8320b2384e61acc66`, results `ea0ec674e8e51e546684fb75696673e5c81d32d6c9dd7a0d11796a91aeaeda07` |
| Runtime | `baseline-v1-runtime-r1` (code identity `baseline-v1-routing-bounded-candidate`): policy source `f9e50a538f1f530e9e485f75ce3d457435cfb9bcc2eb039ecdfa9374d54398ad`, routing-remediation registration `ffe4539d505dc53bc7b3875d9f9e451fc14ead6a4dd89bffe060bac028e87184` |
| Policy source | SHA-256 `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae` over the runtime's sources, byte-identical, plus `experiments/shoot_reservation.py` (`groups.C.policy_source` in the manifest) |
| Golden decisions | trace chain `0d16c814c03909ed89303a776b276b4cc441cd047450a063329009458654910f` (`tests/test_shoot_reservation.py`) |
| Registration | `evaluation/baseline-v2-candidate-shoot-target-reservation/manifest.json`, canonical SHA-256 `01c9c9675af4b0859fc55e54a5dc86513b624208bf13131e7b510b87a3122afd`, commit `e7ed892`, on the public remote 7.0 minutes before the first game |
| Executed | harness commit `e7ed892`; 720 games in engine sessions 0354 to 1073 |
| Results | `results.json` `695d3d7ae384d09a1db94d9e89ca6cc796c625fa0cd3cc72d99e4bb169b40172`; `counterfactual-replay.json` `323787b5ea97f205c0bde6ea78dd2575245df9dd99c50f6f7cb9a7e0bee7d652`; `mutation.json` `8a85954b2059bfdab37d73d853a63f4c48bb24efae26a0744b0f438fcae0e4e5`; `mutation-analysis.json` `3b0567fe5ff5b0e3ecd4d92690b5e705295a80b934ee5de18ca0e85de9c3528f` (file SHA-256) |
| Engine | `land_wargame_train_env` 4.1.0 from the persistent installation; SDK archive SHA-256 `ed4c9fc03cb6eb1e64821d2efbc61024d90735e3dc489dc7ffe0515e653ea725` |
| Runtime environment | CPython 3.10.20 (`miaosuan-runtime`, CPU only); the public tests also pass on CPython 3.12 |
| Refusal taxonomy | `miaosuan-refusal-fact/1`, `refusal-attribution/2` (`docs/REFUSAL_TAXONOMY.md`) |
| Configuration | none: no parameters, thresholds or weights |
| Experiment summary | 720 of 720 games completed; code-516 refusals per 1,000 unit actions 5.634 to 0.634 (difference −5.000, interval −6.125 to −3.937); C2/C3 margin difference +0.25 (interval −2.50 to +3.03, limit −10); no project-gate rejection, contract error, code-1804 refusal, duplicate occupation or new refusal class |

Verify the identity of a checkout:

```bash
python -m unittest tests.test_shoot_reservation tests.test_shoot_registration tests.test_shoot_results
```

## The one change

Units are processed in `baseline-v1`'s ascending id order, with its hierarchy (engage, occupy, move, nothing) and
its shoot ranking. When a unit's shoot action passes the final safety gate, its target is reserved for the rest of
the seat's step. A later unit's shoot options on a reserved target are excluded, and the unit selects exactly as
`baseline-v1` would among what remains. Each affected unit is recorded in the decision trace with reason
`same-step-shoot-target-reserved` and the effect on its selection; it is a coordination decision, not a legality
verdict. Reservations never cross seats or steps. Everything else is `baseline-v1` on `baseline-v1-runtime-r1`,
reused by import.

Before registration, both policies decided on the 33,802 decisions of the routing remediation's pinned corpus:
33,707 were identical, and the 95 that differed were all explained by the rule. 105 units were displaced
from a duplicate-target shot: 79 shot another target and 26 did nothing. No other action changed.

## Known limitations

Carried over from `baseline-v1` except where the change removed them; material now:

* A target is reserved by the first unit, in ascending id order, whose shot at it passes the gate, whatever that
  unit's attack level. A later unit with a stronger option on that target selects among the rest: another
  target, occupation, movement or nothing.
* A target that survives its first shot gets no second shot in that step, and nothing estimates whether one shot
  suffices. In the experiment, 460 displaced units had no unreserved shoot option, occupation or movement left
  and did nothing in that step.
* 16 code-516 refusals remained, each in a step with a single own shot at the target; what destroyed the target
  first was not established.

  > Later finding (2026-10-01; the identity and every result are unchanged): in scenario 1930331196 under C3 the
  > registered residual-516 diagnostic (`docs/RESIDUAL_516_DIAGNOSTIC.md`) established the cause of all 12
  > refusals it captured. The seat's own accepted shot earlier in the same step destroyed the vehicle that had
  > launched the target, an unmanned ground vehicle, and the engine removed the target with it. The other
  > residual refusals of the experiment were not captured, and their cause is not established.
* Code 203, a shot or occupation by a unit destroyed earlier in the step, is not addressed: 63 in the experiment,
  all in the C1 mirror. `move / 404 / CantMoveKeptPeople` occurred 3 times and stays unclassified.
* A unit standing on an unheld objective waits there, and once every objective is held no unit moves. The no-op
  rate of unit-steps stays above 0.99.
* Movement ignores enemy positions, minefields and line of sight, never changes movement state and cannot be
  redirected once issued; passengers are never unloaded.
* Late-game decisions can take more than 1 s: 10 in the experiment, all in scenario 2130511121 C3. The latency
  diagnostic traced such tails to collection pauses of the shared engine process (`docs/LATENCY_DIAGNOSTIC.md`);
  neither `baseline-v1-runtime-r1` nor `baseline-v1-runtime-r2` addresses them.
* Outcomes are stochastic once shots are fired; the experiment's outcome comparisons are means over 15 games per
  configuration.
