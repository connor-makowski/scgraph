"""Assemble the graph of a network from the pieces of its ways.

WHAT IT ANSWERS

`build_graph_from_pieces` turns the pieces that `scgraph.helpers.osm.build_way_pieces`
cut (`scgraph.helpers.polylines.PieceArrays`) into a graph. `assemble_network` turns this graph into the arrays of a network file. A route between
two nodes of the same kept component has the same length before and after `assemble_network`.

HOW A GRAPH IS STORED

A graph is a dict of arrays, with the names of the network file. Node `u` has the edges
`node_first_edge_ids[u]` to `node_first_edge_ids[u + 1] - 1`. Edge `a` goes to node `edge_destination_node_ids[a]` and is
`metric_length[a]` km long. `node_points` holds the latitude, then the longitude of each
node, in units of 1e-7 degree. The shape points of edge `a` are
`shape_points[2 * edge_first_shape_point_ids[a]:2 * edge_first_shape_point_ids[a + 1]]`. `external_node_ids` holds
the id of each node in its source. A node that stage 1 adds has an id below zero.
The node mode of a node is the kind of place where the node is, such as `port`.
`node_mode_ids` holds the node mode id of each node, in a graph of several node modes.
A network file does not hold it: its header gives the count of the nodes of each node mode.

`edge_class_ids`, if the pieces have classes, holds the id of the class of each edge in the classes
table (`scgraph.pipelines.CLASSES`).

Example: two nodes joined both ways by a trunk road of 1.5 km give
`node_first_edge_ids = [0, 1, 2]`, `edge_destination_node_ids = [1, 0]` and `metric_length = [1.5, 1.5]`. `trunk` has
the id 2 in the classes table, so `edge_class_ids = [2, 2]`.

HOW A RUN GOES

1. `build_graph_from_pieces` makes one edge from a one-way piece and two edges from a
   two-way piece. An edge has the class of its piece. `build_csr_from_edges` stores the
   edges by origin. It drops an edge from a node to itself. Of several edges between the
   same two nodes, it keeps the shortest. In a graph with classes, the shortest edge of
   each other class is a "parallel edge". `build_graph_from_pieces` splits the piece of
   each parallel edge in two halves, with a new node between them (*How a piece is
   split*). It then stores the edges again. So one edge at most goes from a node to
   another, and the shortest edge of each class stays in the graph. A caller that
   applies turn restrictions then calls `forbid_turns`, before stage 2. This function
   gives some junctions several nodes. `scgraph.turn_restrictions` gives the reason.
2. `keep_strongly_connected_components` keeps the largest strongly connected
   component, or each component of at least a given number of nodes. In such a
   component, every node can reach every other node. An edge between two components
   is dropped. A junction with a node in a kept component keeps all its nodes:
   `keep_components` adds the other nodes of the junction to this component.
3. `contract_chains` removes each pass-through node. A pass-through node has exactly
   two neighbours, and a route that enters it can only go on to the other neighbour.
   There are two cases. Either an edge joins the node to each neighbour in each
   direction. Or the node has one edge in, from one neighbour, and one edge out, to the
   other. A chain is a run of such nodes between two kept nodes. One contracted edge
   replaces the chain, with the sum of its lengths. The edges that the contracted edge
   replaces are its members. The walk ends a contracted edge at the first node where
   its length reaches `max_km_between_nodes`, and starts the next edge there. A chain
   is never contracted across two node modes. In a graph with classes, a pass-through
   node meets one more condition. All the edges that enter it or leave it have the same
   class. So a chain is never contracted across two classes, and a contracted edge has
   the class of its members. A node of a junction with several nodes is never
   removed.
4. `build_chain_shapes` gives each contracted edge the shape points of its members,
   with the removed nodes between them.
5. `assemble_network` numbers the nodes by node mode, then along a Hilbert curve. A
   network file has this order. The nodes of a junction have the same node mode and
   the same point. So `order_nodes` keeps them together, in the same order.

Example of stage 1: a motorway of 3 km and a primary road of 4 km join the junctions 10
and 20, both ways. The motorway is shorter, so its two edges are kept. The two edges of
the primary road are parallel edges. The primary road is split at its middle, where the
new node -1 is. The graph has the nodes -1, 10 and 20. It has two motorway edges of 3 km
between 10 and 20. It has four primary edges of 2 km: from 10 to -1, from -1 to 20, and
their reverses. Without the split, the graph would lose the primary road.

Example of stage 3: the road 0-4-3-2-1-5 has edges of 1 km, both ways, and
`max_km_between_nodes` is 2. The walk starts at node 0 and cuts at node 3, then at
node 1. The nodes 0, 1, 3 and 5 are kept. The edges 0-3 and 3-1 are 2 km long, and the
edge 1-5 is 1 km long.

Example of the classes in stage 3: the road 0-1-2-3-4 has edges of 1 km, both ways. It
is a motorway from node 0 to node 2, and a primary road from node 2 to node 4. Node 2
has two motorway edges and two primary edges, so it is kept. The nodes 1 and 3 are
removed. The contracted edges between 0 and 2 are motorway edges of 2 km, and the
contracted edges between 2 and 4 are primary edges of 2 km. A node is removed only when
all its edges have one class. With a primary edge from 2 to 1 only, node 1 is kept too.

HOW A PIECE IS SPLIT

A piece is split when one of its edges is a parallel edge. A two-way piece is split in
both directions. The middle of a piece with `k` shape points is its shape point number
`k // 2`, counted from 0. The middle of a piece without a shape point is the point
halfway between its two ends. The new node is at the middle. Each half has the class and
the direction of the piece. The polyline of a half is the line through its two ends and
its shape points. The two halves share the length of the piece in proportion to the
great-circle lengths of their polylines. The new nodes get the ids below zero and below
every id of the pieces: -1, then -2, when no piece has a negative id.

Example: the primary road above goes from junction 10 at (0, 0) to junction 20 at
(0, 0.03). Its shape points are (0.01, 0.01), (0.01, 0.015) and (0.01, 0.02). Its
middle is shape point number 1, (0.01, 0.015). The half from 10 keeps the shape point
(0.01, 0.01), and the half to 20 keeps (0.01, 0.02). The polylines of the two halves
have the same length, so each half is 2 km long.

WHY THE RESULT IS RIGHT

The two halves of a split piece have its length together, so stage 1 does not change the
length of a route. Each half has the new node at one end, and no other piece has this
node. So the second run of `build_csr_from_edges` drops no half.

A pass-through node offers no choice, so stage 3 does not change the length of a route
between two kept nodes. Stage 3 never makes an edge from a node to itself, nor a second
edge between two nodes. When a chain would give one, the function keeps the middle
node of the chain. So stage 3 keeps the new node of a split piece: the kept edge already
joins the two ends of its chain.

Example: the chains 0-1-3 and 0-2-3 would give two edges from 0 to 3. The first chain
loses node 1. The second chain keeps node 2.

THE C++ VERSION

`build_csr_from_edges`, `find_strongly_connected_components` and `contract_chains` have a C++ version
(`cpp/src/network_assembly.hpp`), which a network of the planet needs. The functions of this module call them when the extension
is built and the inputs are `array` or `memoryview` buffers. The pure-Python versions
give the same results. The namespace `python` of this module gives them, for example
`network_assembly.python.contract_chains`. The C++ version returns memoryviews, and the Python
version returns `array`s.

`scgraph.helpers.components` holds the functions of strongly connected components.
"""

