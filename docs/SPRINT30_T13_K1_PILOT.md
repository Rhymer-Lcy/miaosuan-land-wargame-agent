# Sprint 30: T13-K1 keep-one garrison, exploratory pilot

**EXPLORATORY TRACK — AT MOST FOUR ENGINE SESSIONS (2798 TO 2801) — NOT A CONFIRMATION — NOTHING PROMOTED — NOTHING
UPLOADED**

Dates are business dates in UTC+8 (2026-10-10). Sections 1 to 5 were committed and pushed before the historical
preflight ran; section 6 (the pilot card and its stop rules) before session 2798 was opened. No registered section is
edited afterwards; results follow in their own sections.

## 1. Starting state and the owner's authorization

| Item | Identity |
|---|---|
| Repository | `main` `08aff3fd47c2ec9e505276ff93eaef0ddb09ef85`, tree `a7803726953142ff8cd090a55284d0232afdc511`, on the workstation, GitHub and the evaluation server |
| Engine ledger | 2,797 sessions opened and closed, none unclosed; ledger file SHA-256 `70ae38f21e0ac2c0d9c2772a8fe73b5b3a6dbdcc8f4e62af8dbc4443d4df8036` (as at the close of Sprints 27 to 29); session 2798 unopened |
| `baseline-v2` | policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae`, unchanged |
| Platform canary | `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511`, unchanged |
| Privacy baseline | 106 accepted hit lines |

The owner authorized, for this sprint only: one exploratory implementation of Sprint 29's portfolio item H1 (T13-K1,
keep one eligible ground unit on an objective the side already holds); a short historical action-level preflight; its
registration and tests; and **at most four** new local engine sessions, 2798 to 2801, played one at a time with a stop
check after each. Session 2802 and Sprint 29's 20-session proposal are not authorized. The ceiling is not a requirement
to play four games. No retry or replacement game, no promotion, no platform upload, no change to the frozen
`baseline-v2`, the platform package or any historical conclusion. T13-K1 is a new increment; the closed T13-D1
(`docs/SPRINT25_T13_D1.md`) is neither modified nor reinterpreted.

## 2. Isolation from the platform compatibility work

Another session was working on platform compatibility at the start of this sprint. On the workstation the shared
checkout held its uncommitted changes to the package builder and its test; on the evaluation server it ran a replay
check from its own folder that imports the server checkout's source tree. Nothing of that work is touched, staged,
stashed, reset or merged here:

* the workstation work happens in a separate `git worktree` on the branch `sprint30-t13-k1`, created from the committed
  base `08aff3f` (its tree equal to the one above); the shared checkout and its changes are never written;
* on the evaluation server the branch reaches the repository by bundle into a separate worktree; the server checkout's
  branch, HEAD and files are never changed. That worktree reaches the persistent engine installation, the ledger and
  the private historical captures through links to the existing ignored folders, so there is still exactly one
  installation and one ledger;
* only the branch `sprint30-t13-k1` is pushed; `main` is not changed by this sprint;
* the canary package, its builder and the platform adapter are not modified.

Server CPU policy (`docs/SERVER_RESOURCE_POLICY.md`): the topology check matched the policy (2 sockets, 16 physical
cores each, SMT siblings `i` and `i + 32`, node 0 = CPUs 0-15 and 32-47); the colleague's job was pinned to node 1, so
the mode is shared and every job of this sprint runs pinned to node 0. Engine games run serially, one exclusive session
each; the preflight uses a pool of at most 8 worker processes on node 0.

## 3. The candidate: `t13-keep-one-k1`

Module `src/miaosuan_agent/experiments/t13_keep_one_k1.py` on the exploratory add-on
(`experiments/exploratory_addon.py`): frozen `baseline-v2` decides first on the seat's own current observation and
memory, unchanged; one rule then edits that decision.

* **Held objective and centre**: a `cities` entry of the seat's observation whose flag is the side's colour; its centre
  is its hex.
* **Occupants**: own ground units (type 1 or 2, artillery included) whose current hex is the centre.
* **Departing**: an occupant with a non-empty `move_path` (an accepted movement under way) or one for which
  `baseline-v2` emits a MOVE now. Every other occupant **remains**.
* **Trigger** (play stage, per held objective, in increasing centre order): at least one occupant, every occupant
  departs, and at least one departs by a `baseline-v2` MOVE. If an occupant remains, nothing changes. If every occupant
  departs under earlier movement only, the case is uncovered (a withheld order cannot cancel an accepted path) and
  nothing changes.
* **Eligible holder**, in order, the first failing level recorded: `A_stationary` (speed not positive), `B_no_route`
  (empty `move_path`), `C_no_transition` (the `stop` flag not 0; `move_to_stop_remain_time` and
  `change_state_remain_time` not positive), `D_no_transport_transition` (`get_on_remain_time`, `get_off_remain_time`
  not positive), `E_single_departing_move` (`baseline-v2` emits exactly one action for it, a MOVE with a non-empty
  route of integer hexes not ending on the centre). A to D are Sprint 28's idle levels of the same names, restated (a
  test compares the two). A missing field counts as the absence of a transition. Reading of the brief: "no pending
  movement or stop transition" is levels B to D, so a unit that has just arrived and is still in its stop transition
  is not an eligible holder.
* **Selection**: the eligible holder with the longest free-flow travel time of its `baseline-v2` MOVE (the sum over the
  route of `experiments.t9_batch.path_times`: per hex `720 / basic_speed * entry cost`, rounded per hex, in the unit's
  movement mode from its current hex); ties go to the lower unit id. A holder whose time is unreadable (unknown mode or
  speed, a route edge outside the cost graph) is not ranked; if none can be ranked the objective is skipped
  (`no_travel_time`) and nothing changes.
* **Edit**: that one MOVE is withheld. Nothing is added, replaced, reordered or constructed: no stop, no route change,
  no reassignment, no change to fire, occupation, embarkation or any other unit. One holder per objective at most;
  distinct centres hold distinct units, so edits never conflict.
* **Stateless**: no add-on memory; every decision is recomputed from the current observation, so a holder is released
  when the objective is no longer held, another occupant remains, the holder is gone, or it no longer qualifies.
  `baseline-v2`'s own memory is only its deployment flag, so a withheld MOVE cannot desynchronise it.
* **Failure**: an error inside the rule yields `baseline-v2`'s decision with the error recorded in the trace (the
  wrapper's fail-closed path); in the pilot any such error is an integrity stop, never a successful decision.

## 4. Historical feasibility preflight (frozen before it runs)

`scripts/s30_preflight.py` with the rules of `src/miaosuan_agent/evaluation/s30_preflight.py`; inputs pinned in
`evaluation/s30-t13-k1/preflight-inputs.json`. Offline, on the evaluation server.

* **Populations**, never pooled into one figure: **HH**, the `baseline-v2` seat of the four Sprint 12 head-to-head
  games in 2130511121 (two per colour; the opponent was the T9-v3 candidate); **HI**, the three Sprint 10 games of
  `baseline-v2` against the inert control (2120531121 C3, 1930331196 C3, 1930331196 C2); **H0**, the eight
  replay-corpus games, both seats, recorded `baseline-v0` actions with `baseline-v2` reconstructed. HH and HI are
  genuine `baseline-v2` trajectories; H0 is off-policy. Sprint 23's pinned job list, loader and `baseline-v2`
  reconstruction are reused unchanged.
* **Fidelity anchors**: H0 33,696 decisions, 33,680 play decisions, 123 decisions where reconstructed `baseline-v2`
  differs from the record; HH 11,524 and HI 8,643 decisions, every one equal to the recorded seat; 16, 4 and 3
  side-games.
* **Independent check**: at every decision a restatement of the rule written apart from the candidate's code (its own
  reading of the observation and its own free-flow sum over the cost graph) must explain every withheld action and find
  no missed trigger.
* **First divergence**: a side's first decision at which the candidate's list differs from `baseline-v2`'s. Valid in
  HH and HI; in H0 only when the recorded actions equal `baseline-v2`'s at every earlier decision of that seat.
  Withholdings after it lie on recorded states the candidate would not reach: post-divergence diagnostics only.
  **Verified opportunity**: a side-game with a valid first divergence and no independent-check finding.
* **Measured**: per held objective and play decision the rule's outcome; departure episodes (maximal runs of
  decisions at which every occupant of a held objective departs) by their first outcome; units already moving and
  stationary eligible units ordered at an episode's start; failing eligibility levels of ordered occupants; per side the
  first divergence (step, objective label, holder class, occupants, travel time, transit routes through the centre),
  whether an enemy had been seen before it, the first own shot, and historical onward labels (whether the holder was,
  on the record, the first owner of its MOVE's destination; whether the objective was later lost on the record).
* **Stop, first match**: `K1_PREFLIGHT_INVALID` (an anchor, an integrity check or the independent check fails);
  `K1_PREFLIGHT_INADEQUATE` (no verified opportunity among the two HH red side-games, or none among the two HH blue
  side-games, or fewer than two HI configurations with one): **no engine session is opened**; otherwise
  `K1_PREFLIGHT_PASS`.
* **Inert games of the pilot**: the first two of 2120531121 C3 (the configuration in which withholding moves already
  cost an objective: T9-v1 as blue against the inert control), 1930331196 C2 (another scenario, the other colour),
  1930331196 C3, in that order, that have a verified opportunity. All three are among Sprint 29's proposed harm
  configurations and they are the only ones with a genuine `baseline-v2` full-step record.

## 5. Historical controls

The same run reads the registered shoot-reservation experiment's group C records (frozen `baseline-v2`, 15 games per
configuration; each record pinned by SHA-256 in the inputs) for 2120531121 C3 (blue), 1930331196 C2 (red), 1930331196
C3 (blue) and 2130511121 C1 (both seats), and writes `evaluation/s30-t13-k1/controls.json`: for each the occupy,
attack, remain and total values and the margin (the seat's total minus the opponent's, checked against the engine's
own margin field), with minimum, maximum and mean. The pilot's thresholds (section 6) are read from that file, never
typed from memory.
