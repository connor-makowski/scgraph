"""The classes and the metrics of the edges of a GeoGraph, lined up with its edges.

This module is internal. Each `GeoGraph` has one `EdgeData`, and its public methods
call it.

THE EDGES AND THEIR INDEX

A graph stores its edges by origin, in three arrays (`Graph._csr()`): the offsets,
the heads and the lengths. The edges of node `u` go to
`heads[offsets[u]:offsets[u + 1]]`. The "index" of an edge is its position in
`heads`. An array is "lined up with the edges" when its value number `i` belongs to
the edge of index `i`. The classes of the edges are such an array.

Example, a graph of three nodes with the edges 0 -> 1, 0 -> 2 and 2 -> 0:

    offsets = [0, 2, 2, 3]    heads = [1, 2, 0]    edge_classes = [4, 4, 7]

The edge 2 -> 0 has the index 2, and its class is the row 7.

WHAT AN EDGE DATA HOLDS

An `EdgeData` holds what a geograph knows of its edges, beside its graph:

- the three arrays of the edges, as the graph gave them at the last read;
- `classes`, the rows `{"name", "mode"}` of the classes, and the row of the class of
  each edge. A geograph without classes has no row and no such array;
- the metrics other than `length`, by name. A `Metric` record holds one weight for
  each edge (`scgraph/metrics.py`);
- what the `add_` methods of the geograph gave for their new edges, by (origin id,
  destination id): a class, and a weight in each metric that was read. The next
  line-up uses them, then forgets them.

Example, for the three edges above, with lengths of 10, 20 and 20 km. The row 4 is
`{"name": "primary", "mode": "road"}`, the row 7 is the class `motorway`, and the
weights of the metric `hours` are [0.2, 0.4, 0.2]. `get_edges` gives the edge 2 -> 0
as:

    {"origin_id": 2, "destination_id": 0, "length": 20.0, "class": "motorway",
     "mode": "road", "metrics": {"hours": 0.2}}

WHY NO READ IS STALE

The graph of a geograph changes. The geograph adds and removes nodes and edges, and
a caller may edit `graph_object`, or replace it by another `Graph`. The arrays of an
`EdgeData` are then older than the graph. So each method that reads them "lines up"
first. It compares the graph with the graph of the last read, and the count of its
edits (`Graph._edit_count`) with the count at that read. When one of the two
differs, it runs the steps of the next part. No other code reads the arrays, so no
caller can skip this check.

An `EdgeData` keeps no reference to its geograph. Two objects that refer to each
other are freed late, and a geograph may hold a large network. So a method that
reads the edges takes the geograph as its first argument. It reads `graph_object`,
`geograph_units` and the unit of the lengths, and `modes` and `node_modes` for a
metric from tables.

AFTER AN EDIT

An edit of the graph moves the edges: a new edge of node 0 takes the index 2, and
the edge 2 -> 0 gets the index 3. An edge is known by its two nodes, because a graph
holds one edge at most from a node to another. A line-up has five steps.

1. It reads the three arrays of the graph again.
2. `find_old_edge_indexes` gives, for each edge of the edited graph, its index
   before the edit, or -1 for a new edge.
3. `take_edge_values` lines up the classes with the edited graph. An edge that was
   there keeps its class. A new edge takes the class of its `add_` call, or no
   class.
4. Each metric is lined up after the metrics that it uses. A metric that
   `create_metric` made is computed again from the arguments of that call. A metric
   that was read keeps the weight of each edge that was there. A new edge takes the
   weight of its `add_` call. Without this weight, it weighs as an access leg: its
   km times the rate `"off_graph"` of the metric (`off_graph_per_km`). When the
   lengths of the geograph are in seconds, a new edge has no km: it is closed.
5. It forgets what the `add_` calls gave.

Example, after the edge 0 -> 2 is removed and the edge 1 -> 2 is added, with a
length of 30 km:

    offsets = [0, 1, 2, 3]    heads = [1, 2, 0]
    find_old_edge_indexes gives [0, -1, 2]
    take_edge_values([4, 4, 7], [0, -1, 2], 9) gives [4, 9, 7]

Suppose that the metric `hours` was read from a file, with 0.05 hour for 1 km of
access leg, and that the `add_` call gave no weight. The weights [0.2, 0.4, 0.2]
become [0.2, 0.05 * 30, 0.2] = [0.2, 1.5, 0.2].

THE LEGS OF A ROUTE

A "leg" is a part of a route on one mode: consecutive edges whose classes have the
same mode. `cut_legs` cuts the edges of a path into legs, and totals each leg.

Example, the path 3 -> 0 -> 8 -> 9 -> 2. Its four edges are a road of 2 km, a
railway of 1 km, a railway of 90 km and a road of 2 km. The class of the first
railway is `rail_connector`, and the class of the second is `rail_main`:

    modes of the edges = [road, rail, rail, road]
    legs = road, 2 km, nodes [3, 0]
           rail, 91 km, nodes [0, 8, 9], of which rail_connector 1 km, rail_main 90 km
           road, 2 km, nodes [9, 2]

A leg starts at the node where the leg before it ends. The two road legs stay two
legs, because the railway is between them.
"""

