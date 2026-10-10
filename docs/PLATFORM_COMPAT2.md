# Platform compatibility wrapper compat2

The upload package is the frozen `baseline-v2` policy (source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae`)
with a generated entry point, `ai/agent.py`. The canary (`a3d3b022...`) and compat1 (`3c1135f1...`) archives are kept
byte-identical; compat2 changes only the entry point and `ai/PACKAGE.json`. Build it with
`python scripts/build_platform_package.py --variant compat2`. Dates are business dates in UTC+8.

## 1. What the online test showed (2026-10-10, sanitised)

In one human-against-AI test match the platform passed `setup_info.seat` as the string `"p3"`. compat1's setup
raised `ContractError: setup_info.seat: expected an int`; the platform kept calling `step`, and the agent returned no
action for the whole game (deployment ended without it; its units never moved). `cost_data` was present. The platform's
own replay of the match shows the same platform seat representation throughout: `role_and_grouping_info` is keyed
`"p<N>"` plus a non-player entry `"god"` (faction -1, role -1, no units), `user_id` values are strings, operators carry
an `owner` string `"p<N>"`, `scenario_id` is a non-numeric string, and a top-level `extra` field is present. Raw
replays and logs stay under the ignored `local/` tree.

## 2. Contract implemented by compat2

| Item | Rule | Evidence |
|---|---|---|
| External seat | `setup_info["seat"]` as passed: an int, or `"p<N>"` with N a canonical decimal of at least 1; anything else fails setup | online setup log; the replay's seat keys |
| Internal seat | the int, or N | the frozen policy requires an int seat |
| Outbound `actor` | the external seat, verbatim (`"p3"` online, the int locally) | the platform's documented reference agent: `self.seat = setup_info["seat"]`, `"actor": self.seat`, `observation["role_and_grouping_info"][self.seat]`; the documented `owner` field is "int / str" |
| Seat-table keys | int, decimal string (JSON), `"p<N>"` to N, `"god"` to the reserved internal seat -1 only with faction -1, role -1 and no units; anything else, or two keys for one internal seat, is refused for that step | replay |
| `user_id` | a non-int value is left out of the internal view (the policy never reads it) | replay |
| JSON keys | mappings whose keys are all decimal strings are re-keyed by int, `cost_data` included (as compat1) | compat1 |
| Unchanged | every other field, including `scenario_id`, `terrain_id`, `extra` and `owner`, which the policy does not read | source |

Status and diagnostics: `setup` ends `ready` or `failed`; a failure is reported with the exception class, the field
path with indices masked, the expected form and a category (seat, faction, cost_data, contract, internal), never as
success. While not ready, `step` returns nothing except a labelled FALLBACK that only ends the seat's deployment when the
external seat itself was valid. One-time lines report the setup result (seat form, faction, cost_data parsing, router),
the first observation (seat-key forms, own entry, faction consistency, unit count), the first deployment and play
decisions, the first MOVE, the first submitted action's form, zero controllable units and a missing router; distinct
errors and invalid outputs are reported once each, at most 50 lines per game. No unit id, hex, coordinate, user name,
`cost_data` value or credential is printed.

## 3. Verification

* `tests/test_platform_compat2.py`: the incident reproduces against compat1 and not against compat2; 13 malformed seats
  and a malformed faction fail closed; the non-player rule, an unknown key and a key collision are refused; whole
  synthetic games give the repository agent's actions in the engine form, the JSON form and the platform form (actor
  `"p<N>"`), with MOVE paths on the neighbour graph; cost_data present, absent and malformed; reset and repeated setup;
  diagnostics free of unit ids, hexes and user names; seven planted defects (seat mapping, actor conversion, JSON keys,
  non-player rule, collision check, failure status, seat strictness) each caught.
* An independent verifier (private) rebuilds nothing: it checks the archive against `HEAD`, the canary's vendored
  bytes and the frozen digests, then plays a fixture built from a real SDK map's movement costs in the online seat
  representation; six planted archive defects are caught.
* The replay corpus (real engine observations) is replayed in the engine, JSON and platform forms under CPython 3.10.

## 4. Not verified until an online run

The seat observation the AI receives (only the platform's global replay and the setup log were available), acceptance
of `actor` `"p<N>"` by the online engine, the online `cost_data` structure and its parsing, and the movement graph of
the online map (its costs are not in the local SDK data). An online test passes when: no setup error; the setup line
reports the seat mapping and a ready router; deployment reaches play; no recurring contract error; a MOVE is emitted,
recorded as accepted, and a blue unit's path or hex changes; no refusal of the action format.
