# Sprint 10: T9 failure diagnosis and same-route staging revision

Sprint 10 is exploratory. It neither changes Sprint 9's registered result nor authorizes promotion. The frozen
Sprint 9 disposition remains `PRIMARY_SUPPORTED_NEEDS_REVISION`: in `2130511121`, T9-v1's registered seat-averaged
improvement is +305.47 (95% interval 172.87 to 611.24). T9-v2 is not a new baseline.

## Evidence and sessions

Historical Phase B supplied 15 T9-v1 and 15 baseline-v2 games in each adverse configuration, but its captures did
not preserve a complete per-unit timeline. Six committed full-step diagnostic games filled that gap:

| Session | Game | Policy | Terminal observation |
|---:|---|---|---|
| 2773 | `2120531121.C3.s10-t9-v1-diagnosis.g01` | frozen T9-v1 | margin 519; 4 objectives; attack 108 |
| 2774 | `2120531121.C3.s10-t9-v1-diagnosis.g02` | frozen baseline-v2 | margin 579; 5 objectives; attack 98 |
| 2775 | `1930331196.C3.s10-t9-v1-diagnosis.g03` | frozen T9-v1 | margin 434; 5 objectives; attack 20 |
| 2776 | `1930331196.C3.s10-t9-v1-diagnosis.g04` | frozen baseline-v2 | margin 570; 5 objectives; attack 88 |
| 2777 | `1930331196.C2.s10-t9-v1-c2-diagnosis.g01` | frozen T9-v1 | margin 226; 5 objectives; attack 0 |
| 2778 | `1930331196.C2.s10-t9-v1-c2-diagnosis.g02` | frozen baseline-v2 | margin 274; 5 objectives; attack 24 |

All six completed at 2,881 decisions with exact live/reconstructed T9 consistency. Raw observations, unit ids and
paths remain only in ignored server `local/` captures. The public diagnosis is
`evaluation/s10-t9-v2-exploration/diagnosis.json`.

## Diagnosis gate

### `2120531121 C3`

At decision 1, after four baseline assignments reached the commitment cap, T9-v1 redirected four slow, distant
units to the later-missed 80-point objective. Those reservations persisted although the units finished several
hexes away. Starting at decision 442, nearby faster units were withheld because the objective already had four
commitments. T9-v1 never captured it; the independent baseline-v2 trajectory first did so at decision 564.

The defect is emission-order, far-future reservation: a destination slot expresses intent but not timely ability to
arrive. The baseline game shows a feasible allocation pattern, not the exact counterfactual score of the T9 game.

### `1930331196 C3`

At decision 1, twelve moves were redirected across objectives. Four later baseline firing periods (decisions 742,
804, 841 and 876) placed eight direct-fire actions on legal targets. Units in the independent T9-v1 trajectory were
on other corridors and lacked the corresponding legal fire actions; T9-v1 scored 20 attack points versus 88 for
baseline-v2. All five objectives were eventually captured, so the observed regression is tactical geometry rather
than terminal objective count. Separate trajectories prevent attribution of the full score difference to one move.

### `1930331196 C2`

At decision 1, seven moves were redirected. The later shooter was never itself changed by T9-v1, but the early
replacements changed objective capture order, so baseline-v2's dynamic nearest-unheld rule later routed that shooter
differently. At decision 611, the baseline trajectory had visibility and a legal shot that yielded 24 attack points;
the T9-v1 trajectory had neither. The fresh scores exactly reproduced the historical pattern, but remain independent
trajectories rather than a same-game counterfactual.

The three cases support one narrow correction: retain baseline-v2's objective and route, stage overflow units on a
non-objective prefix, and reconsider them later. This avoids cross-objective corridor changes. Objective and staging
endpoints each stay capped at four; a staged action passes the project gate, otherwise it is withheld.

## T9-v2 identity and offline evidence

The experimental identity is `t9-capacity-staging-v2`; its frozen policy-source SHA-256 is
`66a451d513d7ff5df2292238dbc4dd526d6b39c050991a25043546a0bce2bece`. The run card's canonical SHA-256 is
`ce0d806e798a61bd01ea315885f8a5ab031d569fbf83467998145905bc913450`.