import logging
import math
from array import array
from bisect import bisect_left
from collections.abc import Sequence
from functools import reduce
from itertools import accumulate
from operator import add
from types import SimpleNamespace
from typing import NamedTuple

# The C++ kernels take typed buffers only, so each call chooses its kernel.
try:
    from scgraph.cpp import (
        build_csr_from_edges as _cpp_build_csr_from_edges,
        contract_chains as _cpp_contract_chains,
    )
except ImportError:
    _cpp_build_csr_from_edges = None
    _cpp_contract_chains = None

from scgraph.array_views import ExternalNodeIds
from scgraph.coordinates import UNITS_PER_DEGREE
from scgraph.helpers.components import (
    build_csr_from_adjacency_list,
    find_strongly_connected_components as find_strongly_connected_components,
    find_strongly_connected_components_python,
    keep_strongly_connected_components,
)
from scgraph.helpers.douglas_peucker import (
    simplify_shapes as simplify_shapes_python,
)
from scgraph.helpers.hilbert import hilbert_key
from scgraph.helpers.polylines import PieceArrays
from scgraph.utils import haversine
from scgraph.array_checks import is_sorted_from_zero
from scgraph.step_logs import log_step
from scgraph.turn_restrictions import (
    add_junction_nodes,
    list_junctions_with_several_nodes,
)

# The steps of a build log under one logger name, wherever their module is.
logger = logging.getLogger("scgraph.pipelines")


def build_csr_from_edges_python(
    origins: Sequence[int],
    destinations: Sequence[int],
    weights: Sequence[int | float],
    edge_class_ids: Sequence[int] | None = None,
) -> tuple[array, array, array, array, array, array]:
    """Pure-Python version of `build_csr_from_edges`."""
    if not len(origins) == len(destinations) == len(weights) or (
        edge_class_ids is not None and len(edge_class_ids) != len(origins)
    ):
        raise ValueError(
            "expected one destination, one weight and one class for each edge"
        )
    best = (
        {}
    )  # (origin, destination) -> input index of the shortest edge so far
    for i, edge in enumerate(zip(origins, destinations)):
        if (
            edge[0] != edge[1]
            and weights[i] < weights[best.setdefault(edge, i)]
        ):
            best[edge] = i
    # (origin, destination, class) -> input index of the shortest edge so far
    best_of_class = {}
    classes = () if edge_class_ids is None else edge_class_ids
    for i, edge in enumerate(zip(origins, destinations, classes)):
        if (
            edge[0] != edge[1]
            and weights[i] < weights[best_of_class.setdefault(edge, i)]
        ):
            best_of_class[edge] = i
    parallel_edges = sorted(
        i for edge, i in best_of_class.items() if best[edge[:2]] != i
    )
    external_node_ids = array("q", sorted({id for edge in best for id in edge}))
    position = {id: u for u, id in enumerate(external_node_ids)}
    rows = [[] for _ in external_node_ids]
    for (origin, destination), i in best.items():
        rows[position[origin]].append((position[destination], i))
    node_first_edge_ids, edge_destination_node_ids, kept = (
        array("i", [0]),
        array("i"),
        array("i"),
    )
    for row in rows:
        for destination_id, i in sorted(row):
            edge_destination_node_ids.append(destination_id)
            kept.append(i)
        node_first_edge_ids.append(len(edge_destination_node_ids))
    return (
        external_node_ids,
        node_first_edge_ids,
        edge_destination_node_ids,
        array("d", (weights[i] for i in kept)),
        kept,
        array("i", parallel_edges),
    )


