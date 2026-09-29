"""The registered evaluation of the baseline policy.

* :mod:`.selection` - the scenario eligibility and selection rule;
* :mod:`.manifest` - the registered manifest, its canonical digest and the game plan;
* :mod:`.identity` - the digest of the policy source under evaluation;
* :mod:`.game` - one game against an injected engine, producing a private record;
* :mod:`.effects` - whether emitted actions visibly took effect;
* :mod:`.canonical` - order-independent digests of engine data;
* :mod:`.metrics` - percentiles, repetition comparison, gate criteria and the public summary;
* :mod:`.randomness` - the harness's own generators and the probe of engine consumption.

Nothing here imports the SDK; the engine class is always passed in by the caller.
"""
