"""List-like views of the arrays of a network file: points, edge shapes and source ids.

This module is internal. A network file stores the points of the nodes, the shapes of
the edges and the source ids of the nodes as flat arrays, which `network_file.read`
can map into memory. A `GeoGraph` loaded from a file holds `NodePoints` as its `nodes`
and `EdgeShapes` as its `intermediate_nodes`, in place of Python lists. Every
`GeoGraph` holds `ExternalNodeIds` as its `external_node_ids`. Each class reads a
value from the arrays when it is asked for, and behaves as the list that it replaces.
Example: `NodePoints(node_points)[3]` builds the list `[latitude, longitude]` of the
node 3 from its two values in `node_points`, and keeps no list of it.

`coordinates` is of the layer below: this module imports it, and it does not import
this module.
"""

from array import array
from collections.abc import Iterable, MutableSequence, Sequence
from operator import eq, index
from types import MappingProxyType

from scgraph.coordinates import get_units_per_degree
from scgraph.helpers.second_edges import find_pair_shape

# The C++ kernels take typed buffers only, so each call chooses its kernel.
try:
    from scgraph.cpp import coordinate_lists as _coordinate_lists
    from scgraph.cpp import shape_path as _shape_path
except ImportError:
    _coordinate_lists = _shape_path = None


class EdgeShapes(Sequence):
    """
    The `intermediate_nodes` of a GeoGraph read from a network file: for each origin, a
    read-only mapping {destination: shape}, read from the file's arrays when asked for
    instead of one Python list per point. A shape is a new list of [latitude, longitude]
    each time. A second edge reads the shape of its pair edge backwards
    (`scgraph/cpp/src/second_edges.hpp`).
    """

    def __init__(self, arrays):
        self._node_first_edge_ids, self._edge_destination_node_ids = (
            arrays["node_first_edge_ids"],
            arrays["edge_destination_node_ids"],
        )
        self._starts, self._points = (
            arrays["edge_first_shape_point_ids"],
            arrays["shape_points"],
        )
        # `load_from_osm` builds shapes without flags: no edge is a second edge
        self._has_reversed_shape = arrays.get(
            "edge_has_reversed_shape"
        ) or bytes(len(self._edge_destination_node_ids))
        self._scale = get_units_per_degree(self._points)

    def __len__(self):
        return len(self._node_first_edge_ids) - 1

    def __getitem__(self, origin):
        if isinstance(origin, slice):
            return [self[i] for i in range(*origin.indices(len(self)))]
        origin = index(origin)
        if origin < 0:
            origin += len(self)
        if not 0 <= origin < len(self):
            raise IndexError("node index out of range")
        edge_destination_node_ids, starts, has_reversed_shape = (
            self._edge_destination_node_ids,
            self._starts,
            self._has_reversed_shape,
        )
        return MappingProxyType(
            {
                edge_destination_node_ids[edge]: self._read_shape(origin, edge)
                for edge in range(
                    self._node_first_edge_ids[origin],
                    self._node_first_edge_ids[origin + 1],
                )
                if starts[edge + 1] != starts[edge] or has_reversed_shape[edge]
            }
        )

    def _read_shape(self, origin_id, edge_id):
        first, last = self._starts[edge_id], self._starts[edge_id + 1]
        if self._has_reversed_shape[edge_id]:
            first, last = find_pair_shape(
                self._node_first_edge_ids,
                self._edge_destination_node_ids,
                self._starts,
                origin_id,
                edge_id,
            )
        # A mapped file's `edge_first_shape_point_ids` are checked here, where they are
        # read
        if not 0 <= first <= last <= len(self._points) // 2:
            raise ValueError("invalid edge_first_shape_point_ids")
        flat, scale = self._points[2 * first : 2 * last].tolist(), self._scale
        shape = [
            [flat[i] / scale, flat[i + 1] / scale]
            for i in range(0, len(flat), 2)
        ]
        if self._has_reversed_shape[edge_id]:
            shape.reverse()
        return shape

    def coordinate_path(
        self, path: Sequence[int], coordinates: list[list[float]]
    ) -> list[list[float]]:
        """`coordinates` (one [latitude, longitude] per node of `path`) with the shape of
        each edge of the path between them; in one C loop in the C++ build"""
        if _shape_path is not None:
            return _shape_path(
                self._node_first_edge_ids,
                self._edge_destination_node_ids,
                self._starts,
                self._has_reversed_shape,
                self._points,
                path if type(path) is list else list(path),
                coordinates,
            )
        node_first_edge_ids, edge_destination_node_ids, count = (
            self._node_first_edge_ids,
            self._edge_destination_node_ids,
            len(self),
        )
        result = [coordinates[0]]
        for i in range(len(path) - 1):
            origin, destination = path[i], path[i + 1]
            # Nodes added after loading (add_coord_node) have no shapes
            if origin < count:
                for edge in range(
                    node_first_edge_ids[origin], node_first_edge_ids[origin + 1]
                ):
                    if edge_destination_node_ids[edge] == destination:
                        result += self._read_shape(origin, edge)
                        break
            result.append(coordinates[i + 1])
        return result

    def __eq__(self, other):
        if not isinstance(other, (list, EdgeShapes)):
            return NotImplemented
        return len(self) == len(other) and all(map(eq, self, other))

    def __repr__(self):
        return repr([dict(row) for row in self])

    def __reduce__(self):
        # Copied and pickled as a list of dicts (the file's mapping can't be)
        return list, ([dict(row) for row in self],)


