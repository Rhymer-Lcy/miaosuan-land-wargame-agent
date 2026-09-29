# Provenance

Dates are business dates in UTC+8. ZIP member timestamps are reproduced as recorded; the ZIP
format stores no time zone for them.

## 1. Policy

The community SDK and the platform documentation carry no license that authorizes redistribution
(section 4). This repository therefore contains **no SDK source, binaries, data or documentation
snapshots**, verbatim or modified. It records only facts about them: file names, sizes, SHA-256
digests, structure and observed interfaces. Anyone with a legitimately obtained copy of the SDK can
check it against these digests; see section 5.

## 2. Supplied inputs

Obtained 2026-09-29.

| Input | Bytes | SHA-256 |
|---|---:|---|
| `land_wargame_sdk.zip` (community SDK) | 169,108,968 | `ed4c9fc03cb6eb1e64821d2efbc61024d90735e3dc489dc7ffe0515e653ea725` |

A saved copy of the documentation's welcome page was supplied with it: an HTML file and a folder of
7 assets. It was removed from the local archive on 2026-09-30, because its whole visible content (a
heading and two paragraphs) is contained verbatim in the welcome page of the complete live snapshot
kept since 2026-09-29 (section 6.2). Its digests are kept for the record:

| Retired input (was under `docs-saved-page/`) | Bytes | SHA-256 |
|---|---:|---|
| `庙算·陆战指挥官 平台文档.html` | 22,591 | `e9fba6373d68db33f22a929764a7ef4b91e185b1e2537cc3c4767694a7f0f32a` |
| `庙算·陆战指挥官 平台文档_files/bundle.a7c05c9e.min.js.下载` | - | `87420f873fa72d4947835c0f326fdc1bcbd2dea40a23049d524544c476fda7e3` |
| `庙算·陆战指挥官 平台文档_files/css` | - | `831d1cfa48507eb5cbc28b203bb587ae6af87d6c8dbf9f356d39f00b52fb015f` |
| `庙算·陆战指挥官 平台文档_files/extra.css` | - | `290ede793e27415db9798d684b114090a06726a7944b9df619b200faed90af9f` |
| `庙算·陆战指挥官 平台文档_files/main.66ac8b77.min.css` | - | `66ac8b7785c87019ca75bbf91927b3a3cd6691a7e52811a3b60fab4b5a91ef05` |
| `庙算·陆战指挥官 平台文档_files/miaosuan_logo_no_words.png` | - | `3485640b85ccf85fbcca029001abe6c3491ed86de33c5d194fe23757eef6cd50` |
| `庙算·陆战指挥官 平台文档_files/miaosuan_logo_words.png` | - | `b5003ac372cfcab541c617c12a9c6a98ed473ff73325e8b65b8f6bb1135136bf` |
| `庙算·陆战指挥官 平台文档_files/palette.06af60db.min.css` | - | `06af60dbce60d47a167fcab982f7cfa8d2d654a2f2a13d68e5a5fe5ae66df6c0` |

Nested archives inside the SDK ZIP:

| Member | Bytes | SHA-256 |
|---|---:|---|
| `Data.zip` | 144,533,193 | `0d6130e457faf8a96b495792843023245ae1b204fec140c7b954b2a99d51435e` |
| `land_wargame_train_env-4.1.0-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl` | 24,705,556 | `b74f8d273e93942a7bf61894a84a658f7fdd9fbefb581634bac70b3864e069c6` |

## 3. Structure of the SDK archive

The archive has 25 entries: 22 files and 3 directory entries, and no archive comment.

| Member | Bytes | ZIP timestamp | SHA-256 |
|---|---:|---|---|
| `ai/__init__.py` | 24 | 2022-09-23 09:42:20 | `3febf1777f68550ff6b9e3306e4a78055af83a88b9cf96b69e83dd97da688529` |
| `ai/agent.py` | 18,236 | 2022-09-23 09:42:20 | `7d4213758d28b0f2bd3b6e5835d077b108730f5ef02e0d73703cb17e82d596ad` |
| `ai/base_agent.py` | 314 | 2022-09-23 09:42:20 | `6a14d8a1052623d9d6572908e44ec4c94977a93f0d27958451b0b7cbfb802547` |
| `ai/map.py` | 6,718 | 2022-09-23 09:42:20 | `ead67e165e20fe19e6e6926f981e926d327d9e022106043dec5242b2af03a630` |
| `ai/__pycache__/*.pyc` (12 files) | - | 2022-09-23 09:42:20 | - |
| `docs/action_note.json` | 7,062 | 2022-09-23 09:42:20 | `186080de8a11df79c0d04ecf44c4c02cc69475352058e2020b84bce551426b52` |
| `docs/observation_example.json` | 76,219 | 2022-09-23 09:42:20 | `ce2b9ddae6f7fa069f3d36235f08f789e080f1992ee9aa26b14e437767d6cffc` |
| `docs/observation_note.json` | 8,312 | 2022-09-23 09:42:20 | `6147b2a1d90dd7c0abf671bc0d27dc741e3bca9b6a10648cfb2a7e9ac7fc66c2` |
| `run_offline_games.py` | 8,798 | 2023-12-22 17:08:34 | `ed212a471cd214249cf00f1efc6da45afe5f0f7c434c4f33241150c6da1a0384` |
| `Data.zip` | 144,533,193 | 2022-10-10 14:46:30 | see section 2 |
| `land_wargame_train_env-4.1.0-...whl` | 24,705,556 | 2024-03-01 12:46:52 | see section 2 |