from array import array
from collections.abc import Iterable, Iterator
from dataclasses import replace
from itertools import compress, count
from math import inf
from typing import TYPE_CHECKING

from scgraph import Graph
from scgraph.metrics import (
    Metric,
    check_weight,
    compute_min_weight_per_km,
    compute_weights_by_sum,
    compute_weights_by_tables,
    find_used_metrics,
    find_users,
    order_by_dependencies,
    set_edge_weights,
)
from scgraph.utils import get_units_per_km

if TYPE_CHECKING:  # Only for an annotation
    from scgraph.geograph import GeoGraph

# The row of `classes` for an edge without a class, on a geograph with classes
_NO_CLASS = {"name": None, "mode": None}
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
    """Return the index of the edge from one node to another.

    Args:
        offsets: The offsets of the edges, one for each node plus one.
        heads: The destination of each edge.
        origin_id: The node that the edge leaves.
        destination_id: The node that the edge goes to.

    Returns:
        The index of the edge, or None when the graph has no such edge or no node
        `origin_id`.
    """
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
    """Return the index that each edge of a graph had before the graph was edited.

    The function reads each node once in Python: about 1 second for a million
    nodes. It is one function, so that a compiled kernel can replace it.

    Args:
        old_offsets: The offsets of the edges before the edit.
        old_heads: The destination of each edge before the edit.
        offsets: The offsets of the edges now.
        heads: The destination of each edge now.

    Returns:
        One int64 value for each edge of `heads`: the index in `old_heads` of the
        edge with the same two nodes, or -1 for an edge that was not there.
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


def take_edge_values(
    old_values: array | memoryview,
    old_edge_indexes: array,
    new_edge_value: float,
) -> array:
    """Return an array lined up with the edges of an edited graph.

    Args:
        old_values: An array lined up with the edges before the edit.
        old_edge_indexes: The result of `find_old_edge_indexes`.
        new_edge_value: The value of an edge that was not there.

    Returns:
        A new array of the dtype of `old_values`, with one value for each edge.
    """
    old_values = memoryview(old_values)
    values = array(old_values.format)
    values.frombytes(old_values.cast("B"))
    # The index -1 of a new edge reads this last value
    values.append(new_edge_value)
    return array(values.typecode, map(values.__getitem__, old_edge_indexes))


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

    Returns:
        A new array of the dtype of `values`, with one value for each edge.
    """
    values = memoryview(values)
    ordered = array(values.format)
    for origin_id in order:
        first, last = offsets[origin_id], offsets[origin_id + 1]
        ordered.frombytes(values[first:last].cast("B"))
    return ordered


def cut_legs(edges: list[dict]) -> list[dict]:
    """Cut the edges of a path into legs, and total each leg.

    Args:
        edges: The dict of each edge of the path, in the order of the path, as
            `GeoGraph.get_path_edges` returns them.

    Returns:
        One dict for each leg, in the order of the path. `mode` is the mode of the
        edges of the leg. `length` is their total length, and `metrics` their total
        in each metric, by name. `class_lengths` is their total length by class,
        under the name of the class. `path` holds the node ids of the leg. A path
        without an edge has no leg.
    """
    legs = []
    for edge in edges:
        if not legs or legs[-1]["mode"] != edge["mode"]:
            legs.append(
                {
                    "mode": edge["mode"],
                    "length": 0.0,
                    "metrics": dict.fromkeys(edge["metrics"], 0.0),
                    "class_lengths": {},
                    "path": [edge["origin_id"]],
                }
            )
        leg = legs[-1]
        leg["length"] += edge["length"]
        for name, weight in edge["metrics"].items():
            leg["metrics"][name] += weight
        class_lengths = leg["class_lengths"]
        class_lengths[edge["class"]] = (
            class_lengths.get(edge["class"], 0.0) + edge["length"]
        )
        leg["path"].append(edge["destination_id"])
    return legs


def _check_class_count(class_count: int) -> None:
    if class_count > _MAX_CLASS_COUNT:
        raise ValueError(
            f"A geograph holds {_MAX_CLASS_COUNT} classes at most: got "
            f"{class_count}"
        )