class ExternalNodeIds(Sequence):
    """
    The `external_node_ids` of a GeoGraph: the stable id of each node (its id in the
    source it came from, or its position if it has none), then, for each node added
    since, a negative id below all the others. Read-only; pickled with its ids as a
    list.
    """

    def __init__(self, ids, nodes, id_count=None):
        # `nodes` gives the count: nodes past the first `_id_count` ids were added
        # since. `_id_count` falls when `GeoGraph.remove_node` removes a node of the
        # ids: the ids may be a view of a mapped file, which cannot be cut. A copy
        # passes `id_count`, so that it keeps the added nodes of the original.
        self._ids, self._nodes, self._first_added_id = ids, nodes, None
        self._id_count = len(ids) if id_count is None else id_count

    @staticmethod
    def get_first_added_id(lowest_id: int) -> int:
        """Return the external id of the first added node: below zero and below
        every other id. The next added nodes get the ids below it. Example: with
        the lowest id -3, the added nodes get -4, then -5.

        Args:
            lowest_id: The lowest external id of the nodes, or 0 without nodes.
        """
        return min(0, lowest_id) - 1

    def has_added_nodes(self) -> bool:
        """Return True when the last node was added after the ids were given,
        by `add_coord_node` or by an append to `nodes`."""
        return len(self._nodes) > self._id_count

    def forget_removed_nodes(self) -> None:
        """Forget the ids of the nodes that left the end of `nodes`. The next
        added node then gets a new id below zero, not the id of a removed node.
        `GeoGraph.remove_node` calls it after it removes the last node."""
        self._id_count = min(self._id_count, len(self._nodes))

    def __len__(self):
        return len(self._nodes)

    def __getitem__(self, i):
        if isinstance(i, slice):
            return [self[j] for j in range(*i.indices(len(self)))]
        count, i = len(self), index(i)
        if i < 0:
            i += count
        if not 0 <= i < count:
            raise IndexError("node index out of range")
        ids = self._ids
        if i < self._id_count:
            return ids[i]
        # Computed once: the ids of a large network are long to scan
        if self._first_added_id is None:
            low = ids.start if type(ids) is range else min(ids, default=0)
            self._first_added_id = self.get_first_added_id(low)
        return self._first_added_id - (i - self._id_count)

    def __eq__(self, other):
        if not isinstance(other, (list, ExternalNodeIds)):
            return NotImplemented
        return len(self) == len(other) and all(map(eq, self, other))

    def __repr__(self):
        return repr(list(self))

    def __reduce__(self):
        # Every id, also the forgotten ones: the lowest id sets the ids of the
        # added nodes
        return ExternalNodeIds, (list(self._ids), self._nodes, self._id_count)

    def take(self, node_ids: Iterable[int]) -> array:
        """The external ids of the nodes `node_ids`, as an int64 array."""
        ids = self._ids
        if self._id_count < len(self):  # nodes were added since
            return array("q", (self[i] for i in node_ids))
        if ids == range(len(ids)):
            return array("q", node_ids)
        return array("q", (ids[i] for i in node_ids))

    def array(self, order: Iterable[int] | None = None) -> array | None:
        """The ids (in `order`, `order[new] = old`, if given) as an int64 array, int32
        if every id fits, or None if every node's id is its position."""
        ids, count = self._ids, len(self)
        if order is not None:
            result = self.take(order)
        elif count <= self._id_count and ids == range(len(ids)):
            return None
        else:
            result = array("q", ids[: min(count, self._id_count)])
            result.extend(self[i] for i in range(len(result), count))
        try:  # half the size when every id fits, as those of the built-in networks
            return array("i", result)
        except OverflowError:
            return result


