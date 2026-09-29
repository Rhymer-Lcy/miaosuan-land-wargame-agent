"""The controllable randomness of an evaluation process, and a probe of what the engine consumes.

The documented engine interface (``TrainEnv.setup``, ``step``, ``reset``) takes no seed, so none
is claimed. What the harness controls is its own process: it fixes Python's and NumPy's global
generators before the engine is constructed, and fingerprints them at fixed points to record
whether the engine draws from them. Whether games are reproducible is then measured by repeating
them, never assumed.
"""

from __future__ import annotations

import hashlib
import random
from typing import Dict


def seed_globals(seed: int) -> None:
    random.seed(seed)
    try:
        import numpy
    except ImportError:  # pragma: no cover - numpy is part of the runtime environment
        return
    numpy.random.seed(seed)


def fingerprint() -> Dict[str, str]:
    """Short digests of the global generators' full states."""
    result = {"python": hashlib.sha256(repr(random.getstate()).encode("ascii")).hexdigest()[:16]}
    try:
        import numpy
    except ImportError:  # pragma: no cover
        return result
    name, keys, position, has_gauss, cached = numpy.random.get_state()
    material = keys.tobytes() + f"|{name}|{position}|{has_gauss}|{cached!r}".encode("ascii")
    result["numpy"] = hashlib.sha256(material).hexdigest()[:16]
    return result
