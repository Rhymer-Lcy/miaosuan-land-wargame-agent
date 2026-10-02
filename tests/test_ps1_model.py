"""The PS-1 design-study model (``evaluation/ps1_model.py``) on SYNTHETIC graphs.

Stacking (four units fit, a fifth waits), the wait-for graph, the maximal deadlocked set, cycles of two and three
hexes, chains ending at holders, transient queues, speed-aware stall detection, the stop rule (complete a hex in
progress, at once when waiting), flags and occupation, the baseline surrogate's choice, PS-1A admission, PS-1B
recovery (bypass, back-off avoiding other units' paths, capacity-counted placement), no-escape witnesses, the
recovery window against oscillation, contract errors and the independent trajectory validator.
"""

from __future__ import annotations

import unittest

from miaosuan_agent.evaluation import ps1_model as pm

V = 36.0  # vehicle km/h: 20 steps per cost-1 hex
I = 5.0  # infantry km/h: 144 steps per cost-1 hex


def graph(pairs, cost=1.0):
    edges = {}
    for a, b in pairs:
        edges.setdefault(a, {})[b] = cost
        edges.setdefault(b, {})[a] = cost
    return {0: edges, 2: edges}


def unit(uid, hex_, path=(), speed=V, mode=0, ready_at=None, last=0, ground=True):
    return pm.Unit(uid=uid, hex=hex_, speed=speed, mode=mode, path=tuple(path), ready_at=ready_at, last_progress=last,
                   ground=ground)


def line(n):
    return graph([(i, i + 1) for i in range(1, n)])


# Sprint-2-like layout: objective 10 with a corridor hex 11 and a side hex 12; target 20 beyond the corridor; a longer
# detour 10-12-13-20; a spare hex 14 next to the corridor and a farther spare 15 behind it.
LAYOUT = graph([(10, 11), (11, 20), (10, 12), (12, 13), (13, 20), (11, 14), (14, 15), (11, 16)])


def deadlock_state(step=500, last=440):
    occupants = [unit(i, 10, (11, 20), ready_at=step - 1, last=last) for i in (1, 2, 3, 4)]
    waiters = [unit(i, 11, (10,), ready_at=step - 1, last=last) for i in (5, 6, 7, 8)]
    return occupants + waiters


class StackingTest(unittest.TestCase):
    def test_four_fit_and_the_fifth_waits(self) -> None:
        sim = pm.Simulation([unit(i, 1, (2,), ready_at=20) for i in range(1, 5)] + [unit(5, 3, (2,), ready_at=20)],
                            graph([(1, 2), (2, 3)]), step=0, end_step=40)
        sim.run()
        hexes = {u.uid: u.hex for u in sim.units}
        self.assertEqual([hexes[i] for i in range(1, 5)], [2, 2, 2, 2])
        self.assertEqual(hexes[5], 3)  # the fifth never enters the full hex
        self.assertEqual(pm.occupancy(sim.units)[2], 4)
        self.assertEqual(pm.blocked_units(sim.units), frozenset({5}))
        self.assertFalse(pm.validate_trajectory({1: 1, 2: 1, 3: 1, 4: 1, 5: 3},
                                                [(e.step, e.uid, e.detail[0]) for e in sim.events if e.kind == "enter"],
                                                lambda uid, a, b: b in sim.edges_by_mode[0][a], {}))

    def test_aircraft_do_not_count(self) -> None:
        units = [unit(i, 2) for i in range(1, 5)] + [unit(9, 2, ground=False), unit(5, 1, (2,), ready_at=0)]
        self.assertEqual(pm.occupancy(units)[2], 4)
        self.assertEqual(pm.full_hexes(units), frozenset({2}))


