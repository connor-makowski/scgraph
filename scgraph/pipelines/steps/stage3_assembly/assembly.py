"""
Assemble a network file from raw arcs. The C++ kernels
(`cpp/src/pipelines/assembly.hpp`), with the same results at the scale of the planet,
replace these when built; the pure-Python ones stay in `python`. Arrays in: buffers of
the stated types (`array("q"/"i"/"d")`; any sequences for `python`); out: `array`
(read-only memoryviews from C++). `PieceArrays`, `build_graph_from_pieces` and `assemble` chain the
kernels in Python; `build_csr_from_adjacency_list` and `keep_largest_strongly_connected_component` take the GeoGraph layout
for `load_from_osm`.
"""

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
from scgraph.helpers.hilbert import CURVE_ORDER, hilbert_key
from scgraph.network_file import extract_coordinates
from scgraph.utils import haversine


def build_csr_from_arcs_python(
    origins: Sequence[int],
    destinations: Sequence[int],
    weights: Sequence[float | int],
) -> tuple[array, array, array, array, array]:
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


def build_csr_from_arcs(
    origins: Sequence[int],
    destinations: Sequence[int],
    weights: Sequence[float | int],
) -> tuple[
    array | memoryview,
    array | memoryview,
    array | memoryview,
    array | memoryview,
    array | memoryview,
]:
    """
    Store arcs between source ids (int64 `origins`, `destinations`; float64 `weights`)
    by origin. Returns `(node_ids, offsets, heads, weights, kept)`: the arcs' end ids,
    sorted and unique (int64); the arcs of node `u` (its position in `node_ids`),
    `heads[offsets[u]:offsets[u + 1]]` (int32) sorted by head, with their `weights`;
    `kept` (int32), the input index of each arc, for its shape. Self-loops are dropped
    (an id on self-loops only is no node); of parallel arcs the shortest is kept, the
    first in the input on a tie.
    """
    if _cpp_build_csr_from_arcs is not None and isinstance(
        origins, (array, memoryview)
    ):
        return _cpp_build_csr_from_arcs(origins, destinations, weights)
    return build_csr_from_arcs_python(origins, destinations, weights)


def strongly_connected_components_python(
    offsets: Sequence[int], heads: Sequence[int]
) -> tuple[array, array]:
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


def strongly_connected_components(
    offsets: Sequence[int], heads: Sequence[int]
) -> tuple[array | memoryview, array | memoryview]:
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
        offsets, (array, memoryview)
    ):
        return _cpp_strongly_connected_components(offsets, heads)
    return strongly_connected_components_python(offsets, heads)


def build_csr_from_adjacency_list(
    adjacency_list: list[dict[int, int | float]],
) -> tuple[array, array, array]:
    """Store a graph from an adjacency list representation into CSR format.

    `adjacency_list[u]` maps head -> weight.
    Returns:
        tuple[array[int32], array[int32], array[float64]]:
            - offsets (int32)
            - heads (int32, rows sorted by head)
            - weights (float64)
    """
    offsets, heads, weights = array("i", [0]), array("i"), array("d")
    for row in adjacency_list:
        for head in sorted(row):
            heads.append(head)
            weights.append(row[head])
        offsets.append(len(heads))
    return offsets, heads, weights