class NodePoints(MutableSequence):
    """
    The `nodes` of a GeoGraph read from a network file: a list of [latitude, longitude],
    read from the file's points instead of one Python list per node, then the nodes
    added since. `nodes[i]` gives a new list each time: replace a node with
    `nodes[i] = [latitude, longitude]` (changing the list it gives changes nothing).
    An edit before the last node first turns every node into a list.
    """

    def __init__(self, node_points):
        # The C++ kernels read the points directly. The Python loops read two views of
        # the points: one holds the latitudes, the other the longitudes. Reading a value
        # from a view is as fast as reading it from an array. It is faster than computing
        # 2 * i and 2 * i + 1 for each node.
        self._points = memoryview(node_points)
        self._latitudes = self._points[0::2]
        self._longitudes = self._points[1::2]
        self._added = []
        self._scale = get_units_per_degree(node_points)

    def __len__(self):
        return len(self._latitudes) + len(self._added)

    def __getitem__(self, i):
        if type(i) is int and 0 <= i < len(self._latitudes):
            return [
                self._latitudes[i] / self._scale,
                self._longitudes[i] / self._scale,
            ]
        if isinstance(i, slice):
            return [self[j] for j in range(*i.indices(len(self)))]
        j = self._in_added(i, edit=False)
        if j < 0:  # a node of the file, given from the end
            return [
                self._latitudes[j] / self._scale,
                self._longitudes[j] / self._scale,
            ]
        return self._added[j]

    def __setitem__(self, i, value):
        self._added[self._in_added(i)] = value

    def __delitem__(self, i):
        del self._added[self._in_added(i)]

    def insert(self, i: int, value: list[float]) -> None:
        if i < len(self):
            self._own()
        self._added.insert(i - len(self._latitudes), value)

    def take(self, ids: Iterable[int]) -> list[list[float]]:
        """`[nodes[i] for i in ids]` (a route's path), without a method call per node: in one
        C loop in the C++ build when no node was added"""
        if _coordinate_lists is not None and not self._added:
            return _coordinate_lists(
                self._points, ids if type(ids) is list else list(ids)
            )
        latitudes, longitudes = self._latitudes, self._longitudes
        count, scale = len(latitudes), self._scale
        return [
            (
                [latitudes[i] / scale, longitudes[i] / scale]
                if 0 <= i < count
                else self[i]
            )
            for i in ids
        ]

    def __iter__(self):
        scale = self._scale
        for latitude, longitude in zip(self._latitudes, self._longitudes):
            yield [latitude / scale, longitude / scale]
        yield from self._added

    def __eq__(self, other):
        if not isinstance(other, (list, NodePoints)):
            return NotImplemented
        return len(self) == len(other) and all(map(eq, self, other))

    def __repr__(self):
        return repr(list(self))

    def __reduce__(self):
        # Copied and pickled as a list (the file's mapping can't be)
        return list, (list(self),)

    def points(self) -> array | memoryview:
        """The latitude then the longitude of each node, in one array: the file's array
        (int32 in 1e-7 degree or float64 degrees) if no node was added, else a float64
        array."""
        if not self._added:
            return self._points
        scale = self._scale
        result = array("d", (value / scale for value in self._points))
        result.extend(value for node in self._added for value in node[:2])
        return result

    def _in_added(self, i, edit=True):
        # The position of node i (or of slice i) in `added`. To edit a node of the file,
        # every node is first moved into `added`, as a list holds them
        if isinstance(i, slice):
            self._own()
            return i
        count, i = len(self), index(i)
        if i < 0:
            i += count
        if not 0 <= i < count:
            raise IndexError("node index out of range")
        if i < len(self._latitudes) and edit:
            self._own()
        return i - len(self._latitudes)

    def _own(self):
        if len(self._latitudes):
            scale = self._scale
            self._added[:0] = (
                [latitude / scale, longitude / scale]
                for latitude, longitude in zip(
                    self._latitudes, self._longitudes
                )
            )
            self._points = memoryview(array("d"))
            self._latitudes = self._longitudes = self._points
            self._scale = 1.0
