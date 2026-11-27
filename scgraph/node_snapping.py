"""The snapping of a query point to its closest node in a GeoGraph.

Each `GeoGraph` has one `SnapIndexes`, in `GeoGraph._snap_indexes`. The public
names of this module are `OrderedSnapIndex` and `NodeOrderError`. They are the C++ classes
when the extension is installed, and the pure-Python classes otherwise. The other
names of this module are internal.

WORDS

- A "query point" is the origin or the destination of a query. It "snaps" to a
  node: the route starts or ends at this node.
- A "node mode" is the kind of place where a node is, such as `road` or `rail`. A
  "road node" is a node of the node mode `road`. A node that `add_coord_node`
  added without `node_mode` has the node mode None.
- A "snapping index" finds the node closest to a point, among its own nodes. Each
  snapping index of this module has `closest_idx(point)`,
  `closest_idx_per_quadrant(point)` and `list_nodes()`: each of its nodes, as
  `(node id, point)`.
- An `OrderedSnapIndex` (`scgraph/cpp/src/snap_index.hpp`) is the snapping index
  of a list of points. It answers with a position in this list.

WHAT IT HOLDS

- The index of every node: the `OrderedSnapIndex` of `GeoGraph.nodes`. `GeoGraph.snap_index`
  reads it.
- The index of each node mode, by the name of the node mode.

Each index is built at its first use. When the nodes change, the geograph sets
`snap_index` to None: a new, empty `SnapIndexes` replaces this one.

THE DEFAULT RULE

By default, a query point snaps to its closest road node when the geograph has
roads, and to its closest node otherwise. A geograph has roads when one of its
nodes is a road node. With roads, a query point also snaps to a node of the node
mode None: a default query can start at a node that the caller added.

A query can also name the node modes that its points may snap to
(`snap_to_node_modes`). A point then snaps to its closest node of these node modes.

THE IDEA: ONE INDEX FOR EACH NODE MODE

`get_index` gives one snapping index for the nodes that a query point may snap to:

- for one node mode, the index of this node mode;
- for several node modes, a `_CombinedSnapIndex`: the index of each node mode
  gives its closest node, and the answer is the closest of these nodes;
- for a geograph without a road node, by default, a `LazyEveryNodeSnapIndex`.

The nodes of a network file are sorted by node mode. So the nodes of one node mode
are a range of node ids, and their `OrderedSnapIndex` reads their points in the
file.

EXAMPLE

A geograph has four nodes on the equator:

    node id      0         1         2           3
    node mode    road      road      rail        rail
    point        [0, 0]    [0, 1]    [0, 0.4]    [0, 3]

The query point `[0, 0.45]` is 50.0 km from the node 0 and 5.6 km from the node 2:

    get_index(geograph, None).closest_idx([0, 0.45])               gives 0
    get_index(geograph, ["road", "rail"]).closest_idx([0, 0.45])   gives 2

The geograph has roads, so the first index is the index of the road nodes, with
`node_ids = range(0, 2)`. The second one asks the index of the road nodes (the
node 0) and the index of the rail nodes (the node 2), and keeps the closest of the
two.

A second geograph has the two rail nodes alone. It has no road node, so the same
point snaps to its closest node, with the ids of this geograph:

    get_index(rail_geograph, None).closest_idx([0, 0.45])          gives 0
"""

import logging
from array import array
from collections.abc import Iterable, Iterator, Sequence
from itertools import chain
from typing import TYPE_CHECKING

from scgraph import array_views
from scgraph.step_logs import log_step
from scgraph.helpers.hilbert import get_hilbert_order
from scgraph.node_modes import list_node_mode_names
from scgraph.utils import haversine

try:
    from scgraph.cpp import NodeOrderError, OrderedSnapIndex
except ImportError:
    from scgraph.helpers.snap_index import NodeOrderError, OrderedSnapIndex

if TYPE_CHECKING:  # Only for an annotation
    from scgraph.geograph import GeoGraph

__all__ = ["NodeOrderError", "OrderedSnapIndex"]

# The README gives the records of the snapping indexes under this name.
logger = logging.getLogger("scgraph.geograph")

# The node mode that a query point snaps to by default. A journey of a person or of
# goods starts and ends on a road, and the pipelines of scgraph give this name to
# the node mode of their road nodes.
ROAD_NODE_MODE = "road"


