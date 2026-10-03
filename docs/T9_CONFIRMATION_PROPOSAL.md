# Proposal: confirmatory study of T9 capacity-limited objective allocation

Status: PROPOSAL for the owner's approval (2026-10-03, UTC+8). Not a registration: nothing here is frozen, no game is
authorised, and the numbers below are planning figures to be fixed in the registration itself. The CONFIRMATORY
track's full process applies (`docs/EXPLORATORY_TRACK.md`): a frozen manifest with the analysis plan pushed before the
first game, a public registration, the owner's approval, an independent validation of the analysis, fresh games for
both arms. Sprint 8's exploratory games (`docs/SPRINT8_EXPLORATION.md`) motivated this proposal and are never pooled
into it.

## Candidate

`t9-capacity-allocation-v1` unchanged: `experiments/exploratory_addon.py` and `experiments/t9_allocation.py` on top of
the frozen `baseline-v2`, policy source digest as recorded in `evaluation/s8-t9-v1-rep/manifest.json`. Capacity 4 and
detour factor 2 stay as explored; any change would be a new candidate and would need its own exploration first.

## Hypothesis

Against `baseline-v2` and against the inert control, the candidate's terminal score margin is larger than
`baseline-v2`'s in the same scenario and seat.

## Proposed design

| Part | Configurations | Games per configuration and arm | Role |
|---|---|---|---|
| A, primary | 2130511121 head to head: candidate red against `baseline-v2` (H1) and candidate blue (H2); control: fresh `baseline-v2` C1 mirror games, which give both seats | 15 (H1, H2, C1) | primary endpoint |
| B | the three large scenarios (2120531121, 1930331196, 2130511121) against the inert control, C2 and C3, both arms | 15 | key secondary endpoint |
| C | 2120531121 and 1930331196 head to head, as in A | 15 | secondary, descriptive (see power) |
| D | the five small frozen scenarios against the inert control, C2 and C3, both arms | 3 | safety: no harm where the rule rarely binds |

About 375 games on `baseline-v1-runtime-r2` with the qualified scheduler; both arms in one interleaved schedule.

## Endpoints and decision rules (to be fixed at registration)

* Primary: in part A, the difference between the candidate's mean seat margin and `baseline-v2`'s mean seat margin,
  stratified by seat, with a 95% interval; CONFIRMED if its lower bound is above 0 and the safety criteria hold.
* Key secondary: in part B, the same difference per configuration; reported with intervals.
* Safety: no failed or capped candidate game, no contract error, no add-on error, no new refusal class; in part D the
  candidate's margin is not below `baseline-v2`'s by more than 10 points in any configuration.
* Mechanism (descriptive): re-assigned and withheld moves, waiting ground units, objectives held over time.

## Power (planning figures)

`baseline-v2`'s C1 margin in 2130511121 has a standard deviation of 110.8 over 15 games; the candidate's three
exploratory games per seat there had sample standard deviations of 156.6 (red) and 114.3 (blue). With 15 games per
seat and arm and a standard deviation near 111 in both arms, the standard error of one seat's difference is 40.5
points, so a true difference of about 113 points is detected with 80% power at the two-sided 5% level (the
seat-stratified average is at least as precise). The exploratory games placed the candidate on average 2.36 control
standard deviations, about 260 points, above the control mean, a figure that small samples tend to overstate. In
2120531121 and 1930331196 the C1 standard deviations are 566.7 and 437.9; 15 games per seat there detect only
differences of about 580 and 450 points, and detecting 260 points would need about 75 and 45 games per seat and arm,
so part C is descriptive unless the owner funds those sizes.

## Risks named in advance

* The withholding rule leaves units at their start for long stretches; against a stronger opponent than `baseline-v2`
  that could cost objectives. The study measures it; it does not test other opponents.
* The historical controls used in exploration came from games played before Sprint 8; the study uses fresh controls,
  so a drift of the engine or runtime would show as a difference from those historical figures, not as an effect.
* The platform engine is a newer SDK than the local 4.1.0; nothing here speaks to the platform.