Synthetic tests cover same-route prefixing, objective and staging capacity, progress before withholding, no
cross-objective redirection, every objective at capacity, planted gate rejection, non-play and unrelated actions,
unavailable/suppressed/transitioning/destroyed units, malformed observations, the seven-objective primary shape and
agent replay. One-step replay over all 2,881 decisions of each of three diagnostic captures found zero prefix
violations. Those replays compare actions on T9-v1 states; they do not simulate T9-v2 outcomes.

## Eight-game exploratory screen

The full aggregate is `evaluation/s10-t9-v2-exploration/results.json`. Historical means below are the frozen Sprint 9
populations, and comparisons are directional only.

| Session | Configuration | Margin | Attack / shots | Objectives | Stage / withhold | Longest hold | Queue max | p99 ms |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 2779 | 212 C3, game 1 | 423 | 60 / 10 | 4/5 | 18 / 28,988 | 2,459 | 1 | 1.631 |
| 2780 | 212 C3, game 2 | 403 | 50 / 13 | 4/5 | 18 / 28,988 | 2,459 | 1 | 1.648 |
| 2781 | 193 C3, game 1 | 570 | 88 / 14 | 5/5 | 26 / 16,646 | 1,585 | 2 | 1.593 |
| 2782 | 193 C3, game 2 | 570 | 88 / 8 | 5/5 | 26 / 16,650 | 1,585 | 2 | 1.558 |
| 2783 | 193 C2, game 1 | 274 | 24 / 3 | 5/5 | 26 / 209 | 61 | 5 | 1.130 |
| 2784 | 193 C2, game 2 | 274 | 24 / 3 | 5/5 | 26 / 209 | 61 | 5 | 1.137 |
| 2785 | 213 H1, T9-v2 red | -729 | 322 / 65 | 1/7 | 31 / 1,126 | 123 | 1 | 1.924 |
| 2786 | 213 H2, T9-v2 blue | 815 | 486 / 105 | 7/7 | 68 / 288 | 39 | 6 | 2.193 |

T9-v2 restored both `1930331196` adverse configurations: C3's two margins were 570, compared with Sprint 9 means
457.47 for T9-v1 and 568.67 for baseline-v2; C2's were 274, compared with 226 and 272.93. The historical C2
studentized interval still has its registered infinite upper bound; no value is rewritten or replaced here.

It failed `2120531121 C3`: mean margin 413 versus 519 for T9-v1 and 587.67 for baseline-v2, and the same fifth
objective remained neutral. Same-route staging removed cross-objective errors but did not fix emission-order
reservation. Four distant first claimants can still reserve the destination, after which staged overflow units reach
the corridor's end and have no legal prefix left; withholding then persists. Queue counts stay small because a
withheld unit has no active path, so queue count alone does not measure this failure.

The primary smoke also lost most of T9-v1's registered advantage. The two-game seat average was +43 relative to the
mirror, versus T9-v1's registered +305.47. H1 was above its baseline mean but below the T9-v1 mean; H2 was below both
means. This is only one trajectory per seat, but it is not evidence for a confirmation proposal.

One code `516` refusal occurred in session 2781: the target was already dead when the shot resolved
(`CantShootToDiedBop`). It is an understood tactical race, not a project-gate or systemic failure. Across all eight
games there were no contract errors, project-gate rejections, add-on errors, replay mismatches or observer errors;
candidate objective commitment never exceeded four. All sessions closed with unchanged engine state and home and
package integrity true.

## Disposition

`PARTIAL_REPAIR_NOT_READY_FOR_CONFIRMATION`. Same-route staging repairs the two firing regressions but worsens the
missed-objective configuration and directionally erodes the primary benefit. T9-v1 and baseline-v2 remain frozen;
nothing is promoted.

Exactly 14 Sprint 10 sessions were opened after 2772: six diagnostic and eight T9-v2 exploratory sessions. All are
closed and contiguous through 2786.
