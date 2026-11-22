"""The metrics of a GeoGraph: what a metric is, and how its weights are computed.

This module is internal. `scgraph/edge_data.py` calls it for `GeoGraph.create_metric`,
and keeps each metric lined up with the edges of the graph.

A METRIC

A graph stores its edges in an order, and the "index" of an edge is its position in
that order (`scgraph/edge_data.py`, *The edges and their index*). A "metric" is one
weight for every edge, under a name: an array of float64 values, the value number `i`
for the edge of index `i`. A search by a metric adds up these weights in place of the
lengths. The lengths are the metric `length`, which the graph of the geograph holds.
A `Metric` record holds each other metric. An edge is "closed" in a metric when its
weight is infinity: no route by this metric takes it.

A geograph computes the weights of a metric in one of three ways.

- From tables. `resolve_tables` turns the tables of the caller, whose keys are names
  of classes and of modes, into three arrays whose positions are rows. The kernel
  `compute_table_weights` then gives each edge its rate times its km, plus the weight
  of the hub that it leaves and of the hub that it enters.
- As a weighted sum of other metrics, with the kernel `compute_weighted_sum`.
- From a function of the caller, called once for each edge.

`set_edge_weights` then writes the weights that the caller gives for some edges.

A metric "uses" the metrics that its weights are computed from. A weighted sum uses
the metrics that it sums. A function may read the weight of an edge in each metric
that the geograph has at that time, so the metric of a function uses all of them.
When a metric is created again, the geograph computes each of its users again
(`find_users`), each one after the metrics that it uses (`order_by_dependencies`).

Example, a graph with the edges 0 -> 1, 0 -> 2 and 2 -> 0, in this order, with
lengths of 10, 20 and 20 km. The classes of the edges are the rows 4, 4 and 7 of the
classes. The row 4 is the class `primary`, of the mode `road`, and the row 7 is the
class `motorway`. The tables
`per_km={"primary": 0.02, "motorway": 0.01, "off_graph": 0.05}` give the metric
`hours`:

    weights = [0.02 * 10, 0.02 * 20, 0.01 * 20] = [0.2, 0.4, 0.2]

The sum `{"hours": 30, "length": 0.5}` gives [30 * 0.2 + 0.5 * 10, ...] = [11, 22, 16].

The two kernels are explained in `scgraph/cpp/src/metric_weights.hpp`. Their
pure-Python versions are in `scgraph/helpers/metric_weights.py`.
"""

from array import array
from dataclasses import dataclass
from itertools import compress
from math import inf, isfinite
from operator import truediv
from typing import TYPE_CHECKING

from scgraph.utils import earth_radius

try:
    from scgraph.cpp import compute_table_weights, compute_weighted_sum
except ImportError:
    from scgraph.helpers.metric_weights import (
        compute_table_weights,
        compute_weighted_sum,
    )

if TYPE_CHECKING:  # Only for an annotation
    from scgraph.graph import Graph


@dataclass
class Metric:
    """A metric of a geograph other than `length`."""

    name: str
    # Free text, or None: `h`, `EUR`, `kg CO2e`
    unit: str | None
    # Where the weights come from, for a reader
    description: str | None
    # One float64 weight for each edge, lined up with the edges. Never changed in
    # place: the graph of the metric reads this array.
    weights: array | memoryview
    # The weight of 1 km of the straight line between a query point and its node
    off_graph_per_km: float
    # The arguments of the `create_metric` call that made the metric, by name. None
    # for a metric that was read from a file: the geograph cannot compute it again.
    definition: dict | None = None
    # The names of the metrics that the weights were computed from: the metrics of
    # a weighted sum, other than `length`, or the metrics that a function could
    # read. The geograph computes the metric again when one of them changes.
    used_metrics: tuple[str, ...] = ()
    # The smallest weight of an open edge divided by its length, over the edges
    # longer than zero. It scales the bound of an A* search. Computed at the first
    # such search.
    min_weight_per_km: float | None = None
    # The Graph that a search by this metric runs on. Built at the first query.
    graph_object: "Graph | None" = None

    def get_row(self) -> dict:
        """Return the row of the metric, as a network file stores it."""
        row = {
            "name": self.name,
            "unit": self.unit,
            "description": self.description,
            "off_graph_per_km": self.off_graph_per_km,
        }
        return {key: value for key, value in row.items() if value is not None}


