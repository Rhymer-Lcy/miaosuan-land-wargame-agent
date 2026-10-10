"""Sprint 34 integrated tactical agent (``docs/SPRINT34_INTEGRATED_AGENT.md``).

A whole-force decision cycle above the canonical boundary, distinct from ``baseline-v2``'s per-unit hierarchy:

    observation -> world view (:mod:`.world`) -> objective assessment and task allocation (:mod:`.allocation`)
    -> retention (:mod:`.defense`) and transport (:mod:`.transport`) -> routes under traffic capacity
    (:mod:`.movement`) -> fire (:mod:`.fire`) -> per-unit arbitration (:mod:`.policy`) -> independent validation
    (:mod:`.validate`) -> actions and explicit memory (:mod:`.memory`).

Every decision is a function of the seat's own observation, the setup cost data and the memory passed in; no
randomness, clock or omniscient view is read. Nothing here names a scenario, map, unit id or coordinate.
"""
