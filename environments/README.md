# Environments

## Two environments, never merged

| Environment | Purpose | Contents | Status |
|---|---|---|---|
| `miaosuan-runtime` | Platform compatibility: engine smoke tests, SDK contract tests, inference validation, and the basis for upload packaging | CPython 3.10, CPU only, the platform's documented package versions, nothing else | defined here |
| `miaosuan-research` | Training, reinforcement learning, self-play, GPU work | free to add PyTorch, CUDA and RL tooling | not created yet |

This separation is an invariant. Research dependencies never enter `miaosuan-runtime`, and upload
packaging is validated only against `miaosuan-runtime`, because that is the environment the
platform runs submitted agents in.

## `miaosuan-runtime`

The platform documents the online runtime for uploaded agents as CPU-only with:

| Package | Documented | In `miaosuan-runtime` |
|---|---|---|
| python | 3.10 | 3.10.20 |
| numpy | 1.26.2 | 1.26.2 |
| pandas | 1.5.3 | 1.5.3 |
| scipy | 1.10.1 | not installed |
| scikit-learn | 1.0.2 | not installed |
| ray | 2.9.0 | not installed |
| tensorflow | 2.11.0 | not installed |
| torch | 2.0.1 | not installed |

Source: `https://wargame.ia.ac.cn/docs/tutorials/upload/`, read on 2026-09-29 (unchanged between
two reads that day). The environment holds only what the engine and the current code need.
scipy and scikit-learn are to be added at the documented versions when agent code first uses them;
ray, tensorflow and torch belong to research work and are excluded. `getmac` (0.9.5) is not on the
platform list: it is a dependency the engine wheel declares without a version.

The SDK engine wheel itself is **not** installed into the environment. The smoke-test harness
installs it with `pip --target` into a disposable run directory under `local/runtime/` (see the
top-level README and `docs/ENGINE_SMOKE_TEST.md`).

### Files

| File | Content |
|---|---|
| `miaosuan-runtime.conda-explicit.txt` | exact conda packages (32, all from the `pkgs/main` channel), for `conda create --file` |
| `miaosuan-runtime.requirements.txt` | exact pip packages with SHA-256 hashes of the Linux x86-64 wheels |

### Reproducing it (Linux x86-64)

```
conda create -n miaosuan-runtime --file environments/miaosuan-runtime.conda-explicit.txt
PYTHONNOUSERSITE=1 conda run -n miaosuan-runtime python -m pip install \
    --require-hashes -r environments/miaosuan-runtime.requirements.txt
PYTHONNOUSERSITE=1 conda run -n miaosuan-runtime python -m pip check
```

On a host without direct internet access, download the wheels elsewhere with
`pip download --only-binary=:all: --platform manylinux2014_x86_64 --python-version 3.10
--implementation cp --abi cp310 -r environments/miaosuan-runtime.requirements.txt -d <dir>`,
copy them over, and add `--no-index --find-links <dir>` to the install command; the hashes make
the result identical. `PYTHONNOUSERSITE=1` keeps packages from the user's `~/.local` site
directory out of the environment, which matters on shared accounts.