def build_csr_from_edges(
    origins: array | memoryview,
    destinations: array | memoryview,
    weights: array | memoryview,
    edge_class_ids: array | memoryview | None = None,
) -> tuple[
    array | memoryview,
    array | memoryview,
    array | memoryview,
    array | memoryview,
    array | memoryview,
    array | memoryview,
]:
    """Store edges by origin, in CSR arrays.

    Args:
        origins: The id of the origin of each edge in its source (int64).
        destinations: The id of the destination of each edge (int64).
        weights: The length of each edge (float64).
        edge_class_ids: The id of the class of each edge (uint8), or None for edges
            without classes.

    Returns:
        `(external_node_ids, node_first_edge_ids, edge_destination_node_ids, weights, kept, parallel_edges)`.
        `external_node_ids` (int64) lists the ids of the ends, sorted, each once. Node `u`
        is the id at position `u`. The edges of node `u` are
        `edge_destination_node_ids[node_first_edge_ids[u]:node_first_edge_ids[u + 1]]` (int32),
        sorted by destination id, with their `weights`. `kept[a]` (int32) is the input index of
        edge `a`: the caller finds the shape of the edge with it. The function drops an
        edge from a node to itself, and an id that has only such edges gives no node.
        Of several edges between the same two nodes, the function keeps the shortest,
        and the first of the input when two are as short. `parallel_edges` (int32)
        lists the input indices of the parallel edges, in rising order. A parallel edge
        is the shortest edge of its class between its two nodes, by the same rule, and
        it is not the kept edge. Without `edge_class_ids`, `parallel_edges` is empty.
    """
    if _cpp_build_csr_from_edges is not None and isinstance(
        origins, (array, memoryview)
    ):
        return _cpp_build_csr_from_edges(
            origins, destinations, weights, edge_class_ids
        )
    return build_csr_from_edges_python(
        origins, destinations, weights, edge_class_ids
    )


class ContractedGraph(NamedTuple):
    """The result of `contract_chains`.

    Attributes:
        kept: The nodes of the input graph that stay, in rising order.
        origins: The origin of each contracted edge, as a position in `kept`.
        edge_destination_node_ids: The destination id of each contracted edge, as a position in `kept`.
        weights: The length of each contracted edge in km: the sum of its members.
        member_offsets: Where the members of each contracted edge start in `members`.
        members: The edges of the input graph that each contracted edge replaces, in
            travel order. The members of edge `i` are
            `members[member_offsets[i]:member_offsets[i + 1]]`.
    """

    kept: array | memoryview
    origins: array | memoryview
    edge_destination_node_ids: array | memoryview
    weights: array | memoryview
    member_offsets: array | memoryview
    members: array | memoryview


def contract_chains_python(
    node_first_edge_ids: Sequence[int],
    edge_destination_node_ids: Sequence[int],
    weights: Sequence[int | float],
    node_mode_ids: Sequence[int] | None = None,
    max_km_between_nodes: float = math.inf,
    edge_class_ids: Sequence[int] | None = None,
    kept_node_flags: Sequence[int] | None = None,
) -> ContractedGraph:
    """Pure-Python version of `contract_chains`."""
    n = len(node_first_edge_ids) - 1
    if (
        len(weights) != len(edge_destination_node_ids)
        or (node_mode_ids is not None and len(node_mode_ids) != n)
        or (kept_node_flags is not None and len(kept_node_flags) != n)
        or (
            edge_class_ids is not None
            and len(edge_class_ids) != len(edge_destination_node_ids)
        )
    ):
        raise ValueError(
            "expected one weight and one class per edge, and one node mode per node"
        )
    if (
        n < 0
        or node_first_edge_ids[n] != len(edge_destination_node_ids)
        or not is_sorted_from_zero(node_first_edge_ids)
    ):
        raise ValueError(
            "node_first_edge_ids must rise from 0 to the number of items"
        )
    rows = [
        edge_destination_node_ids[
            node_first_edge_ids[u] : node_first_edge_ids[u + 1]
        ]
        for u in range(n)
    ]
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
        same = node_mode_ids is None or all(
            node_mode_ids[x] == node_mode_ids[v] for x in out + inn
        )
        return (
            (two_way or one_way)
            and same
            and (edge_class_ids is None or has_one_class(v, inn))
            and not (kept_node_flags is not None and kept_node_flags[v])
        )

    def has_one_class(v, inn):
        # The edges that leave v, then the edge that enters v from each node of inn
        edges = [
            *range(node_first_edge_ids[v], node_first_edge_ids[v + 1]),
            *(node_first_edge_ids[u] + bisect_left(rows[u], v) for u in inn),
        ]
        return len({edge_class_ids[a] for a in edges}) == 1

    def contract(s, a):
        nodes, path = [s], [a]  # walk to the next kept node
        while not keep[edge_destination_node_ids[path[-1]]]:
            v = edge_destination_node_ids[path[-1]]
            row, seen[v] = rows[v], True
            nodes.append(v)
            path.append(
                node_first_edge_ids[v] + (len(row) == 2 and row[0] == nodes[-2])
            )
        nodes.append(edge_destination_node_ids[path[-1]])
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
                    node_first_edge_ids[nodes[k + 1]]
                    + bisect_left(rows[nodes[k + 1]], nodes[k])
                    for k in range(i, j)
                ]
                emit(e, b, back[::-1], back)

    def emit(u, v, members, canonical):
        # Summed in order from the canonical end, as C++ does (sum() compensates
        # since Python 3.12)
        km = reduce(add, (weights[a] for a in canonical), 0.0)
        edges.append((u, v, km, members))
        pairs.add((u, v))

    def exists(u, v):  # an input edge, or an edge made
        return (u, v) in pairs or v in rows[u]

    chain = [through(v) for v in range(n)]
    keep, seen = [not c for c in chain], [False] * n
    edges = [
        (u, edge_destination_node_ids[a], weights[a], [a])
        for u in range(n)
        for a in range(node_first_edge_ids[u], node_first_edge_ids[u + 1])
        if keep[u] and keep[edge_destination_node_ids[a]]
    ]
    pairs = set()  # (origin, destination id) of the edges made by contraction
    for s in range(n):
        for a in range(node_first_edge_ids[s], node_first_edge_ids[s + 1]):
            if (
                not chain[s]
                and chain[edge_destination_node_ids[a]]
                and not seen[edge_destination_node_ids[a]]
            ):
                contract(s, a)
    for v in range(n):
        if chain[v] and not seen[v]:
            keep[v] = seen[v] = True
            contract(v, node_first_edge_ids[v])
    kept = array("i", (v for v in range(n) if keep[v]))
    position = {v: i for i, v in enumerate(kept)}
    edges.sort(key=lambda edge_: edge_[:2])
    return ContractedGraph(
        kept,
        array("i", (position[edge_[0]] for edge_ in edges)),
        array("i", (position[edge_[1]] for edge_ in edges)),
        array("d", (edge_[2] for edge_ in edges)),
        array("i", accumulate((len(edge_[3]) for edge_ in edges), initial=0)),
        array("i", (a for edge_ in edges for a in edge_[3])),
    )


