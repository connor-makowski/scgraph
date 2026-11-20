"""Assemble the graph of a network from the pieces of its ways.

WHAT IT ANSWERS

`build_graph_from_pieces` turns the pieces that `osm_ways` cut (`PieceArrays`) into a
graph. `assemble_network_arrays` turns this graph into the arrays of a network file. A route between
two nodes of the same kept component has the same length before and after `assemble_network_arrays`.

HOW A GRAPH IS STORED

A graph is a dict of arrays, with the names of the network file. Node `u` has the arcs
`offsets[u]` to `offsets[u + 1] - 1`. Arc `a` goes to node `heads[a]` and is
`weights[a]` km long. `node_points` holds the latitude, then the longitude of each
node, in units of 1e-7 degree. The shape points of arc `a` are
`shape_points[2 * shape_offsets[a]:2 * shape_offsets[a + 1]]`. `node_ids` holds the id
of each node in its source. `node_modes`, if the graph has several modes, holds the row
of each node in the modes table.

`arc_classes`, if the pieces have classes, holds the row of each arc in the classes
table (`scgraph.pipelines.CLASSES`).

Example: two nodes joined both ways by a trunk road of 1.5 km give
`offsets = [0, 1, 2]`, `heads = [1, 0]` and `weights = [1.5, 1.5]`. `trunk` is row 2 of
the classes table, so `arc_classes = [2, 2]`.

HOW A RUN GOES

1. `build_graph_from_pieces` makes one arc from a one-way piece and two arcs from a
   two-way piece. An arc has the class of its piece. `build_csr_from_arcs` stores the
   arcs by origin. It drops an arc from a node to itself. Of several arcs between the
   same two nodes, it keeps the shortest.
2. `keep_strongly_connected_components` keeps the largest strongly connected
   component, or each component of at least a given number of nodes. In such a
   component, every node can reach every other node. An arc between two components
   is dropped.
3. `contract_chains` removes each pass-through node. A pass-through node has exactly
   two neighbours, and a route that enters it can only go on to the other neighbour.
   There are two cases. Either an arc joins the node to each neighbour in each
   direction. Or the node has one arc in, from one neighbour, and one arc out, to the
   other. A chain is a run of such nodes between two kept nodes. One contracted arc
   replaces the chain, with the sum of its lengths. The arcs that the contracted arc
   replaces are its members. The walk ends a contracted arc at the first node where
   its length reaches `max_km_between_nodes`, and starts the next arc there. A chain
   is never contracted across two modes. In a graph with classes, a pass-through node
   meets one more condition. All the arcs that enter it or leave it have the same
   class. So a chain is never contracted across two classes, and a contracted arc has
   the class of its members.
4. `build_chain_shapes` gives each contracted arc the shape points of its members,
   with the removed nodes between them.
5. `assemble_network_arrays` numbers the nodes by mode, then along a Hilbert curve. A network file
   has this order.

Example of step 3: the road 0-4-3-2-1-5 has arcs of 1 km, both ways, and
`max_km_between_nodes` is 2. The walk starts at node 0 and cuts at node 3, then at
node 1. The nodes 0, 1, 3 and 5 are kept. The arcs 0-3 and 3-1 are 2 km long, and the
arc 1-5 is 1 km long.

Example of the classes in step 3: the road 0-1-2-3-4 has arcs of 1 km, both ways. It
is a motorway from node 0 to node 2, and a primary road from node 2 to node 4. Node 2
has two motorway arcs and two primary arcs, so it is kept. The nodes 1 and 3 are
removed. The contracted arcs between 0 and 2 are motorway arcs of 2 km, and the
contracted arcs between 2 and 4 are primary arcs of 2 km. A node is removed only when
all its arcs have one class. With a primary arc from 2 to 1 only, node 1 is kept too.

WHY THE RESULT IS RIGHT

A pass-through node offers no choice, so step 3 does not change the length of a route
between two kept nodes. Step 3 never makes an arc from a node to itself, nor a second
arc between two nodes. When a chain would give one, the function keeps the middle
node of the chain.

Example: the chains 0-1-3 and 0-2-3 would give two arcs from 0 to 3. The first chain
loses node 1. The second chain keeps node 2.

THE C++ VERSION

`build_csr_from_arcs`, `strongly_connected_components`, `contract_chains` and
`simplify_shapes` have a C++ version (`cpp/src/pipelines/assembly.hpp`), which a
network of the planet needs. The functions of this module call it when the extension
is built and the inputs are `array` or `memoryview` buffers. The pure-Python versions
give the same results. The namespace `python` of this module gives them, for example
`network_arrays.python.contract_chains`. The C++ version returns memoryviews, and the Python
version returns `array`s.

`build_csr_from_adjacency_list` and `keep_largest_strongly_connected_component` take
the layout of a GeoGraph, for `load_from_osm`.
"""

