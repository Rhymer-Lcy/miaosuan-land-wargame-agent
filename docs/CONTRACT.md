# SDK contract: observed, accepted, canonical

Project code meets the SDK engine through one package, `miaosuan_agent.boundary`. Three notions are
kept apart:

1. **Observed contract.** What was measured from one engine build in specific runs. It is
   recorded as the profile `local-sdk-4.1.0` (`boundary/profile.py`), which is deliberately strict
   (exact key sets, exact Python types). A deviation from it is a finding about a new engine,
   scenario or platform, not necessarily an error.
2. **Accepted boundary.** The input forms that `normalize_state` and `Observation.from_raw`
   deliberately accept. Tolerance exists only where the conversion is unambiguous and a documented
   or observed form requires it; everything else raises `ContractError`, naming the path, the
   expected form and the actual type without dumping the observation.
3. **Canonical representation.** `StateView`, `Observation` and the value objects they return
   (`TimeInfo`, `Operator`, `SeatInfo`, read-only tuples and mappings with integer keys). Code
   above the boundary consumes only these, never raw SDK containers.

Nothing here claims how the online platform or SDK 5.0.0 and later behave.

## 1. Observed contract of local SDK 4.1.0

Evidence: engine `land_wargame_train_env` 4.1.0 (wheel digest in `PROVENANCE.md`), scenario
201033019601 on map 9601, runs on 2026-09-29: the first probe (`ENGINE_SMOKE_TEST.md`); session
0001 of the persistent installation, which captured the red, blue and all-seeing observations at
setup, after deployment and at the first play step; and session 0002, which reused the
installation, produced identical structural fingerprints at the same three points, and checked
every one of its 1,002 states against the full profile without a deviation.

| Contract element | Observed |
|---|---|
| State container | `dict` with `int` keys `0` (red), `1` (blue), `-1` (all-seeing); the first `step()` returned a new object and did not modify the one returned by `setup()` |
| `step()` return | 2-tuple `(state, done)`, `done` a `bool` |
| Player observation | 13 fields: `cities`, `communication`, `jm_points`, `judge_info`, `landmarks`, `operators`, `passengers`, `role_and_grouping_info`, `scenario_id`, `scores`, `terrain_id`, `time`, `valid_actions` |
| All-seeing observation | the same 13 plus `actions` |
| Visibility | each player view lists only its own seat and its own unit; the all-seeing view lists both seats and both units |
| `valid_actions` | unit ids and action types are `int`; values are `None` or a `list` of `dict`; a player view's keys are exactly its own unit ids |
| Director options | the all-seeing view also has key `-1` with action types 401, 402, 403, 404 (the documented director actions), each with value `None` |
| `time` | `cur_step` (`int`), `tick` (`float`), `max_time` (`int`), `max_step` (`int`), `stage` (`int`) |
| Stage | 1 at setup; 2 in the state returned by the step in which both seats sent 333; `cur_step` was still 0 in that state, 1 after the next step, and 1000 at `done` |
| `role_and_grouping_info` | keyed by seat (`int`); each entry has exactly `faction` (`int`), `role` (`int`), `operators` (`list` of `int`), `user_id` (`int`), `user_name` (`str`), `end_deployment` (`bool`) |
| Deployment completion | `{"actor": <seat>, "type": 333}` from each seat, sent in the same step, was accepted: `stage` became 2 and both seats' `end_deployment` became `True`. 333 appeared in no captured `valid_actions` |
| `communication` | a `list`; empty in every captured state (a populated form was not observed) |
| `actions` (all-seeing only) | a `list`; empty in every captured state, including the one after the step that carried both 333 actions |
| `scenario_id`, `terrain_id` | `int` (`terrain_id` equalled the map id) |
| `scores` | 12 `int` fields: `red_` and `blue_` `occupy`, `remain`, `remain_max`, `attack`, `total`, `win` |
| `landmarks` | exactly `roadblocks`, `minefields`, `fortifications`, each a `list` |
| Value types | every value in the nine captured observations is a plain `dict`, `list`, `int`, `float`, `str`, `bool` or `None` (no numpy scalars, subclasses or tuples) |

## 2. Accepted boundary

| Decision | Accepted | Reason |
|---|---|---|
| Origin | declared by the caller: `Origin.ENGINE` (in-process objects) or `Origin.JSON` (deserialized JSON) | JSON turns integer keys into strings; guessing the origin from the key form would hide a change in the engine's key type |
| Integer-keyed mappings | `ENGINE`: `int` keys only. `JSON`: canonical decimal strings only (`"0"`, `"-1"`, `"123"`; not `"01"`, `"-0"`, `"+1"`, `" 1"`). Mixed forms, `bool` and `float` keys are rejected | exactly the forms each origin can produce; nothing else is converted |
| Where keys are normalized | state slots, both levels of `valid_actions`, and `role_and_grouping_info` seats | nested data the boundary does not validate keeps its delivered key form |
| State container | a mapping containing slots `0`, `1`, `-1` (further integer slots kept in `extra_slots`), or a list or tuple of exactly three observations `[red, blue, all-seeing]` | the mapping form is observed; the list form is documented; with any other length `state[-1]` does not identify a distinct slot |
| Required fields | `time`, `operators`, `passengers`, `valid_actions`, `role_and_grouping_info` | present in every documentation generation and in the observed engine |
| Optional fields | `communication`, `actions`, `scenario_id`, `terrain_id`: `None` when absent, validated when present | each is missing from at least one documented form, or (for `actions`) from the observed player views |
| `time` | `cur_step` and `stage` required `int`; `tick` an `int` or `float`, returned as `float`; `max_time` and `max_step` optional `int` | some SDK scenario files carry an integer `tick` |
| Stage values | any `int`; `Stage.DEPLOYMENT` (1) and `Stage.PLAY` (2) are interpreted, other values are returned but not interpreted | stages beyond 1 and 2 were never observed |
| `valid_actions` values | `None`, or a list or tuple of mappings | observed form, with tuples tolerated as an unambiguous equivalent |
| `role_and_grouping_info` | `role` (`int`) and `operators` (sequence of `int`) required; `faction`, `user_id`, `user_name`, `end_deployment` optional | the bundled SDK documentation shows only `role` and `operators` |
| `scenario_id` | an `int`, or a canonical non-negative decimal string converted to `int` | four of the SDK's own scenario files store the id as a string |
| `terrain_id` | an `int` only | no evidence of another form |
| `bool` | never accepted where an `int` is expected | Python treats `bool` as an `int` subclass |
| Units | each unit record needs an `int` `obj_id`, unique within its list | the minimum the boundary itself relies on |
| Unknown fields | preserved (`Observation.unknown_fields()`, the `extra` members of `TimeInfo` and `SeatInfo`, `Operator.fields`) | later SDK versions may add data without breaking the adapter |