class DependencyTest(unittest.TestCase):
    def test_two_groups_blocking_each_other(self) -> None:
        units = deadlock_state()
        self.assertEqual(pm.blocked_units(units), frozenset(range(1, 9)))
        self.assertEqual(pm.deadlocked(units), frozenset(range(1, 9)))
        self.assertEqual(pm.cycles(units), [(10, 11)])
        self.assertEqual(pm.wait_for(units)[5], (1, 2, 3, 4))

    def test_queue_behind_the_cycle_is_deadlocked_but_not_on_the_cycle(self) -> None:
        units = deadlock_state() + [unit(9, 14, (11,), ready_at=499), unit(10, 14, (11,), ready_at=499)]
        self.assertEqual(pm.deadlocked(units), frozenset(range(1, 11)))
        self.assertEqual(pm.cycles(units), [(10, 11)])

    def test_reciprocal_but_not_deadlocked_reports_no_cycle(self) -> None:
        # B also holds a unit moving away into a free hex: it will leave, so nothing is deadlocked and there is no cycle
        units = [unit(i, 1, (2,), ready_at=0) for i in range(1, 5)] + [unit(i, 2, (1,), ready_at=0) for i in range(5, 8)] \
            + [unit(8, 2, (3,), ready_at=50)]
        self.assertEqual(len(pm.blocked_units(units)), 7)
        self.assertEqual(pm.deadlocked(units), frozenset())
        self.assertEqual(pm.cycles(units), [])

    def test_three_hex_cycle(self) -> None:
        tri = [unit(i, 1, (2,), ready_at=0) for i in range(1, 5)] + [unit(i, 2, (3,), ready_at=0) for i in range(5, 9)] \
            + [unit(i, 3, (1,), ready_at=0) for i in range(9, 13)]
        self.assertEqual(pm.deadlocked(tri), frozenset(range(1, 13)))
        self.assertEqual(pm.cycles(tri), [(1, 2, 3)])

    def test_chain_ending_at_holders_is_a_deadlock_without_a_cycle(self) -> None:
        units = [unit(i, 2) for i in range(1, 5)] + [unit(5, 1, (2,), ready_at=0)]
        self.assertEqual(pm.deadlocked(units), frozenset({5}))
        self.assertEqual(pm.cycles(units), [])

    def test_shared_objective_by_different_routes(self) -> None:
        diamond = graph([(1, 2), (2, 4), (1, 3), (3, 4)])
        units = [unit(i, 1, (2, 4), ready_at=20) for i in (1, 2)] + [unit(i, 1, (3, 4), ready_at=20) for i in (3, 4)] \
            + [unit(5, 2, (4,), ready_at=20), unit(6, 3, (4,), ready_at=20)]
        sim = pm.Simulation(units, diamond, step=0, end_step=200)
        sim.run()
        self.assertEqual(pm.occupancy(sim.units)[4], 4)
        waiting = {u.uid for u in sim.units if u.moving}
        self.assertEqual(len(waiting), 2)
        self.assertEqual(pm.deadlocked(sim.units), frozenset(waiting))  # destination full of holders: a chain
        self.assertEqual(pm.cycles(sim.units), [])

    def test_transient_queue_resolves_and_is_not_deadlocked(self) -> None:
        units = [unit(i, 2, (3,), ready_at=30) for i in range(1, 5)] + [unit(5, 1, (2,), ready_at=10)]
        self.assertEqual(pm.blocked_units(units), frozenset({5}))
        self.assertEqual(pm.deadlocked(units), frozenset())  # its blockers have orders and will leave
        sim = pm.Simulation(units, line(3), step=0, end_step=60)
        sim.run()
        entry = [e.step for e in sim.events if e.kind == "enter" and e.uid == 5]
        self.assertEqual(entry, [30])  # enters in the step its blockers leave: they are processed first (M2)