class EdgeData:
    """The classes and the metrics of the edges of one geograph (see the module
    docstring). A method with the parameter `geograph` lines up with the graph of
    this geograph before it reads an edge."""

    def __init__(self) -> None:
        # The rows `{"name", "mode"}` of the classes: `GeoGraph.classes`. Empty on a
        # geograph without classes. A loader or a merge gives classes to a geograph.
        self.classes = []
        # The row in `classes` of each edge, lined up with the edges. None on a
        # geograph without classes.
        self._edge_classes = None
        # The offsets, the heads and the lengths of the edges at the last line-up
        self._edge_arrays = None
        # The graph at the last line-up, and its `_edit_count` at that time
        self._graph = None
        self._edit_count = None
        # The metrics other than `length`, by name
        self._metrics = {}
        # What the `add_` methods gave for the edges that are not lined up yet, by
        # (origin id, destination id): the row of the class of the edge, or None for
        # no class, and its weight in the metrics that were read, by name
        self._new_edge_classes = {}
        self._new_edge_weights = {}

    # The line-up

    def _line_up(
        self, geograph: "GeoGraph", left_out_metrics: tuple[str, ...] = ()
    ) -> tuple[array | memoryview, ...]:
        """Line up the classes and the metrics with the edges of the graph, if the
        graph was edited since the last line-up (module docstring, *After an edit*).

        Args:
            left_out_metrics: The names of the metrics that the line-up leaves as
                they are. Only `create_metric` names some: the metric that it
                replaces and the users of this metric, which it computes next.

        Returns:
            The offsets, the heads and the lengths of the edges.

        Raises:
            ValueError: An edge without a class needs a row after 256 classes.
            Exception: A metric cannot be computed again. The error leaves the
                lined-up arrays as before the edit. Each later call raises it
                again, until the metric is created again or removed.
        """
        graph = geograph.graph_object
        edit_count = graph._edit_count
        if graph is self._graph and edit_count == self._edit_count:
            return self._edge_arrays
        # 1. The edges of the graph now
        edge_arrays = graph._csr()
        offsets, heads, _ = edge_arrays
        edge_classes = self._edge_classes
        if edge_classes is not None or self._metrics:
            # 2. The index that each edge had
            old_edge_indexes = find_old_edge_indexes(
                *self._edge_arrays[:2], offsets, heads
            )
        if edge_classes is not None:
            # 3. The classes
            names = [edge_class["name"] for edge_class in self.classes]
            no_class_row = names.index(None) if None in names else len(names)
            if no_class_row == _MAX_CLASS_COUNT:
                # A byte cannot hold the row of no class after 256 named classes.
                # The rows are lined up in a wider array, then checked below.
                edge_classes = array("H", edge_classes)
            edge_classes = take_edge_values(
                edge_classes, old_edge_indexes, no_class_row
            )
            for nodes, class_row in self._new_edge_classes.items():
                edge_index = find_edge_index(offsets, heads, *nodes)
                if edge_index is not None:
                    edge_classes[edge_index] = (
                        no_class_row if class_row is None else class_row
                    )
            # The row of no class is added when an edge needs it
            if no_class_row == len(self.classes) and (
                no_class_row in edge_classes
            ):
                _check_class_count(no_class_row + 1)
                self.classes.append(dict(_NO_CLASS))
            if edge_classes.typecode != "B":
                edge_classes = array("B", edge_classes)
        before = self._edge_arrays, self._edge_classes, self._metrics
        self._edge_arrays, self._edge_classes = edge_arrays, edge_classes
        if self._metrics:
            # 4. The metrics
            try:
                self._line_up_metrics(
                    geograph, old_edge_indexes, left_out_metrics
                )
            except Exception:
                self._edge_arrays, self._edge_classes, self._metrics = before
                raise
        # 5. The new edges are lined up
        self._new_edge_classes = {}
        self._new_edge_weights = {}
        self._graph, self._edit_count = graph, edit_count
        return edge_arrays

    def _line_up_metrics(
        self,
        geograph: "GeoGraph",
        old_edge_indexes: array,
        left_out_metrics: tuple[str, ...],
    ) -> None:
        # Step 4 of a line-up. It also drops the graph of each metric. A pair of
        # nodes of `edge_weights` is dropped when the graph no longer has this
        # edge. No metric that is lined up uses a metric of `left_out_metrics`.
        offsets, heads, lengths = self._edge_arrays
        # For the metrics that were read: the weights that the `add_` call of each
        # new edge gave, by the index of the edge. An edge that was not there is
        # new, also when no `add_` call made it. The loop over the edges runs in C.
        weights_of_new_edges = {}
        if any(record.definition is None for record in self._metrics.values()):
            weights_of_new_edges = dict.fromkeys(
                compress(count(), map((-1).__eq__, old_edge_indexes)), {}
            )
            for nodes, weights_of_call in self._new_edge_weights.items():
                edge_index = find_edge_index(offsets, heads, *nodes)
                if edge_index is not None:
                    weights_of_new_edges[edge_index] = weights_of_call
        # A length in seconds gives no km
        has_km = geograph._length_unit != "s"
        units_per_km = get_units_per_km(geograph.geograph_units)
        metrics, self._metrics = self._metrics, {}
        for name in order_by_dependencies(metrics):
            metric_record = metrics[name]
            if name in left_out_metrics:
                self._metrics[name] = metric_record
                continue
            if metric_record.definition is None:
                weights = take_edge_values(
                    metric_record.weights, old_edge_indexes, inf
                )
                # A new edge without a weight weighs as an access leg of its km
                off_graph_per_unit = (
                    metric_record.off_graph_per_km / units_per_km
                )
                for edge_index, weights_of_call in weights_of_new_edges.items():
                    if name in weights_of_call:
                        weights[edge_index] = weights_of_call[name]
                    elif has_km:
                        weights[edge_index] = (
                            lengths[edge_index] * off_graph_per_unit
                        )
                    else:
                        weights[edge_index] = inf
                self._metrics[name] = replace(
                    metric_record,
                    weights=weights,
                    min_weight_per_km=None,
                    graph_object=None,
                )
                continue
            definition = dict(metric_record.definition)
            if definition["edge_weights"]:
                definition["edge_weights"] = {
                    nodes: weight
                    for nodes, weight in definition["edge_weights"].items()
                    if find_edge_index(offsets, heads, *nodes) is not None
                }
            try:
                self._metrics[name] = self._compute_metric(
                    geograph,
                    name,
                    metric_record.unit,
                    metric_record.description,
                    definition,
                    metric_record.used_metrics,
                )
            except Exception as error:
                error.add_note(
                    f"The geograph was edited, and it computes the metric {name!r} "
                    f"again. To repair the geograph, create the metric {name!r} "
                    "again with arguments that give a weight to each new edge, or "
                    f"remove it with `remove_metric({name!r})`."
                )
                raise
        # The metrics keep their order, which `metrics` and the results show
        self._metrics = {name: self._metrics[name] for name in metrics}

    # What the loaders, the merge and the save give and take

    def set_edge_arrays(
        self, graph: Graph, edge_arrays: tuple[array | memoryview, ...]
    ) -> None:
        """Take the edges of a graph from the arrays that the graph was built from,
        so that the first line-up does not read the graph.

        Args:
            graph: The `graph_object` of the geograph.
            edge_arrays: The offsets, the heads and the lengths of its edges, as
                `graph._csr()` would return them.
        """
        self._edge_arrays = edge_arrays
        self._graph, self._edit_count = graph, graph._edit_count

    def set_classes(
        self,
        geograph: "GeoGraph",
        classes: list[dict],
        edge_classes: array | memoryview,
    ) -> None:
        """Give its classes to a geograph.

        Args:
            classes: The rows `{"name", "mode"}` of the classes.
            edge_classes: The row in `classes` of each edge (uint8), in the order
                of the edges of the graph.
        """
        self._line_up(geograph)
        self.classes = classes
        self._edge_classes = edge_classes

    def set_classes_by_name(
        self,
        geograph: "GeoGraph",
        classes: list[dict],
        edge_class_names: list[str | None],
    ) -> None:
        """Give its classes to a geograph, from the name of the class of each edge.

        Args:
            classes: The rows `{"name", "mode"}` of the classes. The row of no class
                is added after them when an edge needs it.
            edge_class_names: The name of the class of each edge, or None for no
                class, in the order of the edges (see `list_edge_values`).
        """
        classes = list(classes)
        if None in edge_class_names:
            classes.append(dict(_NO_CLASS))
        _check_class_count(len(classes))
        class_rows = {
            edge_class["name"]: row for row, edge_class in enumerate(classes)
        }
        self.set_classes(
            geograph,
            classes,
            array("B", map(class_rows.__getitem__, edge_class_names)),
        )

    def list_edge_values(
        self, geograph: "GeoGraph", values_of_each_node: list[dict]
    ) -> list:
        """Return one value for each edge, in the order of the edges.

        Args:
            values_of_each_node: For each node, a dict from the destination of an
                edge of this node to the value of the edge.

        Returns:
            The value of each edge. None for an edge that its dict lacks.
        """
        offsets, heads, _ = self._line_up(geograph)
        return [
            values_of_each_node[origin_id].get(heads[edge_index])
            for origin_id, edge_index in iter_edges(offsets)
        ]

    def add_read_metric(self, metric_record: Metric) -> None:
        """Add a metric that a loader read, with its weights. The geograph cannot
        compute it again.

        Args:
            metric_record: The metric, without a definition. Its weights are in the
                order of the edges of the graph.
        """
        self._metrics[metric_record.name] = metric_record

    def merge_classes(
        self,
        geograph: "GeoGraph",
        other_geograph: "GeoGraph",
        first_node_id: int,
    ) -> dict[tuple[int, int], int]:
        """Add the classes of another geograph to `classes`, for a merge. A class of
        the other geograph is added unless a class has its name. A geograph without
        classes first gets the row of no class for each of its edges.

        Args:
            other_geograph: The geograph whose edges the merge adds. It has classes.
            first_node_id: The id that the node 0 of the other geograph gets in the
                merged graph. Each next node gets the next id.

        Returns:
            The row in `classes` of each edge of the other geograph, by the ids of
            its two nodes in the merged graph. `set_new_edge_classes` takes it when
            the graph holds these edges.

        Raises:
            ValueError: The two geographs have more than 256 classes together. This
                geograph is not changed.
        """
        other = other_geograph._edge_data
        other_offsets, other_heads, _ = other._line_up(other_geograph)
        # A geograph without classes gets the row 0 for each of its edges: no class
        classes = self.classes if self.has_classes() else [dict(_NO_CLASS)]
        names = [edge_class["name"] for edge_class in classes]
        new_classes = [
            dict(edge_class)
            for edge_class in other.classes
            if edge_class["name"] not in names
        ]
        # Checked before any change of this geograph
        _check_class_count(len(classes) + len(new_classes))
        if not self.has_classes():
            heads = self._line_up(geograph)[1]
            self.classes = classes
            self._edge_classes = array("B", bytes(len(heads)))
        self.classes.extend(new_classes)
        # The row in `classes` of each class of the other geograph
        names = [edge_class["name"] for edge_class in self.classes]
        class_rows = [
            names.index(edge_class["name"]) for edge_class in other.classes
        ]
        return {
            (
                first_node_id + origin_id,
                first_node_id + other_heads[edge_index],
            ): class_rows[other._edge_classes[edge_index]]
            for origin_id, edge_index in iter_edges(other_offsets)
        }

    def set_new_edge_classes(
        self, new_edge_classes: dict[tuple[int, int], int]
    ) -> None:
        """Take the class of edges that the graph got without an `add_` method.

        Args:
            new_edge_classes: The row in `classes` of each of these edges, by
                (origin id, destination id).
        """
        self._new_edge_classes.update(new_edge_classes)

    def list_classes(self, geograph: "GeoGraph") -> list[dict]:
        """Return the rows of the classes: `GeoGraph.classes`. The classes are
        lined up first, because a new edge without a class adds its row."""
        if self._edge_classes is not None:
            self._line_up(geograph)
        return self.classes

    def list_file_classes(self, geograph: "GeoGraph") -> list[dict] | None:
        """Return the rows of the classes for the header of a network file, or None
        on a geograph without classes. The classes and the metrics are lined up
        first: the header of the file then says what `get_file_arrays` gives."""
        if self._edge_classes is None and not self._metrics:
            return None
        # An edge without a class may add its row to `classes`
        self._line_up(geograph)
        return None if self._edge_classes is None else self.classes

    def get_file_arrays(
        self, geograph: "GeoGraph", order: list[int] | None
    ) -> dict[str, array | memoryview]:
        """Return the arrays of the classes and of the metrics for a network file.

        Args:
            order: The nodes in the order of the file: `order[new id] = id`. None
                when the file keeps the order of the nodes.

        Returns:
            `edge_classes` on a geograph with classes, and `weights_<name>` for
            each metric other than `length`. Each array is lined up with the edges
            of the file.
        """
        arrays = {}
        if self._edge_classes is None and not self._metrics:
            return arrays
        offsets = self._line_up(geograph)[0]
        if self._edge_classes is not None:
            arrays["edge_classes"] = self._edge_classes
        for name, metric_record in self._metrics.items():
            arrays[f"weights_{name}"] = metric_record.weights
        if order is not None:
            arrays = {
                key: reorder_edge_values(values, offsets, order)
                for key, values in arrays.items()
            }
        return arrays

    # The new edges of the `add_` methods

    def has_classes(self) -> bool:
        """Return whether the geograph has classes."""
        return self._edge_classes is not None

    def find_class_row(self, edge_class: str | None) -> int | None:
        """Return the row of a class in `classes`.

        Args:
            edge_class: The name of the class. None stands for no class.

        Returns:
            The row. None for None.

        Raises:
            ValueError: No class has this name.
        """
        if edge_class is None:
            return None
        names = [row["name"] for row in self.classes]
        if edge_class not in names:
            raise ValueError(
                f"Unknown class {edge_class!r}: the classes of this geograph are "
                f"{names}"
            )
        return names.index(edge_class)

    def check_new_edge_weights(self, metrics: dict | None) -> dict[str, float]:
        """Check the `metrics` of an `add_` call.

        Args:
            metrics: The weight of the new edges in the metrics that
                `create_metric` did not make, by name. None as a weight closes the
                edges. None for no weight.

        Returns:
            The weights as floats, by name. Infinity for None.

        Raises:
            ValueError: A name is not such a metric, or a weight is below zero or
                not a number.
        """
        new_edge_weights = {}
        for name, weight in (metrics or {}).items():
            metric_record = self._metrics.get(name)
            if metric_record is None or metric_record.definition is not None:
                names = [
                    other_name
                    for other_name, other_record in self._metrics.items()
                    if other_record.definition is None
                ]
                raise ValueError(
                    f"metrics names {name!r}. An `add_` method takes a weight only "
                    f"in a metric that `create_metric` did not make: {names}"
                )
            new_edge_weights[name] = inf if weight is None else float(weight)
            # A comparison with a value that is not a number is false
            if not new_edge_weights[name] >= 0:
                raise ValueError(
                    f"The weight of the new edge in the metric {name!r} is below "
                    "zero or not a number"
                )
        return new_edge_weights

    def record_new_edges(
        self,
        edges: Iterable[tuple[int, int]],
        class_row: int | None,
        new_edge_weights: dict[str, float],
    ) -> None:
        """Keep what an `add_` call gave for its new edges, for the next line-up.

        Args:
            edges: The (origin id, destination id) of each new edge.
            class_row: The result of `find_class_row` for the call.
            new_edge_weights: The result of `check_new_edge_weights` for the call.
        """
        for nodes in edges:
            if self._edge_classes is not None:
                self._new_edge_classes[nodes] = class_row
            if self._metrics:
                self._new_edge_weights[nodes] = new_edge_weights

    def forget_new_edges(self, edges: Iterable[tuple[int, int]]) -> None:
        """Drop what an `add_` call gave for edges that the graph no longer has.

        Args:
            edges: The (origin id, destination id) of each removed edge.
        """
        for nodes in edges:
            self._new_edge_classes.pop(nodes, None)
            self._new_edge_weights.pop(nodes, None)

    def forget_new_edges_of_node(self, node_id: int) -> None:
        """Drop what an `add_` call gave for the edges of a node that the graph no
        longer has. The method reads each new edge: `forget_new_edges` is faster
        for a caller that knows the edges of the node."""
        for new_edges in (self._new_edge_classes, self._new_edge_weights):
            for nodes in [nodes for nodes in new_edges if node_id in nodes]:
                del new_edges[nodes]

    # The metrics

    def has_metrics(self) -> bool:
        """Return whether the geograph has a metric other than `length`."""
        return bool(self._metrics)

    def list_metric_rows(self) -> list[dict]:
        """Return the row of each metric other than `length`, as a network file
        stores it."""
        return [
            metric_record.get_row() for metric_record in self._metrics.values()
        ]

    def _get_metric_record(self, metric: str) -> Metric:
        # The record of a metric other than `length`
        if metric not in self._metrics:
            raise ValueError(
                f"Unknown metric {metric!r}: the metrics of this geograph are "
                f"{['length', *self._metrics]}"
            )
        return self._metrics[metric]

    def create_metric(
        self,
        geograph: "GeoGraph",
        name: str,
        unit: str | None,
        description: str | None,
        definition: dict,
    ) -> None:
        """Compute a metric and keep it, in place of a metric of the same name. Each
        metric that uses it is then computed again, after the metrics that it uses.

        Args:
            name: The name of the metric.
            unit: The unit of the weights, as free text, or None.
            description: Where the weights come from, as free text, or None.
            definition: The arguments `per_km`, `at_hub`, `weighted_sum_of`,
                `edge_weight_fn` and `edge_weights` of `GeoGraph.create_metric`, by
                name. The `EdgeData` keeps this dict.

        Raises:
            ValueError: An argument does not fit the network, or a weight is below
                zero or not a number. No metric changes.
        """
        used_metrics = find_used_metrics(self._metrics, name, definition)
        users = find_users(self._metrics, name)
        state_before = dict(vars(self))
        try:
            # The call computes the metric of this name and its users from the new
            # definition. The line-up leaves them out: after an edit, the
            # definition that the call replaces may fit the graph no longer.
            self._line_up(geograph, (name, *users))
            # A metric that is created again keeps its place among the metrics
            self._metrics = dict(self._metrics)
            self._metrics[name] = self._compute_metric(
                geograph, name, unit, description, definition, used_metrics
            )
            for user_name in users:
                user_record = self._metrics[user_name]
                self._metrics[user_name] = self._compute_metric(
                    geograph,
                    user_name,
                    user_record.unit,
                    user_record.description,
                    user_record.definition,
                    user_record.used_metrics,
                )
        except Exception:
            # No metric changes when one of them cannot be computed. The line-up
            # is undone with them: it left out the metrics that the call computes.
            vars(self).update(state_before)
            raise

    def _compute_metric(
        self,
        geograph: "GeoGraph",
        name: str,
        unit: str | None,
        description: str | None,
        definition: dict,
        used_metrics: tuple[str, ...],
    ) -> Metric:
        """Return a metric computed on the lined-up edges.

        Args:
            definition: As in `create_metric`.
            used_metrics: The names of the metrics that the metric uses. A function
                reads these metrics, and no other, in the `metrics` of an edge.
        """
        offsets, heads, lengths = self._edge_arrays
        units_per_km = get_units_per_km(geograph.geograph_units)
        if definition["per_km"] is not None:
            edge_classes = self._edge_classes
            if edge_classes is None:
                # Every edge has the row 0, the only row of the table of rates
                edge_classes = array("B", bytes(len(heads)))
            # Nodes appended to `nodes` directly are in the first mode
            geograph.node_modes.extend(
                bytes(len(offsets) - 1 - len(geograph.node_modes))
            )
            weights, off_graph_per_km = compute_weights_by_tables(
                definition["per_km"],
                definition["at_hub"],
                self.classes,
                geograph.modes,
                self._edge_arrays,
                edge_classes,
                geograph.node_modes,
            )
        elif definition["weighted_sum_of"] is not None:
            weights, off_graph_per_km = compute_weights_by_sum(
                name,
                definition["weighted_sum_of"],
                self._metrics,
                lengths,
                units_per_km,
            )
        else:
            edge_weight_fn = definition["edge_weight_fn"]
            read_metrics = {
                used_name: self._metrics[used_name]
                for used_name in used_metrics
            }
            weights = array(
                "d",
                (
                    check_weight(
                        edge_weight_fn(
                            self._build_edge(
                                origin_id, edge_index, read_metrics
                            )
                        ),
                        origin_id,
                        heads[edge_index],
                    )
                    for origin_id, edge_index in iter_edges(offsets)
                ),
            )
            # The function gives the weight of 1 km of access leg, as of an edge
            off_graph_per_km = edge_weight_fn(
                {
                    "origin_id": None,
                    "destination_id": None,
                    "length": units_per_km,
                    "class": None,
                    "mode": "off_graph",
                    "metrics": {
                        used_name: used_record.off_graph_per_km
                        for used_name, used_record in read_metrics.items()
                    },
                }
            )
        if definition["edge_weights"]:
            weights = set_edge_weights(
                weights,
                definition["edge_weights"],
                [
                    find_edge_index(offsets, heads, *nodes)
                    for nodes in definition["edge_weights"]
                ],
            )
        # A comparison with a value that is not a number is false
        if off_graph_per_km is None or not 0 <= off_graph_per_km < inf:
            raise ValueError(
                f"The weight of 1 km of access leg in the metric {name!r} must "
                f"be a finite number of zero or more: got {off_graph_per_km!r} "
                "(for a function: the value that it returns for the mode "
                "'off_graph')"
            )
        return Metric(
            name,
            unit,
            description,
            weights,
            float(off_graph_per_km),
            definition,
            used_metrics,
        )

    def remove_metric(self, metric: str) -> None:
        """Remove a metric.

        Raises:
            ValueError: The geograph has no such metric, or another metric uses it.
        """
        self._get_metric_record(metric)
        users = find_users(self._metrics, metric)
        if users:
            raise ValueError(
                f"The metric {metric!r} is used by the metric {users[0]!r}: remove "
                f"{users[0]!r} first. A weighted sum uses the metrics that it "
                "sums, and a metric made by edge_weight_fn uses every metric that "
                "the geograph had at its creation"
            )
        del self._metrics[metric]

    def remove_metrics(self) -> None:
        """Remove every metric other than `length`."""
        self._metrics = {}

    def get_metric_graph(
        self,
        geograph: "GeoGraph",
        metric: str,
        reduce_iterations: int | None,
    ) -> Graph:
        """Return the `Graph` that a search by a metric runs on: the edges of the
        geograph with the weights of the metric. It is built at the first call, and
        again after a change of the metric or of the edges.

        Args:
            metric: The name of a metric other than `length`.
            reduce_iterations: The argument of the last `GeoGraph.reduce`, or None.
                A new graph is reduced when `graph_object` is reduced.

        Raises:
            ValueError: The geograph has no such metric.
        """
        offsets, heads, _ = self._line_up(geograph)
        metric_record = self._get_metric_record(metric)
        if metric_record.graph_object is None:
            # The graph reads the three arrays in place and keeps them alive
            graph = Graph.from_csr(
                offsets, heads, metric_record.weights, copy=False
            )
            if geograph.graph_object.is_reduced is not None:
                graph.reduce(
                    -1 if reduce_iterations is None else reduce_iterations
                )
            metric_record.graph_object = graph
        return metric_record.graph_object

    def reduce_metric_graphs(self, iterations: int) -> None:
        """Reduce the graph of each metric that has one (see `Graph.reduce`)."""
        for metric_record in self._metrics.values():
            if metric_record.graph_object is not None:
                metric_record.graph_object.reduce(iterations)

    def get_off_graph_per_km(self, metric: str) -> float:
        """Return the weight of 1 km of access leg in a metric other than `length`.

        Raises:
            ValueError: The geograph has no such metric.
        """
        return self._get_metric_record(metric).off_graph_per_km

    def weigh_access_leg(self, off_graph_km: float) -> dict[str, float]:
        """Return the weight of an access leg in each metric other than `length`.

        Args:
            off_graph_km: The km of the leg, with its circuity.
        """
        return {
            name: off_graph_km * metric_record.off_graph_per_km
            for name, metric_record in self._metrics.items()
        }

    def get_min_weight_per_km(self, geograph: "GeoGraph", metric: str) -> float:
        """Return the smallest weight of an open edge divided by its length, for a
        metric other than `length` (see `compute_min_weight_per_km`). It is computed
        at the first call, and again after a change of the metric or of the edges.
        """
        lengths = self._line_up(geograph)[2]
        metric_record = self._metrics[metric]
        if metric_record.min_weight_per_km is None:
            metric_record.min_weight_per_km = compute_min_weight_per_km(
                metric_record.weights, lengths
            )
        return metric_record.min_weight_per_km

    # The edges

    def _build_edge(
        self, origin_id: int, edge_index: int, metrics: dict[str, Metric]
    ) -> dict:
        # The dict of the edge `edge_index` of the lined-up arrays, as `get_edges`
        # returns it. `metrics` holds the metrics of the dict, by name.
        _, heads, lengths = self._edge_arrays
        edge_class = (
            _NO_CLASS
            if self._edge_classes is None
            else self.classes[self._edge_classes[edge_index]]
        )
        return {
            "origin_id": origin_id,
            "destination_id": heads[edge_index],
            "length": lengths[edge_index],
            "class": edge_class["name"],
            "mode": edge_class["mode"],
            "metrics": {
                name: metric_record.weights[edge_index]
                for name, metric_record in metrics.items()
            },
        }

    def get_edges(
        self,
        geograph: "GeoGraph",
        origin_id: int | None,
        edge_class: str | None,
    ) -> list[dict]:
        """Return the dict of each edge, as `GeoGraph.get_edges` describes it.

        Args:
            origin_id: Only the edges that leave this node. None for every node.
            edge_class: Only the edges of the class of this name. None for every
                class.

        Raises:
            ValueError: The graph has no node `origin_id`, or no class has this
                name.
        """
        offsets = self._line_up(geograph)[0]
        if origin_id is None:
            origin_ids = None
        elif 0 <= origin_id < len(offsets) - 1:
            origin_ids = (origin_id,)
        else:
            raise ValueError(f"Node {origin_id} is not in the geograph")
        class_row = self.find_class_row(edge_class)
        return [
            self._build_edge(origin_id, edge_index, self._metrics)
            for origin_id, edge_index in iter_edges(offsets, origin_ids)
            if class_row is None or self._edge_classes[edge_index] == class_row
        ]

    def _find_path_edge_indexes(
        self, geograph: "GeoGraph", path: list[int]
    ) -> list[int]:
        # The index of each edge of a path, in the lined-up arrays
        offsets, heads, _ = self._line_up(geograph)
        edge_indexes = []
        for origin_id, destination_id in zip(path, path[1:]):
            edge_index = find_edge_index(
                offsets, heads, origin_id, destination_id
            )
            if edge_index is None:
                raise ValueError(
                    f"The geograph has no edge from node {origin_id} to node "
                    f"{destination_id}"
                )
            edge_indexes.append(edge_index)
        return edge_indexes

    def get_path_edges(
        self, geograph: "GeoGraph", path: list[int]
    ) -> list[dict]:
        """Return the dict of each edge of a path, in the order of the path.

        Args:
            path: The node ids of the path.

        Raises:
            ValueError: The graph has no edge between two consecutive nodes of the
                path.
        """
        return [
            self._build_edge(origin_id, edge_index, self._metrics)
            for origin_id, edge_index in zip(
                path, self._find_path_edge_indexes(geograph, path)
            )
        ]

    def get_path_legs(
        self, geograph: "GeoGraph", path: list[int]
    ) -> list[dict]:
        """Return the legs of a path (see `cut_legs`)."""
        return cut_legs(self.get_path_edges(geograph, path))

    def get_path_total(
        self, geograph: "GeoGraph", path: list[int], metric: str
    ) -> float:
        """Return the total of a metric along the edges of a path.

        Args:
            path: The node ids of the path.
            metric: The name of a metric of the geograph. It may be `length`.

        Raises:
            ValueError: The geograph has no such metric, or no edge between two
                consecutive nodes of the path.
        """
        lengths = self._line_up(geograph)[2]
        weights = (
            lengths
            if metric == "length"
            else self._get_metric_record(metric).weights
        )
        return sum(
            map(
                weights.__getitem__,
                self._find_path_edge_indexes(geograph, path),
            )
        )

    def get_path_totals(
        self, geograph: "GeoGraph", path: list[int], off_graph_km: float
    ) -> dict[str, float]:
        """Return the total of each metric other than `length` along a route.

        Args:
            path: The node ids of the route.
            off_graph_km: The km of the access legs of the route, with their
                circuity. An access leg weighs its km times `off_graph_per_km` of
                the metric.

        Returns:
            The weight of the edges of the path plus the weight of the access legs,
            by the name of the metric.
        """
        edge_indexes = self._find_path_edge_indexes(geograph, path)
        return {
            name: sum(map(metric_record.weights.__getitem__, edge_indexes))
            + off_graph_km * metric_record.off_graph_per_km
            for name, metric_record in self._metrics.items()
        }