def contract_chains(
    node_first_edge_ids: array | memoryview,
    edge_destination_node_ids: array | memoryview,
    weights: array | memoryview,
    node_mode_ids: array | memoryview | None = None,
    max_km_between_nodes: float = math.inf,
    edge_class_ids: array | memoryview | None = None,
    kept_node_flags: bytes | array | memoryview | None = None,
) -> ContractedGraph:
    """Contract the chains of pass-through nodes of a graph.

    The module docstring (*How a run goes*, stage 3) gives the rule and an example. The
    function walks a chain from its canonical end: the start of a one-way chain, or the
    end with the lower index. A part of a chain that would give an edge from a node to
    itself, or a second edge between two nodes, is split at its middle node. A cycle of
    pass-through nodes is walked from its lowest node, which is kept.

    Args:
        node_first_edge_ids: For each node, the id of its first edge, and one more
            value at the end: the count of the edges (int32).
        edge_destination_node_ids: The destination id of each edge (int32).
        weights: The length of each edge in km (float64).
        node_mode_ids: The node mode of each node (uint8), or None. A chain is never
            contracted across two node modes.
        max_km_between_nodes: The length in km at which a chain is cut. Along the chain,
            an edge ends at the first node where it is this long or longer. So an edge
            can be longer than this value, by less than the length of one input edge.
        edge_class_ids: The class of each edge (uint8), or None.
        kept_node_flags: One byte for each node, or None. A node with a byte other
            than 0 is never removed. `assemble_network` gives 1 to each node of a
            junction with several nodes (`scgraph.turn_restrictions`).

    Returns:
        A `ContractedGraph`.
    """
    if _cpp_contract_chains is not None and isinstance(
        node_first_edge_ids, (array, memoryview)
    ):
        return ContractedGraph(
            *_cpp_contract_chains(
                node_first_edge_ids,
                edge_destination_node_ids,
                weights,
                node_mode_ids,
                max_km_between_nodes,
                edge_class_ids,
                kept_node_flags,
            )
        )
    return contract_chains_python(
        node_first_edge_ids,
        edge_destination_node_ids,
        weights,
        node_mode_ids=node_mode_ids,
        max_km_between_nodes=max_km_between_nodes,
        edge_class_ids=edge_class_ids,
        kept_node_flags=kept_node_flags,
    )


def _list_edges(pieces, skipped=frozenset()):
    """List the edges of `pieces`: two for a two-way piece, and one for a one-way piece
    in its direction. A piece of `skipped` gives no edge.

    Returns:
        Six arrays, with one value for each edge: the index of its piece, 1 if it goes
        against its piece and 0 otherwise, the id of its origin, the id of its
        destination, its length in km, and the id of its class. The last one is None
        when the pieces have no class.
    """
    piece, back = array("i"), array("b")
    for i, direction in enumerate(pieces.directions):
        if i in skipped:
            continue
        for reverse in (0, 1) if direction == 0 else (int(direction < 0),):
            piece.append(i)
            back.append(reverse)
    ends, class_ids = (pieces.origins, pieces.destinations), None
    if len(pieces.class_ids):
        class_ids = array("B", (pieces.class_ids[i] for i in piece))
    return [
        piece,
        back,
        array("q", (ends[b][i] for i, b in zip(piece, back))),
        array("q", (ends[1 - b][i] for i, b in zip(piece, back))),
        array("d", (pieces.km[i] for i in piece)),
        class_ids,
    ]