def resolve_tables(
    per_km: float | dict,
    at_hub: dict | None,
    classes: list[dict],
    modes: list[dict],
    edge_classes: array | memoryview,
) -> tuple[array, array, array, float]:
    """Turn the tables of a `create_metric` call into the arrays of the kernel
    `compute_table_weights`.

    In a table, the key of a class is its name, or the mode of its edges. The name
    wins: `{"road": 0.02, "motorway": 0.01}` gives 0.01 to the motorways and 0.02 to
    the other classes of the mode `road`.

    Args:
        per_km: The rate of every edge, or a dict from a class, a mode of edges or
            `"off_graph"` to a rate. A rate of None closes the class.
        at_hub: A dict from the mode of a node to a dict from a class, or a mode of
            edges, to a weight. The weight is a number, paid on the way in and on
            the way out, or a pair (into the hub, out of the hub). None for no hub
            weight.
        classes: The rows `{"name", "mode"}` of the classes. Empty for a geograph
            without classes: every edge then has the row 0.
        modes: The rows of the modes of the nodes, each with its `name`.
        edge_classes: The row of the class of each edge.

    Returns:
        `class_rates_per_km`, `weights_out_of_hub`, `weights_into_hub` and the rate
        of the access legs. The docstring of `compute_table_weights` describes the
        three arrays.

    Raises:
        ValueError: A table has a key that it may not have, or lacks a rate.
    """
    class_count = max(len(classes), 1)
    if isinstance(per_km, dict):
        if not classes:
            raise ValueError(
                "per_km must be a number: this geograph has no classes"
            )
        _check_keys(per_km, "per_km", classes, ("off_graph",))
        if per_km.get("off_graph") is None:
            raise ValueError(
                "per_km must give a rate for 'off_graph': the weight of 1 km "
                "between a query point and its node"
            )
        off_graph_per_km = per_km["off_graph"]
        class_rows = bytes(edge_classes)
        rates = array("d")
        for row, edge_class in enumerate(classes):
            key = _find_key(per_km, edge_class)
            if (
                key is None
                and edge_class["name"] is not None
                and class_rows.count(row)
            ):
                raise ValueError(
                    f"per_km gives no rate for the class {edge_class['name']!r}, "
                    f"which has edges: name it, or its mode {edge_class['mode']!r}"
                )
            # A class without a rate has no edge. An edge without a class is closed.
            rate = None if key is None else per_km[key]
            rates.append(inf if rate is None else rate)
    else:
        off_graph_per_km = per_km
        rates = array("d", [per_km]) * class_count

    mode_names = [mode.get("name") for mode in modes]
    weights_out_of_hub = array("d", bytes(8 * len(modes) * class_count))
    weights_into_hub = array("d", weights_out_of_hub)
    for hub_mode, hub_weights in (at_hub or {}).items():
        if hub_mode not in mode_names:
            raise ValueError(
                f"at_hub has the key {hub_mode!r}, which is no mode of a node: "
                f"the modes of this geograph are {mode_names}"
            )
        _check_keys(hub_weights, f"at_hub[{hub_mode!r}]", classes, ())
        for row, edge_class in enumerate(classes):
            key = _find_key(hub_weights, edge_class)
            if key is None:
                continue
            weight = hub_weights[key]
            if weight is None:
                raise ValueError(
                    f"at_hub[{hub_mode!r}][{key!r}] is None: a hub weight is a "
                    "number, or a pair (into the hub, out of the hub)"
                )
            into_hub, out_of_hub = (
                weight
                if isinstance(weight, (tuple, list))
                else (weight, weight)
            )
            # Two modes may have the same name, after a merge
            for mode_row, mode_name in enumerate(mode_names):
                if mode_name == hub_mode:
                    weights_into_hub[mode_row * class_count + row] = into_hub
                    weights_out_of_hub[mode_row * class_count + row] = (
                        out_of_hub
                    )
    return rates, weights_out_of_hub, weights_into_hub, off_graph_per_km


def compute_weights_by_tables(
    per_km: float | dict,
    at_hub: dict | None,
    classes: list[dict],
    modes: list[dict],
    edge_arrays: tuple[array | memoryview, ...],
    edge_classes: array | memoryview,
    node_modes: array | memoryview,
) -> tuple[array | memoryview, float]:
    """Compute the weights of a metric from the tables of a `create_metric` call.

    Args:
        per_km, at_hub, classes, modes, edge_classes: See `resolve_tables`.
        edge_arrays: The offsets, the heads and the km of the edges.
        node_modes: The row of the mode of each node.

    Returns:
        One float64 weight for each edge, and the rate of the access legs.

    Raises:
        ValueError: As `resolve_tables`, or a weight is below zero or not a number.
    """
    *tables, off_graph_per_km = resolve_tables(
        per_km, at_hub, classes, modes, edge_classes
    )
    weights = compute_table_weights(
        *edge_arrays, edge_classes, node_modes, *tables
    )
    return weights, off_graph_per_km