class RestartAfterWaitTest(unittest.TestCase):
    """M1b (protocol amendment 1): a unit that finds its next hex full waits at its hex centre and needs a full hex
    time again once the hex has room; a unit following a column that vacates the hex in the same step never waits."""

    def blocked_then_freed(self, restart):
        units = [unit(i, 2, (3,), ready_at=30) for i in range(1, 5)] + [unit(5, 1, (2,), ready_at=10)]
        sim = pm.Simulation(units, line(3), step=0, end_step=80, restart_after_wait=restart)
        sim.run()
        return sim

    def test_restart_needs_a_full_hex_time(self) -> None:
        m1 = self.blocked_then_freed(False)
        m1b = self.blocked_then_freed(True)
        self.assertEqual([e.step for e in m1.events if e.kind == "enter" and e.uid == 5], [30])
        self.assertEqual([e.step for e in m1b.events if e.kind == "enter" and e.uid == 5], [49])  # 30 + 20 - 1

    def test_waiting_flag_while_blocked(self) -> None:
        sim = pm.Simulation([unit(i, 2) for i in range(1, 5)] + [unit(5, 1, (2,), ready_at=10)], line(3), step=0,
                            end_step=15, restart_after_wait=True)
        sim.run()
        u = sim.unit(5)
        self.assertEqual((u.waiting, u.ready_at, u.hex), (True, None, 1))
        sim.order_stop(5)
        self.assertEqual((sim.unit(5).path, sim.events[-1].detail), ((), ("at once",)))

    def test_column_following_a_vacating_column_does_not_wait(self) -> None:
        leaders = [unit(i, 2, (3, 4), ready_at=20) for i in range(1, 5)]
        follower = [unit(5, 1, (2, 3), ready_at=20)]
        sim = pm.Simulation(leaders + follower, line(4), step=0, end_step=45, restart_after_wait=True)
        sim.run()
        self.assertEqual([e.step for e in sim.events if e.kind == "enter" and e.uid == 5], [20, 40])
        self.assertFalse(any(u.waiting for u in sim.units))


class WaitAtEntryTest(unittest.TestCase):
    """M1c (post hoc): a unit entering a hex whose next hex is full waits at once instead of starting its traversal, so
    when room appears it restarts together with the units already waiting and loses to lower indices."""

    def contention(self, restart, entry_wait):
        leaving = [unit(i, 3, (4,), ready_at=20) for i in (1, 2)]  # two places free up at step 20
        holders = [unit(i, 3) for i in (8, 9)]
        waiting = [unit(i, 2, (3,), ready_at=0) for i in (5, 6)]
        arriving = [unit(7, 1, (2, 3), ready_at=1)]  # enters hex 2 while hex 3 is full
        sim = pm.Simulation(leaving + holders + waiting + arriving, line(4), step=0, end_step=60,
                            restart_after_wait=restart, wait_at_entry=entry_wait)
        sim.run()
        return sim

    def entries(self, sim):
        return sorted((e.step, e.uid) for e in sim.events if e.kind == "enter" and e.detail[0] == 3)

    def test_entering_unit_waits_and_loses_the_place(self) -> None:
        m1b = self.contention(True, False)
        m1c = self.contention(True, True)
        self.assertEqual(self.entries(m1b), [(21, 7), (39, 5)])  # M1b: the arriving unit was traversing all along
        self.assertEqual(self.entries(m1c), [(39, 5), (39, 6)])  # M1c: all three restart at 20, ascending index wins
        self.assertTrue(m1c.unit(7).waiting)

    def test_waits_from_the_entry_step(self) -> None:
        sim = self.contention(True, True)
        sim2 = pm.Simulation([unit(i, 3) for i in range(1, 5)] + [unit(7, 1, (2, 3), ready_at=1)], line(4), step=0,
                             end_step=2, restart_after_wait=True, wait_at_entry=True)
        sim2.run()
        self.assertEqual((sim2.unit(7).hex, sim2.unit(7).waiting, sim2.unit(7).ready_at), (2, True, None))
        self.assertEqual(sim.unit(6).hex, 3)

    def test_flag_needs_restart_mode(self) -> None:
        def lone(entry_wait):  # one arriving unit, two places freed at step 20, M1 timing
            units = [unit(i, 3, (4,), ready_at=20) for i in (1, 2)] + [unit(i, 3) for i in (8, 9)]
            units += [unit(7, 1, (2, 3), ready_at=1)]
            sim = pm.Simulation(units, line(4), step=0, end_step=60, wait_at_entry=entry_wait)
            sim.run()
            return self.entries(sim)
        self.assertEqual(lone(False), [(21, 7)])
        self.assertEqual(lone(True), [(21, 7)])  # ignored without restart_after_wait


