"""The class of each edge of a GeoGraph, found by the two nodes of the edge.

This module is internal. Each `GeoGraph` has one `EdgeClasses`.

WHAT IT HOLDS

A "class" is the category of an edge, such as `motorway`. An `EdgeClasses` holds:

- `classes`: one entry `{"name", "edge_mode"}` for each class of the geograph. The "row"
  of a class is the position of its entry in `classes`, counted from 0. An edge
  without a class has the entry `{"name": None, "edge_mode": None}`.
- The "loaded edges": the edges of the graph that a loader read, with the row of
  the class of each one. They are three arrays. The edges of the node `u` go to
  `heads[offsets[u]:offsets[u + 1]]`. The "index" of an edge is its position in
  `heads`, and `edge_class_ids` holds the row of its class at this index. No edit of
  the graph changes these arrays.
- The "added edges": the class that an `add_` method of the geograph gave to an
  edge, in a dict by (origin id, destination id).

THE IDEA: AN EDGE IS KNOWN BY ITS TWO NODES

An edit of the graph moves the index of an edge, and not its two nodes: the id of
a node never changes. So `find_class` takes the two nodes of an edge. It gives the
entry of the class of the added edge of these nodes, else of their loaded edge,
else the entry of no class. An edit of the graph makes no answer out of date.

A network file and the kernel of the weights per km need one array, lined up with
the edges of the graph: the row of the class of each edge, at the index of the edge.
`list_class_rows` computes this array from `find_class`, when a caller asks for it.
It keeps the array until the graph is edited.

Example, a loader reads three nodes with the edges 0 -> 1, 0 -> 2 and 2 -> 0:

    classes = [{"name": "motorway", "edge_mode": "road"},
               {"name": "primary", "edge_mode": "road"}]
    offsets = [0, 2, 2, 3]    heads = [1, 2, 0]    edge_class_ids = [1, 1, 0]

`find_class(2, 0)` gives the entry of `motorway`: the edge 2 -> 0 has the index 2,
and the row 0.

Then the edge 0 -> 2 is removed. `add_edge` adds the edge 1 -> 2 with the class
`motorway`, and `graph_object` adds the edge 1 -> 0 itself. The three arrays stay,
and the added edges are `{(1, 2): "motorway"}`:

    find_class(0, 1) gives the entry of "primary"     the loaded edge of index 0
    find_class(1, 2) gives the entry of "motorway"    an added edge
    find_class(1, 0) gives the entry of no class      no added edge, no loaded edge

The graph now has `offsets = [0, 1, 3, 4]` and `heads = [1, 2, 0, 0]`. For these
arrays, `list_class_rows` gives `edge_class_ids = [1, 0, 2, 0]`. The row 2 is the
class without a name, added after the two classes for the edge 1 -> 0.
"""

from array import array
from collections.abc import Iterable
from itertools import chain, pairwise, repeat, starmap

# The entry of an edge without a class: the class without a name. A network file
# stores the row of a class for each edge, so it has this entry for such an edge.
_NO_CLASS = {"name": None, "edge_mode": None}
# A network file stores the row of the class of an edge in one byte
_MAX_CLASS_COUNT = 256


def find_edge_index(
    offsets: array | memoryview,
    heads: array | memoryview,
    origin_id: int,
    destination_id: int,
) -> int | None:
    """Return the index of the edge from one node to another, or None when the
    graph has no such edge or no node `origin_id`."""
    if not 0 <= origin_id < len(offsets) - 1:
        return None
    for edge_index in range(offsets[origin_id], offsets[origin_id + 1]):
        if heads[edge_index] == destination_id:
            return edge_index
    return None


def _check_class_count(class_count: int) -> None:
    if class_count > _MAX_CLASS_COUNT:
        raise ValueError(
            f"A geograph holds {_MAX_CLASS_COUNT} classes at most: got "
            f"{class_count}"
        )


def _list_class_names(classes: Iterable[dict]) -> list[str | None]:
    return [class_entry["name"] for class_entry in classes]


