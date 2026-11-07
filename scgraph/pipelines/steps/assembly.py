"""
Assemble a network file from raw arcs. The C++ kernels
(`cpp/src/pipelines/assembly.hpp`), with the same results at the scale of the planet,
replace these when built; the pure-Python ones stay in `python`. Arrays in: buffers of
the stated types (`array("q"/"i"/"d")`; any sequences for `python`); out: `array`
(read-only memoryviews from C++).
"""

import math
from array import array
from operator import le
from types import SimpleNamespace


def csr_from_arcs(origins, destinations, weights):
    """
    Store arcs between source ids (int64 `origins`, `destinations`; float64 `weights`)
    by origin. Returns `(node_ids, offsets, heads, weights, kept)`: the arcs' end ids,
    sorted and unique (int64); the arcs of node `u` (its position in `node_ids`),
    `heads[offsets[u]:offsets[u + 1]]` (int32) sorted by head, with their `weights`;
    `kept` (int32), the input index of each arc, for its shape. Self-loops are dropped
    (an id on self-loops only is no node); of parallel arcs the shortest is kept, the
    first in the input on a tie.
    """
    if not len(origins) == len(destinations) == len(weights):
        raise ValueError("one destination and one weight per origin expected")
    best = {}  # (origin, destination) -> input index of the shortest arc so far
    for i, arc in enumerate(zip(origins, destinations)):
        if arc[0] != arc[1] and weights[i] < weights[best.setdefault(arc, i)]:
            best[arc] = i
    node_ids = array("q", sorted({id for arc in best for id in arc}))
    position = {id: u for u, id in enumerate(node_ids)}
    rows = [[] for _ in node_ids]
    for (origin, destination), i in best.items():
        rows[position[origin]].append((position[destination], i))
    offsets, heads, kept = array("i", [0]), array("i"), array("i")
    for row in rows:
        for head, i in sorted(row):
            heads.append(head)
            kept.append(i)
        offsets.append(len(heads))
    return (
        node_ids,
        offsets,
        heads,
        array("d", (weights[i] for i in kept)),
        kept,
    )


def strong_components(offsets, heads):
    """
    Strongly connected components (where every node reaches every other) of a graph
    stored by origin (int32 `offsets`, `heads`). Returns `(labels, sizes)` (int32): the
    component of each node, numbered in the order of their smallest node, and sizes.
    """
    n = len(offsets) - 1
    if n < 0 or offsets[n] != len(heads) or not _rising(offsets):
        raise ValueError("offsets must rise from 0 to the number of items")
    if heads and not (0 <= min(heads) and max(heads) < n):
        raise IndexError("head out of range")

    def successors(node):
        return iter(heads[offsets[node] : offsets[node + 1]])

    # Kosaraju: order the nodes by the end of a depth-first search, then search the
    # reverse graph from the last one finished
    finished, seen = [], [False] * n
    for first in range(n):
        if seen[first]:
            continue
        seen[first] = True
        stack = [(first, successors(first))]
        while stack:
            node, ahead = stack[-1]
            successor = next(ahead, None)
            if successor is None:
                stack.pop()
                finished.append(node)
            elif not seen[successor]:
                seen[successor] = True
                stack.append((successor, successors(successor)))
    reverse = [[] for _ in range(n)]
    for origin in range(n):
        for destination in successors(origin):
            reverse[destination].append(origin)
    component, count = [-1] * n, 0
    for first in reversed(finished):
        if component[first] != -1:
            continue
        component[first], stack = count, [first]
        while stack:
            for predecessor in reverse[stack.pop()]:
                if component[predecessor] == -1:
                    component[predecessor] = count
                    stack.append(predecessor)
        count += 1
    # Number the components in the order of their smallest node
    number, labels, sizes = [-1] * count, array("i", bytes(4 * n)), array("i")
    for node in range(n):
        if number[component[node]] == -1:
            number[component[node]] = len(sizes)
            sizes.append(0)
        labels[node] = number[component[node]]
        sizes[labels[node]] += 1
    return labels, sizes


_METRES = 6371000.0 * math.pi / 1.8e9  # per 1e-7 degree of latitude


def _rising(offsets):
    return offsets[0] == 0 and all(map(le, offsets, offsets[1:]))


def simplify_shapes(points, offsets, ends, tolerance_m):
    """
    Douglas-Peucker: drop the shape points within `tolerance_m` metres of the segment
    between the points kept around them, in metres on a flat map local to each arc.

    The network file's layout: `points` (int32), the shapes' interior points as flat
    latitude, longitude pairs in 1e-7 degree; shape `i` is points `offsets[i]:offsets[i
    + 1]` (int32); `ends` (int32), four per shape: the arc's origin then destination,
    always kept. Returns `(points, offsets)` of the points kept.
    """
    shapes = len(offsets) - 1
    if not tolerance_m >= 0:
        raise ValueError("tolerance_m must be >= 0")
    if shapes < 0 or len(points) % 2 or len(ends) != 4 * shapes:
        raise ValueError("expected two ints per point and four ends per shape")
    if offsets[shapes] != len(points) // 2 or not _rising(offsets):
        raise ValueError("offsets must rise from 0 to the number of items")
    # Same formulas and order of operations as the C++ kernel: the same points kept
    tolerance2 = tolerance_m * tolerance_m
    kept, kept_offsets = array("i"), array("i", [0])
    for s in range(shapes):
        lat0, lon0 = ends[4 * s], ends[4 * s + 1]
        kx = _METRES * math.cos(lat0 * math.pi / 1.8e9)
        x, y = [], []
        # Metres from the origin, longitudes unwrapped across the antimeridian
        line = points[2 * offsets[s] : 2 * offsets[s + 1]]
        for latitude, longitude in zip(
            [lat0, *line[::2], ends[4 * s + 2]],
            [lon0, *line[1::2], ends[4 * s + 3]],
        ):
            dlon = longitude - lon0
            if dlon > 1800000000:
                dlon -= 3600000000
            elif dlon < -1800000000:
                dlon += 3600000000
            x.append(dlon * kx)
            y.append((latitude - lat0) * _METRES)
        last = len(x) - 1
        keep, stack = [False] * (last + 1), [(0, last)]
        while stack:
            a, b = stack.pop()
            dx, dy = x[b] - x[a], y[b] - y[a]
            length2 = dx * dx + dy * dy
            farthest, worst = -1, tolerance2
            for i in range(a + 1, b):
                px, py = x[i] - x[a], y[i] - y[a]
                if length2 > 0:
                    t = (px * dx + py * dy) / length2
                    t = 0 if t < 0 else 1 if t > 1 else t
                    px = px - t * dx
                    py = py - t * dy
                d2 = px * px + py * py
                if d2 > worst:
                    farthest, worst = i, d2
            if farthest >= 0:
                keep[farthest] = True
                stack.append((a, farthest))
                stack.append((farthest, b))
        for i in range(1, last):
            if keep[i]:
                kept.extend(line[2 * i - 2 : 2 * i])
        kept_offsets.append(len(kept) // 2)
    return kept, kept_offsets


python = SimpleNamespace(
    csr_from_arcs=csr_from_arcs,
    strong_components=strong_components,
    simplify_shapes=simplify_shapes,
)
try:
    from scgraph.cpp import csr_from_arcs, simplify_shapes, strong_components
except ImportError:
    pass
