"""The classes of the edges of a GeoGraph, lined up with its edges.

This module is internal. Each `GeoGraph` has one `EdgeClasses`.

A graph stores its edges by origin, in three arrays (`Graph._csr()`): the offsets,
the heads and the lengths. The edges of node `u` go to
`heads[offsets[u]:offsets[u + 1]]`. The "index" of an edge is its position in
`heads`. An array is "lined up with the edges" when its value number `i` belongs to
the edge of index `i`. A "class" is the category of an edge, such as `motorway`. An
`EdgeClasses` holds the rows `{"name", "mode"}` of the classes, and the row of the
class of each edge, lined up with the edges.

Example, a graph of three nodes with the edges 0 -> 1, 0 -> 2 and 2 -> 0:

    offsets = [0, 2, 2, 3]    heads = [1, 2, 0]    edge_rows = [4, 4, 7]

The edge 2 -> 0 has the index 2, and its class is the row 7 of the classes.

THE RULE: LINE UP BEFORE A READ

An edit of the graph moves the edges, so `edge_rows` is then older than the graph.
`line_up` runs before each read of `edge_rows` or of `edge_arrays`. It compares the
graph and the count of its edits (`Graph._edit_count`) with those of the last
line-up. When one of the two differs, it reads the edges again. An edge is known by
its two nodes: an edge that was there keeps its class, and a new edge takes the
class of its `add_` call, or no class.

Example, after the edge 0 -> 2 is removed and `add_edge` adds the edge 1 -> 2 with
the class of the row 9:

    offsets = [0, 1, 2, 3]    heads = [1, 2, 0]
    find_old_edge_indexes gives [0, -1, 2]    edge_rows = [4, 9, 7]

An assignment into the list of dicts of a graph (`geograph.graph[0][1] = 10.0`, in
pure Python) does not change the count, so no line-up sees it. After such an
assignment, the caller replaces the graph:
`geograph.graph_object = Graph(graph=geograph.graph)`.
"""

from array import array
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # Only for an annotation
    from scgraph.graph import Graph

# The row of an edge without a class, on a geograph with classes
NO_CLASS = {"name": None, "mode": None}
# The row of the class of an edge is stored in one byte
_MAX_CLASS_COUNT = 256


def iter_edges(
    offsets: array | memoryview, origin_ids: Iterable[int] | None = None
) -> Iterator[tuple[int, int]]:
    """Yield each edge as (origin id, index of the edge), in the order of the edges.

    Example: the offsets [0, 2, 2, 3] give (0, 0), (0, 1) and (2, 2).

    Args:
        offsets: The offsets of the edges, one for each node plus one.
        origin_ids: The nodes whose edges are given, in this order. None for every
            node.
    """
    if origin_ids is None:
        origin_ids = range(len(offsets) - 1)
    for origin_id in origin_ids:
        for edge_index in range(offsets[origin_id], offsets[origin_id + 1]):
            yield origin_id, edge_index


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


def find_old_edge_indexes(
    old_offsets: array | memoryview,
    old_heads: array | memoryview,
    offsets: array | memoryview,
    heads: array | memoryview,
) -> array:
    """Return the index that each edge of a graph had before the graph was edited,
    or -1 for an edge that was not there (int64).

    The function reads each node once in Python: about 0.5 second for a million
    nodes. It is one function, so that a compiled kernel can replace it.
    """
    old_edge_indexes = array("q")
    old_node_count = len(old_offsets) - 1
    for origin_id in range(len(offsets) - 1):
        first, last = offsets[origin_id], offsets[origin_id + 1]
        if origin_id >= old_node_count:
            old_edge_indexes.extend([-1] * (last - first))
            continue
        old_first, old_last = old_offsets[origin_id], old_offsets[origin_id + 1]
        # Most rows are as they were. Two slices are compared in C, so that an edit
        # of a few rows of a large graph does not read each edge in Python.
        if heads[first:last] == old_heads[old_first:old_last]:
            old_edge_indexes.extend(range(old_first, old_last))
            continue
        old_row = {old_heads[i]: i for i in range(old_first, old_last)}
        old_edge_indexes.extend(
            old_row.get(heads[i], -1) for i in range(first, last)
        )
    return old_edge_indexes


