# Environment and compatibility findings (bootstrap audit, 2026-09-29)

Every finding carries an evidence tag:

- **[V]** verified by inspecting the supplied inputs (source read, archive listed, data parsed);
- **[L]** stated by the live documentation fetched on 2026-09-29 (see `PROVENANCE.md` section 6.2);
- **[I]** inference from the evidence, not verified;
- **[U]** unknown until the engine is executed.

This is the static audit written before anything from the SDK was executed. File paths such as
`ai/agent.py:334` name members of `land_wargame_sdk.zip` (digests in `PROVENANCE.md` section 3);
those members are not part of this repository.

## 1. Execution environment required by the engine

| Item | Finding | Tag |
|---|---|---|
| Engine build | Wheel tags `cp310-cp310-manylinux_2_17_x86_64` / `manylinux2014_x86_64`; 125 CPython-3.10 extension modules, no pure-Python fallback | [V] |
| Consequence | Runs only on x86-64 Linux (glibc 2.17 or newer) under CPython **3.10 exactly**; `Requires-Python: >=3.10` is looser than the ABI tag; later Python versions cannot load the modules | [V] |
| Native Windows | Not possible: no Windows build exists | [V] |
| Declared dependencies | `getmac`, `numpy`, `pandas`, all unpinned | [V] |
| Undeclared dependency | `pymysql` is imported by `env/common/mysql_op`, which `env/wgwriter/db_operator` uses; whether offline play reaches it is unknown | [V] / [U] |
| numpy ABI | No numpy C-API symbols (`_ARRAY_API`) in any extension module, so the modules use numpy at Python level only; numpy 2.x is not excluded by ABI, but behaviour under it is untested | [V] / [U] |
| Network use | No `http://`, `https://`, `socket`, `requests` or `urllib` strings in any extension module | [V] |
| Import side effect | `train_env/__init__.py` prints `SDK version: 4.1.0` on import | [V] |
| Official local environment | Ubuntu 20.04, Python 3.10 | [L] |
| Online runtime (upload) | CPU; `python==3.10`, `numpy==1.26.2`, `pandas==1.5.3`, `ray==2.9.0`, `scikit-learn==1.0.2`, `scipy==1.10.1`, `tensorflow==2.11.0`, `torch==2.0.1` | [L] |

An unpinned `pip install` of the wheel today would resolve numpy 2.x and pandas 2.x [I], which
differ from the online runtime; the local environment should pin the online versions.

## 2. Engine authentication mechanism (highest risk)

Static string inspection of `train_env/env/authenticate/authenticator.cpython-310-x86_64-linux-gnu.so`
[V] shows a class `Authenticator` with methods `run_authenticate_processes`, `pass_MAC_check`,
`pass_time_check_since_first_use`, `set_mac_time`, `get_mac_time`, `clean_time_stamp`,
`clea_mac_bound` and `start_self_destruction`, and references to `getmac` / `get_mac_address`,
`pathlib` / `Path` / `home`, `remove`, `time_ns`, `expire_flag_file`, `mac_time_file` and
`.engine_config`, with the messages `did pass authentication`, `did not pass authentication` and
`failed to initialize authenticator`. `env/train_env` imports `authenticate.authenticator` and
references `run_authenticate_processes` [V].

The FAQ [L] says that `did not pass authentication` means the SDK version is outdated, and that the
remedy is to reinstall the wheel and delete `~/.engin_config` (note: spelled differently from the
`.engine_config` string in the binary).

Reading [I]: the engine binds itself to a MAC address, limits use by time since first use, keeps
state in a file under the home directory, and on expiry may delete files. The wheel was built on
2024-03-01; the live documentation already describes SDK 5.0.0 or later. **There is a material risk
that engine 4.1.0 refuses to run today** [U], and what `start_self_destruction` removes is unknown
[U]. First execution must therefore happen in a disposable environment with an isolated `HOME`,
never against the only copy of anything; the hashed source archive is the backup. A newer SDK may
have to be obtained from `http://wargame.ia.ac.cn/aidevelopment` [L] (not attempted).

## 3. Demo runner versus supplied data