class EdgeClasses:
    """The class of each edge of one geograph (see the module docstring)."""

    def __init__(
        self,
        classes: Iterable[dict] = (),
        offsets: array | memoryview | None = None,
        heads: array | memoryview | None = None,
        edge_class_ids: array | memoryview | None = None,
    ) -> None:
        """
        Args:
            classes: The entry `{"name", "edge_mode"}` of each class that a loader read.
                Empty for a geograph without classes.
            offsets: The offsets of the loaded edges, one for each node plus one.
                None for a geograph without classes, as `heads` and `edge_class_ids`.
            heads: The destination of each loaded edge.
            edge_class_ids: The row of the class of each loaded edge (uint8). The
                three arrays are kept without a copy.
        """
        self.classes = [dict(class_entry) for class_entry in classes]
        if offsets is None:
            # A geograph without classes has no loaded edge.
            offsets, heads = array("i", [0]), array("i")
            edge_class_ids = array("B")
        self._loaded_offsets, self._loaded_heads = offsets, heads
        self._loaded_edge_class_ids = edge_class_ids
        # The entry of the class of each added edge, by (origin id, destination id)
        self._classes_of_added_edges = {}
        # The last result of `list_class_rows`, and the heads of its graph. The
        # edges of a graph read from a network file are the loaded edges.
        self._listed_heads = heads
        self._listed_class_rows = (self.classes, edge_class_ids)

    @classmethod
    def build_from_class_names(
        cls, classes: list[dict], edge_class_names: list[dict]
    ) -> "EdgeClasses":
        """Return the `EdgeClasses` of a loader that read the class of each edge as
        a name.

        Args:
            classes: The entry `{"name", "edge_mode"}` of each class.
            edge_class_names: For each node, a dict from the destination of an edge
                of this node to the name of the class of the edge, as
                `intermediate_nodes` gives its shape. An edge that its dict lacks
                has no class.

        Raises:
            ValueError: The loader read more than 256 classes.
        """
        _check_class_count(len(classes))
        find_class_row = _list_class_names(classes).index
        offsets, heads, edge_class_ids = array("i", [0]), array("i"), array("B")
        for class_names_of_origin in edge_class_names:
            heads.extend(class_names_of_origin)
            edge_class_ids.extend(
                map(find_class_row, class_names_of_origin.values())
            )
            offsets.append(len(heads))
        return cls(classes, offsets, heads, edge_class_ids)

    def find_class(self, origin_id: int, destination_id: int) -> dict:
        """Return the entry of the class of the edge from one node to another:
        `{"name": None, "edge_mode": None}` for an edge without a class."""
        edge = (origin_id, destination_id)
        if edge in self._classes_of_added_edges:
            return self._classes_of_added_edges[edge]
        edge_index = find_edge_index(
            self._loaded_offsets, self._loaded_heads, origin_id, destination_id
        )
        if edge_index is None:
            return _NO_CLASS
        return self.classes[self._loaded_edge_class_ids[edge_index]]

    def list_class_rows(
        self, offsets: array | memoryview, heads: array | memoryview
    ) -> tuple[list[dict], array | memoryview | None]:
        """Return the classes and the row of the class of each edge of a graph, as
        a network file stores them. The method keeps its last result: a second call
        for the same graph computes nothing.

        Args:
            offsets: The offsets of the edges of the graph, one for each node plus
                one.
            heads: The destination of each edge. The same array means the same
                graph: the caller gives new arrays after an edit of the graph.

        Returns:
            The entries of the classes, and the row of the class of each edge in
            these entries (uint8), at the index of the edge. The entries are
            `classes`, and after them the class without a name when an edge has no
            class and `classes` lacks this entry. `([], None)` for a geograph
            without classes.

        Raises:
            ValueError: An edge without a class needs a 257th class.
        """
        if heads is self._listed_heads:
            return self._listed_class_rows
        if not self.classes:
            return [], None
        classes, class_names = self.classes, _list_class_names(self.classes)
        edge_class_ids = array("B")
        # An array and a memoryview do not compare by their values: two
        # memoryviews do.
        graph_heads = memoryview(heads)
        loaded_heads = memoryview(self._loaded_heads)
        # The slice of the edges of each node, in the graph and in the loaded
        # edges. A node after the last loaded node has no loaded edge.
        edge_slices = starmap(slice, pairwise(offsets))
        loaded_edge_slices = chain(
            starmap(slice, pairwise(self._loaded_offsets)), repeat(slice(0))
        )
        origins_of_added_edges = {
            origin_id for origin_id, _ in self._classes_of_added_edges
        }
        for origin_id, (edges_of_origin, loaded_edges_of_origin) in enumerate(
            zip(edge_slices, loaded_edge_slices)
        ):
            destination_ids = graph_heads[edges_of_origin]
            # Most nodes have their loaded edges, in the same order. The two
            # slices are compared in C, so that an edit of a few nodes of a large
            # graph does not read each edge in Python.
            if (
                origin_id not in origins_of_added_edges
                and destination_ids == loaded_heads[loaded_edges_of_origin]
            ):
                edge_class_ids.frombytes(
                    self._loaded_edge_class_ids[loaded_edges_of_origin]
                )
                continue
            for destination_id in destination_ids:
                class_name = self.find_class(origin_id, destination_id)["name"]
                if class_name is None and None not in class_names:
                    classes = [*classes, dict(_NO_CLASS)]
                    class_names.append(None)
                    _check_class_count(len(classes))
                edge_class_ids.append(class_names.index(class_name))
        self._listed_heads = heads
        self._listed_class_rows = (classes, edge_class_ids)
        return self._listed_class_rows

    def check_class(self, edge_class: str | None) -> None:
        """Check the class that a caller names.

        Raises:
            ValueError: `edge_class` is not None and not the name of a class.
        """
        if edge_class is None:
            return
        class_names = _list_class_names(self.classes)
        if edge_class not in class_names:
            raise ValueError(
                f"Unknown class {edge_class!r}: the classes of this geograph are "
                f"{class_names}"
            )

    def set_class(
        self, edges: Iterable[tuple[int, int]], edge_class: str | None
    ) -> None:
        """Keep the class that an `add_` method gives to its new edges, each one an
        (origin id, destination id). `edge_class` is the name of a class, or None
        for no class. It replaces the class of a loaded edge of the same nodes.
        """
        class_entry = _NO_CLASS
        if edge_class is not None:
            class_row = _list_class_names(self.classes).index(edge_class)
            class_entry = self.classes[class_row]
        self._classes_of_added_edges.update(dict.fromkeys(edges, class_entry))

    def forget_added_edges(self, edges: Iterable[tuple[int, int]]) -> None:
        """Drop the class of the added edges that the graph no longer has, each one
        an (origin id, destination id)."""
        for edge in edges:
            self._classes_of_added_edges.pop(edge, None)

    def merge(self, other: "EdgeClasses", first_node_id: int) -> None:
        """Take the classes of the edges of another geograph, for a merge. A class
        of the other geograph is added to `classes`, unless a class has its name.
        Its loaded edges follow the loaded edges of this geograph, and its added
        edges join the added edges of this geograph.

        Args:
            other: The `EdgeClasses` of the other geograph.
            first_node_id: The id that the node 0 of the other geograph gets in the
                merged graph. Each next node gets the next id.

        Raises:
            ValueError: The two geographs have more than 256 classes together. This
                geograph is not changed.
        """
        if not other.classes:
            return
        class_names = _list_class_names(self.classes)
        classes = self.classes + [
            dict(class_entry)
            for class_entry in other.classes
            if class_entry["name"] not in class_names
        ]
        _check_class_count(len(classes))
        # The row in the merged classes of each class row of the other geograph
        merged_class_rows = bytes(
            map(
                _list_class_names(classes).index,
                _list_class_names(other.classes),
            )
        ).ljust(256, b"\0")
        # The loaded edges of the other geograph start at the node
        # `first_node_id`. A node of this geograph without loaded edges, such as
        # an added node, has none in the new arrays.
        offsets = array("i", self._loaded_offsets[: first_node_id + 1])
        edge_count = offsets[-1]
        offsets.extend([edge_count] * (first_node_id + 1 - len(offsets)))
        offsets.extend(map(edge_count.__add__, other._loaded_offsets[1:]))
        heads = array("i", self._loaded_heads[:edge_count])
        heads.extend(map(first_node_id.__add__, other._loaded_heads))
        edge_class_ids = array("B")
        edge_class_ids.frombytes(self._loaded_edge_class_ids[:edge_count])
        edge_class_ids.frombytes(
            bytes(other._loaded_edge_class_ids).translate(merged_class_rows)
        )
        self.classes = classes
        self._loaded_offsets, self._loaded_heads = offsets, heads
        self._loaded_edge_class_ids = edge_class_ids
        for edge, class_entry in other._classes_of_added_edges.items():
            origin_id, destination_id = edge
            self._classes_of_added_edges[
                (first_node_id + origin_id, first_node_id + destination_id)
            ] = class_entry