def compute_weights_by_sum(
    name: str,
    weighted_sum_of: dict[str, float],
    metrics: dict[str, Metric],
    lengths: array | memoryview,
    units_per_km: float,
) -> tuple[array | memoryview, float]:
    """Compute the weights of a metric that is a weighted sum of other metrics.

    Args:
        name: The name of the sum.
        weighted_sum_of: A dict from the name of a metric to its coefficient, a
            finite number above zero. `length` may be one of the metrics.
        metrics: The metrics of the geograph other than `length`, by name.
        lengths: The length of each edge: the weights of the metric `length`.
        units_per_km: 1 km in the unit of `lengths` (`get_units_per_km`): the
            weight of 1 km of access leg in the metric `length`.

    Returns:
        One float64 weight for each edge, and the rate of the access legs: the
        same sum of the rates of the metrics.

    Raises:
        ValueError: The sum names no metric, an unknown metric or itself, or a
            coefficient is not a finite number above zero.
    """
    if name in weighted_sum_of or not set(weighted_sum_of).isdisjoint(
        find_users(metrics, name)
    ):
        raise ValueError(
            f"The metric {name!r} would use itself: weighted_sum_of names it, or "
            "a metric that uses it"
        )
    weights_of_metrics, off_graph_per_km = [], 0.0
    for summed_name, coefficient in weighted_sum_of.items():
        if summed_name != "length" and summed_name not in metrics:
            raise ValueError(
                f"weighted_sum_of names the unknown metric {summed_name!r}: the "
                f"metrics of this geograph are {['length', *metrics]}"
            )
        if not (isfinite(coefficient) and coefficient > 0):
            raise ValueError(
                f"The coefficient of {summed_name!r} in weighted_sum_of must be "
                f"a finite number above zero: got {coefficient!r}"
            )
        if summed_name == "length":
            weights_of_metrics.append(lengths)
            off_graph_per_km += coefficient * units_per_km
        else:
            weights_of_metrics.append(metrics[summed_name].weights)
            off_graph_per_km += (
                coefficient * metrics[summed_name].off_graph_per_km
            )
    weights = compute_weighted_sum(
        weights_of_metrics, array("d", weighted_sum_of.values())
    )
    return weights, off_graph_per_km


def _find_key(table: dict, edge_class: dict) -> str | None:
    # The key of a class in a table: its name, else the mode of its edges, else None
    for key in (edge_class["name"], edge_class["mode"]):
        if key is not None and key in table:
            return key
    return None


def _check_keys(
    table: dict, table_name: str, classes: list[dict], other_keys: tuple
) -> None:
    # Refuse a key of a table that is no class, no mode of edges and no other key
    known = {row[key] for row in classes for key in ("name", "mode")}
    for key in table:
        if key not in known and key not in other_keys:
            raise ValueError(
                f"{table_name} has the key {key!r}, which is no class and no "
                f"mode of the edges of this geograph"
            )


def check_weight(
    weight: float | None, origin_id: int, destination_id: int
) -> float:
    """Check the weight that a caller gives for an edge, and return it as a float.

    Args:
        weight: A weight of zero or more, or None to close the edge.
        origin_id: The node that the edge leaves, for the message of the error.
        destination_id: The node that the edge goes to.

    Returns:
        The weight. Infinity for None.

    Raises:
        ValueError: The weight is below zero or not a number.
    """
    weight = inf if weight is None else float(weight)
    # A comparison with a value that is not a number is false
    if not weight >= 0.0:
        raise ValueError(
            f"The weight of the edge from node {origin_id} to node "
            f"{destination_id} is below zero or not a number"
        )
    return weight


def set_edge_weights(
    weights: array | memoryview,
    edge_weights: dict,
    edge_indexes: list[int | None],
) -> array:
    """Return a copy of the weights of a metric with the weights of some edges set.

    Args:
        weights: One weight for each edge.
        edge_weights: A dict from (origin id, destination id) to the weight of
            this edge, or to None to close it.
        edge_indexes: The index of the edge of each pair of `edge_weights`, in the
            order of the dict. None for a pair that is not an edge.

    Returns:
        A new float64 array.

    Raises:
        ValueError: A pair of nodes is not an edge, or a weight is below zero or
            not a number.
    """
    new_weights = array("d")
    new_weights.frombytes(memoryview(weights).cast("B"))
    for ((origin_id, destination_id), weight), edge_index in zip(
        edge_weights.items(), edge_indexes
    ):
        if edge_index is None:
            raise ValueError(
                f"edge_weights names an edge from node {origin_id} to node "
                f"{destination_id}: the geograph has no such edge"
            )
        new_weights[edge_index] = check_weight(
            weight, origin_id, destination_id
        )
    return new_weights