| # | Finding | Tag |
|---|---|---|
| 3.1 | `run_offline_games.py:45-51` and `:163-169` read `data/scenarios/333.json`, `data/maps/333/333_basic.json`, `data/maps/333/333_cost.pickle` and `data/maps/333/333_see.npz` | [V] |
| 3.2 | `Data.zip` provides `Data/scenarios/<id>.json` and `Data/maps/map_<id>/{basic.json, cost.pickle, <id>see.npz}`; neither scenario 333 nor map 333 exists, and the directory case differs (`data` against `Data`), which matters on Linux, the only supported platform | [V] |
| 3.3 | Hence the runner cannot run as shipped on any platform; the install page's claim that `python run_offline_games.py` completes within a minute after `unzip Data.zip` [L] cannot hold without editing the paths | [I] |
| 3.4 | Scenario files do not record their map. Keys are `scenario_id`, `operators`, `time`, `cities` and, in 27 of 50, `annual_version` | [V] |
| 3.5 | Reading the map id as the last two digits of the scenario id (the last four for 9601): 40 of 50 scenarios name a supplied map and all their operator and city hexes fall inside it; 10 name none (1231, 1531, 1631, 3231, 3531, 3631, 2201010101, 2201010105, 2201010109, 2201010110), so their map is not identifiable from the supplied data; maps 19, 43, 82, 83, 84, 86, 123, 212 and 221 are named by no scenario | [I] |
| 3.6 | `scenario_id` is an integer in 46 files and a string in the four `22010101xx` files | [V] |
| 3.7 | The live scenario page describes keys absent from every supplied scenario (`landmarks`, `blueprints`, `config`, `launch_sites`, `com_graph`); whether engine 4.1.0 accepts the older files is unknown | [L] / [U] |
| 3.8 | The bundled `docs/observation_example.json` matches scenario 3231: the same five city hexes, and its 22 operators plus 12 passengers carry exactly the 34 unit ids of red in that scenario. It is therefore red's view of 3231 at step 0 | [V] / [I] |
| 3.9 | Replays go to `logs/replays/replay_<epoch>.zip` (`run_offline_games.py:134-140`); the engine's `wgwriter/saver` module embeds a developer path `../../logs/replay/s12281011_3531_0.json` | [V] |

## 4. Map data

| # | Finding | Tag |
|---|---|---|
| 4.1 | Three `basic.json` cell schemas: long keys (`elev`, `cond`, `roads`, `rivers`, `neighbors`, `pos`) in 13 maps (map 9601 adds `minefield`, `roadblock`); short keys only (`c`, `e`, `nb`, `r`, plus `cd`, `rd`, `rv` on some cells) in map 212; both sets in maps 123 and 221 | [V] |
| 4.2 | `ai/map.py:73` reads `["neighbors"]` and `ai/agent.py:334` reads `["roads"]`, so the demo `Map` and agent raise `KeyError` on map 212 | [V] / [I] |
| 4.3 | `see.npz` always holds one array `data` of shape (modes, rows, cols, rows, cols); dtype is bool except map 92 (`int32`); 8 maps carry 10 line-of-sight modes, 8 maps (19, 43, 82, 83, 84, 86, 92, 9601) only 3 | [V] |
| 4.4 | The live map page defines 10 modes [L]; `Map.can_see` (`ai/map.py:94-99`) returns `False` for a mode beyond the array instead of raising, so air-mode queries on 3-mode maps silently report no line of sight | [V] |
| 4.5 | `cost.pickle`: all 16 files contain only primitive opcodes (no `GLOBAL`/`REDUCE`), checked with `pickletools` without loading; loading them executes no code | [V] |
| 4.6 | Map sizes range from 50x50 (map 212) to 100x100 (map 123); `max_row`/`max_column` exist only in maps 123, 212, 221 | [V] |

## 5. Demo agent, bundled documentation and live documentation disagree

