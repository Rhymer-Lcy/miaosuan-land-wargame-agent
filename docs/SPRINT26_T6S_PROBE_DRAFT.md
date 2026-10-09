# DRAFT: T6-S two-session mechanism probe (for the owner's review)

**DRAFT — UNAPPROVED — NOT REGISTERED — NOT EXECUTED — NO ENGINE SESSION AUTHORIZED — NO RUN CARD — NOTHING PROMOTED**

This draft follows Sprint 26's registered offline disposition `T6_S_OFFLINE_PASS` (`docs/SPRINT26_T6S_SHADOW.md`,
R10). It is returned to the owner. No executable candidate, run card or capture configuration exists for it; session
2797 is not opened. If the owner approves, a separate registration (code, tests, mutation, card and protocol, committed
and pushed before any session) would implement it. Dates are business dates in UTC+8.

## 1. Questions (mechanism only)

On the candidate's own on-policy trajectory, in head-to-head play against frozen `baseline-v2`:

1. Does the stagger fire where the offline study says it would, and does it withhold only the registered follower MOVEs?
2. How long do followers actually wait, and do leader and followers then move apart, or close up again?
3. Do stacked moving unit-steps inside applicable envelopes fall for the candidate's seat?
4. What does a wait cost in onward capture: are objectives first owned later, and are waiting followers hit or lost?

It does not ask whether the candidate scores better; score is not an endpoint and cannot rescue a stop.

## 2. Design

| Item | Proposal |
|---|---|
| Scenario | 2130511121 (the HH scenario; Sprint 24's registered probe scenario) |
| Sessions | exactly two, 2797 and 2798; no retry, no replacement |
| Session A | candidate blue, `baseline-v2` red |
| Session B | candidate red, `baseline-v2` blue |
| Candidate | `baseline-v2` with the T6-S rule as an add-on: the frozen rule of `experiments/t6s_stagger_shadow.py` at Sprint 26's registration (`20453dc`), made executable under a new identity (proposed `t6s-column-stagger-p1`), its memory the rule's episode state, nothing else changed |
| Opponent | frozen `baseline-v2` |
| Runtime | the registered runtime of the recent probes (one game per exclusive session, serial) |
| Capture | full-step timelines of both seats (Sprint 12/16/22 capture family): every observation, the candidate's submitted list, `baseline-v2`'s list reconstructed on the candidate's own observation, the rule's events |
| References | the four Sprint 12 head-to-head games (HH), `baseline-v2` seats, same colour where an endpoint compares a seat; descriptive only, since HH's opponent was a different candidate |

## 3. Integrity (structural stops, any one ends the probe's interpretation)

* Before the candidate's first episode, its list equals `baseline-v2`'s at every decision (live and offline).
* At every decision, every difference between the candidate's list and `baseline-v2`'s reconstructed list is a
  registered withholding (Sprint 26's independent check, applied to the candidate's own trajectory); zero unexplained
  differences.
* The candidate issues no stop, constructs no MOVE and changes no route, target or non-MOVE action.
* Engine, ledger and capture integrity as in earlier probes (sessions 2797 and 2798 opened and closed, no other session).

## 4. Endpoints (denominators fixed in the registration)

| Id | Endpoint | Unit |
|---|---|---|
| E1 | episodes executed, their decisions, group sizes and classes; first episode against the offline prediction (the first divergence at step 161 for the blue seat and 401 for the red seat, if the prefix is identical) | episodes per seat |
| E2 | actual wait of each follower (start to release) and its departure from the start hex, against the projected wait; releases by reason (reference left, reference absent, timeout) | followers |
| E3 | leader/follower separation: whether members are co-located while moving on a hex other than the start hex within 300 steps, and for how many decisions | episodes |
| E4 | stacked moving own ground unit-steps inside applicable envelopes, the candidate's seat, whole game; the same in the HH games of that colour | unit-steps per seat-game |
| E5 | damage events on episode members within 300 steps of the start, by the member's state at the event (waiting on the start hex, moving stacked, moving alone) | events, members |
| E6 | followers destroyed while waiting | followers |
| E7 | first-ownership step of every objective for the candidate's seat, against the HH games; for each episode whose follower's destination is first owned, whether the ownership came before the follower arrived | objectives, episodes |
| E8 | unexplained non-T6 differences (must be zero, section 3) | decisions |

## 5. Probe stops (Sprint 24's registered stops for this step, preserved)

Sprint 24 registered the probe's stops as: "stacked moving unit-steps inside envelopes not halved against HH, or any
objective first owned later than in all four HH games". Proposed exact reading for the registration:

* **P1, exposure not halved**: met when, for either session, E4 for the candidate's seat is more than one half of the
  mean of E4 over the HH games of the same colour.
* **P2, onward capture delayed**: met when any objective is first owned by the candidate's seat later than in all four
  HH games (or never, where an HH game owned it).

**Decision needed from the owner**: Sprint 24's P2 compares with all four HH games, which mixes seat colours whose
distances to each objective differ; the registration should either keep "all four" (Sprint 24 verbatim) or compare
with the two HH games of the same colour. The draft does not choose.

Disposition (proposed, first match): `T6S_P1_INVALID` (any structural stop); `T6S_P1_MECHANISM_NOT_SUPPORTED` (P1 or
P2 met); `T6S_P1_MECHANISM_SUPPORTED` (otherwise). A supported mechanism would not establish improved survival or
score; it would allow the owner to consider a separately registered screen.

## 6. Known risks, from the offline study

* Every valid first divergence of the HH games withholds a follower that was a historical first owner of its
  destination, with another own unit a co-owner (Sprint 26, R11, post hoc). E7 measures whether the 20-step wait delays
  that ownership.
* A waiting follower stays stacked and exposed on its start hex; E5 and E6 measure it.
* A faster follower can close up after release; E3 measures it.
* One scenario, one opponent policy, two games: a mechanism observation, not a performance estimate.

## 7. Engineering before any session (not done)

An executable add-on module under the new identity (the frozen rule's semantics, unchanged), a card builder and the
owner-approved whitelist entries, the runner reusing the existing head-to-head capture, the analysis of E1 to E8 and the
stops, synthetic and stand-in tests, a mutation record, a rehearsal on the HH captures (the candidate replayed on
`baseline-v2`'s recorded states must reproduce Sprint 26's first divergences), and the registration pushed before the
first session.

## 8. What the owner is asked to decide

1. Approve or decline this probe (two sessions, 2797 and 2798).
2. If approved: the P2 comparison set (section 5) and the candidate identity.

Nothing is executed until both are decided and the registration is pushed.
