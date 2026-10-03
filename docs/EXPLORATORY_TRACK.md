# Exploratory track

From Sprint 8 (2026-10-03, UTC+8) the project runs two research tracks side by side.

| Track | Purpose | What it needs before the first game | What it can conclude |
|---|---|---|---|
| `EXPLORATORY` | build tactics, run them, learn from failures, find candidates worth confirming | a versioned run card committed (and pushed) before the first game of each batch | directional, game-level findings; mechanism facts; which candidate deserves a confirmatory study |
| `CONFIRMATORY` | establish a performance claim or a baseline promotion | the full registration of the earlier sprints: frozen manifest, statistical analysis plan, public registration, owner approval, independent validation | a confirmed improvement, or its absence |

An exploratory result is never reported as a confirmed improvement, never promotes a baseline and is never turned
into a retrospective confirmation. A candidate selected from exploration enters the confirmatory track as a new,
separately registered study with fresh games.

## Run cards

A run card is `evaluation/<card>/manifest.json`, built by `scripts/build_run_card.py --card <card>` from a definition
in that script and the committed inputs, and checked byte for byte (`--check`) before its games run. It holds:

* the candidate's identity: its policy source digest over `baseline-v2`'s frozen sources plus the candidate's modules
  (`baseline-v2`'s own digest must be the frozen `7cbaf032...`);
* the specific tactical mechanism, the controls, every game's configuration (scenario, condition, red and blue
  policies), the batch's session budget and the sprint's ledger-counted session cap;
* the essential safety checks, the intended observations and the rule for the next step;
* `track: EXPLORATORY`, `eligible_for_promotion: false`.

It deliberately holds no statistical analysis plan, no public issue and no per-game owner approval. A card is never
edited after its batch has started; a corrected or improved candidate is a new module under a new identity with a
new card, and the old card, its games and its results stay as they are (failed experiments are kept).

## Engine safeguards (unchanged)

`scripts/run_explore.sh --python PYTHON --sdk-archive ZIP --card <card>` plays a card's games, serially, one
exclusive session each (`scripts/run_explore_game.py` plays one game). The registered evaluator,
`scripts/run_evaluation.py` and `scripts/run_evaluation.sh`, is not changed: earlier registrations pin its digests. The
exploratory runner reuses its helpers by import and its game loop unchanged, with the same process isolation:

* every game uses the persistent installation, the session ledger and its integrity checks (`docs/ENGINE_INSTALL.md`);
  nothing in the track can reset, reinstall, restore or modify the engine or its state file;
* the tree must be clean and committed; the card must rebuild byte-identically; every policy's source digest is
  checked before the first game, by every game and after the last game;
* the batch, and each game, is refused when the sessions opened after the sprint's base session plus the planned
  ones would exceed the sprint's cap (Sprint 8: 24 sessions after session 2464);
* records and captures are never overwritten, and no game is retried or replaced;
* the sessions are recorded in the ledger as diagnostic sessions, and each game's harness block names the track and
  the card.

Candidates are built on `experiments/exploratory_addon.py`: the frozen `baseline-v2` decides first, unchanged, and
one add-on rule edits that decision, checking every action it adds or replaces itself and failing closed to
`baseline-v2` on any error. Each decision's trace carries the digest of `baseline-v2`'s own trace for that decision.
Nothing exploratory is packaged for the platform.

## Evidence and reporting

`scripts/explore_report.py --card <card>` reports each game: completion, terminal scores and the candidate's margin,
its placement against the historical `baseline-v2` control (the registered shoot-reservation experiment's own games
of the same scenario and seat against the same kind of opponent, 15 per configuration), the candidate seat's actions,
engine refusals, contract errors, gate rejections and decision latency, and the mechanism facts of the read-only
capture (`evaluation.exploratory.ExploreCapture`). With `--public` it writes aggregates only to
`evaluation/<card>/results.json`.

Small exploratory samples are directional. Against an active opponent `baseline-v2`'s own margins vary by several
hundred points between games, so one game there is a diagnostic, not a comparison; against the inert control they
are close to constant, so a game there places a candidate sharply against the control.

## Stopping

Stop immediately on an engine-integrity failure, a ledger inconsistency, a privacy exposure or an unexplained
systemic contract failure. Ordinary tactical losses, ineffective ideas and understood action refusals are exploratory
findings. When the session cap is reached the sprint stops and reports; no sessions are requested to finish a
planned sequence.