| # | Finding | Tag |
|---|---|---|
| 5.1 | `ai/agent.py:119-132` requires `observation["role_and_grouping_info"]`, `observation["communication"]` and `observation["time"]["stage"]`; the bundled example observation has none of the three, and the bundled note documents neither `communication` nor `time.stage`. The live pages document all three (stage 1 = deployment, 2 = play) | [V] / [L] |
| 5.2 | In the example observation, `valid_actions` is keyed by strings (`"14231"` then `"1"`, `"6"`, ...) as JSON requires; the agent (`ai/agent.py:153-159`) looks these keys up in `controllable_ops` and compares them with the integer `ActionType` constants. The key types the engine delivers in memory decide whether the demo agent ever acts | [V] / [U] |
| 5.3 | `gen_change_altitude` (`ai/agent.py:431-440`) sends key `target_obj_id` holding the altitude; both the bundled and the live action docs require `target_altitude` | [V] |
| 5.4 | Seven generators (`gen_fork`, `gen_union`, `gen_change_altitude`, `gen_activate_radar`, `gen_enter_fort`, `gen_exit_fort`, `gen_lay_mine`) return nothing with probability p, the others act with probability p; with p = 1, `gen_activate_radar` and `gen_lay_mine` never act. `gen_lay_mine` also targets a random hex in 0-9177 regardless of the map | [V] |
| 5.5 | `reset()` (`ai/agent.py:108-115`) clears 7 attributes; the live DemoAI `reset()` clears 17, so the supplied version carries `my_mission` / `my_direction` over between games | [V] / [L] |
| 5.6 | `get_scenario_info` (`ai/agent.py:173-178`) reads `ai/scenario_<id>.json`, which is not shipped; its only call is commented out (line 36) | [V] |
| 5.7 | The single-agent runner registers seats 1 and 11 with `role` 1 (battalion) in `player_info` (`run_offline_games.py:57-70`) but gives the agents `role` 0 (`:95`, `:109`); the live example uses 0 in both places | [V] / [L] |
| 5.8 | The bundled action note has mission/direction commands 200/201, which the agent reads (`ai/agent.py:125-129`); the live action page lists 207-210 for issuing missions and 202 for deleting one, and does not list 200/201 | [V] / [L] |
| 5.9 | The live pages describe features absent from the supplied SDK: `see_data=None` accepted from SDK 5.0.0 on, `Map.get_grid_distance`, and many observation fields (`landmarks`, `scenario_id`, `terrain_id`, `owner`, `altitude`, fort state) | [L] |
| 5.10 | Unseeded randomness: the agent uses `random` throughout and `Map.gen_move_route` breaks ties with `random.random()` (`ai/map.py:163`, `:179`); the engine exposes `get_rng_state`/`set_rng_state` names, whose use is unverified | [V] / [U] |
| 5.11 | Minor bundled-doc inconsistencies: `move_state` 0-4 against `target_state` 0-5 (5 = 半速机动); `keep_remain_time` labelled as fatigue time (the live page: suppression time); `cities[].flag = -1` appears in the example but only 0/1 are documented | [V] |
| 5.12 | Engine strings reference `doc/state_data_note.json` (not shipped) and a legacy loader layout (`Data/scenario.xlsx`, `Data/map/`, `Data/cities/`) that is not shipped either | [V] |

Chronology from the ZIP timestamps [V]: `ai/` and `docs/` 2022-09-23; `Data.zip` 2022-10-10;
`run_offline_games.py` 2023-12-22; wheel 2024-03-01. The demo agent and its documentation predate
the engine by about 17 months. The live pages carry no dates but describe SDK 5.0.0 or later, a
newer engine than the supplied 4.1.0 [I].

## 6. Upload and online-play constraints [L]

- Submit a zip containing exactly one top-level folder `ai` whose `agent.py` defines class `Agent`
  (subclassing `BaseAgent` with `setup`, `step`, `reset`).
- The planned package name `miaosuan_agent` therefore cannot ship as a sibling top-level package; it
  must live inside `ai/` in the upload artifact, with imports that work from there.
- Online, the engine and the two agents run as three processes; the engine advances on an
  accelerated clock and does not wait for decisions (at 5x, one frame every 200 ms). A slow decision
  produces actions that may be judged stale and invalid, and the frames received meanwhile are
  dropped. Offline, the runner is lock-step, so offline timing does not predict online behaviour.
- Each user has three test slots and one official AI; the official AI is entered automatically in
  competitions its owner has registered for.
- Not stated on any page consulted: upload size limit, per-step time budget beyond the example,
  memory limit, GPU availability, network access, and which engine version the platform runs.