import logging
import math
import mmap
import os
from array import array
from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Iterator, Sequence
from functools import reduce
from itertools import accumulate
from operator import add
from types import SimpleNamespace
from typing import NamedTuple

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
from scgraph.helpers.hilbert import CURVE_ORDER, hilbert_key
from scgraph.network_file import extract_coordinates
from scgraph.utils import _log_step, haversine

logger = logging.getLogger(__name__)


def build_csr_from_arcs_python(
    origins: Sequence[int],
    destinations: Sequence[int],
    weights: Sequence[int | float],
) -> tuple[array, array, array, array, array]:
    """Pure-Python version of `build_csr_from_arcs`."""
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


def build_csr_from_arcs(
    origins: array | memoryview,
    destinations: array | memoryview,
    weights: array | memoryview,
) -> tuple[
    array | memoryview,
    array | memoryview,
    array | memoryview,
    array | memoryview,
    array | memoryview,
]:
    """Store arcs by origin, in CSR arrays.

    Args:
        origins: The id of the origin of each arc in its source (int64).
        destinations: The id of the destination of each arc (int64).
        weights: The length of each arc (float64).

    Returns:
        `(node_ids, offsets, heads, weights, kept)`. `node_ids` (int64) lists the ids of
        the ends, sorted, each once. Node `u` is the id at position `u`. The arcs of node
        `u` are `heads[offsets[u]:offsets[u + 1]]` (int32), sorted by head, with their
        `weights`. `kept[a]` (int32) is the input index of arc `a`: the caller finds the
        shape of the arc with it. The function drops an arc from a node to itself, and an
        id that has only such arcs gives no node. Of several arcs between the same two
        nodes, the function keeps the shortest, and the first of the input when two are
        as short.
    """
    if _cpp_build_csr_from_arcs is not None and isinstance(
        origins, (array, memoryview)
    ):
        return _cpp_build_csr_from_arcs(origins, destinations, weights)
    return build_csr_from_arcs_python(origins, destinations, weights)


def strongly_connected_components_python(
    offsets: Sequence[int], heads: Sequence[int]
) -> tuple[array, array]:
    """Pure-Python version of `strongly_connected_components`."""
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


def strongly_connected_components(
    offsets: array | memoryview, heads: array | memoryview
) -> tuple[array | memoryview, array | memoryview]:
    """Find the strongly connected components of a graph, with Kosaraju's algorithm.

    In a strongly connected component, every node can reach every other node along the
    arcs.

    Args:
        offsets: The CSR offsets of the graph, one more than its nodes (int32).
        heads: The head of each arc (int32).

    Returns:
        `(labels, sizes)`. `labels[u]` is the number of the component of node `u`. The
        components are numbered in the order of their lowest node. `sizes[c]` is the
        number of nodes of component `c`.
    """
    if _cpp_strongly_connected_components is not None and isinstance(
        offsets, (array, memoryview)
    ):
        return _cpp_strongly_connected_components(offsets, heads)
    return strongly_connected_components_python(offsets, heads)


def build_csr_from_adjacency_list(
    adjacency_list: list[dict[int, int | float]],
) -> tuple[array, array, array]:
    """Store a graph in the layout of a GeoGraph as CSR arrays.

    Args:
        adjacency_list: For each node, a dict that gives the weight of the arc to each
            head.

    Returns:
        `(offsets, heads, weights)`: int32, int32 and float64. The arcs of a node are
        sorted by head.
    """
    offsets, heads, weights = array("i", [0]), array("i"), array("d")
    for row in adjacency_list:
        for head in sorted(row):
            heads.append(head)
            weights.append(row[head])
        offsets.append(len(heads))
    return offsets, heads, weights