class NodeIdSnapIndex:
    """
    A snapping index that answers with node ids. It covers either every node in
    Hilbert order (an exact tie between two places goes to the node earlier on the
    curve, not to the lower id), or the nodes of one node mode.
    """

    def __init__(
        self, node_ids: array | range, index: OrderedSnapIndex, nodes: Sequence
    ):
        # node_ids[position in the index] = node id. An array or a range, not a list:
        # the garbage collector never walks it (a list of 572,009 ids cost a 16 ms pause)
        self.node_ids, self.index = node_ids, index
        # `nodes` are the nodes of the geograph
        self.nodes = nodes

    def list_nodes(self) -> Iterator[tuple[int, Sequence[float]]]:
        return ((node_id, self.nodes[node_id]) for node_id in self.node_ids)

    def closest_idx(self, point) -> int:
        return self.node_ids[self.index.closest_idx(point)]

    def closest_idx_per_quadrant(self, point) -> dict[str, int | None]:
        # Changes the index's dict in place and creates no object the garbage collector
        # tracks, so that queries don't make it run more often
        found = self.index.closest_idx_per_quadrant(point)
        for quadrant in ("ne", "nw", "se", "sw"):
            p = found[quadrant]
            if p is not None:
                found[quadrant] = self.node_ids[p]
        return found


class _CombinedSnapIndex:
    """
    The snapping indexes of several node modes, used as one index. Each index gives
    its closest node, and the answer is the closest of these nodes.

    Of two nodes at the same distance, the answer is the lowest id, as in one index.
    """

    def __init__(self, indexes: list[NodeIdSnapIndex], nodes: Sequence):
        # `nodes` are the nodes of the geograph: an answer of an index is a node id
        self.indexes, self.nodes = indexes, nodes

    def list_nodes(self) -> Iterator[tuple[int, Sequence[float]]]:
        return chain.from_iterable(index.list_nodes() for index in self.indexes)

    def _find_closest(self, point, node_ids: list[int | None]) -> int | None:
        # The node closest to `point` among the answers of the indexes. An index
        # answers None for a quadrant without a node.
        return min(
            (node_id for node_id in node_ids if node_id is not None),
            key=lambda node_id: (
                haversine(point, self.nodes[node_id]),
                node_id,
            ),
            default=None,
        )

    def closest_idx(self, point) -> int:
        return self._find_closest(
            point, [index.closest_idx(point) for index in self.indexes]
        )

    def closest_idx_per_quadrant(self, point) -> dict[str, int | None]:
        answers = [
            index.closest_idx_per_quadrant(point) for index in self.indexes
        ]
        return {
            quadrant: self._find_closest(
                point, [answer[quadrant] for answer in answers]
            )
            for quadrant in ("ne", "nw", "se", "sw")
        }


class LazyEveryNodeSnapIndex:
    """
    The snapping index of every node of a geograph: `GeoGraph.snap_index`, read at
    each answer. So a point that connects to all the nodes of a box builds no index.
    """

    def __init__(self, geograph: "GeoGraph"):
        self.geograph = geograph

    def list_nodes(self) -> Iterator[tuple[int, Sequence[float]]]:
        return enumerate(self.geograph.nodes)

    def closest_idx(self, point) -> int:
        return self.geograph.snap_index.closest_idx(point)

    def closest_idx_per_quadrant(self, point) -> dict[str, int | None]:
        return self.geograph.snap_index.closest_idx_per_quadrant(point)


QuerySnapIndex = NodeIdSnapIndex | _CombinedSnapIndex | LazyEveryNodeSnapIndex


class SnapIndexes:
    """The snapping indexes of a geograph: of every node, and of each node mode.

    A `SnapIndexes` does not keep its geograph: each call receives it. So a
    geograph that the caller drops is freed at once.
    """

    def __init__(self, index_of_every_node=None):
        # An `OrderedSnapIndex`, a `NodeIdSnapIndex`, or the `GeoKDTree` that the caller set
        self._index_of_every_node = index_of_every_node
        # {name of a node mode: its index, or None for a node mode without a node}
        self._index_of_each_node_mode = {}

    def get_index_of_every_node(self, geograph: "GeoGraph"):
        """Return the snapping index of every node, built at the first call."""
        if self._index_of_every_node is None:
            with log_step(
                logger,
                "build the snapping index",
                {"nodes": len(geograph.nodes)},
            ) as values:
                self._index_of_every_node = _build_snap_index(geograph.nodes)
                values["sorted_for_the_index"] = isinstance(
                    self._index_of_every_node, NodeIdSnapIndex
                )
        return self._index_of_every_node

    def get_index(
        self, geograph: "GeoGraph", snap_to_node_modes: list[str] | None
    ) -> QuerySnapIndex:
        """
        Return the snapping index of the nodes that a query point may snap to.

        Args:
            geograph: The geograph of the query.
            snap_to_node_modes: The argument of the query: names of
                `geograph.node_modes`, or None for the default rule (see the
                module docstring).

        Raises:
            ValueError: A name of the list is not in `node_modes`, or no node has a
                node mode of the list. An empty list is such a list.
        """
        if snap_to_node_modes is None:
            indexes = self._list_indexes(geograph, [ROAD_NODE_MODE])
            if not indexes:
                return LazyEveryNodeSnapIndex(geograph)
            indexes += self._list_indexes(geograph, [None])
        else:
            # A query cannot name the node mode without a name
            list_node_mode_names(
                [
                    row
                    for row in geograph.node_modes
                    if row.get("name") is not None
                ],
                snap_to_node_modes,
                "snap_to_node_modes",
            )
            indexes = self._list_indexes(geograph, snap_to_node_modes)
            if not indexes:
                raise ValueError(
                    "snap_to_node_modes names no node mode that a node of this geograph "
                    f"has: got {snap_to_node_modes!r}"
                )
        if len(indexes) == 1:
            return indexes[0]
        return _CombinedSnapIndex(indexes, geograph.nodes)

    def _list_indexes(
        self, geograph: "GeoGraph", node_modes: Iterable[str | None]
    ) -> list[NodeIdSnapIndex]:
        # The index of each of these node modes that has a node, built at its first
        # use. A name given twice counts once.
        indexes = []
        for node_mode in dict.fromkeys(node_modes):
            if node_mode not in self._index_of_each_node_mode:
                self._index_of_each_node_mode[node_mode] = (
                    _build_index_of_node_mode(geograph, node_mode)
                )
            index = self._index_of_each_node_mode[node_mode]
            if index is not None:
                indexes.append(index)
        return indexes