def _split_pieces(pieces, split_pieces, first_new_id):
    """Split pieces in two halves, by the rule of the module docstring (*How a piece is
    split*).

    Args:
        pieces: The pieces, with their classes.
        split_pieces: The indices of the pieces to split.
        first_new_id: The id of the new node of the first split piece. Each next new
            node gets the id below.

    Returns:
        The halves, as pieces kept in memory. The pieces `2 * j` and `2 * j + 1` are the
        halves of piece `split_pieces[j]`: from its origin to the new node, then from the new
        node to its destination.
    """
    halves = PieceArrays(tolerance_meters=None)
    for j, i in enumerate(split_pieces):
        first, last = (
            pieces.piece_first_shape_point_ids[i],
            pieces.piece_first_shape_point_ids[i + 1],
        )
        units = [  # the latitude, then the longitude of each point, in 1e-7 degree
            *pieces.ends[4 * i : 4 * i + 2],
            *pieces.points[2 * first : 2 * last],
            *pieces.ends[4 * i + 2 : 4 * i + 4],
        ]
        # The points of the piece in degrees: its origin, its shape points, its
        # destination
        line = [
            [latitude / UNITS_PER_DEGREE, longitude / UNITS_PER_DEGREE]
            for latitude, longitude in zip(units[0::2], units[1::2])
        ]
        if len(line) == 2:
            # No shape point: the middle is the point halfway between the two ends
            line.insert(1, [(a + b) / 2 for a, b in zip(*line)])
        middle = len(line) // 2  # shape point number k // 2 is point 1 + k // 2
        lengths = [haversine(p, q) for p, q in zip(line, line[1:])]
        # fsum gives the same sum on every version of Python
        total, km = math.fsum(lengths), pieces.km[i]
        first_km = km * math.fsum(lengths[:middle]) / total if total else km / 2
        new_id, direction = first_new_id - j, pieces.directions[i]
        class_id = pieces.class_ids[i]
        way_id = pieces.way_ids[i] if len(pieces.way_ids) else None
        halves.append(
            pieces.origins[i],
            new_id,
            first_km,
            direction,
            [line[0], line[middle]],
            line[1:middle],
            class_id,
            way_id,
        )
        halves.append(
            new_id,
            pieces.destinations[i],
            km - first_km,
            direction,
            [line[middle], line[-1]],
            line[middle + 1 : -1],
            class_id,
            way_id,
        )
    halves.flush()
    return halves