def keep_strongly_connected_components(
    offsets: array | memoryview,
    heads: array | memoryview,
    min_component_nodes: int | None = None,
) -> tuple[array, array | memoryview]:
    """Choose the nodes to keep, by strongly connected component.

    A node outside the kept components is a one-way dead end, a place that no route can
    enter, or a fragment that the border of an extract cut off.

    Args:
        offsets: The CSR offsets of the graph, one more than its nodes (int32).
        heads: The head of each arc (int32).
        min_component_nodes: The smallest number of nodes of a kept component. None keeps
            only the largest component. Example: `osm_world_multimodal` gives 1000, so that
            an island with roads of its own stays in the network.

    Returns:
        `(kept_nodes, labels)`. `kept_nodes` lists the kept nodes in rising order.
        `labels[u]` is the number of the component of node `u`, kept or not.
    """
    labels, sizes = strongly_connected_components(offsets, heads)
    if min_component_nodes is None:
        largest = max(range(len(sizes)), key=sizes.__getitem__, default=-1)
        wanted = [c == largest for c in range(len(sizes))]
    else:
        wanted = [size >= min_component_nodes for size in sizes]
    return array("i", (u for u, c in enumerate(labels) if wanted[c])), labels


def keep_largest_strongly_connected_component(
    graph: list[dict[int, int | float]],
    nodes: list[list[float]],
    shapes: list[dict[int, list[list[float]]]],
    node_ids: list[int],
) -> tuple[
    list[dict[int, int | float]],
    list[list[float]],
    list[dict[int, list[list[float]]]],
    list[int],
]:
    """Keep the largest strongly connected component of a graph in the layout of a
    GeoGraph. Return `(graph, nodes, shapes, node_ids)` with the kept nodes only.
    """
    kept, _ = keep_strongly_connected_components(
        *build_csr_from_adjacency_list(graph)[:2]
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
    """The result of `contract_chains`.

    Attributes:
        kept: The nodes of the input graph that stay, in rising order.
        origins: The origin of each contracted arc, as a position in `kept`.
        heads: The head of each contracted arc, as a position in `kept`.
        weights: The length of each contracted arc in km: the sum of its members.
        member_offsets: Where the members of each contracted arc start in `members`.
        members: The arcs of the input graph that each contracted arc replaces, in
            travel order. The members of arc `i` are
            `members[member_offsets[i]:member_offsets[i + 1]]`.
    """

    kept: array | memoryview
    origins: array | memoryview
    heads: array | memoryview
    weights: array | memoryview
    member_offsets: array | memoryview
    members: array | memoryview


def contract_chains_python(
    offsets: Sequence[int],
    heads: Sequence[int],
    weights: Sequence[int | float],
    node_modes: Sequence[int] | None = None,
    max_km_between_nodes: float = math.inf,
    arc_classes: Sequence[int] | None = None,
) -> ContractedGraph:
    """Pure-Python version of `contract_chains`."""
    n = len(offsets) - 1
    if (
        len(weights) != len(heads)
        or (node_modes is not None and len(node_modes) != n)
        or (arc_classes is not None and len(arc_classes) != len(heads))
    ):
        raise ValueError(
            "expected one weight and one class per arc, and one mode per node"
        )
    if (
        n < 0
        or offsets[n] != len(heads)
        or not _is_monotonically_increasing(offsets)
    ):
        raise ValueError("offsets must rise from 0 to the number of items")
    rows = [heads[offsets[u] : offsets[u + 1]] for u in range(n)]
    ins = [[] for _ in range(n)]
    for u, row in enumerate(rows):
        if any(
            not 0 <= v < n or v == u or (i and v <= row[i - 1])
            for i, v in enumerate(row)
        ):
            raise IndexError("rows must rise within the nodes, without loops")
        for v in row:
            ins[v].append(u)

    def through(v):
        out, inn = list(rows[v]), sorted(ins[v])
        two_way = len(out) == 2 and out == inn
        one_way = len(out) == len(inn) == 1 and out != inn
        same = node_modes is None or all(
            node_modes[x] == node_modes[v] for x in out + inn
        )
        return (
            (two_way or one_way)
            and same
            and (arc_classes is None or has_one_class(v, inn))
        )

    def has_one_class(v, inn):
        # The arcs that leave v, then the arc that enters v from each node of inn
        arcs = [
            *range(offsets[v], offsets[v + 1]),
            *(offsets[u] + bisect_left(rows[u], v) for u in inn),
        ]
        return len({arc_classes[a] for a in arcs}) == 1

    def contract(s, a):
        nodes, path = [s], [a]  # walk to the next kept node
        while not keep[heads[path[-1]]]:
            v = heads[path[-1]]
            row, seen[v] = rows[v], True
            nodes.append(v)
            path.append(offsets[v] + (len(row) == 2 and row[0] == nodes[-2]))
        nodes.append(heads[path[-1]])
        # Cut where the length from the canonical end reaches max_km_between_nodes
        pieces, start, total = [], 0, 0.0
        for i in range(1, len(path) + 1):
            total += weights[path[i - 1]]
            if total >= max_km_between_nodes or i == len(path):
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
    offsets: array | memoryview,
    heads: array | memoryview,
    weights: array | memoryview,
    node_modes: array | memoryview | None = None,
    max_km_between_nodes: float = math.inf,
    arc_classes: array | memoryview | None = None,
) -> ContractedGraph:
    """Contract the chains of pass-through nodes of a graph.

    The module docstring (*How a run goes*, step 3) gives the rule and an example. The
    function walks a chain from its canonical end: the start of a one-way chain, or the
    end with the lower index. A part of a chain that would give an arc from a node to
    itself, or a second arc between two nodes, is split at its middle node. A cycle of
    pass-through nodes is walked from its lowest node, which is kept.

    Args:
        offsets: The CSR offsets of the graph, one more than its nodes (int32).
        heads: The head of each arc (int32).
        weights: The length of each arc in km (float64).
        node_modes: The mode of each node (uint8), or None. A chain is never contracted
            across two modes.
        max_km_between_nodes: The length in km at which a chain is cut. Along the chain,
            an arc ends at the first node where it is this long or longer. So an arc can
            be longer than this value, by less than the length of one input arc.
        arc_classes: The class of each arc (uint8), or None.

    Returns:
        A `ContractedGraph`.
    """
    if _cpp_contract_chains is not None and isinstance(
        offsets, (array, memoryview)
    ):
        return ContractedGraph(
            *_cpp_contract_chains(
                offsets,
                heads,
                weights,
                node_modes,
                max_km_between_nodes,
                arc_classes,
            )
        )
    return contract_chains_python(
        offsets,
        heads,
        weights,
        node_modes=node_modes,
        max_km_between_nodes=max_km_between_nodes,
        arc_classes=arc_classes,
    )