def keep_strongly_connected_components(
    offsets: Sequence[int],
    heads: Sequence[int],
    min_nodes: int | None = None,
) -> tuple[array, array | memoryview]:
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
    """Filter a GeoGraph-layout graph to keep only its largest strongly connected component."""
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
    offsets: Sequence[int],
    heads: Sequence[int],
    weights: Sequence[float | int],
    node_modes: Sequence[int] | None = None,
    max_km_between_nodes: float | int = math.inf,
) -> ContractedGraph:
    """Pure-Python implementation of CSR degree-2 chain contraction."""
    n = len(offsets) - 1
    if len(weights) != len(heads) or (
        node_modes is not None and len(node_modes) != n
    ):
        raise ValueError("expected one weight per arc and one mode per node")
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
        return (two_way or one_way) and same

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
    offsets: Sequence[int],
    heads: Sequence[int],
    weights: Sequence[float | int],
    node_modes: Sequence[int] | None = None,
    max_km_between_nodes: float | int = math.inf,
) -> ContractedGraph:
    """Contract degree-2 pass-through chains into composite weighted edges.

    A node is contracted away if it has degree 2 (two distinct neighbours,
    either bidirectional with each or one-way through) and shares their mode.
    Walking from its canonical end (a one-way start, or the end with the lower
    index), a chain is segmented at the first node where the segment reaches
    `max_km_between_nodes`, and any segment that would create a self-loop or duplicate arc is
    split at its midpoint. Isolated cycles are walked from their lowest-index
    node, which is retained.

    Delegates to the C++ extension when available and inputs are arrays,
    falling back to pure Python.

    Parameters:
        offsets (array[int32]): CSR row offsets of size `num_nodes + 1`.
        heads (array[int32]): Target node indices of size `num_arcs`.
        weights (array[float64]): Arc lengths in kilometres.
        node_modes (array[uint8] | None): Optional per-node travel mode. If provided,
            chains are never contracted across different modes.
        max_km_between_nodes (float): Maximum length of a contracted composite segment in km.
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
    if _cpp_contract_chains is not None and isinstance(
        offsets, (array, memoryview)
    ):
        return ContractedGraph(
            *_cpp_contract_chains(
                offsets, heads, weights, node_modes, max_km_between_nodes
            )
        )
    return contract_chains_python(
        offsets,
        heads,
        weights,
        node_modes=node_modes,
        max_km_between_nodes=max_km_between_nodes,
    )


def simplify_shapes(
    shape_points: Sequence[int],
    shape_offsets: Sequence[int],
    endpoint_coords: Sequence[int],
    tolerance_meters: float | int,
) -> tuple[array | memoryview, array | memoryview]:
    """Simplify intermediate polyline shapes using the Douglas-Peucker algorithm.

    Drops intermediate shape points that fall within `tolerance_meters` metres of the
    segment connecting the retained endpoints, calculated on a local flat-map
    projection for each arc.
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
    """
    The nodes near a point, from their coordinates (`lats`, `lons`: sequences of degrees
    once multiplied by `scale`, such as int32 at 1e-7 degree at the scale of the planet),
    without a Python object per node: node indices by rows of 0.2 degree of latitude,
    each sorted by longitude and searched by bisection.
    """

    def __init__(self, lats, lons, scale=1):
        self.lats, self.lons, self.rows, self.scale = lats, lons, {}, scale
        for i, lat in enumerate(lats):
            row = math.floor(lat * scale / 0.2)
            self.rows.setdefault(row, array("i")).append(i)
        for row, nodes in self.rows.items():
            self.rows[row] = array("i", sorted(nodes, key=lons.__getitem__))

    def within(
        self, point: list[float | int], km: float | int
    ) -> Iterator[tuple[float, int]]:
        """`(km, node)` of each node within `km` of `point` ([latitude, longitude])."""
        lat, lon = point
        dlat = km / 110  # degrees: more than `km` (111.2 km per degree)
        cos = math.cos(math.radians(min(90, abs(lat) + dlat)))
        if cos < 1e-9 or (dlon := km / (110 * cos)) >= 180:
            spans = [(-180, 180)]
        else:  # around the antimeridian, two spans
            spans = [(lon - dlon, lon + dlon)]
            spans += [(w + 360, e + 360) for w, e in spans if w < -180]
            spans += [(w - 360, e - 360) for w, e in spans[:1] if e > 180]
        lats, lons, scale = self.lats, self.lons, self.scale
        key = lambda i: lons[i] * scale  # degrees (x * 1 == x)
        for row in range(
            math.floor((lat - dlat) / 0.2), math.floor((lat + dlat) / 0.2) + 1
        ):
            nodes = self.rows.get(row, ())
            for west, east in spans:
                lo, hi = bisect_left(nodes, west, key=key), bisect_right(
                    nodes, east, key=key
                )
                for i in nodes[lo:hi]:
                    d = haversine(point, [lats[i] * scale, lons[i] * scale])
                    if d <= km:
                        yield d, i

    def nearest(
        self, point: list[float | int], km: float | int
    ) -> tuple[int | None, float]:
        """`(node, km)` of the node nearest to `point` within `km` (ties: the lowest
        node), or `(None, inf)`."""
        d, i = min(self.within(point, km), default=(math.inf, None))
        return i, d


