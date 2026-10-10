"""Maximum-utility assignment solvers (deterministic, bounded, pure Python).

``hungarian(utility)`` solves the rectangular assignment problem exactly: rows (units) to columns (slots), each used at
most once, maximising the sum of the positive utilities. It is the O(n^3) shortest augmenting path form of the
Kuhn-Munkres algorithm on the square cost matrix ``-max(0, utility)`` padded with zeros, so a pair with non-positive
utility is never better than leaving both free and is dropped from the result. Ties are resolved by the first strictly
smaller value in index order, so the result depends only on the matrix.

``greedy(pairs)`` takes the highest-utility pair first, then the next pair whose members and slot are all still free,
and so on (a pair may consume more than one member, which is how a lift of an infantry unit on a carrier is
represented). Ties are broken by the pair's key, which callers build from ids only.
"""

from __future__ import annotations

from typing import Dict, Hashable, List, Optional, Sequence, Tuple

INF = float("inf")
EPS = 1e-12


def hungarian(utility: Sequence[Sequence[float]]) -> List[Optional[int]]:
    """For each row, the column it takes (or ``None``); only positive-utility pairs are ever returned."""
    rows = len(utility)
    if rows == 0:
        return []
    cols = len(utility[0]) if rows else 0
    if cols == 0:
        return [None] * rows
    n = max(rows, cols)
    cost = [[0.0] * n for _ in range(n)]
    for r in range(rows):
        row = utility[r]
        for c in range(cols):
            if row[c] > 0:
                cost[r][c] = -row[c]
    u = [0.0] * (n + 1)
    v = [0.0] * (n + 1)
    p = [0] * (n + 1)
    way = [0] * (n + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [INF] * (n + 1)
        used = [False] * (n + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = INF
            j1 = 0
            row = cost[i0 - 1]
            ui0 = u[i0]
            for j in range(1, n + 1):
                if not used[j]:
                    cur = row[j - 1] - ui0 - v[j]
                    if cur < minv[j] - EPS:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta - EPS:
                        delta = minv[j]
                        j1 = j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    assignment: List[Optional[int]] = [None] * rows
    for j in range(1, n + 1):
        i = p[j]
        if 1 <= i <= rows and j - 1 < cols and utility[i - 1][j - 1] > 0:
            assignment[i - 1] = j - 1
    return assignment


def greedy(pairs: Sequence[Tuple[float, Hashable, Tuple[Hashable, ...], Hashable]]
           ) -> List[Tuple[Hashable, Tuple[Hashable, ...], Hashable]]:
    """``pairs``: (utility, key, members, slot). Returns the chosen (key, members, slot), highest utility first."""
    chosen = []
    used_members: Dict[Hashable, bool] = {}
    used_slots: Dict[Hashable, bool] = {}
    for utility, key, members, slot in sorted(pairs, key=lambda p: (-p[0], repr(p[1]))):
        if utility <= 0:
            break
        if slot in used_slots or any(m in used_members for m in members):
            continue
        chosen.append((key, members, slot))
        used_slots[slot] = True
        for m in members:
            used_members[m] = True
    return chosen


def total(utility: Sequence[Sequence[float]], assignment: Sequence[Optional[int]]) -> float:
    return sum(utility[r][c] for r, c in enumerate(assignment) if c is not None)