def get_units_per_km(geograph_units: str) -> float:
    """Return 1 km in the units of a geograph: 0.621 for `mi`.

    `haversine` multiplies an angle by the Earth radius of a unit, so the ratio of
    two radiuses converts a distance.

    Args:
        geograph_units: The `geograph_units` of the geograph.
    """
    return earth_radius.get(geograph_units, 6371) / earth_radius["km"]


def compute_min_weight_per_km(
    weights: array | memoryview, lengths: array | memoryview
) -> float:
    """Return the smallest weight of an open edge divided by its length.

    A route of `d` km by the metric weighs `d` times this value at least. An A*
    search by the metric multiplies its great-circle bound by it.

    Args:
        weights: The weight of each edge in the metric.
        lengths: The length of each edge.

    Returns:
        The smallest ratio over the open edges longer than zero. 0.0 without such
        an edge.
    """
    # `compress` leaves out the edges of length zero. The loops run in C.
    ratios = map(
        truediv, compress(weights, lengths), compress(lengths, lengths)
    )
    return min(filter(isfinite, ratios), default=0.0)


def order_by_dependencies(metrics: dict[str, Metric]) -> list[str]:
    """Return the names of the metrics, each one after the metrics that it uses.

    Example: `cost` is a sum of `hours`, and `fare` is a sum of `cost`. The order
    is `hours`, `cost`, `fare`, also when the dict lists `fare` first.

    Args:
        metrics: The metrics by name. No metric uses itself, directly or through
            another metric: `create_metric` refuses such a metric.

    Returns:
        Every name of `metrics`. Two metrics that do not use each other keep the
        order of `metrics`.
    """
    ordered = {}

    def add_after_its_metrics(name: str) -> None:
        if name not in ordered:
            for used_name in metrics[name].used_metrics:
                add_after_its_metrics(used_name)
            ordered[name] = None

    for name in metrics:
        add_after_its_metrics(name)
    return list(ordered)


def find_users(metrics: dict[str, Metric], name: str) -> list[str]:
    """Return the metrics that use a metric, directly or through another metric.

    Example: `cost` is a sum of `hours`, and `fare` is a sum of `cost`. The users
    of `hours` are `cost` and `fare`.

    Args:
        metrics: The metrics by name.
        name: The name of the metric. It may be a name that `metrics` lacks.

    Returns:
        The names of the users, each one after the metrics that it uses.
    """
    used_names = {name}
    users = []
    for other_name in order_by_dependencies(metrics):
        if other_name != name and used_names.intersection(
            metrics[other_name].used_metrics
        ):
            used_names.add(other_name)
            users.append(other_name)
    return users


def find_used_metrics(
    metrics: dict[str, Metric], name: str, definition: dict
) -> tuple[str, ...]:
    """Return the names of the metrics that a new metric uses.

    Args:
        metrics: The metrics of the geograph, by name.
        name: The name of the new metric. `metrics` may hold a metric of this name,
            which the new metric replaces.
        definition: The arguments of the `create_metric` call, by name.

    Returns:
        For a weighted sum, the metrics that it sums, other than `length`. For a
        function, every other metric that does not use `name`: the function may
        read each of them in the `metrics` of an edge. For tables, no metric.
    """
    if definition["weighted_sum_of"] is not None:
        return tuple(
            summed_name
            for summed_name in definition["weighted_sum_of"]
            if summed_name != "length"
        )
    if definition["edge_weight_fn"] is not None:
        users = find_users(metrics, name)
        return tuple(
            other_name
            for other_name in metrics
            if other_name != name and other_name not in users
        )
    return ()


def describe_definition(definition: dict) -> str:
    """Return the `create_metric` call of a definition as text, for the description
    of a metric: `create_metric(per_km={'road': 0.02, 'off_graph': 0.05},
    edge_weights=<12 edges>)`. A function is written by its name."""
    arguments = []
    for key, value in definition.items():
        if value is None:
            continue
        if key == "edge_weight_fn":
            value = getattr(value, "__name__", "<function>")
        elif key == "edge_weights":
            value = f"<{len(value)} edges>"
        else:
            value = repr(value)
        arguments.append(f"{key}={value}")
    return f"create_metric({', '.join(arguments)})"