def simplify_shapes(
    shape_points: array | memoryview,
    shape_offsets: array | memoryview,
    endpoint_coords: array | memoryview,
    tolerance_meters: float,
) -> tuple[array | memoryview, array | memoryview]:
    """Simplify the shape of each arc with the Douglas-Peucker algorithm.

    A shape point is dropped when it is within `tolerance_meters` of the line between the
    two kept points around it. Distances are measured on a flat map around each arc.

    Args:
        shape_points: The shape points of all the arcs (int32 pairs, 1e-7 degree).
        shape_offsets: Where the points of each arc start.
        endpoint_coords: The latitude and the longitude of the two ends of each arc
            (int32, four values per arc).
        tolerance_meters: The tolerance, in meters.

    Returns:
        `(shape_points, shape_offsets)` of the simplified shapes.
    """
    if _cpp_simplify_shapes is not None and isinstance(
        shape_points, (array, memoryview)
    ):
        return _cpp_simplify_shapes(
            shape_points, shape_offsets, endpoint_coords, tolerance_meters
        )
    return simplify_shapes_python(
        shape_points, shape_offsets, endpoint_coords, tolerance_meters
    )


class NearNodes:
    """Find the nodes near a point, without one Python object per node.

    `latitudes` and `longitudes` are sequences of numbers. A value times `scale` is in
    degrees. For example, int32 values in units of 1e-7 degree take `scale=1e-7`. The
    index groups the nodes in rows of 0.2 degree of latitude. In a row, the nodes are
    sorted by longitude, and a search finds them by bisection.
    """

    def __init__(self, latitudes, longitudes, scale=1):
        self.latitudes, self.longitudes = latitudes, longitudes
        self.rows, self.scale = {}, scale
        for i, lat in enumerate(latitudes):
            row = math.floor(lat * scale / 0.2)
            self.rows.setdefault(row, array("i")).append(i)
        for row, nodes in self.rows.items():
            self.rows[row] = array(
                "i", sorted(nodes, key=longitudes.__getitem__)
            )

    def find_within(
        self, point: Sequence[float], km: float
    ) -> Iterator[tuple[float, int]]:
        """Yield `(km, node)` for each node within `km` of `point`, a `[latitude, longitude]`
        pair in degrees.
        """
        lat, lon = point
        dlat = km / 110  # degrees: more than `km` (111.2 km per degree)
        cos = math.cos(math.radians(min(90, abs(lat) + dlat)))
        if cos < 1e-9 or (dlon := km / (110 * cos)) >= 180:
            spans = [(-180, 180)]
        else:  # around the antimeridian, two spans
            spans = [(lon - dlon, lon + dlon)]
            spans += [(w + 360, e + 360) for w, e in spans if w < -180]
            spans += [(w - 360, e - 360) for w, e in spans[:1] if e > 180]
        latitudes, longitudes = self.latitudes, self.longitudes
        scale = self.scale

        def key(i):
            return longitudes[i] * scale  # degrees (x * 1 == x)

        for row in range(
            math.floor((lat - dlat) / 0.2), math.floor((lat + dlat) / 0.2) + 1
        ):
            nodes = self.rows.get(row, ())
            for west, east in spans:
                lo, hi = bisect_left(nodes, west, key=key), bisect_right(
                    nodes, east, key=key
                )
                for i in nodes[lo:hi]:
                    d = haversine(
                        point, [latitudes[i] * scale, longitudes[i] * scale]
                    )
                    if d <= km:
                        yield d, i

    def find_nearest(
        self, point: Sequence[float], km: float
    ) -> tuple[float, int | None]:
        """Return `(km, node)` for the node nearest to `point` within `km`, or
        `(inf, None)` when there is none. When two nodes are as near, the lower one is
        returned.
        """
        return min(self.find_within(point, km), default=(math.inf, None))


