"""Assemble the graph of a network from the pieces of its ways.

WHAT IT ANSWERS

`build_graph_from_pieces` turns the pieces that `step1_osm_ways` cut (`PieceArrays`) into a
graph. `assemble_network` turns this graph into the arrays of a network file. A route between
two nodes of the same kept component has the same length before and after `assemble_network`.

HOW A GRAPH IS STORED

A graph is a dict of arrays, with the names of the network file. Node `u` has the edges
`offsets[u]` to `offsets[u + 1] - 1`. Edge `a` goes to node `heads[a]` and is
`weights_length[a]` km long. `node_points` holds the latitude, then the longitude of each
node, in units of 1e-7 degree. The shape points of edge `a` are
`shape_points[2 * shape_offsets[a]:2 * shape_offsets[a + 1]]`. `source_node_ids` holds
the id of each node in its source. A node that step 1 adds has an id below zero.
The node mode of a node is the kind of place where the node is, such as `port`.
`node_mode_ids` holds the node mode id of each node, in a graph of several node modes.

`edge_class_ids`, if the pieces have classes, holds the id of the class of each edge in the classes
table (`scgraph.pipelines.CLASSES`).

Example: two nodes joined both ways by a trunk road of 1.5 km give
`offsets = [0, 1, 2]`, `heads = [1, 0]` and `weights_length = [1.5, 1.5]`. `trunk` has
the id 2 in the classes table, so `edge_class_ids = [2, 2]`.

HOW A RUN GOES

1. `build_graph_from_pieces` makes one edge from a one-way piece and two edges from a
   two-way piece. An edge has the class of its piece. `build_csr_from_edges` stores the
   edges by origin. It drops an edge from a node to itself. Of several edges between the
   same two nodes, it keeps the shortest. In a graph with classes, the shortest edge of
   each other class is a "parallel edge". `build_graph_from_pieces` splits the piece of
   each parallel edge in two halves, with a new node between them (*How a piece is
   split*). It then stores the edges again. So one edge at most goes from a node to
   another, and the shortest edge of each class stays in the graph.
2. `keep_strongly_connected_components` keeps the largest strongly connected
   component, or each component of at least a given number of nodes. In such a
   component, every node can reach every other node. An edge between two components
   is dropped.
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
   the class of its members.
4. `build_chain_shapes` gives each contracted edge the shape points of its members,
   with the removed nodes between them.
5. `assemble_network` numbers the nodes by node mode, then along a Hilbert curve. A
   network file has this order.

Example of step 1: a motorway of 3 km and a primary road of 4 km join the junctions 10
and 20, both ways. The motorway is shorter, so its two edges are kept. The two edges of
the primary road are parallel edges. The primary road is split at its middle, where the
new node -1 is. The graph has the nodes -1, 10 and 20. It has two motorway edges of 3 km
between 10 and 20. It has four primary edges of 2 km: from 10 to -1, from -1 to 20, and
their reverses. Without the split, the graph would lose the primary road.

Example of step 3: the road 0-4-3-2-1-5 has edges of 1 km, both ways, and
`max_km_between_nodes` is 2. The walk starts at node 0 and cuts at node 3, then at
node 1. The nodes 0, 1, 3 and 5 are kept. The edges 0-3 and 3-1 are 2 km long, and the
edge 1-5 is 1 km long.

Example of the classes in step 3: the road 0-1-2-3-4 has edges of 1 km, both ways. It
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

The two halves of a split piece have its length together, so step 1 does not change the
length of a route. Each half has the new node at one end, and no other piece has this
node. So the second run of `build_csr_from_edges` drops no half.

A pass-through node offers no choice, so step 3 does not change the length of a route
between two kept nodes. Step 3 never makes an edge from a node to itself, nor a second
edge between two nodes. When a chain would give one, the function keeps the middle
node of the chain. So step 3 keeps the new node of a split piece: the kept edge already
joins the two ends of its chain.

Example: the chains 0-1-3 and 0-2-3 would give two edges from 0 to 3. The first chain
loses node 1. The second chain keeps node 2.

THE C++ VERSION

`build_csr_from_edges`, `find_strongly_connected_components`, `contract_chains` and
`simplify_shapes` have a C++ version (`cpp/src/pipelines/assembly.hpp`), which a
network of the planet needs. The functions of this module call it when the extension
is built and the inputs are `array` or `memoryview` buffers. The pure-Python versions
give the same results. The namespace `python` of this module gives them, for example
`step3_network_assembly.python.contract_chains`. The C++ version returns memoryviews, and the Python
version returns `array`s.

`scgraph.helpers.components` holds the functions of strongly connected components, and
those that take the layout of a GeoGraph.
"""