class PieceArrays:
    """The cut pieces of ways (`cut_polylines`) as growing columns: the source ids of
    their ends (`origins`, `destinations`, int64) and the ends' coordinates (`ends`, int32
    in 1e-7 degree, four per piece), `km` (float64), `directions` (int8, as polylines),
    and their interior points (`points`, int32 pairs, piece `i`'s from `offsets[i]`),
    each piece's drawing simplified at `tolerance_meters` metres (`simplify_shapes`, by
    batches of BATCH pieces), or stored as it is with `tolerance_meters=None`. The columns are
    `array`s, or files of `work_dir` read through memory maps; they hold the pieces up to
    the last `flush`."""

    BATCH = 10_000
    COLUMNS = dict(origins="q", destinations="q", ends="i", km="d")
    COLUMNS.update(directions="b", points="i", offsets="q")

    def __init__(self, tolerance_meters=50, work_dir=None, truncate=True):
        self.tolerance_meters, self.work_dir = tolerance_meters, work_dir
        if work_dir is not None:
            os.makedirs(work_dir, exist_ok=True)
        self._views = []
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
                file = open(path, "rb")
                view = mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ)
                self._views.append((file, view))
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
        length_km: float | int,
        direction: int,
        endpoint_coords: Iterable[Iterable[float | int]],
        shape_points: Iterable[Iterable[float | int]],
    ) -> None:
        """One piece; `endpoint_coords` and `shape_points`: [latitude, longitude] points in degrees."""
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
        self._starts.append(len(new["points"]) // 2)
        if len(self._starts) > self.BATCH:
            self.flush()

    def flush(self) -> None:
        """Simplify and store the drawings of the pieces appended since the last call."""
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

    def close(self) -> None:
        """Release mapped memory views."""
        for file, view in getattr(self, "_views", []):
            try:
                view.close()
            except Exception:
                pass
            try:
                file.close()
            except Exception:
                pass
        self._views = []


def build_graph_from_pieces(
    pieces: PieceArrays,
) -> dict[str, array | memoryview]:
    """Build a directed CSR network graph from polyline segments (`PieceArrays`).

    Each polyline piece generates directed arcs according to its legal traversal
    direction (bidirectional, one-way forward, or one-way reverse). Parallel arcs
    between the same pair of nodes are resolved by retaining the shortest arc.

    Used across all transportation networks (road, railway, and intermodal port networks).

    Parameters:
        pieces (PieceArrays): Growing columns of cut way pieces.

    Returns:
        dict[str, array]: CSR network representation containing offsets, heads,
            weights, latitudes, longitudes, shape_offsets, shape_points, node_ids.
    """
    pieces.flush()
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
    lats, lons = (array("i", bytes(4 * len(node_ids))) for _ in "xy")
    points, shape_offsets = array("i"), array("i", [0])
    for u in range(len(node_ids)):
        for a in range(offsets[u], offsets[u + 1]):
            i, b = piece[kept[a]], back[kept[a]]
            e = pieces.ends[4 * i : 4 * i + 4]
            lats[u], lons[u], lats[heads[a]], lons[heads[a]] = (
                (e[2], e[3], e[0], e[1]) if b else e
            )
            first, last = pieces.offsets[i], pieces.offsets[i + 1]
            line = array("i", pieces.points[2 * first : 2 * last])
            if b:  # its points from the destination
                line[0::2], line[1::2] = line[-2::-2], line[-1::-2]
            points.extend(line)
            shape_offsets.append(len(points) // 2)
    return {
        "offsets": offsets,
        "heads": heads,
        "weights": weights,
        "latitudes": lats,
        "longitudes": lons,
        "shape_offsets": shape_offsets,
        "shape_points": points,
        "node_ids": node_ids,
    }


def assemble(
    graph: dict[str, array | memoryview],
    *,
    max_km_between_nodes: float | int,
    min_nodes_per_strongly_connected_component: int | None,
) -> tuple[dict[str, array], list[dict[str, str | int]]]:
    """The network file's arrays of `graph` (`build_graph_from_pieces`'s layout, with
    `node_modes` if it has several modes): keep the components
    (`keep_strongly_connected_components` with `min_nodes_per_strongly_connected_component`,
    each one closed), contract the chains (`contract_chains` at `max_km_between_nodes`,
    which never merges two modes), join their shapes (`build_chain_shapes`), and number the
    nodes by mode, then along the Hilbert curve, as `GeoGraph.save_as_scgraph` does. Empties `graph`.
    Returns `(arrays, steps)`, `steps` the counts of the components and the contraction.
    """
    order = keep_strongly_connected_components(
        graph["offsets"],
        graph["heads"],
        min_nodes_per_strongly_connected_component,
    )
    given, graph = graph, _renumbered(graph, *order)
    given.clear()  # freed now, not when the caller lets it go: one copy at a time
    steps = [_counts("components", graph)]
    modes = graph.get("node_modes")
    kept, origins, heads, weights, member_offsets, members = contract_chains(
        graph["offsets"],
        graph["heads"],
        graph["weights"],
        node_modes=modes,
        max_km_between_nodes=max_km_between_nodes,
    )
    points, shape_offsets = build_chain_shapes(graph, member_offsets, members)
    offsets = array("i", bytes(4 * (len(kept) + 1)))
    for u in origins:  # rows by origin, as contract_chains sorts them
        offsets[u + 1] += 1
    graph = {  # the graph before contraction is freed
        "offsets": array("i", accumulate(offsets)),
        "heads": heads,
        "weights": weights,
        "shape_offsets": shape_offsets,
        "shape_points": points,
        **{
            key: array(_TYPES[key], (graph[key][u] for u in kept))
            for key in _TYPES
            if key in graph
        },
    }
    steps.append(_counts("contract", graph))
    lats, lons = graph["latitudes"], graph["longitudes"]
    modes = graph.get("node_modes") or bytes(len(kept))

    def key(u):  # mode, Hilbert key (below 4^CURVE_ORDER), index: one int
        curve = hilbert_key(lats[u] * 1e-7, lons[u] * 1e-7)
        return (modes[u] << 2 * CURVE_ORDER | curve) << 32 | u

    # One int per node, not a list; the sorted ints are freed before _renumbered
    keys = sorted(map(key, range(len(kept))))
    order, keys = array("i", (k & 0xFFFFFFFF for k in keys)), None
    return _renumbered(graph, order), steps


def build_chain_shapes(
    graph: dict[str, array | memoryview],
    member_offsets: Sequence[int],
    members: Sequence[int],
) -> tuple[array, array]:
    """The shapes of the arcs that `contract_chains` gives for `graph`, as `(points,
    offsets)` in its layout: the shapes of each arc's members in travel order, each
    followed by the node it ends at, except the last."""
    heads, lats, lons = graph["heads"], graph["latitudes"], graph["longitudes"]
    starts, line = graph["shape_offsets"], graph["shape_points"]
    points, offsets = array("i"), array("i", [0])
    for i in range(len(member_offsets) - 1):
        chain = members[member_offsets[i] : member_offsets[i + 1]]
        for k, a in enumerate(chain):
            if k:
                node = heads[chain[k - 1]]
                points.extend((lats[node], lons[node]))
            points.extend(line[2 * starts[a] : 2 * starts[a + 1]])
        offsets.append(len(points) // 2)
    return points, offsets


# Node columns and their types
_TYPES = {
    "latitudes": "i",
    "longitudes": "i",
    "node_ids": "q",
    "node_modes": "B",
}


def _renumbered(graph, order, labels=None):
    """`graph` with the nodes of `order` only, node `order[i]` becoming node `i`, its rows
    sorted by head; with `labels`, only the arcs whose ends share one."""
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
        out["offsets"].append(len(out["heads"]))
    for key in _TYPES:  # in this order: the same file at every run
        if key in graph:
            out[key] = array(_TYPES[key], (graph[key][u] for u in order))
    return out


def _counts(step, graph):  # a step of build metadata
    nodes, arcs = len(graph["offsets"]) - 1, len(graph["heads"])
    return {"step": step, "nodes": nodes, "arcs": arcs}


python = SimpleNamespace(
    build_csr_from_adjacency_list=build_csr_from_adjacency_list,
    build_csr_from_arcs=build_csr_from_arcs_python,
    strongly_connected_components=strongly_connected_components_python,
    contract_chains=contract_chains_python,
    simplify_shapes=simplify_shapes_python,
)
