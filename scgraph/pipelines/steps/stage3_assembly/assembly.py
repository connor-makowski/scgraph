"""
Assemble a network file from raw arcs. The C++ kernels
(`cpp/src/pipelines/assembly.hpp`), with the same results at the scale of the planet,
replace these when built; the pure-Python ones stay in `python`. Arrays in: buffers of
the stated types (`array("q"/"i"/"d")`; any sequences for `python`); out: `array`
(read-only memoryviews from C++). `build_csr_from_adjacency` and `keep_largest_strongly_connected_component` take the GeoGraph layout
for `load_from_osm`.
"""

import math
from array import array
from bisect import bisect_left
from functools import reduce
from itertools import accumulate
from operator import add
from types import SimpleNamespace
from typing import Any, NamedTuple

try:
    from scgraph.cpp import (
        build_csr_from_arcs as _cpp_build_csr_from_arcs,
        contract_chains as _cpp_contract_chains,
        simplify_shapes as _cpp_simplify_shapes,
        strongly_connected_components as _cpp_strongly_connected_components,
    )
except ImportError:
    _cpp_build_csr_from_arcs = None
    _cpp_contract_chains = None
    _cpp_simplify_shapes = None
    _cpp_strongly_connected_components = None

from scgraph.helpers.douglas_peucker import (
    _is_monotonically_increasing,
    simplify_shapes as simplify_shapes_python,
)


def build_csr_from_arcs_python(origins, destinations, weights):
    """Pure-Python implementation of CSR construction from raw arcs."""
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


def build_csr_from_arcs(origins, destinations, weights):
    """
    Store arcs between source ids (int64 `origins`, `destinations`; float64 `weights`)
    by origin. Returns `(node_ids, offsets, heads, weights, kept)`: the arcs' end ids,
    sorted and unique (int64); the arcs of node `u` (its position in `node_ids`),
    `heads[offsets[u]:offsets[u + 1]]` (int32) sorted by head, with their `weights`;
    `kept` (int32), the input index of each arc, for its shape. Self-loops are dropped
    (an id on self-loops only is no node); of parallel arcs the shortest is kept, the
    first in the input on a tie.
    """
    if _cpp_build_csr_from_arcs is not None and isinstance(origins, array):
        return _cpp_build_csr_from_arcs(origins, destinations, weights)
    return build_csr_from_arcs_python(origins, destinations, weights)


def strongly_connected_components_python(offsets, heads):
    """Pure-Python implementation of Kosaraju's strongly connected components."""
    n = len(offsets) - 1
    if (
        n < 0
        or offsets[n] != len(heads)
        or not _is_monotonically_increasing(offsets)
    ):
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


def strongly_connected_components(offsets, heads):
    """Compute the strongly connected components of a directed CSR graph.

    A strongly connected component (SCC) is a maximal subset of nodes where every
    node can reach every other node following the directed arcs. In logistics networks,
    this identifies mutually accessible clusters and isolates dead ends or cut fragments.

    Computed using Kosaraju's two-pass depth-first search algorithm.

    Parameters:
        offsets (array[int32]): CSR row offsets of size `num_nodes + 1`.
        heads (array[int32]): CSR target node indices of size `num_arcs`.

    Returns:
        tuple[array[int32], array[int32]]:
            - `labels`: Component index (0-based) for each node, numbered in order
              of appearance of their smallest node index.
            - `sizes`: Number of nodes in each component.
    """
    if _cpp_strongly_connected_components is not None and isinstance(
        offsets, array
    ):
        return _cpp_strongly_connected_components(offsets, heads)
    return strongly_connected_components_python(offsets, heads)


def build_csr_from_adjacency(rows):
    """Store a graph from an adjacency list representation into CSR format.

    `rows[u]` maps head -> weight.
    Returns:
        tuple[array[int32], array[int32], array[float64]]:
            - offsets (int32)
            - heads (int32, rows sorted by head)
            - weights (float64)
    """
    offsets, heads, weights = array("i", [0]), array("i"), array("d")
    for row in rows:
        for head in sorted(row):
            heads.append(head)
            weights.append(row[head])
        offsets.append(len(heads))
    return offsets, heads, weights


def keep_strongly_connected_components(offsets, heads, min_nodes=None):
    """Filter a CSR graph to retain only viable strongly connected components (SCCs).

    In logistics and road routing, every location must be mutually reachable so that
    vehicles are guaranteed a legal return route. This filtering prunes one-way dead
    ends (sinks), unreachable origins (sources), and artificial fragments severed at
    extract borders.

    Selection strategy:
    - If `min_nodes` is None: keeps only the single largest SCC (e.g. mainland road
      network of a regional extract).
    - If `min_nodes` is an integer: retains every SCC having at least that many nodes,
      preserving separate viable landmasses and islands (e.g. Eurasia, Americas,
      Australia, Great Britain at the world scale).

    Parameters:
        offsets (array[int32]): CSR row offsets of size `num_nodes + 1`.
        heads (array[int32]): CSR target node indices of size `num_arcs`.
        min_nodes (int | None): Minimum node count threshold for retained SCCs.
            Defaults to None (retaining only the largest SCC).

    Returns:
        tuple[array[int32], array[int32]]:
            - `kept_nodes`: Sorted indices of nodes retained in the graph.
            - `labels`: Component index assigned to each original node.
    """
    labels, sizes = strongly_connected_components(offsets, heads)
    if min_nodes is None:
        largest = max(range(len(sizes)), key=sizes.__getitem__, default=-1)
        wanted = [c == largest for c in range(len(sizes))]
    else:
        wanted = [size >= min_nodes for size in sizes]
    return array("i", (u for u, c in enumerate(labels) if wanted[c])), labels