class TimingTest(unittest.TestCase):
    def test_hex_time_by_speed_and_cost(self) -> None:
        self.assertEqual((pm.hex_time(V, 1), pm.hex_time(I, 1), pm.hex_time(V, 3), pm.hex_time(V, 1.5)), (20, 144, 60, 30))
        self.assertEqual((pm.hex_time(7, 1), pm.hex_time(11, 1)), (103, 65))  # 102.86 and 65.45, rounded to the nearest
        with self.assertRaises(ValueError):
            pm.hex_time(0, 1)

    def test_stall_threshold_is_class_aware(self) -> None:
        g = line(3)
        infantry = unit(1, 1, (2,), speed=I, mode=2, ready_at=144, last=0)
        vehicle = unit(2, 1, (2,), ready_at=20, last=0)
        self.assertFalse(pm.stalled(infantry, 200, g))  # 2 * 144 + 10 = 298
        self.assertTrue(pm.stalled(infantry, 299, g))
        self.assertFalse(pm.stalled(vehicle, 50, g))  # 2 * 20 + 10 = 50
        self.assertTrue(pm.stalled(vehicle, 51, g))
        self.assertFalse(pm.stalled(unit(3, 1), 999, g))  # no order, never stalled

    def test_apparent_stall_that_resumes_triggers_no_recovery(self) -> None:
        slow = [unit(i, 2, (3,), speed=I, mode=0, ready_at=144) for i in range(1, 5)]
        sim = pm.Simulation(slow + [unit(5, 1, (2,), ready_at=20)], line(3), step=0, end_step=200)
        state = pm.Recovery()
        sim.run(pm.ps1b(state))
        self.assertFalse([e for e in sim.events if e.kind in ("stop", "recover", "no-escape")])
        self.assertEqual(sim.unit(5).hex, 2)  # it resumed once the slow units left

    def test_missing_or_inconsistent_paths(self) -> None:
        g = line(3)
        odd = unit(1, 1, (3,), ready_at=0)  # next hex not adjacent: an inconsistent observation
        self.assertIsNone(pm.expected_hex_time(odd, g))
        self.assertFalse(pm.stalled(odd, 10 ** 6, g))
        problems = pm.validate_trajectory({1: 1}, [(5, 1, 3)], lambda uid, a, b: b in g[0].get(a, {}), {})
        self.assertIn("step 5: unit 1 moved to a non-adjacent hex", problems)
        crowded = pm.validate_trajectory({i: 2 for i in range(1, 5)} | {5: 1}, [(3, 5, 2)],
                                         lambda uid, a, b: True, {})
        self.assertIn("step 3: unit 5 entered a hex already holding 4", crowded)