def _build_index_of_node_mode(
    geograph: "GeoGraph", node_mode: str | None
) -> NodeIdSnapIndex | None:
    # The snapping index of the nodes of one node mode, or None when no node has it
    node_ids = _find_node_ids(geograph, node_mode)
    if not node_ids:
        return None
    with log_step(
        logger,
        "build the snapping index",
        {"nodes": len(node_ids), "node_mode": node_mode},
    ) as values:
        index = _build_snap_index(geograph.nodes, node_ids)
        values["sorted_for_the_index"] = index.node_ids is not node_ids
    return index


def _build_snap_index(
    nodes: Sequence, node_ids: range | array | None = None
) -> OrderedSnapIndex | NodeIdSnapIndex:
    """
    Builds the snapping index of the nodes, or of the nodes `node_ids` alone: a
    range, or an array of ids in rising order (see `_find_node_ids`). Nodes too
    scattered for an `OrderedSnapIndex` are indexed in Hilbert order, and keep their ids.
    """
    try:
        if node_ids is None:
            return (
                OrderedSnapIndex.from_array(nodes.points())
                if isinstance(nodes, array_views.NodePoints)
                else OrderedSnapIndex(nodes)
            )
        if isinstance(node_ids, range) and isinstance(
            nodes, array_views.NodePoints
        ):
            # The index reads the points of the range in place, as the index of
            # every node does
            points = memoryview(nodes.points())
            return NodeIdSnapIndex(
                node_ids,
                OrderedSnapIndex.from_array(
                    points[2 * node_ids.start : 2 * node_ids.stop]
                ),
                nodes,
            )
        return NodeIdSnapIndex(
            node_ids, OrderedSnapIndex([nodes[i] for i in node_ids]), nodes
        )
    except NodeOrderError:
        # A graph built from a list, or one with many added nodes, does not keep
        # nearby nodes together
        points = (
            list(nodes) if node_ids is None else [nodes[i] for i in node_ids]
        )
        order = array("q", get_hilbert_order(points))
        index = OrderedSnapIndex([points[i] for i in order])
        if node_ids is not None:
            # A position in `points` becomes the id of its node
            order = array("q", [node_ids[i] for i in order])
        return NodeIdSnapIndex(order, index, nodes)


def _find_node_ids(
    geograph: "GeoGraph", node_mode: str | None
) -> range | array:
    """
    Returns the ids of the nodes of one node mode, in rising order. `node_mode` is
    a name of `node_modes`, or None.

    - A merge or an added node changes the order of a network file: the ids are
      then an array. A merge can also give the same name to two rows of
      `node_modes`, and a geograph may have no row for a name
    - A node appended to `nodes` directly is in the first node mode
    """
    wanted_node_mode_ids = [
        node_mode_id
        for node_mode_id, row in enumerate(geograph.node_modes)
        if row.get("name") == node_mode
    ]
    if not wanted_node_mode_ids:
        return range(0)
    node_mode_ids = geograph._read_node_mode_ids()
    if len(wanted_node_mode_ids) == 1:
        # `bytes` searches a value in C: a search in the array costs as much as
        # the build of the index
        node_mode_ids = bytes(node_mode_ids)
        node_mode_id = wanted_node_mode_ids[0]
        first = node_mode_ids.find(node_mode_id)
        last = node_mode_ids.rfind(node_mode_id)
        if node_mode_ids.count(node_mode_id) == last - first + 1:
            return range(first, last + 1)
    return array(
        "q",
        [
            node_id
            for node_id, node_mode_id in enumerate(node_mode_ids)
            if node_mode_id in wanted_node_mode_ids
        ],
    )
