"""
Assemble a network file from raw arcs. The C++ kernels
(`cpp/src/pipelines/assembly.hpp`), with the same results at the scale of the planet,
replace these when built; the pure-Python ones stay in `python`. Arrays in: buffers of
the stated types (`array("q"/"i"/"d")`; any sequences for `python`); out: `array`
(read-only memoryviews from C++). `csr_from_rows` and `keep_largest_component` take the
GeoGraph layout and call the kernels.
"""

import math
from array import array
from bisect import bisect_left
from functools import reduce
from itertools import accumulate
from operator import add, le
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


def csr_from_rows(rows):
    """A graph in the GeoGraph layout (`rows[u]`: head -> weight) stored by origin:
    `(offsets, heads, weights)` (int32, int32, float64), rows sorted by head."""
    offsets, heads, weights = array("i", [0]), array("i"), array("d")
    for row in rows:
        for head in sorted(row):
            heads.append(head)
            weights.append(row[head])
        offsets.append(len(heads))
    return offsets, heads, weights


def keep_largest_component(graph, nodes, shapes, node_ids, *, min_nodes=None):
    """Keep the largest strongly connected component (with `min_nodes`, every one of at
    least that many nodes), the part where every node can reach every other, so that no
    origin or destination is placed on a one-way dead end or on a fragment cut by the
    border of an extract (of equal ones, the one with the smallest node index).
    """
    offsets, heads, _ = csr_from_rows(graph)
    labels, sizes = strong_components(offsets, heads)
    if min_nodes is None:
        largest = max(range(len(sizes)), key=sizes.__getitem__, default=-1)
        wanted = [label == largest for label in range(len(sizes))]
    else:
        wanted = [size >= min_nodes for size in sizes]
    kept = [u for u, label in enumerate(labels) if wanted[label]]
    index = {old: new for new, old in enumerate(kept)}
    return (
        [
            {index[v]: w for v, w in graph[u].items() if v in index}
            for u in kept
        ],
        [nodes[u] for u in kept],
        [
            {index[v]: s for v, s in shapes[u].items() if v in index}
            for u in kept
        ],
        [node_ids[u] for u in kept],
    )


def contract_chains(offsets, heads, weights, modes=None, max_km=math.inf):
    """
    Contract the chains of a graph stored by origin (int32 `offsets`, `heads`, rows
    sorted by head, no self-loop; float64 `weights`): a node goes if it has two
    distinct neighbours, both ways with each or one way through, and shares their mode
    (uint8 `modes`, one per node, or None). Walking from its canonical end (a one-way
    start, or the end with the lower index), a chain is cut at the first node where the
    piece since the last cut reaches `max_km`, and a piece that would be a self-loop or
    repeat an arc is cut at its middle node; an isolated cycle is walked from its
    lowest node, which it keeps. Returns `(kept, origins, heads, weights,
    member_offsets, members)` (int32, `weights` float64): the kept nodes; the arcs
    between them (positions in `kept`), the two directions of a two-way chain cut at
    the same nodes and summed in the same order; arc `i`'s input arcs in travel order,
    `members[member_offsets[i]:member_offsets[i + 1]]`.
    """
    n = len(offsets) - 1
    rows = [heads[offsets[u] : offsets[u + 1]] for u in range(n)]
    ins = [[] for _ in range(n)]
    for u, row in enumerate(rows):
        for v in row:
            ins[v].append(u)

    def through(v):
        out, inn = list(rows[v]), sorted(ins[v])
        two_way = len(out) == 2 and out == inn
        one_way = len(out) == len(inn) == 1 and out != inn
        same = modes is None or all(modes[x] == modes[v] for x in out + inn)
        return (two_way or one_way) and same

    def contract(s, a):
        nodes, path = [s], [a]  # walk to the next kept node
        while not keep[heads[path[-1]]]:
            v = heads[path[-1]]
            row, seen[v] = rows[v], True
            nodes.append(v)
            path.append(offsets[v] + (len(row) == 2 and row[0] == nodes[-2]))
        nodes.append(heads[path[-1]])
        # Cut where the length from the canonical end reaches max_km
        pieces, start, total = [], 0, 0.0
        for i in range(1, len(path) + 1):
            total += weights[path[i - 1]]
            if total >= max_km or i == len(path):
                pieces.append((start, i))
                start, total = i, 0.0
        pieces, both = pieces[::-1], len(rows[nodes[1]]) == 2
        while pieces:
            i, j = pieces.pop()
            b, e = nodes[i], nodes[j]
            if j - i > 1 and (b == e or exists(b, e) or both and exists(e, b)):
                pieces += [(i + (j - i) // 2, j), (i, i + (j - i) // 2)]
                continue
            keep[b] = keep[e] = True
            emit(b, e, path[i:j], path[i:j])
            if both:
                back = [
                    offsets[nodes[k + 1]]
                    + bisect_left(rows[nodes[k + 1]], nodes[k])
                    for k in range(i, j)
                ]
                emit(e, b, back[::-1], back)

    def emit(u, v, members, canonical):
        # Summed in order from the canonical end, as C++ does (sum() compensates
        # since Python 3.12)
        km = reduce(add, (weights[a] for a in canonical), 0.0)
        arcs.append((u, v, km, members))
        pairs.add((u, v))

    def exists(u, v):  # an input arc, or an arc made
        return (u, v) in pairs or v in rows[u]

    chain = [through(v) for v in range(n)]
    keep, seen = [not c for c in chain], [False] * n
    arcs = [
        (u, heads[a], weights[a], [a])
        for u in range(n)
        for a in range(offsets[u], offsets[u + 1])
        if keep[u] and keep[heads[a]]
    ]
    pairs = set()  # (origin, head) of the arcs made by contraction
    for s in range(n):
        for a in range(offsets[s], offsets[s + 1]):
            if not chain[s] and chain[heads[a]] and not seen[heads[a]]:
                contract(s, a)
    for v in range(n):
        if chain[v] and not seen[v]:
            keep[v] = seen[v] = True
            contract(v, offsets[v])
    kept = array("i", (v for v in range(n) if keep[v]))
    position = {v: i for i, v in enumerate(kept)}
    arcs.sort(key=lambda arc_: arc_[:2])
    return (
        kept,
        array("i", (position[arc_[0]] for arc_ in arcs)),
        array("i", (position[arc_[1]] for arc_ in arcs)),
        array("d", (arc_[2] for arc_ in arcs)),
        array("i", accumulate((len(arc_[3]) for arc_ in arcs), initial=0)),
        array("i", (a for arc_ in arcs for a in arc_[3])),
    )


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
    contract_chains=contract_chains,
    simplify_shapes=simplify_shapes,
)
try:
    from scgraph.cpp import (
        contract_chains,
        csr_from_arcs,
        simplify_shapes,
        strong_components,
    )
except ImportError:
    pass