class OrderTest(unittest.TestCase):
    def test_an_issued_move_cannot_be_changed(self) -> None:
        sim = pm.Simulation([unit(1, 1)], line(3), step=0)
        sim.order_move(1, (2, 3))
        with self.assertRaises(pm.ModelError):
            sim.order_move(1, (2,))
        with self.assertRaises(pm.ModelError):
            pm.Simulation([unit(2, 1)], line(3), step=0).order_stop(2)
        with self.assertRaises(pm.ModelError):
            pm.Simulation([unit(3, 1)], line(3), step=0).order_move(3, (3,))  # not an edge

    def test_stop_completes_the_hex_in_progress(self) -> None:
        sim = pm.Simulation([unit(1, 1)], line(4), step=0, end_step=200)
        sim.order_move(1, (2, 3, 4))
        sim.advance()
        sim.order_stop(1)  # moving into 2: completes it first (C2)
        sim.end_step = 30
        sim.run()
        u = sim.unit(1)
        self.assertEqual((u.hex, u.path, u.stopped_until), (2, (), 20 + pm.STOP_PENALTY))
        self.assertFalse(sim.can_order(1))
        sim.step = 95
        self.assertTrue(sim.can_order(1))

    def test_stop_while_waiting_takes_effect_at_once(self) -> None:
        sim = pm.Simulation(deadlock_state(), LAYOUT, step=500, objectives={10: 0, 20: -1}, faction=0)
        sim.order_stop(5)
        u = sim.unit(5)
        self.assertEqual((u.hex, u.path, u.stopped_until), (11, (), 575))
        self.assertEqual(sim.events[-1].detail, ("at once",))

    def test_occupation_flips_the_flag_next_step(self) -> None:
        sim = pm.Simulation([unit(1, 20)], LAYOUT, step=7, objectives={10: 0, 20: -1}, faction=0)
        sim.occupy(1)
        self.assertEqual(sim.objectives[20], -1)
        sim.advance()
        self.assertEqual(sim.objectives[20], 0)
        with self.assertRaises(pm.ModelError):
            sim.occupy(1)


class SurrogateTest(unittest.TestCase):
    def test_cheapest_objective_ties_to_lower_hex_and_occupation_once(self) -> None:
        g = graph([(5, 4), (5, 6)])
        sim = pm.Simulation([unit(1, 5), unit(2, 5)], g, step=0, objectives={4: -1, 6: -1}, faction=0)
        pm.surrogate(sim)
        self.assertEqual([u.path for u in sim.units], [(4,), (4,)])  # equal cost: the lower hex
        here = pm.Simulation([unit(1, 4), unit(2, 4)], g, step=0, objectives={4: -1, 6: -1}, faction=0)
        pm.surrogate(here)
        self.assertEqual([e.kind for e in here.events], ["occupy"])  # one occupation per objective per step
        self.assertEqual([u.path for u in here.units], [(), ()])  # standing on an unheld objective: no move

    def test_ps1a_admission_holds_or_redirects(self) -> None:
        g = graph([(1, 2), (2, 3), (1, 15), (15, 16), (16, 4)])  # objective 3 is nearer (2 hexes) than 4 (3 hexes)
        units = [unit(i, 3) for i in (1, 2, 3)] + [unit(4, 1, (2, 3), ready_at=20)] + [unit(5, 1), unit(6, 1)]
        sim = pm.Simulation(units, g, step=0, objectives={3: -1, 4: -1}, faction=0)
        pm.ps1a(sim)
        # 3 standing + 1 ordered = 4 committed to hex 3: units 5 and 6 go to the farther objective instead
        self.assertEqual((sim.unit(5).path, sim.unit(6).path), ((15, 16, 4), (15, 16, 4)))
        # with three units already standing on the other objective, unit 5 fills it and unit 6 is held
        full = pm.Simulation(units + [unit(7, 4), unit(8, 4), unit(9, 4)], g, step=0, objectives={3: -1, 4: -1},
                             faction=0)
        pm.ps1a(full)
        self.assertEqual((full.unit(5).path, full.unit(6).path), ((15, 16, 4), ()))
        self.assertEqual([(e.kind, e.uid) for e in full.events if e.kind == "hold"], [("hold", 6)])
        unchecked = pm.Simulation(units + [unit(7, 4), unit(8, 4), unit(9, 4)], g, step=0, objectives={3: -1, 4: -1},
                                  faction=0)
        pm.surrogate(unchecked)  # without admission both go to the nearer, saturated objective
        self.assertEqual((unchecked.unit(5).path, unchecked.unit(6).path), ((2, 3), (2, 3)))


