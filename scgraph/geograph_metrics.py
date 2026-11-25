"""The metrics of a `GeoGraph`.

This module is internal. `GeoGraphMetrics` is the mixin of `GeoGraph` that creates, reads and
removes the metrics, and builds the graph that a search by a metric runs on. It reads the
arrays of the edges with the methods of `GeoGraphEdges`: a mixin calls a method of another
mixin through `self`.
"""

from dataclasses import replace
from scgraph.utils import get_units_per_km
from scgraph.metrics import (
    Metric,
    parse_off_graph_weight_per_km,
    compute_weights_from_weighted_sum,
    compute_weights_from_function,
    build_default_description,
    resolve_weights_per_km,
    copy_with_edge_weights,
)
from scgraph import network_file
import warnings
import re
from array import array
from collections.abc import Callable
from scgraph import Graph

try:
    from scgraph.cpp import compute_weights_from_km
except ImportError:
    from scgraph.helpers.metric_weights import compute_weights_from_km


class GeoGraphMetrics:
    """The metrics of a `GeoGraph`."""

    def _remove_metrics(self) -> None:
        # Remove every metric other than `length`, at an edit of the network, and
        # warn with their names.
        if self._metrics:
            warnings.warn(
                "An edit of the network removed its metrics "
                f"{list(self._metrics)}. Create them again with `create_metric`.",
                stacklevel=3,
            )
            self._metrics = {}

    def _read_metrics(self) -> dict[str, Metric]:
        # Return the metrics other than `length`, by name. A geograph with
        # metrics first reads its edges: an edit made on `graph_object` removes
        # the metrics here.
        if self._metrics:
            self._read_edge_arrays()
        return self._metrics

    def _read_metric(self, metric: str) -> Metric:
        # Return the record of a metric, as `_read_metrics` reads it. The record
        # of `length` is built without a read of the edges.
        if metric == "length":
            record = self._length_metric
            if (
                record is None
                or record.graph_object is not self.graph_object
                or record.unit != self.geograph_units
            ):
                # The weight of 1 km of an off-graph leg is 1 km in
                # `geograph_units`
                record = self._length_metric = Metric(
                    "length",
                    self.geograph_units,
                    None,
                    None,
                    get_units_per_km(self.geograph_units),
                    min_weight_per_length_unit=1.0,
                    graph_object=self.graph_object,
                )
            return record
        metrics = self._read_metrics()
        if metric not in metrics:
            raise ValueError(
                f"Unknown metric {metric!r}: the metrics of this geograph are "
                f"{['length', *metrics]}. An edit of the network removes the "
                "metrics other than 'length'"
                + (
                    f". {metric!r} is the `default_metric` of this geograph: "
                    "create this metric again, or set `default_metric`"
                    if metric == self.default_metric
                    else ""
                )
            )
        return metrics[metric]

    @property
    def metrics(self) -> list[dict]:
        """
        The info of each metric (see `create_metric`): what describes the metric,
        without the weights of its edges. The first one is `length`, with its unit:
        `geograph_units`. The info of another metric has its `name`, its `unit` and
        `description` if it has them, and `off_graph_weight_per_km`: the weight of
        1 km of an off-graph leg.
        """
        return [{"name": "length", "unit": self.geograph_units}] + [
            metric_record.get_info()
            for metric_record in self._read_metrics().values()
        ]

    def create_metric(
        self,
        name: str,
        *,
        weight_per_km: float | dict | None = None,
        class_weight_per_km: dict | None = None,
        weight_at_hub: dict | None = None,
        weighted_sum_of: dict[str, float] | None = None,
        edge_weight_fn: Callable | None = None,
        off_graph_weight_per_km: float | None = None,
        edge_weights: dict | None = None,
        unit: str | None = None,
        description: str | None = None,
    ) -> None:
        """
        Function:

        - Create a metric: one weight for each edge, under a name. `get_shortest_path(metric=name)` then finds the route with the smallest total of these weights
        - Every optional argument is None by default. A call gives exactly one of `weight_per_km`, `weighted_sum_of` and `edge_weight_fn`. A weight is a number of zero or more. None in place of a weight closes its edges: no route by this metric takes them
        - The weights are computed at the call. A metric of the same name is replaced, and no other metric changes. An edit of the network removes the metric (see `add_edge`)
        - Example: `geograph.create_metric("hours", weight_per_km={"road": 1 / 60, "rail": 1 / 40, "off_graph": 1 / 30}, class_weight_per_km={"motorway": 1 / 90}, weight_at_hub={"rail_terminal": {"rail": 4}}, unit="h")`

        Required Arguments:

        - `name`: The name of the metric: small letters, digits and `_`, starting with a letter; not `length`

        Optional Arguments:

        - `weight_per_km`: The weight of 1 km: the weight of an edge is its weight per km times its km. The lengths of the geograph must be in km
            - A number is the weight per km of every edge, and of the off-graph legs: the straight lines between the points of a query and their nodes
            - A dict is `{mode of a leg: weight of 1 km}`. Its keys are the edge modes (see `classes`) and `"off_graph"`, for the off-graph legs. The dict must have `"off_graph"`, and the edge mode of each class that has an edge and that `class_weight_per_km` does not name. None closes an edge mode
            - With a dict, an edge without a class has the weight of an off-graph leg: its km times the weight of `"off_graph"`. `weight_at_hub` adds nothing to it
        - `class_weight_per_km`: With `weight_per_km`, `{name of a class: weight of 1 km}`: the weight per km of the edges of this class, in place of the weight per km of their edge mode. None closes a class
        - `weight_at_hub`: With `weight_per_km`, `{node mode of a hub: {edge mode: weight}}`: the weight that is added to an edge of this edge mode when it leaves a node of this node mode, and when it enters one. `{"port": {"sea": 12}}` adds 12 to each sea edge that enters a port, and to each sea edge that leaves a port
        - `weighted_sum_of`: `{name of a metric: coefficient}`: the weight of an edge is the sum of its weight in each metric times the coefficient, a finite number above zero. `length` may be one of the metrics. An edge that is closed in one of these metrics is closed in the sum. The sum keeps its weights when one of these metrics is created again
        - `edge_weight_fn`: A function that takes the dictionary of an edge (see `get_edges`) and returns its weight. It is called once for each edge, and for the edges only. It needs `off_graph_weight_per_km`
        - `off_graph_weight_per_km`: With `edge_weight_fn`, the weight of 1 km of an off-graph leg, a finite number of zero or more. The other ways refuse it: a number of `weight_per_km` is also the weight per km of the off-graph legs, a dict of `weight_per_km` has the key `"off_graph"`, and a sum adds the weights per km of the off-graph legs of its metrics
        - `edge_weights`: `{(origin_id, destination_id): weight}`: the weight of these edges, in place of the weight computed above
        - `unit`: The unit of the weights, as free text
        - `description`: Where the weights come from, as free text; the text of this call when None

        Raises:

        - `ValueError`: An argument breaks a rule above. The message names the argument, or the two nodes of the first edge with a weight below zero or not a number
        """
        self._check_metric_name(name)
        self._check_one_weight_definition(
            weight_per_km, weighted_sum_of, edge_weight_fn
        )
        self._check_weight_per_km_arguments(
            weight_per_km, class_weight_per_km, weight_at_hub
        )
        self._check_edge_weight_fn_arguments(
            edge_weight_fn, off_graph_weight_per_km
        )
        description = description or build_default_description(
            weight_per_km=weight_per_km,
            class_weight_per_km=class_weight_per_km,
            weight_at_hub=weight_at_hub,
            weighted_sum_of=weighted_sum_of,
            edge_weight_fn=edge_weight_fn,
            off_graph_weight_per_km=off_graph_weight_per_km,
            edge_weights=edge_weights,
        )
        node_first_edge_ids, edge_destination_node_ids, _ = (
            self._read_edge_arrays(check_edge_count=True)
        )
        if edge_weight_fn is None:
            weights, off_graph_weight_per_km = self._compute_metric_weights(
                weight_per_km,
                class_weight_per_km,
                weight_at_hub,
                weighted_sum_of,
            )
        else:
            weights = compute_weights_from_function(
                edge_weight_fn, self._iter_edge_dicts(self._iter_edges())
            )
        if edge_weights:
            weights = copy_with_edge_weights(
                weights,
                edge_weights,
                node_first_edge_ids,
                edge_destination_node_ids,
            )
        # The metric is kept when every check has passed
        self._metrics[name] = Metric(
            name,
            unit,
            description,
            weights,
            parse_off_graph_weight_per_km(name, off_graph_weight_per_km),
        )

    def _check_metric_name(self, name: str) -> None:
        """Raise a ValueError when `name` cannot name a metric: small letters,
        digits and `_`, starting with a letter, and not `length`."""
        if (
            not (
                isinstance(name, str) and re.fullmatch("[a-z][a-z0-9_]*", name)
            )
            or name == "length"
        ):
            raise ValueError(
                "The name of a metric has small letters, digits and '_', starts "
                f"with a letter and is not 'length': got {name!r}"
            )

    def _check_one_weight_definition(
        self,
        weight_per_km: float | dict | None,
        weighted_sum_of: dict[str, float] | None,
        edge_weight_fn: Callable | None,
    ) -> None:
        """Raise a ValueError unless the caller defines the weights with exactly
        one of `weight_per_km`, `weighted_sum_of` and `edge_weight_fn`."""
        if [weight_per_km, weighted_sum_of, edge_weight_fn].count(None) != 2:
            raise ValueError(
                "create_metric takes exactly one of weight_per_km, "
                "weighted_sum_of and edge_weight_fn"
            )

    def _check_weight_per_km_arguments(
        self,
        weight_per_km: float | dict | None,
        class_weight_per_km: dict | None,
        weight_at_hub: dict | None,
    ) -> None:
        """Raise a ValueError when `class_weight_per_km` or `weight_at_hub` comes
        without `weight_per_km`, or when `weight_per_km` comes on a geograph whose
        lengths are not in km."""
        if weight_per_km is None:
            if class_weight_per_km is not None:
                raise ValueError(
                    "class_weight_per_km needs weight_per_km: it replaces the "
                    "weight per km of the edge mode of a class"
                )
            if weight_at_hub is not None:
                raise ValueError(
                    "weight_at_hub needs weight_per_km: a hub weight is added "
                    "to the weight that a weight per km gives"
                )
        elif self.geograph_units != "km":
            raise ValueError(
                "weight_per_km needs lengths in km: the lengths of this "
                f"geograph are in {self.geograph_units!r}"
            )

    def _check_edge_weight_fn_arguments(
        self,
        edge_weight_fn: Callable | None,
        off_graph_weight_per_km: float | None,
    ) -> None:
        """Raise a ValueError when `edge_weight_fn` and `off_graph_weight_per_km`
        do not come together."""
        if edge_weight_fn is None:
            if off_graph_weight_per_km is not None:
                raise ValueError(
                    "off_graph_weight_per_km needs edge_weight_fn: weight_per_km "
                    "and weighted_sum_of give the weight of 1 km of an off-graph "
                    "leg themselves"
                )
        elif off_graph_weight_per_km is None:
            raise ValueError(
                "edge_weight_fn needs off_graph_weight_per_km: the weight of 1 km "
                "of an off-graph leg. The function is called for the edges only"
            )

    def _compute_metric_weights(
        self,
        weight_per_km: float | dict | None,
        class_weight_per_km: dict | None,
        weight_at_hub: dict | None,
        weighted_sum_of: dict[str, float] | None,
    ) -> tuple[array, float | None]:
        """Return the weight of each edge, by edge id, and the weight of 1 km of
        an off-graph leg, for a metric by `weight_per_km` (with
        `class_weight_per_km` and `weight_at_hub`) or by `weighted_sum_of`.
        `create_metric` has checked the arguments and the count of the edges."""
        node_first_edge_ids, edge_destination_node_ids, lengths = (
            self._read_edge_arrays()
        )
        if weighted_sum_of is not None:
            length = replace(self._read_metric("length"), weights=lengths)
            return compute_weights_from_weighted_sum(
                weighted_sum_of, {"length": length, **self._metrics}
            )
        edge_class_ids = self._read_edge_class_ids()
        if edge_class_ids is None:
            # No edge has a class: `weight_per_km` is one weight per km for
            # every edge
            edge_class_ids = array(
                "B",
                bytes([network_file.NO_CLASS_ID])
                * len(edge_destination_node_ids),
            )
        class_weights_per_km, hub_weights, off_graph_weight_per_km = (
            resolve_weights_per_km(
                weight_per_km,
                class_weight_per_km,
                weight_at_hub,
                self.classes,
                self.node_modes,
                edge_class_ids,
            )
        )
        weights = compute_weights_from_km(
            node_first_edge_ids,
            edge_destination_node_ids,
            lengths,
            edge_class_ids,
            self._read_node_mode_ids(),
            class_weights_per_km,
            hub_weights,
        )
        return weights, off_graph_weight_per_km

    def remove_metric(self, name: str) -> None:
        """
        Function:

        - Remove a metric that `create_metric` made, or that a loader read
        - Example: `geograph.remove_metric("hours")`

        Required Arguments:

        - `name`: The name of a metric of `metrics`, other than `length`; an unknown name raises a ValueError
        """
        self._read_metric(name)
        del self._metrics[name]

    def get_graph_object(self, metric: str | None = None) -> Graph:
        """
        Function:

        - Get the `Graph` that a search by a metric runs on: the edges of the geograph, with the weights of the metric. A search called on it returns the total of the metric under the key `length`
        - For `length`, it is `graph_object`. For another metric, the graph is built at the first call and kept until the metric is created again or removed. It is reduced when `graph_object` is reduced (see `reduce`)
        - Example: `geograph.get_graph_object("hours").dijkstra(origin_id=0, destination_id=2)`

        Optional Arguments:

        - `metric`: The name of a metric of `metrics`; an unknown name raises a ValueError. None is the `default_metric` of the geograph, which is 'length' unless a loader or the caller set it
        """
        if metric is None:
            metric = self.default_metric
        metric_record = self._read_metric(metric)
        if metric_record.graph_object is None:
            node_first_edge_ids, edge_destination_node_ids, _ = (
                self._read_edge_arrays()
            )
            # The graph reads the three arrays in place and keeps them alive
            graph = Graph.from_edge_arrays(
                node_first_edge_ids,
                edge_destination_node_ids,
                metric_record.weights,
                copy=False,
            )
            if self.graph_object.is_reduced is not None:
                graph.reduce(
                    -1
                    if self._reduce_iterations is None
                    else self._reduce_iterations
                )
            metric_record.graph_object = graph
        return metric_record.graph_object