def reorder_edge_values(
    values: array | memoryview,
    offsets: array | memoryview,
    order: list[int],
) -> array:
    """Return an array lined up with the edges of a graph whose nodes are reordered.

    Args:
        values: An array lined up with the edges.
        offsets: The offsets of the edges, one for each node plus one.
        order: The nodes in their new order: `order[new id] = id`. A node keeps the
            order of its edges, as `Graph._csr(order)` does.
    """
    values = memoryview(values)
    ordered = array(values.format)
    for origin_id in order:
        first, last = offsets[origin_id], offsets[origin_id + 1]
        ordered.frombytes(values[first:last].cast("B"))
    return ordered


def _check_class_count(class_count: int) -> None:
    if class_count > _MAX_CLASS_COUNT:
        raise ValueError(
            f"A geograph holds {_MAX_CLASS_COUNT} classes at most: got "
            f"{class_count}"
        )


class EdgeClasses:
    """The classes of the edges of one geograph (see the module docstring)."""

    def __init__(self) -> None:
        # The rows `{"name", "mode"}` of the classes: `GeoGraph.classes`. Empty on a
        # geograph without classes. A loader or a merge gives classes to a geograph.
        self.rows = []
        # The row in `rows` of each edge (uint8), lined up with the edges. None on
        # a geograph without classes.
        self.edge_rows = None
        # The offsets, the heads and the lengths of the edges at the last line-up
        self.edge_arrays = None
        # The graph at the last line-up, and its `_edit_count` at that time
        self._graph = None
        self._edit_count = None
        # What the `add_` methods gave for the edges that are not lined up yet, by
        # (origin id, destination id): the row of the class of the edge, or None for
        # no class. The next line-up uses them, then forgets them.
        self.new_edge_rows = {}

    def line_up(self, graph: "Graph") -> bool:
        """Line up the classes with the edges of a graph, if the graph was edited
        since the last line-up.

        Returns:
            Whether the graph was edited. The geograph then removes its metrics.

        Raises:
            ValueError: An edge without a class needs a row after 256 classes.
        """
        edit_count = graph._edit_count
        if graph is self._graph and edit_count == self._edit_count:
            return False
        edge_arrays = graph._csr()
        offsets, heads, _ = edge_arrays
        edge_rows = self.edge_rows
        if edge_rows is not None:
            names = [row["name"] for row in self.rows]
            no_class_row = names.index(None) if None in names else len(names)
            old_edge_rows = array("B", bytes(edge_rows))
            if no_class_row == _MAX_CLASS_COUNT:
                # A byte cannot hold the row of no class after 256 named classes.
                # The rows are lined up in a wider array, then checked below.
                old_edge_rows = array("H", old_edge_rows)
            # An edge that was there keeps its row. The index -1 of a new edge reads
            # this last value.
            old_edge_rows.append(no_class_row)
            edge_rows = array(
                old_edge_rows.typecode,
                map(
                    old_edge_rows.__getitem__,
                    find_old_edge_indexes(
                        *self.edge_arrays[:2], offsets, heads
                    ),
                ),
            )
            for nodes, row in self.new_edge_rows.items():
                edge_index = find_edge_index(offsets, heads, *nodes)
                if edge_index is not None:
                    edge_rows[edge_index] = no_class_row if row is None else row
            # The row of no class is added when an edge needs it
            if no_class_row == len(names) and no_class_row in edge_rows:
                _check_class_count(no_class_row + 1)
                self.rows.append(dict(NO_CLASS))
            if edge_rows.typecode != "B":
                edge_rows = array("B", edge_rows)
        self.edge_arrays, self.edge_rows = edge_arrays, edge_rows
        self.new_edge_rows = {}
        self._graph, self._edit_count = graph, edit_count
        return True

    def set_edge_arrays(
        self, graph: "Graph", edge_arrays: tuple[array | memoryview, ...]
    ) -> None:
        """Take the edges of a graph from the arrays that the graph was built from
        (offsets, heads, lengths), so that the first line-up does not read the
        graph."""
        self.edge_arrays = edge_arrays
        self._graph, self._edit_count = graph, graph._edit_count

    def list_edge_values(self, values_of_each_node: list[dict]) -> list:
        """Return one value for each edge, in the order of the lined-up edges.

        Args:
            values_of_each_node: For each node, a dict from the destination of an
                edge of this node to the value of the edge. An edge that its dict
                lacks gets None.
        """
        offsets, heads, _ = self.edge_arrays
        return [
            values_of_each_node[origin_id].get(heads[edge_index])
            for origin_id, edge_index in iter_edges(offsets)
        ]

    def set_classes_by_name(
        self, rows: list[dict], edge_class_names: list[str | None]
    ) -> None:
        """Give its classes to a geograph, from the name of the class of each edge.

        Args:
            rows: The rows `{"name", "mode"}` of the classes. The row of no class
                is added after them when an edge needs it.
            edge_class_names: The name of the class of each edge, or None for no
                class, in the order of the lined-up edges (see `list_edge_values`).
        """
        rows = list(rows)
        if None in edge_class_names:
            rows.append(dict(NO_CLASS))
        _check_class_count(len(rows))
        row_of_each_name = {
            row["name"]: index for index, row in enumerate(rows)
        }
        self.rows = rows
        self.edge_rows = array(
            "B", map(row_of_each_name.__getitem__, edge_class_names)
        )

    def merge(
        self, other: "EdgeClasses", first_node_id: int
    ) -> dict[tuple[int, int], int]:
        """Add the classes of another geograph to the rows, for a merge. A class of
        the other geograph is added unless a class has its name. A geograph without
        classes first gets the row of no class for each of its edges. Both
        `EdgeClasses` are lined up.

        Args:
            other: The classes of the geograph whose edges the merge adds.
            first_node_id: The id that the node 0 of the other geograph gets in the
                merged graph. Each next node gets the next id.

        Returns:
            The row in `rows` of each edge of the other geograph, by the ids of its
            two nodes in the merged graph. The caller adds it to `new_edge_rows`
            when the graph holds these edges.

        Raises:
            ValueError: The two geographs have more than 256 classes together. This
                geograph is not changed.
        """
        rows = self.rows if self.edge_rows is not None else [dict(NO_CLASS)]
        names = [row["name"] for row in rows]
        new_rows = [dict(row) for row in other.rows if row["name"] not in names]
        # Checked before any change of this geograph
        _check_class_count(len(rows) + len(new_rows))
        if self.edge_rows is None:
            self.rows = rows
            self.edge_rows = array("B", bytes(len(self.edge_arrays[1])))
        self.rows.extend(new_rows)
        # The row in `rows` of each class of the other geograph
        names = [row["name"] for row in self.rows]
        merged_rows = [names.index(row["name"]) for row in other.rows]
        other_offsets, other_heads, _ = other.edge_arrays
        return {
            (
                first_node_id + origin_id,
                first_node_id + other_heads[edge_index],
            ): merged_rows[other.edge_rows[edge_index]]
            for origin_id, edge_index in iter_edges(other_offsets)
        }

    def find_row(self, edge_class: str | None) -> int | None:
        """Return the row of the class of a name, or None for None.

        Raises:
            ValueError: No class has this name.
        """
        if edge_class is None:
            return None
        names = [row["name"] for row in self.rows]
        if edge_class not in names:
            raise ValueError(
                f"Unknown class {edge_class!r}: the classes of this geograph are "
                f"{names}"
            )
        return names.index(edge_class)

    def record_new_edges(
        self, edges: Iterable[tuple[int, int]], row: int | None
    ) -> None:
        """Keep the row that an `add_` call gave to its new edges, each one an
        (origin id, destination id), for the next line-up."""
        if self.edge_rows is not None:
            for nodes in edges:
                self.new_edge_rows[nodes] = row

    def forget_new_edges(self, edges: Iterable[tuple[int, int]]) -> None:
        """Drop what an `add_` call gave for edges that the graph no longer has,
        each one an (origin id, destination id)."""
        for nodes in edges:
            self.new_edge_rows.pop(nodes, None)

    def forget_new_edges_of_node(self, node_id: int) -> None:
        """Drop what an `add_` call gave for the edges of a removed node. The method
        reads each new edge: `forget_new_edges` is faster for a caller that knows
        the edges of the node."""
        new_edge_rows = self.new_edge_rows
        for nodes in [nodes for nodes in new_edge_rows if node_id in nodes]:
            del new_edge_rows[nodes]