class RecoveryTest(unittest.TestCase):
    def test_back_off_of_the_waiting_group_avoids_other_units_paths(self) -> None:
        sim = pm.Simulation(deadlock_state() + [unit(9, 14)], LAYOUT, step=500, objectives={10: 0, 20: -1}, faction=0)
        state = pm.Recovery()
        pm.ps1b(state)(sim)
        stopped = sorted(e.uid for e in sim.events if e.kind == "stop")
        self.assertEqual(stopped, [5, 6, 7, 8])  # the waiting group (not on the objective) is moved
        targets = sorted(p[-1] for p in state.pending.values())
        self.assertNotIn(20, targets)  # 20 is on the occupants' remaining path, so it is not a waiting hex
        self.assertEqual(targets, [14, 14, 14, 16])  # spare capacity counted as units are placed (14 has room for 3)

    def test_a_smaller_group_queued_behind_the_cycle_is_not_chosen(self) -> None:
        queued = [unit(9, 14, (11,), ready_at=499), unit(10, 14, (11,), ready_at=499)]
        sim = pm.Simulation(deadlock_state() + queued, LAYOUT, step=500, objectives={10: 0, 20: -1}, faction=0)
        pm.ps1b(pm.Recovery())(sim)
        self.assertEqual(sorted(e.uid for e in sim.events if e.kind == "stop"), [5, 6, 7, 8])

    def test_bypass_when_back_off_is_forbidden(self) -> None:
        sim = pm.Simulation(deadlock_state(), LAYOUT, step=500, objectives={10: 0, 20: -1}, faction=0)
        state = pm.Recovery(option="bypass")
        pm.ps1b(state)(sim)
        self.assertEqual(sorted(state.pending), [1, 2, 3, 4])  # the occupants re-route around the full corridor
        self.assertTrue(all(p == (12, 13, 20) for p in state.pending.values()))
        self.assertIn({"step": 500, "hex": 11, "mode": "bypass", "units": 4,
                       "reason": "no path avoiding full hexes to a free hex or the destination"}, state.witnesses)

    def test_recovery_breaks_the_cycle_in_simulation(self) -> None:
        sim = pm.Simulation(deadlock_state(), LAYOUT, step=500, objectives={10: 0, 20: -1}, faction=0, end_step=900)
        sim.run(pm.ps1b(pm.Recovery()))
        self.assertEqual([e.detail for e in sim.events if e.kind == "recover"], [("back-off", 4)])  # one recovery only
        self.assertEqual(sorted(e.uid for e in sim.events if e.kind == "stop"), [5, 6, 7, 8])
        self.assertEqual(sim.objectives[20], 0)  # the far objective is taken
        # eight units for one objective of capacity four: the occupants end queued before it, a chain, not a cycle
        self.assertEqual(pm.cycles(sim.units), [])
        entries = [(e.step, e.uid, e.detail[0]) for e in sim.events if e.kind == "enter"]
        start = {u.uid: u.hex for u in deadlock_state()}
        self.assertEqual(pm.validate_trajectory(start, entries, lambda uid, a, b: b in LAYOUT[0][a], {}), [])

    def test_no_escape_produces_a_witness_and_respects_the_window(self) -> None:
        dead_end = line(4)  # 1 is a dead end; occupants in 1 must pass 2, where the waiters stand
        occupants = [unit(i, 1, (2, 3), ready_at=0, last=0) for i in (1, 2, 3, 4)]
        waiters = [unit(i, 2, (1,), ready_at=0, last=0) for i in (5, 6, 7, 8)]
        sim = pm.Simulation(occupants + waiters, dead_end, step=100, objectives={1: 0, 4: -1}, faction=0, end_step=1200)
        state = pm.Recovery()
        sim.run(pm.ps1b(state))
        no_escape = [e.step for e in sim.events if e.kind == "no-escape"]
        self.assertEqual(no_escape, [100, 700])  # once per recovery window, not every step
        self.assertFalse([e for e in sim.events if e.kind == "stop"])
        self.assertTrue(state.witnesses)
        self.assertEqual(pm.deadlocked(sim.units), frozenset(range(1, 9)))


if __name__ == "__main__":
    unittest.main()