def build_graph_from_pieces(
    pieces: PieceArrays,
) -> dict[str, array | memoryview]:
    """Build a graph from the pieces of ways.

    A two-way piece gives two edges, and a one-way piece gives one edge in its
    direction. Of several edges between the same two nodes, the shortest is kept. In a
    graph with classes, the piece of the shortest edge of each other class is split in
    two halves, with a new node between them. The module docstring gives the rule
    (*How a run goes*, stage 1, and *How a piece is split*).

    Args:
        pieces: The pieces, as `scgraph.helpers.osm.build_way_pieces` or `step2_hub_connectors.join_networks_at_hubs` fill them.

    Returns:
        The graph as a dict of arrays: `node_first_edge_ids`, `edge_destination_node_ids`, `metric_length`,
        `node_points`, `edge_first_shape_point_ids`, `shape_points` and `external_node_ids`, and
        `edge_class_ids` when the pieces have classes. The module docstring describes
        them. When the pieces have way ids, `edge_way_ids` gives the id of the way
        of each edge. It is not an array of a network file: the caller removes it
        when the turn restrictions are applied.

    Raises:
        ValueError: Every piece joins a node to itself. Or some pieces have a class
            and the others have none.
    """
    pieces.flush()
    if len(pieces.class_ids) not in (0, len(pieces.km)):
        raise ValueError("Some pieces have a class and the others have none")
    piece, back, *columns = _list_edges(pieces)
    (
        external_node_ids,
        node_first_edge_ids,
        edge_destination_node_ids,
        weights,
        kept,
        parallel_edges,
    ) = build_csr_from_edges(*columns)
    if not len(external_node_ids):
        raise ValueError("The pieces join no two points: every one is a loop")
    # The new nodes get the ids below zero and below every id of the pieces. The
    # ids are sorted, so the first one is the lowest.
    split_pieces = sorted({piece[e] for e in parallel_edges})
    halves = _split_pieces(
        pieces,
        split_pieces,
        ExternalNodeIds.get_first_added_id(external_node_ids[0]),
    )
    # The edges below this index are edges of `pieces`. The others are edges of `halves`.
    first_edge_of_halves = len(piece)
    if split_pieces:
        # The edges are stored again, with the halves in place of the split pieces.
        # This run gets no classes, so it splits nothing more. With classes, the
        # second shortest edge of the class of a split piece would be parallel.
        piece = back = columns = None  # freed before the edges are listed again
        piece, back, *columns = _list_edges(pieces, set(split_pieces))
        first_edge_of_halves = len(piece)
        for column, more in zip((piece, back, *columns), _list_edges(halves)):
            column.extend(more)
        (
            external_node_ids,
            node_first_edge_ids,
            edge_destination_node_ids,
            weights,
            kept,
            _,
        ) = build_csr_from_edges(*columns[:3])
    node_points = array("i", bytes(8 * len(external_node_ids)))
    points, edge_first_shape_point_ids = array("i"), array("i", [0])
    edge_way_ids = array("q")
    for u in range(len(external_node_ids)):
        for a in range(node_first_edge_ids[u], node_first_edge_ids[u + 1]):
            i, b = piece[kept[a]], back[kept[a]]
            source_pieces = pieces if kept[a] < first_edge_of_halves else halves
            if len(pieces.way_ids):
                edge_way_ids.append(source_pieces.way_ids[i])
            e = source_pieces.ends[4 * i : 4 * i + 4]
            # e holds the points of the two ends of the piece, in the order of the
            # piece. For an edge that goes against the piece, the ends swap.
            origin, destination = (e[2:], e[:2]) if b else (e[:2], e[2:])
            v = edge_destination_node_ids[a]
            node_points[2 * u], node_points[2 * u + 1] = origin
            node_points[2 * v], node_points[2 * v + 1] = destination
            first, last = (
                source_pieces.piece_first_shape_point_ids[i],
                source_pieces.piece_first_shape_point_ids[i + 1],
            )
            line = array("i", source_pieces.points[2 * first : 2 * last])
            if b:  # its points from the destination
                line[0::2], line[1::2] = line[-2::-2], line[-1::-2]
            points.extend(line)
            edge_first_shape_point_ids.append(len(points) // 2)
    graph = {
        "node_first_edge_ids": node_first_edge_ids,
        "edge_destination_node_ids": edge_destination_node_ids,
        "metric_length": weights,
        "node_points": node_points,
        "edge_first_shape_point_ids": edge_first_shape_point_ids,
        "shape_points": points,
        "external_node_ids": external_node_ids,
    }
    if columns[3] is not None:
        graph["edge_class_ids"] = array("B", (columns[3][i] for i in kept))
    if edge_way_ids:
        graph["edge_way_ids"] = edge_way_ids
    return graph


def assemble_network(
    graph: dict[str, array | memoryview],
    *,
    max_km_between_nodes: float,
    min_component_nodes: int | None,
) -> dict[str, array]:
    """Turn a graph into the arrays of a network file.

    The function runs stages 2 to 5 of the module docstring. It keeps the strongly
    connected components (`keep_components`), contracts the chains, joins the shapes
    of the contracted edges, and numbers the nodes (`order_nodes`). The stage that
    keeps the components and the stage that contracts the chains log their counts
    at DEBUG.

    Args:
        graph: The graph, as `build_graph_from_pieces` returns it, with `node_mode_ids`
            if it has several node modes. The function empties this dict, to free it.
        max_km_between_nodes: The length in km at which `contract_chains` cuts a chain.
        min_component_nodes: The smallest number of nodes of a kept component. None keeps
            only the largest component.

    Returns:
        The arrays of the network file, as `network_file.write` takes them, and
        `node_mode_ids` if the graph has several node modes.
    """
    graph = keep_components(graph, min_component_nodes)
    with log_step(
        logger, "contract the chains", count_nodes_and_edges(graph)
    ) as counts:
        node_mode_ids, edge_class_ids = graph.get("node_mode_ids"), graph.get(
            "edge_class_ids"
        )
        (
            kept,
            origins,
            edge_destination_node_ids,
            weights,
            member_offsets,
            members,
        ) = contract_chains(
            graph["node_first_edge_ids"],
            graph["edge_destination_node_ids"],
            graph["metric_length"],
            node_mode_ids=node_mode_ids,
            max_km_between_nodes=max_km_between_nodes,
            edge_class_ids=edge_class_ids,
            kept_node_flags=_flag_junctions_with_several_nodes(graph),
        )
        points, edge_first_shape_point_ids = build_chain_shapes(
            graph, member_offsets, members
        )
        node_first_edge_ids = array("i", bytes(4 * (len(kept) + 1)))
        for u in origins:  # rows by origin, as contract_chains sorts them
            node_first_edge_ids[u + 1] += 1
        graph = {  # the graph before contraction is freed
            "node_first_edge_ids": array("i", accumulate(node_first_edge_ids)),
            "edge_destination_node_ids": edge_destination_node_ids,
            "metric_length": weights,
            "edge_first_shape_point_ids": edge_first_shape_point_ids,
            "shape_points": points,
            **_select_nodes(graph, kept),
        }
        if edge_class_ids is not None:  # the members of an edge have one class
            graph["edge_class_ids"] = array(
                "B", (edge_class_ids[members[i]] for i in member_offsets[:-1])
            )
        counts.update(count_nodes_and_edges(graph, "kept_"))
    return order_nodes(graph)


def forbid_turns(
    graph: dict[str, array | memoryview], forbidden_turns: list[list[int]]
) -> dict[str, array | memoryview]:
    """Add to a graph the nodes that make it follow forbidden turns
    (`scgraph.turn_restrictions` explains the method). The function logs its counts
    at DEBUG.

    Args:
        graph: The graph, as `build_graph_from_pieces` returns it, with
            `node_mode_ids` if it has several node modes.
        forbidden_turns: The forbidden turns, each as a list of three node ids or
            more.

    Returns:
        The graph with the added nodes. An added node comes right after the node of
        its junction. It has the point, the external id and the node mode of this
        node. Each edge of the new graph has the length, the class and the shape of
        the edge of `graph` between the same two points. Without a forbidden turn,
        the function returns `graph` itself.
    """
    if not forbidden_turns:
        return graph
    with log_step(
        logger,
        "forbid the turns",
        {
            "forbidden_turns": len(forbidden_turns),
            **count_nodes_and_edges(graph),
        },
    ) as counts:
        (
            node_first_edge_ids,
            edge_destination_node_ids,
            given_node_ids,
            given_edge_ids,
        ) = add_junction_nodes(
            graph["node_first_edge_ids"],
            graph["edge_destination_node_ids"],
            forbidden_turns,
        )
        starts, line = (
            graph["edge_first_shape_point_ids"],
            graph["shape_points"],
        )
        edge_first_shape_point_ids, shape_points = array("i", [0]), array("i")
        for edge_id in given_edge_ids:
            shape_points.extend(
                line[2 * starts[edge_id] : 2 * starts[edge_id + 1]]
            )
            edge_first_shape_point_ids.append(len(shape_points) // 2)
        new = {
            "node_first_edge_ids": node_first_edge_ids,
            "edge_destination_node_ids": edge_destination_node_ids,
            "metric_length": array(
                "d", (graph["metric_length"][e] for e in given_edge_ids)
            ),
            "edge_first_shape_point_ids": edge_first_shape_point_ids,
            "shape_points": shape_points,
        }
        if "edge_class_ids" in graph:
            new["edge_class_ids"] = array(
                "B", (graph["edge_class_ids"][e] for e in given_edge_ids)
            )
        new.update(_select_nodes(graph, given_node_ids))
        counts.update(count_nodes_and_edges(new, "new_"))
    return new


def _flag_junctions_with_several_nodes(graph):
    """Return one byte for each node of `graph`: 1 for a node of a junction with
    several nodes (`scgraph.turn_restrictions`), and 0 for any other node. Return
    None when no junction has several nodes.
    """
    flags = bytearray(len(graph["external_node_ids"]))
    for junction in list_junctions_with_several_nodes(
        graph["external_node_ids"], graph.get("node_mode_ids")
    ):
        flags[junction.start : junction.stop] = bytes([1]) * len(junction)
    return array("B", flags) if any(flags) else None


def keep_junctions_whole(
    graph: dict[str, array | memoryview],
    kept_nodes: array | memoryview,
    labels: array | memoryview,
) -> tuple[array, array]:
    """Add to the kept nodes the other nodes of each junction that has a kept node
    (`scgraph.turn_restrictions`). A route may start at the first node of a
    junction, even when no edge enters this node.

    Args:
        graph: The graph, with `external_node_ids`.
        kept_nodes: The kept nodes, as `keep_strongly_connected_components`
            returns them.
        labels: The number of the component of each node, from the same call.

    Returns:
        `(kept_nodes, labels)` with the nodes that the function adds. Such a node
        gets the label of the first kept node of its junction. So
        `renumber_nodes` keeps its edges to the kept nodes of this component.
    """

    junctions = list_junctions_with_several_nodes(
        graph["external_node_ids"], graph.get("node_mode_ids")
    )
    if not junctions:
        return kept_nodes, labels
    labels, is_kept = array("i", labels), bytearray(len(labels))
    for node_id in kept_nodes:
        is_kept[node_id] = 1
    for junction in junctions:
        kept_node_id = next((u for u in junction if is_kept[u]), None)
        if kept_node_id is not None:
            for node_id in junction:
                if not is_kept[node_id]:
                    is_kept[node_id] = 1
                    labels[node_id] = labels[kept_node_id]
    return array("i", (u for u, kept in enumerate(is_kept) if kept)), labels


def keep_components(
    graph: dict[str, array | memoryview], min_component_nodes: int | None
) -> dict[str, array]:
    """Keep the strongly connected components of a graph (stage 2 of the module
    docstring). The function logs its counts at DEBUG.

    Args:
        graph: The graph, as `build_graph_from_pieces` returns it. The function
            empties this dict, to free it.
        min_component_nodes: The smallest number of nodes of a kept component. None
            keeps only the largest component.

    Returns:
        The graph of the kept nodes, with the edges between two nodes of one
        component. A junction with a node in a kept component keeps all its nodes
        (`scgraph.turn_restrictions`).
    """
    with log_step(
        logger,
        "keep the strongly connected components",
        count_nodes_and_edges(graph),
    ) as counts:
        kept_nodes, labels = keep_junctions_whole(
            graph,
            *keep_strongly_connected_components(
                graph["node_first_edge_ids"],
                graph["edge_destination_node_ids"],
                min_component_nodes,
            ),
        )
        given, graph = graph, renumber_nodes(graph, kept_nodes, labels)
        given.clear()  # freed now, not when the caller lets it go: one copy at a time
        counts.update(count_nodes_and_edges(graph, "kept_"))
    return graph


def order_nodes(graph: dict[str, array | memoryview]) -> dict[str, array]:
    """Number the nodes of a graph by node mode, then along the Hilbert curve (stage 5
    of the module docstring). A network file has this order. `hilbert_key` gives
    the key of a node, here and in `GeoGraph.save_as_scgraph`.

    Args:
        graph: The graph, with `node_mode_ids` if it has several node modes.

    Returns:
        The graph with its nodes in the new order.
    """
    node_points = memoryview(graph["node_points"])
    latitudes, longitudes = node_points[0::2], node_points[1::2]
    node_count = len(latitudes)
    node_mode_ids = graph.get("node_mode_ids") or bytes(node_count)

    def key(u):  # the key of a network file, then the node id: one int
        return (
            hilbert_key(
                latitudes[u] / UNITS_PER_DEGREE,
                longitudes[u] / UNITS_PER_DEGREE,
                node_mode_ids[u],
            )
            << 32
            | u
        )

    # One int per node, not a list; the sorted ints are freed before renumber_nodes
    keys = sorted(map(key, range(node_count)))
    order, keys = array("i", (k & 0xFFFFFFFF for k in keys)), None
    return renumber_nodes(graph, order)


def build_chain_shapes(
    graph: dict[str, array | memoryview],
    member_offsets: Sequence[int],
    members: Sequence[int],
) -> tuple[array, array]:
    """Build the shape of each contracted edge.

    The shape holds the shape points of each member, in travel order. Between two
    members, it holds the point of the node that the contraction removed.

    Returns:
        `(points, edge_first_shape_point_ids)`, as `shape_points` and `edge_first_shape_point_ids` of a graph.
    """
    edge_destination_node_ids, node_points = (
        graph["edge_destination_node_ids"],
        graph["node_points"],
    )
    starts, line = graph["edge_first_shape_point_ids"], graph["shape_points"]
    points, edge_first_shape_point_ids = array("i"), array("i", [0])
    for i in range(len(member_offsets) - 1):
        chain = members[member_offsets[i] : member_offsets[i + 1]]
        for k, a in enumerate(chain):
            if k:
                node = edge_destination_node_ids[chain[k - 1]]
                points.extend(node_points[2 * node : 2 * node + 2])
            points.extend(line[2 * starts[a] : 2 * starts[a + 1]])
        edge_first_shape_point_ids.append(len(points) // 2)
    return points, edge_first_shape_point_ids


def _select_nodes(graph, nodes):
    """Copy the arrays of `graph` that describe the nodes, for the nodes listed in
    `nodes` only. Node `nodes[i]` becomes node `i`.

    The arrays are `node_points`, then `external_node_ids` and `node_mode_ids` if `graph`
    has them. `network_file.write` writes the arrays in the order of the returned dict.
    This order is fixed, so every run writes the same file.
    """
    # One view holds the latitudes and another the longitudes, without a copy.
    # Reading a value from a view is as fast as reading it from an array.
    node_points = memoryview(graph["node_points"])
    latitudes, longitudes = node_points[0::2], node_points[1::2]
    points = array("i", bytes(8 * len(nodes)))
    points[0::2] = array("i", (latitudes[u] for u in nodes))
    points[1::2] = array("i", (longitudes[u] for u in nodes))
    selected = {"node_points": points}
    for key, typecode in (("external_node_ids", "q"), ("node_mode_ids", "B")):
        if key in graph:
            selected[key] = array(typecode, (graph[key][u] for u in nodes))
    return selected


def renumber_nodes(graph, order, labels=None):
    """Return `graph` with the nodes of `order` only. Node `order[i]` becomes node `i`, and
    the edges of each node are sorted by destination id. With `labels`, an edge is kept only when
    its two ends have the same label. A kept edge keeps its shape, and its class if
    `graph` has `edge_class_ids`.
    """
    new = array("i", [-1]) * (len(graph["node_first_edge_ids"]) - 1)
    for i, u in enumerate(order):
        new[u] = i
    node_first_edge_ids, edge_destination_node_ids, weights = (
        graph[key]
        for key in (
            "node_first_edge_ids",
            "edge_destination_node_ids",
            "metric_length",
        )
    )
    starts, line = graph["edge_first_shape_point_ids"], graph["shape_points"]
    out = {
        "node_first_edge_ids": array("i", [0]),
        "edge_destination_node_ids": array("i"),
        "metric_length": array("d"),
    }
    out["edge_first_shape_point_ids"], out["shape_points"] = array(
        "i", [0]
    ), array("i")
    edge_class_ids = graph.get("edge_class_ids")
    if edge_class_ids is not None:
        out["edge_class_ids"] = array("B")
    for u in order:
        for v, a in sorted(
            (new[edge_destination_node_ids[a]], a)
            for a in range(node_first_edge_ids[u], node_first_edge_ids[u + 1])
        ):
            if v >= 0 and (
                labels is None
                or labels[u] == labels[edge_destination_node_ids[a]]
            ):
                out["edge_destination_node_ids"].append(v)
                out["metric_length"].append(weights[a])
                out["shape_points"].extend(
                    line[2 * starts[a] : 2 * starts[a + 1]]
                )
                out["edge_first_shape_point_ids"].append(
                    len(out["shape_points"]) // 2
                )
                if edge_class_ids is not None:
                    out["edge_class_ids"].append(edge_class_ids[a])
        out["node_first_edge_ids"].append(len(out["edge_destination_node_ids"]))
    return {**out, **_select_nodes(graph, order)}


def count_nodes_and_edges(graph: dict, prefix: str = "") -> dict[str, int]:
    """The number of nodes and the number of edges of `graph`, as the values of a log:
    `nodes` and `edges`, each with `prefix` before it."""
    return {
        f"{prefix}nodes": len(graph["node_first_edge_ids"]) - 1,
        f"{prefix}edges": len(graph["edge_destination_node_ids"]),
    }


python = SimpleNamespace(
    build_csr_from_adjacency_list=build_csr_from_adjacency_list,
    build_csr_from_edges=build_csr_from_edges_python,
    find_strongly_connected_components=find_strongly_connected_components_python,
    contract_chains=contract_chains_python,
    simplify_shapes=simplify_shapes_python,
)