def keep_largest_strongly_connected_component(graph, nodes, shapes, node_ids):
    """Filter a GeoGraph-layout graph to keep only its largest strongly connected component."""
    kept, _ = keep_strongly_connected_components(
        *build_csr_from_adjacency(graph)[:2]
    )
    index = {old: new for new, old in enumerate(kept)}

    def row(values):
        return {index[v]: x for v, x in values.items() if v in index}

    return (
        [row(graph[u]) for u in kept],
        [nodes[u] for u in kept],
        [row(shapes[u]) for u in kept],
        [node_ids[u] for u in kept],
    )


class ContractedGraph(NamedTuple):
    """Result of contracting degree-2 pass-through chains on a CSR graph.

    Inherits from tuple for full backward-compatible unpacking:
        kept, origins, heads, weights, member_offsets, members = contracted

    Attributes:
        kept (sequence[int]): Original node indices retained in the contracted graph.
        origins (sequence[int]): Origin indices of the contracted arcs (indexed into kept).
        heads (sequence[int]): Destination indices of the contracted arcs (indexed into kept).
        weights (sequence[float]): Summed composite edge lengths in kilometres.
        member_offsets (sequence[int]): Offsets into members for each contracted arc.
        members (sequence[int]): Input arc indices comprising each contracted arc, in travel order.
    """

    kept: Any
    origins: Any
    heads: Any
    weights: Any
    member_offsets: Any
    members: Any


def contract_chains_python(
    offsets, heads, weights, modes=None, max_km=math.inf
) -> ContractedGraph:
    """Pure-Python implementation of CSR degree-2 chain contraction."""
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
    return ContractedGraph(
        kept,
        array("i", (position[arc_[0]] for arc_ in arcs)),
        array("i", (position[arc_[1]] for arc_ in arcs)),
        array("d", (arc_[2] for arc_ in arcs)),
        array("i", accumulate((len(arc_[3]) for arc_ in arcs), initial=0)),
        array("i", (a for arc_ in arcs for a in arc_[3])),
    )


def contract_chains(
    offsets, heads, weights, modes=None, max_km=math.inf
) -> ContractedGraph:
    """Contract degree-2 pass-through chains into composite weighted edges.

    A node is contracted away if it has degree 2 (two distinct neighbours,
    either bidirectional with each or one-way through) and shares their mode.
    Walking from its canonical end (a one-way start, or the end with the lower
    index), a chain is segmented at the first node where the segment reaches
    `max_km`, and any segment that would create a self-loop or duplicate arc is
    split at its midpoint. Isolated cycles are walked from their lowest-index
    node, which is retained.

    Delegates to the C++ extension when available and inputs are arrays,
    falling back to pure Python.

    Parameters:
        offsets (array[int32]): CSR row offsets of size `num_nodes + 1`.
        heads (array[int32]): Target node indices of size `num_arcs`.
        weights (array[float64]): Arc lengths in kilometres.
        modes (array[uint8] | None): Optional per-node travel mode. If provided,
            chains are never contracted across different modes.
        max_km (float): Maximum length of a contracted composite segment in km.
            Defaults to infinity (unlimited segment length).

    Returns:
        ContractedGraph: A namedtuple with fields:
            - `kept`: Original node indices retained in the contracted graph.
            - `origins`: Origin indices of the contracted arcs (indexed into `kept`).
            - `heads`: Destination indices of the contracted arcs (indexed into `kept`).
            - `weights`: Summed composite edge lengths in kilometres.
            - `member_offsets`: Offsets into `members` for each contracted arc.
            - `members`: Input arc indices comprising each contracted arc, in travel order.
    """
    if _cpp_contract_chains is not None and isinstance(offsets, array):
        return ContractedGraph(
            *_cpp_contract_chains(offsets, heads, weights, modes, max_km)
        )
    return contract_chains_python(
        offsets, heads, weights, modes=modes, max_km=max_km
    )


def simplify_shapes(points, offsets, ends, tolerance_m):
    """Simplify intermediate polyline shapes using the Douglas-Peucker algorithm.

    Drops intermediate shape points that fall within `tolerance_m` metres of the
    segment connecting the retained endpoints, calculated on a local flat-map
    projection for each arc.
    """
    if _cpp_simplify_shapes is not None and isinstance(points, array):
        return _cpp_simplify_shapes(points, offsets, ends, tolerance_m)
    return simplify_shapes_python(points, offsets, ends, tolerance_m)


python = SimpleNamespace(
    build_csr_from_arcs=build_csr_from_arcs_python,
    strongly_connected_components=strongly_connected_components_python,
    contract_chains=contract_chains_python,
    simplify_shapes=simplify_shapes_python,
)