Deployment completion is decided by `deployment_completion_available(observation, seat)`: the stage
is deployment and the seat's `end_deployment` is not `True` (stage alone when the flag is absent).
The action itself is built by `end_deployment_action(seat)`.

## 3. Canonical representation

```
normalize_state(raw, origin)          -> StateView(form, red, blue, global_observation, extra_slots)
Observation.from_raw(raw, origin)     -> Observation
Observation.time()                    -> TimeInfo(cur_step, stage, tick, max_time, max_step, extra)
Observation.operators(), passengers() -> tuple of Operator(obj_id, fields)
Operator.color, unit_type, cur_hex    -> int (required when read)
Operator.sub_type, move_state         -> int or None;  Operator.move_path -> tuple of int or None
Observation.valid_actions()           -> {unit id: {action type: None | tuple of option mappings}}
Observation.role_and_grouping()       -> {seat: SeatInfo(...)};  Observation.seat(seat)
Observation.cities()                  -> tuple of City(coord, value, flag, name, extra) or None
Observation.roadblocks()              -> tuple of roadblock hexes or None
Observation.communication(), action_feedback(), scenario_id(), terrain_id()  -> value or None
MoveCosts.from_raw(cost_data, origin) -> MoveCosts;  MoveCosts.neighbours(mode, hex) -> {hex: cost}
```

`MoveCosts` normalizes the setup-supplied movement costs: exactly four modes (documented as
0 vehicle maneuver, 1 vehicle march, 2 infantry, 3 air), equal grid sizes, neighbour keys inside
the map, positive int or float costs. Observed: the cost graph of map 9601 still contains edges
into its roadblock cells, which the rules make impassable to vehicles, so movement code must also
consult `Observation.roadblocks()`.

Validation is lazy per accessor and cached; `normalize_state(..., validate=True)` and
`Observation.validate()` validate everything at once. Returned containers are read-only copies of
the top level, so an observation cannot be altered through the view. In the all-seeing view,
`valid_actions()` includes the director key `-1`; unit-level code should use a player view.

## 4. JSON caveat

JSON object keys are always strings, so a JSON copy of an engine state has keys `"0"`, `"1"`, `"-1"`
and string unit ids. Reading such data with `Origin.ENGINE` fails at the first stringified key;
reading it with `Origin.JSON` yields canonical results identical to the in-process data (checked on
every captured observation). Plain JSON is therefore not a faithful fixture format; private
captures use `miaosuan_agent.typed_json`, which preserves key types and tuples and reports any value
it could not encode exactly. `tests/fixtures/synthetic_state_json.json` shows the stringified form.

## 5. Fixtures and fingerprints

**Private real fixtures.** Captured observations derive from SDK scenario data without a
redistribution license, so they exist only under the git-ignored
`local/contract-fixtures/sdk-4.1.0/<capture-id>/`: per capture point a `container.json`, one
`<slot>.typed.json` per slot, one private fingerprint per slot, and a `manifest.json` with engine
version, scenario, harness commit, session id and the SHA-256 of every file. They are never
committed. `tests/test_real_fixtures.py` checks them when present and skips with a stated reason
when absent, so public test runs need no SDK material.

**Public synthetic fixtures.** `tests/fixtures/synthetic.py` builds observations with the
observed field names and types and fabricated values only: unit ids in the 900000 range, seats 7
and 17, scenario 900000001, terrain 9000, user names prefixed `synthetic-`. Tests state each
variation they need; the static JSON example is generated from the builders and checked against
them.

**Fingerprints.** `miaosuan_agent.fingerprint` reduces an observation to field names, value types,
key kinds and emptiness, keeping values only for the stage and the end-of-deployment flags. Its
public detail also reduces unit records to a field count. No fingerprint of a real observation is
committed; `tests/test_real_fixtures.py` checks that a public fingerprint contains none of the
observation's distinctive values.

## 6. Unknown

* how the online platform delivers observations (in-process objects or JSON), and which engine
  version it runs;
* any behaviour of SDK 5.0.0 and later, and of other scenarios, multi-agent seating, passengers,
  populated `communication`, or `actions` feedback;
* how the engine reports a rejected action to the player views, which lack `actions`;
* what the engine does when its time-since-first-use limit is reached.
