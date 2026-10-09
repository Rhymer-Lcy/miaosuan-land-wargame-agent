# Platform canary: manual upload and compatibility check

Instructions for the owner. The upload is a manual step on the platform; nothing in this repository uploads
anything, and no platform test has taken place until the owner reports one. Platform observations are recorded apart
from local-engine evidence (`docs/TACTICAL_FRONTIER.md`, "Platform canary and feedback loop").

## 1. The file

| Field | Value |
|---|---|
| File | `dist/miaosuan-baseline-v2-canary.zip` (git-ignored; rebuild with `python scripts/build_platform_package.py`) |
| Size | 107,646 bytes |
| SHA-256 | `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511` |
| Policy | `baseline-v2`, policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae` |
| Contents | one top-level `ai` package with `agent.py` defining `Agent`, the frozen policy vendored byte for byte, standard library only |

Re-verified 2026-10-09 (Sprint 29, `docs/SPRINT29_PLATFORM_FIRST.md`, section 2): rebuilt byte-identically on the
workstation and on the evaluation server, the isolated smoke and the replay corpus without a mismatch under CPython
3.10.20, and an independent verifier passed.

Check the digest before uploading (PowerShell: `Get-FileHash dist\miaosuan-baseline-v2-canary.zip`; Linux:
`sha256sum dist/miaosuan-baseline-v2-canary.zip`). If it differs, do not upload; rebuild and compare again.

## 2. Upload

1. Sign in at the platform's AI test page (user centre, AI test).
2. Upload the zip to one of the three test slots ("AI代码"). Do not upload it to the official ("正式") slot: that slot
   is entered automatically into any competition the account has registered for.
3. Keep the zip unchanged. A file renamed on upload is fine; a re-zipped or edited copy is no longer the canary.

## 3. Compatibility check (what to run)

Run whatever the test slot offers, in this order, and note each outcome:

1. A machine test (机机测试) on a small scenario if one is offered, then on a large one (more than 40 units per side);
   the agent's per-step work grows with the force size.
2. A human-machine test (人机测试) of a few minutes is enough to see whether the agent deploys, moves and fires.

Signs of an environment problem (record them as compatibility, not tactics): the slot reports an import or start-up
error; the agent never ends its deployment; its units never move; the log shows exceptions or timeouts, or lines
beginning `[baseline-v2] contract error:` or `[baseline-v2] step error:`. Units that fire and occupy but never leave
their start hexes point to movement-cost data missing from the setup information, which the package does not report
(`docs/SPRINT29_PLATFORM_FIRST.md`, section 2.1, U2). The online
engine advances on its own clock and does not wait for the agent; slow decisions arrive late and are judged invalid,
and intermediate states can be skipped. Locally the slowest `baseline-v2` decisions exceed 1 s only in the largest
scenario (`docs/LATENCY_DIAGNOSTIC.md`).

## 4. What to send back

For each platform game: the date, the scenario name or id, the opponent (machine, human, which AI), the side played,
the result and final score if shown, and the downloadable log and replay ("日志及复盘下载"). The full intake record is
section 4 of `docs/SPRINT29_PLATFORM_FIRST.md`. Screenshots of errors
help. Replays and logs stay private (`local/`, never committed); only the classification below is published.

## 5. How the feedback is used

Each meaningful loss gets one failure-ledger entry in `docs/TACTICAL_FRONTIER.md`: deployment, reconnaissance,
movement, fire allocation, indirect fire, transport, objective timing, survival, special equipment, or unknown.
Repeated patterns become exploratory candidates (`docs/EXPLORATORY_TRACK.md`); nothing is patched silently after a
loss, and a platform result is kept apart as environment compatibility, tactical result and opponent-specific result.
One human win confirms nothing.
