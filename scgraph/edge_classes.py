"""The class of each edge of a GeoGraph, found by the two nodes of the edge.

This module is internal. Each `GeoGraph` has one `EdgeClasses`.

WORDS

- A "class" is the category of an edge, such as `motorway`. `classes` holds one
  row `{"name", "edge_mode"}` for each class.
- A "class id" is the position of a class in `classes`. The class id 255 means
  "no class", so a geograph holds 255 classes at most.
- An "edge id" is the position of an edge in the arrays of a graph. The edges of
  the node `u` have the ids `offsets[u]` to `offsets[u + 1] - 1`, and
  `heads[edge_id]` is the node that the edge goes to.

WHAT IT HOLDS

- The "loaded edges": the edges that a loader or the constructor gave, as the two
  arrays above, with `edge_class_ids`: the class id of each of them. No edit of
  the graph changes these three arrays.
- The "added edges": a dict `{(origin id, destination id): class id}` of the
  edges that an `add_` method of the geograph added.

THE IDEA: AN EDGE IS KNOWN BY ITS TWO NODES

An edit of the graph changes the id of an edge, but never the ids of its two
nodes. So `find_class` takes the two nodes of an edge. It looks in the added
edges, then in the loaded edges. An edge that is in neither has no class.

A network file and the kernel of the weights per km need one array: the class id
of each edge of the graph as it is now. `list_edge_class_ids` computes it node by
node. A node that still has exactly its loaded edges copies their class ids. For
another node, each edge is found by its two nodes, as in `find_class`.

EXAMPLE

A loader reads three nodes, with the edges 0 -> 1, 0 -> 2 and 2 -> 0:

    classes        = [motorway, primary]    the class ids 0 and 1
    offsets        = [0, 2, 2, 3]
    heads          = [1, 2, 0]
    edge_class_ids = [1, 1, 0]

`find_class(2, 0)` gives the row of `motorway`: the edge 2 -> 0 has the edge id 2,
and its class id is 0.

Then the edge 0 -> 2 is removed, `add_edge` adds 1 -> 2 as a `motorway`, and the
caller adds 1 -> 0 on `graph_object` directly. The loaded edges stay as they are,
and the added edges are `{(1, 2): 0}`:

    find_class(0, 1) gives the row of primary     a loaded edge
    find_class(1, 2) gives the row of motorway    an added edge
    find_class(1, 0) gives the row of no class    not loaded, not added

The graph now has `heads = [1, 2, 0, 0]`, and `list_edge_class_ids` gives
`[1, 0, 255, 0]`. The node 2 still has its loaded edge, and copies its class id.
The nodes 0 and 1 changed, so each of their edges is found by its two nodes.
"""

from array import array
from collections.abc import Iterable

from scgraph.network_file import NO_CLASS_ID

# What `find_class` gives for an edge without a class
_NO_CLASS_ROW = {"name": None, "edge_mode": None}


def find_edge_id(
    offsets: array | memoryview,
    heads: array | memoryview,
    origin_id: int,
    destination_id: int,
) -> int | None:
    """Return the id of the edge from one node to another: its position in `heads`.
    Return None when the graph has no such edge, or no node `origin_id`."""
    if not 0 <= origin_id < len(offsets) - 1:
        return None
    for edge_id in range(offsets[origin_id], offsets[origin_id + 1]):
        if heads[edge_id] == destination_id:
            return edge_id
    return None


def _check_class_count(class_count: int) -> None:
    # A class id is one byte, and NO_CLASS_ID is the id of no class.
    if class_count > NO_CLASS_ID:
        raise ValueError(
            f"A geograph holds {NO_CLASS_ID} classes at most: got {class_count}"
        )