class PieceArrays:
    """The pieces of the cut ways, stored as columns that grow.

    A piece is the part of a way between two consecutive nodes (`cut_polylines`). Entry
    `i` of each column describes piece `i`:

    - `origins`, `destinations` (int64): the ids of its two ends in the source;
    - `ends` (int32, four values per piece): the latitude and the longitude of its two
      ends, in units of 1e-7 degree;
    - `km` (float64): its length;
    - `directions` (int8): its direction, as in a polyline (1, -1 or 0);
    - `points` (int32 pairs) and `offsets`: its shape points. The points of piece `i` are
      `points[2 * offsets[i]:2 * offsets[i + 1]]`;
    - `class_rows` (uint8): the row of its class in `scgraph.pipelines.CLASSES`. The
      column is empty when the pieces have no class.

    `flush` simplifies the shapes of the new pieces to within `tolerance_meters`
    (`simplify_shapes`) and stores them. `append` calls it every BATCH pieces.
    `tolerance_meters=None` stores the shapes as they are.

    Without `work_dir`, the columns are `array`s in memory. With `work_dir`, each column
    is a file of that folder, read through a memory map. The columns hold the pieces up to
    the last `flush`.
    """

    BATCH = 10_000
    COLUMNS = dict(origins="q", destinations="q", ends="i", km="d")
    COLUMNS.update(directions="b", points="i", offsets="q", class_rows="B")

    def __init__(self, tolerance_meters=50, work_dir=None, truncate=True):
        self.tolerance_meters, self.work_dir = tolerance_meters, work_dir
        if work_dir is not None:
            os.makedirs(work_dir, exist_ok=True)
        for name, code in self.COLUMNS.items():
            path = (
                os.path.join(work_dir, name) if work_dir is not None else None
            )
            if (
                not truncate
                and path is not None
                and os.path.isfile(path)
                and os.path.getsize(path) > 0
            ):
                with open(path, "rb") as file:
                    view = mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ)
                setattr(self, name, memoryview(view).cast(code))
            else:
                setattr(self, name, array(code))
                if work_dir is not None and truncate:
                    open(path, "wb").close()
        self._new = {name: array(code) for name, code in self.COLUMNS.items()}
        self._new["offsets"].append(0)
        self._starts = [0]

    def append(
        self,
        origin_id: int,
        destination_id: int,
        length_km: float,
        direction: int,
        endpoint_coords: Iterable[Sequence[float]],
        shape_points: Iterable[Sequence[float]],
        class_row: int | None = None,
    ) -> None:
        """Add one piece. `endpoint_coords` and `shape_points` are `[latitude, longitude]`
        points in degrees. `class_row` is the row of the class of the piece in
        `scgraph.pipelines.CLASSES`. It is None for pieces without a class.
        """
        new = self._new
        new["origins"].append(origin_id)
        new["destinations"].append(destination_id)
        new["km"].append(length_km)
        new["directions"].append(direction)
        flat = [
            [x for point in points for x in point]
            for points in (endpoint_coords, shape_points)
        ]
        ends, points = extract_coordinates(flat, "int32")
        new["ends"].extend(ends)
        new["points"].extend(points)
        if class_row is not None:
            new["class_rows"].append(class_row)
        self._starts.append(len(new["points"]) // 2)
        if len(self._starts) > self.BATCH:
            self.flush()

    def flush(self) -> None:
        """Simplify and store the shapes of the pieces added since the last call."""
        new, starts = self._new, self._starts
        if self.tolerance_meters is not None:
            new["points"], starts = simplify_shapes(
                new["points"],
                array("i", starts),
                new["ends"],
                self.tolerance_meters,
            )
        stored = len(self.points) // 2
        new["offsets"].extend(stored + start for start in starts[1:])
        for name, column in new.items():
            if self.work_dir is None:
                getattr(self, name).extend(column)
                continue
            with open(os.path.join(self.work_dir, name), "ab+") as file:
                file.write(column)
                file.flush()
                if file.tell():
                    view = mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ)
                    setattr(
                        self, name, memoryview(view).cast(self.COLUMNS[name])
                    )
        self._new = {name: array(code) for name, code in self.COLUMNS.items()}
        self._starts = [0]