import logging
import math
import mmap
import os
from array import array
from bisect import bisect_left
from collections.abc import Iterable, Sequence
from functools import reduce
from itertools import accumulate
from operator import add
from types import SimpleNamespace
from typing import NamedTuple

try:
    from scgraph.cpp import (
        build_csr_from_edges as _cpp_build_csr_from_edges,
        contract_chains as _cpp_contract_chains,
        simplify_shapes as _cpp_simplify_shapes,
    )
except ImportError:
    _cpp_build_csr_from_edges = None
    _cpp_contract_chains = None
    _cpp_simplify_shapes = None

from scgraph.helpers.components import (
    build_csr_from_adjacency_list,
    find_strongly_connected_components as find_strongly_connected_components,
    find_strongly_connected_components_python,
    keep_largest_strongly_connected_component as keep_largest_strongly_connected_component,
    keep_strongly_connected_components,
)
from scgraph.helpers.douglas_peucker import (
    simplify_shapes as simplify_shapes_python,
)
from scgraph.helpers.hilbert import CURVE_ORDER, hilbert_key
from scgraph.network_file import encode_coordinates
from scgraph.utils import haversine
from scgraph._internal import is_sorted_from_zero, log_step

logger = logging.getLogger(__name__)


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
    source_node_ids = array("q", sorted({id for edge in best for id in edge}))
    position = {id: u for u, id in enumerate(source_node_ids)}
    rows = [[] for _ in source_node_ids]
    for (origin, destination), i in best.items():
        rows[position[origin]].append((position[destination], i))
    offsets, heads, kept = array("i", [0]), array("i"), array("i")
    for row in rows:
        for head, i in sorted(row):
            heads.append(head)
            kept.append(i)
        offsets.append(len(heads))
    return (
        source_node_ids,
        offsets,
        heads,
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
        `(source_node_ids, offsets, heads, weights, kept, parallel_edges)`.
        `source_node_ids` (int64) lists the ids of the ends, sorted, each once. Node `u`
        is the id at position `u`. The edges of node `u` are
        `heads[offsets[u]:offsets[u + 1]]` (int32),
        sorted by head, with their `weights`. `kept[a]` (int32) is the input index of
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
        heads: The head of each contracted edge, as a position in `kept`.
        weights: The length of each contracted edge in km: the sum of its members.
        member_offsets: Where the members of each contracted edge start in `members`.
        members: The edges of the input graph that each contracted edge replaces, in
            travel order. The members of edge `i` are
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
    node_mode_ids: Sequence[int] | None = None,
    max_km_between_nodes: float = math.inf,
    edge_class_ids: Sequence[int] | None = None,
) -> ContractedGraph:
    """Pure-Python version of `contract_chains`."""
    n = len(offsets) - 1
    if (
        len(weights) != len(heads)
        or (node_mode_ids is not None and len(node_mode_ids) != n)
        or (edge_class_ids is not None and len(edge_class_ids) != len(heads))
    ):
        raise ValueError(
            "expected one weight and one class per edge, and one node mode per node"
        )
    if n < 0 or offsets[n] != len(heads) or not is_sorted_from_zero(offsets):
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
        same = node_mode_ids is None or all(
            node_mode_ids[x] == node_mode_ids[v] for x in out + inn
        )
        return (
            (two_way or one_way)
            and same
            and (edge_class_ids is None or has_one_class(v, inn))
        )

    def has_one_class(v, inn):
        # The edges that leave v, then the edge that enters v from each node of inn
        edges = [
            *range(offsets[v], offsets[v + 1]),
            *(offsets[u] + bisect_left(rows[u], v) for u in inn),
        ]
        return len({edge_class_ids[a] for a in edges}) == 1

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
        edges.append((u, v, km, members))
        pairs.add((u, v))

    def exists(u, v):  # an input edge, or an edge made
        return (u, v) in pairs or v in rows[u]

    chain = [through(v) for v in range(n)]
    keep, seen = [not c for c in chain], [False] * n
    edges = [
        (u, heads[a], weights[a], [a])
        for u in range(n)
        for a in range(offsets[u], offsets[u + 1])
        if keep[u] and keep[heads[a]]
    ]
    pairs = set()  # (origin, head) of the edges made by contraction
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
    offsets: array | memoryview,
    heads: array | memoryview,
    weights: array | memoryview,
    node_mode_ids: array | memoryview | None = None,
    max_km_between_nodes: float = math.inf,
    edge_class_ids: array | memoryview | None = None,
) -> ContractedGraph:
    """Contract the chains of pass-through nodes of a graph.

    The module docstring (*How a run goes*, step 3) gives the rule and an example. The
    function walks a chain from its canonical end: the start of a one-way chain, or the
    end with the lower index. A part of a chain that would give an edge from a node to
    itself, or a second edge between two nodes, is split at its middle node. A cycle of
    pass-through nodes is walked from its lowest node, which is kept.

    Args:
        offsets: The CSR offsets of the graph, one more than its nodes (int32).
        heads: The head of each edge (int32).
        weights: The length of each edge in km (float64).
        node_mode_ids: The node mode of each node (uint8), or None. A chain is never
            contracted across two node modes.
        max_km_between_nodes: The length in km at which a chain is cut. Along the chain,
            an edge ends at the first node where it is this long or longer. So an edge
            can be longer than this value, by less than the length of one input edge.
        edge_class_ids: The class of each edge (uint8), or None.

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
                node_mode_ids,
                max_km_between_nodes,
                edge_class_ids,
            )
        )
    return contract_chains_python(
        offsets,
        heads,
        weights,
        node_mode_ids=node_mode_ids,
        max_km_between_nodes=max_km_between_nodes,
        edge_class_ids=edge_class_ids,
    )


def simplify_shapes(
    shape_points: array | memoryview,
    shape_offsets: array | memoryview,
    endpoint_coords: array | memoryview,
    tolerance_meters: float,
) -> tuple[array | memoryview, array | memoryview]:
    """Simplify the shape of each edge with the Douglas-Peucker algorithm.

    A shape point is dropped when it is within `tolerance_meters` of the line between the
    two kept points around it. Distances are measured on a flat map around each edge.

    Args:
        shape_points: The shape points of all the edges (int32 pairs, 1e-7 degree).
        shape_offsets: Where the points of each edge start.
        endpoint_coords: The latitude and the longitude of the two ends of each edge
            (int32, four values per edge).
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
    - `class_ids` (uint8): the id of its class in `scgraph.pipelines.CLASSES`. The
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
    COLUMNS.update(directions="b", points="i", offsets="q", class_ids="B")

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
        class_id: int | None = None,
    ) -> None:
        """Add one piece. `endpoint_coords` and `shape_points` are `[latitude, longitude]`
        points in degrees. `class_id` is the id of the class of the piece in
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
        ends, points = encode_coordinates(flat, "int32")
        new["ends"].extend(ends)
        new["points"].extend(points)
        if class_id is not None:
            new["class_ids"].append(class_id)
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
        first, last = pieces.offsets[i], pieces.offsets[i + 1]
        units = [  # the latitude, then the longitude of each point, in 1e-7 degree
            *pieces.ends[4 * i : 4 * i + 2],
            *pieces.points[2 * first : 2 * last],
            *pieces.ends[4 * i + 2 : 4 * i + 4],
        ]
        # The points of the piece in degrees: its origin, its shape points, its
        # destination
        line = [
            [latitude * 1e-7, longitude * 1e-7]
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
        halves.append(
            pieces.origins[i],
            new_id,
            first_km,
            direction,
            [line[0], line[middle]],
            line[1:middle],
            class_id,
        )
        halves.append(
            new_id,
            pieces.destinations[i],
            km - first_km,
            direction,
            [line[middle], line[-1]],
            line[middle + 1 : -1],
            class_id,
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
    (*How a run goes*, step 1, and *How a piece is split*).

    Args:
        pieces: The pieces, as `step1_osm_ways.build_way_pieces` or `step2_hub_connectors.join_networks_at_hubs` fill them.

    Returns:
        The graph as a dict of arrays: `offsets`, `heads`, `weights_length`,
        `node_points`, `shape_offsets`, `shape_points` and `source_node_ids`, and
        `edge_class_ids` when the pieces have classes. The module docstring describes
        them.

    Raises:
        ValueError: Every piece joins a node to itself. Or some pieces have a class
            and the others have none.
    """
    pieces.flush()
    if len(pieces.class_ids) not in (0, len(pieces.km)):
        raise ValueError("Some pieces have a class and the others have none")
    piece, back, *columns = _list_edges(pieces)
    source_node_ids, offsets, heads, weights, kept, parallel_edges = (
        build_csr_from_edges(*columns)
    )
    if not len(source_node_ids):
        raise ValueError("The pieces join no two points: every one is a loop")
    # The new nodes get the ids below zero and below every id of the pieces
    split_pieces = sorted({piece[e] for e in parallel_edges})
    halves = _split_pieces(pieces, split_pieces, min(0, source_node_ids[0]) - 1)
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
        source_node_ids, offsets, heads, weights, kept, _ = (
            build_csr_from_edges(*columns[:3])
        )
    node_points = array("i", bytes(8 * len(source_node_ids)))
    points, shape_offsets = array("i"), array("i", [0])
    for u in range(len(source_node_ids)):
        for a in range(offsets[u], offsets[u + 1]):
            i, b = piece[kept[a]], back[kept[a]]
            source_pieces = pieces if kept[a] < first_edge_of_halves else halves
            e = source_pieces.ends[4 * i : 4 * i + 4]
            # e holds the points of the two ends of the piece, in the order of the
            # piece. For an edge that goes against the piece, the ends swap.
            origin, destination = (e[2:], e[:2]) if b else (e[:2], e[2:])
            v = heads[a]
            node_points[2 * u], node_points[2 * u + 1] = origin
            node_points[2 * v], node_points[2 * v + 1] = destination
            first, last = source_pieces.offsets[i], source_pieces.offsets[i + 1]
            line = array("i", source_pieces.points[2 * first : 2 * last])
            if b:  # its points from the destination
                line[0::2], line[1::2] = line[-2::-2], line[-1::-2]
            points.extend(line)
            shape_offsets.append(len(points) // 2)
    graph = {
        "offsets": offsets,
        "heads": heads,
        "weights_length": weights,
        "node_points": node_points,
        "shape_offsets": shape_offsets,
        "shape_points": points,
        "source_node_ids": source_node_ids,
    }
    if columns[3] is not None:
        graph["edge_class_ids"] = array("B", (columns[3][i] for i in kept))
    return graph


def assemble_network(
    graph: dict[str, array | memoryview],
    *,
    max_km_between_nodes: float,
    min_component_nodes: int | None,
) -> dict[str, array]:
    """Turn a graph into the arrays of a network file.

    The function runs steps 2 to 5 of the module docstring. It keeps the strongly
    connected components, contracts the chains, joins the shapes of the contracted
    edges, and numbers the nodes by node mode, then along the Hilbert curve.
    `GeoGraph.save_as_scgraph` uses the same order. The first two steps log their counts
    at DEBUG.

    Args:
        graph: The graph, as `build_graph_from_pieces` returns it, with `node_mode_ids`
            if it has several node modes. The function empties this dict, to free it.
        max_km_between_nodes: The length in km at which `contract_chains` cuts a chain.
        min_component_nodes: The smallest number of nodes of a kept component. None keeps
            only the largest component.

    Returns:
        The arrays of the network file, as `network_file.write` takes them.
    """
    with log_step(
        logger,
        "keep the strongly connected components",
        count_nodes_and_edges(graph),
    ) as counts:
        order = keep_strongly_connected_components(
            graph["offsets"],
            graph["heads"],
            min_component_nodes,
        )
        given, graph = graph, renumber_nodes(graph, *order)
        given.clear()  # freed now, not when the caller lets it go: one copy at a time
        counts.update(count_nodes_and_edges(graph, "kept_"))
    with log_step(
        logger, "contract the chains", count_nodes_and_edges(graph)
    ) as counts:
        node_mode_ids, edge_class_ids = graph.get("node_mode_ids"), graph.get(
            "edge_class_ids"
        )
        kept, origins, heads, weights, member_offsets, members = (
            contract_chains(
                graph["offsets"],
                graph["heads"],
                graph["weights_length"],
                node_mode_ids=node_mode_ids,
                max_km_between_nodes=max_km_between_nodes,
                edge_class_ids=edge_class_ids,
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
            "weights_length": weights,
            "shape_offsets": shape_offsets,
            "shape_points": points,
            **_select_nodes(graph, kept),
        }
        if edge_class_ids is not None:  # the members of an edge have one class
            graph["edge_class_ids"] = array(
                "B", (edge_class_ids[members[i]] for i in member_offsets[:-1])
            )
        counts.update(count_nodes_and_edges(graph, "kept_"))
    node_points = memoryview(graph["node_points"])
    latitudes, longitudes = node_points[0::2], node_points[1::2]
    node_mode_ids = graph.get("node_mode_ids") or bytes(len(kept))

    def key(u):  # node mode, Hilbert key (below 4^CURVE_ORDER), index: one int
        curve = hilbert_key(latitudes[u] * 1e-7, longitudes[u] * 1e-7)
        return (node_mode_ids[u] << 2 * CURVE_ORDER | curve) << 32 | u

    # One int per node, not a list; the sorted ints are freed before renumber_nodes
    keys = sorted(map(key, range(len(kept))))
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

    The arrays are `node_points`, then `source_node_ids` and `node_mode_ids` if `graph`
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
    for key, typecode in (("source_node_ids", "q"), ("node_mode_ids", "B")):
        if key in graph:
            selected[key] = array(typecode, (graph[key][u] for u in nodes))
    return selected


def renumber_nodes(graph, order, labels=None):
    """Return `graph` with the nodes of `order` only. Node `order[i]` becomes node `i`, and
    the edges of each node are sorted by head. With `labels`, an edge is kept only when
    its two ends have the same label. A kept edge keeps its shape, and its class if
    `graph` has `edge_class_ids`.
    """
    new = array("i", [-1]) * (len(graph["offsets"]) - 1)
    for i, u in enumerate(order):
        new[u] = i
    offsets, heads, weights = (
        graph[key] for key in ("offsets", "heads", "weights_length")
    )
    starts, line = graph["shape_offsets"], graph["shape_points"]
    out = {
        "offsets": array("i", [0]),
        "heads": array("i"),
        "weights_length": array("d"),
    }
    out["shape_offsets"], out["shape_points"] = array("i", [0]), array("i")
    edge_class_ids = graph.get("edge_class_ids")
    if edge_class_ids is not None:
        out["edge_class_ids"] = array("B")
    for u in order:
        for v, a in sorted(
            (new[heads[a]], a) for a in range(offsets[u], offsets[u + 1])
        ):
            if v >= 0 and (labels is None or labels[u] == labels[heads[a]]):
                out["heads"].append(v)
                out["weights_length"].append(weights[a])
                out["shape_points"].extend(
                    line[2 * starts[a] : 2 * starts[a + 1]]
                )
                out["shape_offsets"].append(len(out["shape_points"]) // 2)
                if edge_class_ids is not None:
                    out["edge_class_ids"].append(edge_class_ids[a])
        out["offsets"].append(len(out["heads"]))
    return {**out, **_select_nodes(graph, order)}


def count_nodes_and_edges(graph: dict, prefix: str = "") -> dict[str, int]:
    """The number of nodes and the number of edges of `graph`, as the values of a log:
    `nodes` and `edges`, each with `prefix` before it."""
    return {
        f"{prefix}nodes": len(graph["offsets"]) - 1,
        f"{prefix}edges": len(graph["heads"]),
    }


python = SimpleNamespace(
    build_csr_from_adjacency_list=build_csr_from_adjacency_list,
    build_csr_from_edges=build_csr_from_edges_python,
    find_strongly_connected_components=find_strongly_connected_components_python,
    contract_chains=contract_chains_python,
    simplify_shapes=simplify_shapes_python,
)
