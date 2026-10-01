"""The registered execution settings of an evaluation: worker count, runtime identity, numerical-thread environment.

A manifest may register an ``execution`` block: ``{"workers": N, "runtime": "<runtime identity>",
"scheduler": "<scheduler identity>"}``. A missing field means what every registration before it ran with: one
worker (the serial loop of ``scripts/run_evaluation.sh``) on ``baseline-v1-runtime-r1``, whose game processes set
no numerical-thread variable. ``baseline-v1-runtime-r2`` is the same code with ``OPENBLAS_NUM_THREADS=1``
(``docs/BASELINE_V1_RUNTIME_R2.md``). The table below is the only place a runtime's environment is defined: the
serial loop and the parallel pool both take the variables from it, never from the caller's environment, and a
game refuses to play when its effective numerical-thread variables differ from its runtime's.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

DEFAULT_RUNTIME = "baseline-v1-runtime-r1"
RUNTIMES: Dict[str, Dict[str, str]] = {
    "baseline-v1-runtime-r1": {},
    "baseline-v1-runtime-r2": {"OPENBLAS_NUM_THREADS": "1"},
}
#: Every numerical-thread variable a game process is checked for (the libraries that read them need not exist).
THREAD_VARIABLES = ("OPENBLAS_NUM_THREADS", "GOTO_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
                    "NUMEXPR_NUM_THREADS")


def runtime_env(runtime: str) -> Dict[str, str]:
    if runtime not in RUNTIMES:
        raise ValueError(f"unknown runtime {runtime!r}; known: {sorted(RUNTIMES)}")
    return dict(RUNTIMES[runtime])


def registered(manifest: Mapping[str, Any]) -> Dict[str, Any]:
    """The manifest's execution settings with their defaults."""
    execution = manifest.get("execution", {})
    runtime = execution.get("runtime", DEFAULT_RUNTIME)
    return {"workers": int(execution.get("workers", 1)), "runtime": runtime, "thread_env": runtime_env(runtime),
            "scheduler": execution.get("scheduler")}


def effective_thread_env(environ: Mapping[str, str]) -> Dict[str, str]:
    return {name: environ[name] for name in THREAD_VARIABLES if name in environ}


def check_thread_env(environ: Mapping[str, str], runtime: str) -> Optional[str]:
    """Why ``environ`` does not carry exactly ``runtime``'s numerical-thread variables, or None."""
    effective, expected = effective_thread_env(environ), runtime_env(runtime)
    if effective != expected:
        return f"numerical-thread environment {effective} differs from {runtime}'s {expected}"
    return None