def build_graph_from_pieces(
    pieces: PieceArrays,
) -> dict[str, array | memoryview]:
    """Build a graph from the pieces of ways.

    A two-way piece gives two arcs, and a one-way piece gives one arc in its direction.
    Of several arcs between the same two nodes, the shortest is kept.

    Args:
        pieces: The pieces, as `osm_ways.build_way_pieces` or `hub_connectors.join_networks_at_hubs` fill them.

    Returns:
        The graph as a dict of arrays: `offsets`, `heads`, `weights`, `node_points`,
        `shape_offsets`, `shape_points` and `node_ids`, and `arc_classes` when the
        pieces have classes. The module docstring describes them.

    Raises:
        ValueError: Every piece joins a node to itself. Or some pieces have a class
            and the others have none.
    """
    pieces.flush()
    if len(pieces.class_rows) not in (0, len(pieces.km)):
        raise ValueError("Some pieces have a class and the others have none")
    piece, back = array("i"), array("b")
    for i, direction in enumerate(pieces.directions):
        for reverse in (0, 1) if direction == 0 else (int(direction < 0),):
            piece.append(i)
            back.append(reverse)
    ends = pieces.origins, pieces.destinations
    node_ids, offsets, heads, weights, kept = build_csr_from_arcs(
        array("q", (ends[b][i] for i, b in zip(piece, back))),
        array("q", (ends[1 - b][i] for i, b in zip(piece, back))),
        array("d", (pieces.km[i] for i in piece)),
    )
    if not len(node_ids):
        raise ValueError("The pieces join no two points: every one is a loop")
    node_points = array("i", bytes(8 * len(node_ids)))
    points, shape_offsets = array("i"), array("i", [0])
    for u in range(len(node_ids)):
        for a in range(offsets[u], offsets[u + 1]):
            i, b = piece[kept[a]], back[kept[a]]
            e = pieces.ends[4 * i : 4 * i + 4]
            # e holds the points of the two ends of the piece, in the order of the
            # piece. For an arc that goes against the piece, the ends swap.
            origin, destination = (e[2:], e[:2]) if b else (e[:2], e[2:])
            v = heads[a]
            node_points[2 * u], node_points[2 * u + 1] = origin
            node_points[2 * v], node_points[2 * v + 1] = destination
            first, last = pieces.offsets[i], pieces.offsets[i + 1]
            line = array("i", pieces.points[2 * first : 2 * last])
            if b:  # its points from the destination
                line[0::2], line[1::2] = line[-2::-2], line[-1::-2]
            points.extend(line)
            shape_offsets.append(len(points) // 2)
    graph = {
        "offsets": offsets,
        "heads": heads,
        "weights": weights,
        "node_points": node_points,
        "shape_offsets": shape_offsets,
        "shape_points": points,
        "node_ids": node_ids,
    }
    if len(pieces.class_rows):
        graph["arc_classes"] = array(
            "B", (pieces.class_rows[piece[i]] for i in kept)
        )
    return graph


def assemble_network_arrays(
    graph: dict[str, array | memoryview],
    *,
    max_km_between_nodes: float,
    min_component_nodes: int | None,
) -> dict[str, array]:
    """Turn a graph into the arrays of a network file.

    The function runs steps 2 to 5 of the module docstring. It keeps the strongly
    connected components, contracts the chains, joins the shapes of the contracted arcs,
    and numbers the nodes by mode, then along the Hilbert curve.
    `GeoGraph.save_as_scgraph` uses the same order. The first two steps log their counts
    at DEBUG.

    Args:
        graph: The graph, as `build_graph_from_pieces` returns it, with `node_modes` if it
            has several modes. The function empties this dict, to free its memory.
        max_km_between_nodes: The length in km at which `contract_chains` cuts a chain.
        min_component_nodes: The smallest number of nodes of a kept component. None keeps
            only the largest component.

    Returns:
        The arrays of the network file, as `network_file.write` takes them.
    """
    with _log_step(
        logger,
        "keep the strongly connected components",
        _count_nodes_and_arcs(graph),
    ) as counts:
        order = keep_strongly_connected_components(
            graph["offsets"],
            graph["heads"],
            min_component_nodes,
        )
        given, graph = graph, _renumbered(graph, *order)
        given.clear()  # freed now, not when the caller lets it go: one copy at a time
        counts.update(_count_nodes_and_arcs(graph, "kept_"))
    with _log_step(
        logger, "contract the chains", _count_nodes_and_arcs(graph)
    ) as counts:
        modes, arc_classes = graph.get("node_modes"), graph.get("arc_classes")
        kept, origins, heads, weights, member_offsets, members = (
            contract_chains(
                graph["offsets"],
                graph["heads"],
                graph["weights"],
                node_modes=modes,
                max_km_between_nodes=max_km_between_nodes,
                arc_classes=arc_classes,
            )
        )
        points, shape_offsets = build_chain_shapes(
            graph, member_offsets, members
        )
        offsets = array("i", bytes(4 * (len(kept) + 1)))
        for u in origins:  # rows by origin, as contract_chains sorts them
            offsets[u + 1] += 1
        graph = {  # the graph before contraction is freed
            "offsets": array("i", accumulate(offsets)),
            "heads": heads,
            "weights": weights,
            "shape_offsets": shape_offsets,
            "shape_points": points,
            **_select_nodes(graph, kept),
        }
        if arc_classes is not None:  # the members of an arc have one class
            graph["arc_classes"] = array(
                "B", (arc_classes[members[i]] for i in member_offsets[:-1])
            )
        counts.update(_count_nodes_and_arcs(graph, "kept_"))
    node_points = memoryview(graph["node_points"])
    latitudes, longitudes = node_points[0::2], node_points[1::2]
    modes = graph.get("node_modes") or bytes(len(kept))

    def key(u):  # mode, Hilbert key (below 4^CURVE_ORDER), index: one int
        curve = hilbert_key(latitudes[u] * 1e-7, longitudes[u] * 1e-7)
        return (modes[u] << 2 * CURVE_ORDER | curve) << 32 | u

    # One int per node, not a list; the sorted ints are freed before _renumbered
    keys = sorted(map(key, range(len(kept))))
    order, keys = array("i", (k & 0xFFFFFFFF for k in keys)), None
    return _renumbered(graph, order)


def build_chain_shapes(
    graph: dict[str, array | memoryview],
    member_offsets: Sequence[int],
    members: Sequence[int],
) -> tuple[array, array]:
    """Build the shape of each contracted arc.

    The shape holds the shape points of each member, in travel order. Between two
    members, it holds the point of the node that the contraction removed.

    Returns:
        `(points, offsets)`, as `shape_points` and `shape_offsets` of a graph.
    """
    heads, node_points = graph["heads"], graph["node_points"]
    starts, line = graph["shape_offsets"], graph["shape_points"]
    points, offsets = array("i"), array("i", [0])
    for i in range(len(member_offsets) - 1):
        chain = members[member_offsets[i] : member_offsets[i + 1]]
        for k, a in enumerate(chain):
            if k:
                node = heads[chain[k - 1]]
                points.extend(node_points[2 * node : 2 * node + 2])
            points.extend(line[2 * starts[a] : 2 * starts[a + 1]])
        offsets.append(len(points) // 2)
    return points, offsets


def _select_nodes(graph, nodes):
    """Copy the arrays of `graph` that describe the nodes, for the nodes listed in
    `nodes` only. Node `nodes[i]` becomes node `i`.

    The arrays are `node_points`, then `node_ids` and `node_modes` if `graph` has
    them. `network_file.write` writes the arrays in the order of the returned dict. This
    order is fixed, so every run writes the same file.
    """
    # One view holds the latitudes and another the longitudes, without a copy.
    # Reading a value from a view is as fast as reading it from an array.
    node_points = memoryview(graph["node_points"])
    latitudes, longitudes = node_points[0::2], node_points[1::2]
    points = array("i", bytes(8 * len(nodes)))
    points[0::2] = array("i", (latitudes[u] for u in nodes))
    points[1::2] = array("i", (longitudes[u] for u in nodes))
    selected = {"node_points": points}
    for key, typecode in (("node_ids", "q"), ("node_modes", "B")):
        if key in graph:
            selected[key] = array(typecode, (graph[key][u] for u in nodes))
    return selected


def _renumbered(graph, order, labels=None):
    """Return `graph` with the nodes of `order` only. Node `order[i]` becomes node `i`, and
    the arcs of each node are sorted by head. With `labels`, an arc is kept only when its
    two ends have the same label. A kept arc keeps its shape, and its class if `graph`
    has `arc_classes`.
    """
    new = array("i", [-1]) * (len(graph["offsets"]) - 1)
    for i, u in enumerate(order):
        new[u] = i
    offsets, heads, weights = (
        graph[key] for key in ("offsets", "heads", "weights")
    )
    starts, line = graph["shape_offsets"], graph["shape_points"]
    out = {
        "offsets": array("i", [0]),
        "heads": array("i"),
        "weights": array("d"),
    }
    out["shape_offsets"], out["shape_points"] = array("i", [0]), array("i")
    arc_classes = graph.get("arc_classes")
    if arc_classes is not None:
        out["arc_classes"] = array("B")
    for u in order:
        for v, a in sorted(
            (new[heads[a]], a) for a in range(offsets[u], offsets[u + 1])
        ):
            if v >= 0 and (labels is None or labels[u] == labels[heads[a]]):
                out["heads"].append(v)
                out["weights"].append(weights[a])
                out["shape_points"].extend(
                    line[2 * starts[a] : 2 * starts[a + 1]]
                )
                out["shape_offsets"].append(len(out["shape_points"]) // 2)
                if arc_classes is not None:
                    out["arc_classes"].append(arc_classes[a])
        out["offsets"].append(len(out["heads"]))
    return {**out, **_select_nodes(graph, order)}


def _count_nodes_and_arcs(graph, prefix=""):
    """The number of nodes and the number of arcs of `graph`, as the values of a log:
    `nodes` and `arcs`, each with `prefix` before it."""
    return {
        f"{prefix}nodes": len(graph["offsets"]) - 1,
        f"{prefix}arcs": len(graph["heads"]),
    }


python = SimpleNamespace(
    build_csr_from_adjacency_list=build_csr_from_adjacency_list,
    build_csr_from_arcs=build_csr_from_arcs_python,
    strongly_connected_components=strongly_connected_components_python,
    contract_chains=contract_chains_python,
    simplify_shapes=simplify_shapes_python,
)