def _list_class_names(classes: Iterable[dict]) -> list[str | None]:
    return [class_row["name"] for class_row in classes]


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
            classes: The row `{"name", "edge_mode"}` of each class that a loader
                read. Empty for a geograph without classes.
            offsets: The id of the first loaded edge of each node, then the count
                of the loaded edges. None for a geograph without classes.
            heads: The destination of each loaded edge. None with `offsets`.
            edge_class_ids: The class id of each loaded edge (uint8), 255 for an
                edge without a class. The three arrays are kept without a copy.

        Raises:
            ValueError: `classes` has more than 255 rows.
        """
        self.classes = [dict(class_row) for class_row in classes]
        _check_class_count(len(self.classes))
        if offsets is None:
            # A geograph without classes has no loaded edge.
            offsets, heads = array("i", [0]), array("i")
            edge_class_ids = array("B")
        self._loaded_offsets, self._loaded_heads = offsets, heads
        self._loaded_edge_class_ids = edge_class_ids
        # The class id of each added edge, by (origin id, destination id)
        self._class_ids_of_added_edges = {}

    @classmethod
    def build_from_class_names(
        cls,
        classes: list[dict] | None,
        edge_classes: list[dict[int, str]] | None,
        offsets: array | memoryview,
        heads: array | memoryview,
    ) -> "EdgeClasses":
        """Return the `EdgeClasses` of a geograph whose constructor got the class
        of each edge as a name. The edges of the graph become the loaded edges.

        Args:
            classes: The argument `classes` of `GeoGraph`: the row
                `{"name", "edge_mode"}` of each class.
            edge_classes: The argument `edge_classes` of `GeoGraph`: for each
                node, a dict from the destination of an edge of this node to the
                name of the class of the edge. An edge that its dict lacks has no
                class. None gives a class to no edge.
            offsets: The id of the first edge of each node of the graph, then the
                count of its edges.
            heads: The destination of each edge.

        Raises:
            ValueError: `classes` is None, has more than 255 rows, or has a row
                without a name or without an edge mode. `edge_classes` does not
                have one dict for each node, or names a destination that is no
                edge of the graph, or a class that `classes` lacks.
        """
        if classes is None:
            raise ValueError(
                "edge_classes needs classes: the row {'name': ..., 'edge_mode': "
                "...} of each class"
            )
        for class_row in classes:
            if not (
                isinstance(class_row, dict)
                and isinstance(class_row.get("name"), str)
                and "edge_mode" in class_row
            ):
                raise ValueError(
                    "classes must give each class as a row {'name': ..., "
                    f"'edge_mode': ...}}, with a string as name: got {class_row!r}"
                )
        node_count = len(offsets) - 1
        if edge_classes is None:
            edge_classes = [{}] * node_count
        if len(edge_classes) != node_count:
            raise ValueError(
                "edge_classes must give one dict for each node: got "
                f"{len(edge_classes)} dicts for {node_count} nodes"
            )
        class_names = _list_class_names(classes)
        edge_class_ids = array("B")
        for origin_id, class_names_of_origin in enumerate(edge_classes):
            destination_ids = heads[offsets[origin_id] : offsets[origin_id + 1]]
            for destination_id in class_names_of_origin:
                if destination_id not in destination_ids:
                    raise ValueError(
                        f"edge_classes gives a class to the edge from node "
                        f"{origin_id} to node {destination_id}, which is no "
                        "edge of the graph"
                    )
            for destination_id in destination_ids:
                class_name = class_names_of_origin.get(destination_id)
                if class_name is None:
                    edge_class_ids.append(NO_CLASS_ID)
                elif class_name in class_names:
                    edge_class_ids.append(class_names.index(class_name))
                else:
                    raise ValueError(
                        f"edge_classes gives the class {class_name!r} to the "
                        f"edge from node {origin_id} to node {destination_id}"
                        ": classes has no row with this name"
                    )
        # The loaded edges are copies: the graph may change its own arrays at
        # an edit.
        return cls(
            classes, array("i", offsets), array("i", heads), edge_class_ids
        )

    def find_class(self, origin_id: int, destination_id: int) -> dict:
        """Return the row `{"name", "edge_mode"}` of the class of the edge from one
        node to another. Both values are None for an edge without a class."""
        class_id = self._find_class_id(origin_id, destination_id)
        return (
            _NO_CLASS_ROW if class_id == NO_CLASS_ID else self.classes[class_id]
        )

    def _find_class_id(self, origin_id: int, destination_id: int) -> int:
        # Return the class id of the edge from one node to another: of the added
        # edge of these nodes, else of their loaded edge, else NO_CLASS_ID.
        edge = (origin_id, destination_id)
        if edge in self._class_ids_of_added_edges:
            return self._class_ids_of_added_edges[edge]
        edge_id = find_edge_id(
            self._loaded_offsets, self._loaded_heads, origin_id, destination_id
        )
        if edge_id is None:
            return NO_CLASS_ID
        return self._loaded_edge_class_ids[edge_id]

    def list_edge_class_ids(
        self, offsets: array | memoryview, heads: array | memoryview
    ) -> array | memoryview | None:
        """Return the class id of each edge of a graph, as a network file stores
        it.

        Args:
            offsets: The id of the first edge of each node of the graph, then the
                count of its edges.
            heads: The destination of each edge.

        Returns:
            An array with the class id of each edge at the id of the edge (uint8),
            255 for an edge without a class. None for a geograph without classes.
        """
        if not self.classes:
            return None
        edge_class_ids = array("B")
        # A slice of a memoryview makes no copy, and two slices compare by their
        # values, in C.
        heads = memoryview(heads)
        loaded_offsets = self._loaded_offsets
        loaded_heads = memoryview(self._loaded_heads)
        loaded_node_count = len(loaded_offsets) - 1
        origins_of_added_edges = {
            origin_id for origin_id, _ in self._class_ids_of_added_edges
        }
        for origin_id in range(len(offsets) - 1):
            destination_ids = heads[offsets[origin_id] : offsets[origin_id + 1]]
            # A node after the last loaded node has no loaded edge.
            first_loaded_edge_id = last_loaded_edge_id = 0
            if origin_id < loaded_node_count:
                first_loaded_edge_id = loaded_offsets[origin_id]
                last_loaded_edge_id = loaded_offsets[origin_id + 1]
            loaded_edges = slice(first_loaded_edge_id, last_loaded_edge_id)
            # Most nodes have their loaded edges, in the same order. They take
            # the class ids of these edges, so that an edit of a few nodes of a
            # large graph does not read each edge in Python.
            if (
                origin_id not in origins_of_added_edges
                and destination_ids == loaded_heads[loaded_edges]
            ):
                edge_class_ids.frombytes(
                    self._loaded_edge_class_ids[loaded_edges]
                )
            else:
                for destination_id in destination_ids:
                    edge_class_ids.append(
                        self._find_class_id(origin_id, destination_id)
                    )
        return edge_class_ids

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
        """Store the class that an `add_` method gives to its new edges, each one an
        (origin id, destination id). `edge_class` is the name of a class, or None
        for no class. It replaces the class of a loaded edge of the same nodes.
        """
        class_id = NO_CLASS_ID
        if edge_class is not None:
            class_id = _list_class_names(self.classes).index(edge_class)
        self._class_ids_of_added_edges.update(dict.fromkeys(edges, class_id))

    def forget_added_edges(self, edges: Iterable[tuple[int, int]]) -> None:
        """Remove the class of the added edges that the graph no longer has, each
        one an (origin id, destination id)."""
        for edge in edges:
            self._class_ids_of_added_edges.pop(edge, None)

    def merge(self, other: "EdgeClasses", first_node_id: int) -> None:
        """Take the classes of the edges of another geograph, for a merge. A class
        of the other geograph is added to `classes`, unless a class has its name.
        The loaded edges of the other geograph follow the loaded edges of this
        geograph. Its added edges are added to the added edges of this geograph.

        Args:
            other: The `EdgeClasses` of the other geograph.
            first_node_id: The id that the node 0 of the other geograph gets in the
                merged graph. Each next node gets the next id.

        Raises:
            ValueError: The two geographs have more than 255 classes together. This
                geograph is not changed.
        """
        if not other.classes:
            return
        class_names = _list_class_names(self.classes)
        classes = self.classes + [
            dict(class_row)
            for class_row in other.classes
            if class_row["name"] not in class_names
        ]
        _check_class_count(len(classes))
        # The class id in the merged classes of each class id of the other
        # geograph. The id of no class stays the id of no class.
        merged_class_names = _list_class_names(classes)
        merged_class_ids = bytes(
            merged_class_names.index(class_row["name"])
            for class_row in other.classes
        ).ljust(NO_CLASS_ID, b"\0") + bytes([NO_CLASS_ID])
        # The loaded edges of the other geograph start at the node
        # `first_node_id`. A node of this geograph without loaded edges, such as
        # an added node, has none in the new arrays.
        offsets = array("i", self._loaded_offsets[: first_node_id + 1])
        edge_count = offsets[-1]
        offsets.extend([edge_count] * (first_node_id + 1 - len(offsets)))
        offsets.extend(
            edge_count + other_offset
            for other_offset in other._loaded_offsets[1:]
        )
        heads = array("i", self._loaded_heads[:edge_count])
        heads.extend(
            first_node_id + destination_id
            for destination_id in other._loaded_heads
        )
        edge_class_ids = array("B")
        edge_class_ids.frombytes(self._loaded_edge_class_ids[:edge_count])
        edge_class_ids.frombytes(
            bytes(other._loaded_edge_class_ids).translate(merged_class_ids)
        )
        self.classes = classes
        self._loaded_offsets, self._loaded_heads = offsets, heads
        self._loaded_edge_class_ids = edge_class_ids
        for edge, class_id in other._class_ids_of_added_edges.items():
            origin_id, destination_id = edge
            self._class_ids_of_added_edges[
                (first_node_id + origin_id, first_node_id + destination_id)
            ] = merged_class_ids[class_id]