- **`Data.zip`** (stored without compression) holds 98 files: `Data/maps/map_<id>/basic.json`,
  `cost.pickle` and `<id>see.npz` for 16 map ids (19, 21, 29, 43, 53, 82, 83, 84, 86, 92, 94, 96,
  123, 212, 221, 9601), and `Data/scenarios/<id>.json` for 50 scenarios.
- **The wheel** holds 150 files: 125 Cython extension modules
  (`*.cpython-310-x86_64-linux-gnu.so`), one Python file (`train_env/__init__.py`), 19 weapon
  tables under `train_env/Data/weapons/`, an empty `train_env/env/authenticate/.engine_config`, and
  4 dist-info files. All 149 hashed `RECORD` entries match their contents; the 150th entry is
  `RECORD` itself, which is unhashed by design.
- **The 12 `.pyc` files** cover CPython 3.7, 3.8 and 3.9 for each of the 4 `ai/` modules. Their
  headers record the size of the source they were compiled from: the 3.7 files match the shipped
  sources, while the 3.8 and 3.9 files come from earlier, different sources (for example
  `agent.py` at 17,294 and 17,290 bytes against 18,236 shipped).
- The Python members are pure ASCII with LF line endings; the JSON members are UTF-8 with LF line
  endings. `ai/__init__.py` and the three JSON files end without a final newline.

## 4. Licensing

No license terms were found:

- no file named like LICENSE, COPYING, NOTICE, README, AUTHORS or COPYRIGHT exists anywhere in the
  archive, `Data.zip` or the wheel;
- the wheel `METADATA` has no `License` field and no license classifier; its author address is at
  `ia.ac.cn` (Institute of Automation, Chinese Academy of Sciences);
- the module docstring of `ai/map.py` says the module is released "under open source license"
  without naming a license;
- none of the 22 documentation pages consulted (section 6) states terms of use; the About page
  gives only the laboratory's public contact details.

Consequently this repository redistributes none of that material. This repository's own license is
a separate decision that has not been made; no license file is present.

## 5. Local source archives

Machines that hold the SDK keep it outside version control, under the git-ignored `local/` tree:

```
local/source-archives/
  land_wargame_sdk.zip
  docs-live-snapshot-20260929/             (raw HTML and text of the pages in section 6.2)
  SHA256SUMS
```

`python scripts/verify_source_archives.py` checks the SDK archive, its nested archives and its text
members against the digests above and reports absent files as skipped. `SHA256SUMS` lists the
digest of every file in this directory, the live snapshot included; `sha256sum -c SHA256SUMS`
checks them all.

## 6. Documentation sources

### 6.1 Supplied saved page (retired)

The saved HTML was the **welcome page only** of an MkDocs site (generator `mkdocs-1.6.0,
mkdocs-material-9.5.21`) saved from `https://wargame.ia.ac.cn/docs/`. Its content was a heading and
two paragraphs describing the platform. Its navigation linked 21 further pages, none of which was
saved with it; all of them were fetched later (section 6.2), and the saved page was removed from the
local archive on 2026-09-30 (section 2):

| Section | Pages (path under `https://wargame.ia.ac.cn/docs/`) |
|---|---|
| 教程 | `tutorials/basic/`, `tutorials/replay_system/`, `tutorials/upload/`, `tutorials/shortcuts/`, `tutorials/videos/` |
| AI开发 | `reference/`, `reference/install/`, `reference/usage/`, `reference/apis/`, `reference/observations/`, `reference/actions/`, `reference/map/`, `reference/scenario/`, `reference/weapons/` |
| 规则 | `rules/elements/`, `rules/process/`, `rules/rules/`, `rules/tables/`, `rules/others/` |
| Other | `faq/`, `about/` |

### 6.2 Live documentation consulted

The welcome page and all 21 linked pages were fetched read-only, without authentication, with
HTTP 200 for each, between 2026-09-29T18:41:02+08:00 and 2026-09-29T18:41:39+08:00. They are kept
only in the local archive (section 5) and are not redistributed.

Findings drawn from these pages are marked **[L]** in `docs/COMPATIBILITY.md`. The live site
describes SDK 5.0.0 or later while the supplied engine is 4.1.0, so live statements are evidence
about the platform, not about the supplied SDK.
