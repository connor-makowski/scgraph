"""The edges of a `GeoGraph`, each with its class.

This module is internal. `GeoGraphEdges` is the mixin of `GeoGraph` that holds the edge classes,
reads the arrays of the edges, and lists the edges of the network or of a path.
"""

import operator
from scgraph.edge_classes import find_edge_id
from array import array
from collections.abc import Iterable, Iterator


class GeoGraphEdges:
    """The edges of a `GeoGraph`, each with its class."""

    @property
    def classes(self) -> list[dict]:
        """
        The classes of the edges, as rows `{"name": ..., "edge_mode": ...}`. A class
        is the category of an edge, such as `motorway`. Its edge mode is the kind of
        transport of its edges, such as `road`. A loader, the arguments `classes` and
        `edge_classes` of the constructor, or a merge gives classes to a geograph.
        Without them, the list is empty. `get_edges` gives the class of each edge.
        """
        return self._edge_classes.classes

    def _read_edge_arrays(
        self, check_edge_count: bool = False
    ) -> tuple[array | memoryview, ...]:
        # Return the arrays of the edges of `graph_object`: `node_first_edge_ids`,
        # `edge_destination_node_ids` and the lengths. The method reads them again when the graph or its count
        # of edits has changed: the caller may have edited `graph_object` itself.
        # It then removes the metrics: a metric has the weight of each edge at the
        # id that the edge had before the edit.
        graph = self.graph_object
        # A pure-Python graph keeps its edges in the list `__graph__`, which a
        # caller can change without a counted edit. A C++ graph has no such list.
        # The count reads every node, so only a call that computes or writes one
        # value for each edge asks for it: a query does not.
        rows = getattr(graph, "__graph__", None) if check_edge_count else None
        if (
            graph is not self._edge_arrays_graph
            or graph._edit_count != self._edge_arrays_edit_count
        ):
            self._remove_metrics()
            self._set_edge_arrays(graph._get_edge_arrays())
        elif rows is not None and sum(map(len, rows)) != len(
            self._edge_arrays[1]
        ):
            raise ValueError(
                "The edges of graph_object changed without add_edge, "
                "remove_edge, add_node or remove_node. Edit the edges with "
                "these methods of the geograph or of graph_object."
            )
        return self._edge_arrays

    def _set_edge_arrays(
        self,
        edge_arrays: tuple[array | memoryview, ...],
        edge_class_ids: array | memoryview | None = None,
    ) -> None:
        # Keep the arrays of the edges of `graph_object` for `_read_edge_arrays`:
        # `node_first_edge_ids`, `edge_destination_node_ids` and the lengths. `edge_class_ids` gives the
        # class id of each of these edges when a network file holds it. With
        # None, `_read_edge_class_ids` computes it.
        self._edge_arrays = edge_arrays
        self._edge_arrays_graph = self.graph_object
        self._edge_arrays_edit_count = self.graph_object._edit_count
        self._edge_class_ids = edge_class_ids

    def _read_edge_class_ids(self) -> array | memoryview | None:
        # Return the class id of each edge of `graph_object`, by edge id: 255 for
        # an edge without a class. Return None for a geograph without classes.
        # The array is computed at the first call, and again after an edit.
        node_first_edge_ids, edge_destination_node_ids, _ = (
            self._read_edge_arrays()
        )
        if self._edge_class_ids is None:
            self._edge_class_ids = self._edge_classes.list_edge_class_ids(
                node_first_edge_ids, edge_destination_node_ids
            )
        return self._edge_class_ids

    def get_edges(
        self,
        origin_id: int | None = None,
        edge_class: str | None = None,
    ) -> list[dict]:
        """
        Function:

        - Get the edges of the geograph, or those of one node or of one class. With both arguments, only the edges that fit both are returned

        Optional Arguments:

        - `origin_id`: The id of a node: only the edges that leave this node are returned; an id that is not in the geograph raises a ValueError
        - `edge_class`: The name of a class of `classes`: only the edges of this class are returned; an unknown name raises a ValueError

        Returns:

        - A list with one dictionary for each edge, in the order of the origins: `{"origin_id", "destination_id", "length", "edge_class", "edge_mode", "metric_weights"}`
        - `length` is in `geograph_units`. `edge_class` is the name of the class of the edge and `edge_mode` is the edge mode of that class; both are None for an edge without a class
        - `metric_weights` is a dictionary `{name: weight}`: the weight of the edge in each metric other than `length`; infinity for an edge that is closed in the metric
        """
        node_first_edge_ids, edge_destination_node_ids, _ = (
            self._read_edge_arrays()
        )
        if (
            origin_id is not None
            and not 0 <= origin_id < len(node_first_edge_ids) - 1
        ):
            raise ValueError(f"Node {origin_id} is not in the geograph")
        self._edge_classes.check_class(edge_class)
        edges = self._iter_edges(origin_id)
        if edge_class is not None:
            find_class = self._edge_classes.find_class
            edges = (
                (origin_id, edge_id)
                for origin_id, edge_id in edges
                if find_class(origin_id, edge_destination_node_ids[edge_id])[
                    "name"
                ]
                == edge_class
            )
        return list(self._iter_edge_dicts(edges))

    def _iter_edges(
        self, origin_id: int | None = None
    ) -> Iterator[tuple[int, int]]:
        """Return each edge of one node, or every edge for None, as (origin id,
        edge id), in the order of the edges."""
        node_first_edge_ids = self._read_edge_arrays()[0]
        origin_ids = (
            range(len(node_first_edge_ids) - 1)
            if origin_id is None
            else (origin_id,)
        )
        return (
            (origin_id, edge_id)
            for origin_id in origin_ids
            for edge_id in range(
                node_first_edge_ids[origin_id],
                node_first_edge_ids[origin_id + 1],
            )
        )

    def _iter_edge_dicts(
        self, edges: Iterable[tuple[int, int]]
    ) -> Iterator[dict]:
        """Yield the dictionary of each edge, as `get_edges` returns it. `edges`
        gives each edge as (origin id, edge id)."""
        _, edge_destination_node_ids, lengths = self._read_edge_arrays()
        find_class = self._edge_classes.find_class
        weights_of_metrics = [
            (name, metric_record.weights)
            for name, metric_record in self._read_metrics().items()
        ]
        for origin_id, edge_id in edges:
            destination_id = edge_destination_node_ids[edge_id]
            class_row = find_class(origin_id, destination_id)
            yield {
                "origin_id": origin_id,
                "destination_id": destination_id,
                "length": lengths[edge_id],
                "edge_class": class_row["name"],
                "edge_mode": class_row["edge_mode"],
                "metric_weights": {
                    name: weights[edge_id]
                    for name, weights in weights_of_metrics
                },
            }

    def _find_path_edge_ids(self, path: list[int]) -> list[int]:
        # The id of each edge of a path
        node_first_edge_ids, edge_destination_node_ids, _ = (
            self._read_edge_arrays()
        )
        edge_ids = []
        for origin_id, destination_id in zip(path, path[1:]):
            edge_id = find_edge_id(
                node_first_edge_ids,
                edge_destination_node_ids,
                origin_id,
                destination_id,
            )
            if edge_id is None:
                raise ValueError(
                    f"The geograph has no edge from node {origin_id} to node "
                    f"{destination_id}"
                )
            edge_ids.append(edge_id)
        return edge_ids

    def get_path_edges(self, path: list[int]) -> list[dict]:
        """
        Function:

        - Get the edges of a path, in the order of the path

        Required Arguments:

        - `path`: The node ids of a path, as the `path` of `get_shortest_path` with `output_path=True`

        Returns:

        - A list with one dictionary for each pair of consecutive nodes of the path (see `get_edges`)

        Raises:

        - `TypeError`: `path` is not a sequence of integer node ids
        - `ValueError`: The geograph has no edge between two consecutive nodes of the path
        """
        try:
            # A set or a dict has no order, and a string is not a path
            if isinstance(path, (str, bytes, set, frozenset, dict)):
                raise TypeError
            path = [operator.index(node_id) for node_id in path]
        except TypeError:
            raise TypeError(
                f"path must be a sequence of integer node ids, not {path!r}"
            ) from None
        return list(
            self._iter_edge_dicts(zip(path, self._find_path_edge_ids(path)))
        )
