"""The metrics of a GeoGraph: what a metric is, and how its weights are computed.

This module is internal. `GeoGraph.create_metric` calls it, and a geograph keeps its
metrics by name in `GeoGraph._metrics`.

A "metric" is one weight for every edge, under a name: an array of float64 values,
lined up with the edges (`scgraph/edge_classes.py`). A search by a metric adds up
these weights in place of the lengths. The lengths are the metric `length`, which the
graph of the geograph holds. A `Metric` record holds each other metric. An edge is
"closed" in a metric when its weight is infinity: no route by this metric takes it.

The weights of a metric are computed in one of three ways:

- from rates: the rate of the class of an edge times its km, plus the weight of
  each hub that the edge leaves or enters. `GeoGraph.create_metric` gives the
  result of `resolve_rates` to the kernel `compute_weights_from_rates`;
- as a weighted sum of other metrics (`compute_weights_from_sum`);
- from a function of the caller, called once for each edge
  (`compute_weights_from_function`).

`set_edge_weights` then writes the weights that the caller gives for some edges.

THE RULE: A METRIC KEEPS THE WEIGHTS OF ITS CREATION

An edit of the network removes every metric, and a metric that is created again
changes no other metric. So no code lines up a metric or computes it again: the
caller creates it again.

Example, a graph with the edges 0 -> 1, 0 -> 2 and 2 -> 0, with lengths of 10, 20
and 20 km. The first two edges have the class `primary` and the third the class
`motorway`. The rates `per_km={"primary": 0.02, "motorway": 0.01, "off_graph": 0.05}`
give the metric `hours`, and the sum `{"hours": 30, "length": 0.5}` gives the metric
`cost`:

    hours = [0.02 * 10, 0.02 * 20, 0.01 * 20] = [0.2, 0.4, 0.2]
    cost = [30 * 0.2 + 0.5 * 10, ...] = [11, 22, 16]

The two kernels are explained in `scgraph/cpp/src/metric_weights.hpp`. Their
pure-Python versions are in `scgraph/helpers/metric_weights.py`.
"""

from array import array
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from itertools import compress
from math import inf, isfinite
from operator import truediv
from typing import TYPE_CHECKING

try:
    from scgraph.cpp import compute_weighted_sum
except ImportError:
    from scgraph.helpers.metric_weights import compute_weighted_sum

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
    # The result of `get_min_weight_per_km`. Computed at the first A* search.
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

    def get_min_weight_per_km(self, lengths: array | memoryview) -> float:
        """Return the smallest weight of an open edge divided by its length, over
        the edges longer than zero. 0.0 without such an edge.

        A route of `d` km by the metric weighs `d` times this value at least. An A*
        search by the metric multiplies its great-circle bound by it.

        Args:
            lengths: The length of each edge.
        """
        if self.min_weight_per_km is None:
            # `compress` leaves out the edges of length zero. The loops run in C.
            ratios = map(
                truediv,
                compress(self.weights, lengths),
                compress(lengths, lengths),
            )
            self.min_weight_per_km = min(filter(isfinite, ratios), default=0.0)
        return self.min_weight_per_km


def resolve_rates(
    per_km: float | dict,
    at_hub: dict | None,
    classes: list[dict],
    modes: list[dict],
    edge_classes: array | memoryview,
) -> tuple[array, array, float]:
    """Turn the rates and the hub weights of a `create_metric` call into the arrays
    of the kernel `compute_weights_from_rates`.

    In `per_km` and in the dict of a hub, the key of a class is its name, or the
    mode of its edges. The name
    wins: `{"road": 0.02, "motorway": 0.01}` gives 0.01 to the motorways and 0.02 to
    the other classes of the mode `road`.

    Args:
        per_km: The rate of every edge, or a dict from a class, a mode of edges or
            `"off_graph"` to a rate. A rate of None closes the class. With a dict,
            an edge without a class weighs as an access leg: its km times the rate
            `"off_graph"` of the metric. It pays no hub weight.
        at_hub: A dict from the mode of a node to a dict from a class, or a mode of
            edges, to a weight: a number, which an edge pays when it enters the
            hub and when it leaves the hub. None for no hub weight.
        classes: The rows `{"name", "mode"}` of the classes. Empty for a geograph
            without classes: every edge then has the row 0.
        modes: The rows of the modes of the nodes, each with its `name`.
        edge_classes: The row of the class of each edge.

    Returns:
        `class_rates_per_km`, `hub_weights` and the rate of the access legs. The
        docstring of `compute_weights_from_rates` describes the two arrays.

    Raises:
        ValueError: A dict has a key that it may not have, or lacks a rate, or a
            hub weight is not a number.
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
            # Without a key, the class has no edge, or it is the row of no class:
            # an edge without a class takes the rate of the access legs.
            rate = off_graph_per_km if key is None else per_km[key]
            rates.append(inf if rate is None else rate)
    else:
        off_graph_per_km = per_km
        rates = array("d", [per_km]) * class_count

    mode_names = [mode.get("name") for mode in modes]
    hub_weights = array("d", bytes(8 * len(modes) * class_count))
    for hub_mode, weights_of_hub in (at_hub or {}).items():
        if hub_mode not in mode_names:
            raise ValueError(
                f"at_hub has the key {hub_mode!r}, which is no mode of a node: "
                f"the modes of this geograph are {mode_names}"
            )
        _check_keys(weights_of_hub, f"at_hub[{hub_mode!r}]", classes, ())
        for row, edge_class in enumerate(classes):
            key = _find_key(weights_of_hub, edge_class)
            if key is None:
                continue
            weight = weights_of_hub[key]
            if not isinstance(weight, (int, float)):
                raise ValueError(
                    f"at_hub[{hub_mode!r}][{key!r}] must be a number, which an "
                    "edge pays when it enters the hub and when it leaves the "
                    f"hub: got {weight!r}"
                )
            # Two modes may have the same name, after a merge
            for mode_row, mode_name in enumerate(mode_names):
                if mode_name == hub_mode:
                    hub_weights[mode_row * class_count + row] = weight
    return rates, hub_weights, off_graph_per_km


def compute_weights_from_sum(
    weighted_sum_of: dict[str, float],
    metrics: dict[str, Metric],
    lengths: array | memoryview,
    units_per_km: float,
) -> tuple[array | memoryview, float]:
    """Compute the weights of a metric that is a weighted sum of other metrics.

    Args:
        weighted_sum_of: A dict from the name of a metric to its coefficient, a
            finite number above zero. `length` may be one of the metrics.
        metrics: The metrics of the geograph other than `length`, by name.
        lengths: The length of each edge: the weights of the metric `length`.
        units_per_km: 1 km in the unit of `lengths`, from
            `utils.get_units_per_km`: the weight of 1 km of access leg in the
            metric `length`.

    Returns:
        One float64 weight for each edge, and the rate of the access legs: the
        same sum of the rates of the metrics.

    Raises:
        ValueError: The sum names no metric or an unknown metric, or a coefficient
            is not a finite number above zero.
    """
    weights_of_metrics, off_graph_per_km = [], 0.0
    for summed_name, coefficient in weighted_sum_of.items():
        if summed_name != "length" and summed_name not in metrics:
            raise ValueError(
                f"weighted_sum_of names the unknown metric {summed_name!r}: the "
                f"metrics of this geograph are {['length', *metrics]}. An edit of "
                "the network removes the metrics other than 'length'"
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


def compute_weights_from_function(
    edge_weight_fn: Callable,
    edges: Iterable[dict],
    metrics: dict[str, Metric],
    units_per_km: float,
) -> tuple[array, float | None]:
    """Compute the weights of a metric from a function of the caller.

    Args:
        edge_weight_fn: A function that takes the dict of an edge and returns its
            weight, or None to close it.
        edges: The dict of each edge, in the order of the edges, as
            `GeoGraph.get_edges` returns them.
        metrics: The metrics of the geograph other than `length`, by name.
        units_per_km: 1 km in the unit of the lengths.

    Returns:
        One float64 weight for each edge, and the weight of 1 km of access leg: the
        value of the function for 1 km of the mode `off_graph`.

    Raises:
        ValueError: A weight is below zero or not a number.
    """
    weights = array(
        "d",
        (
            check_weight(
                edge_weight_fn(edge), edge["origin_id"], edge["destination_id"]
            )
            for edge in edges
        ),
    )
    off_graph_per_km = edge_weight_fn(
        {
            "origin_id": None,
            "destination_id": None,
            "length": units_per_km,
            "class": None,
            "mode": "off_graph",
            "metrics": {
                name: metric_record.off_graph_per_km
                for name, metric_record in metrics.items()
            },
        }
    )
    return weights, off_graph_per_km


def _find_key(values: dict, edge_class: dict) -> str | None:
    # The key of a class in a dict of rates or of hub weights: its name, else the
    # mode of its edges, else None
    for key in (edge_class["name"], edge_class["mode"]):
        if key is not None and key in values:
            return key
    return None


def _check_keys(
    values: dict, argument: str, classes: list[dict], other_keys: tuple
) -> None:
    # Refuse a key of a dict of rates or of hub weights that is no class, no mode
    # of edges and no other key. `argument` names the dict in the message.
    known = {row[key] for row in classes for key in ("name", "mode")}
    for key in values:
        if key not in known and key not in other_keys:
            edge_modes = sorted({row["mode"] for row in classes} - {None})
            raise ValueError(
                f"{argument} has the key {key!r}, which is no class and no "
                "mode of the edges of this geograph: the modes of its edges are "
                f"{edge_modes}, and `classes` gives its classes"
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


def check_off_graph_per_km(name: str, off_graph_per_km: float | None) -> float:
    """Check the weight of 1 km of access leg in a new metric, and return it as a
    float.

    Raises:
        ValueError: The weight is not a finite number of zero or more.
    """
    # A comparison with a value that is not a number is false
    if off_graph_per_km is None or not 0 <= off_graph_per_km < inf:
        raise ValueError(
            f"The weight of 1 km of access leg in the metric {name!r} must "
            f"be a finite number of zero or more: got {off_graph_per_km!r} "
            "(for a function: the value that it returns for the mode "
            "'off_graph')"
        )
    return float(off_graph_per_km)


def describe_call(**arguments: object) -> str:
    """Return a `create_metric` call as text, for the description of a metric:
    `create_metric(per_km={'road': 0.02, 'off_graph': 0.05}, edge_weights=<12
    edges>)`. A function is written by its name."""
    texts = []
    for key, value in arguments.items():
        if value is None:
            continue
        if key == "edge_weight_fn":
            value = getattr(value, "__name__", "<function>")
        elif key == "edge_weights":
            value = f"<{len(value)} edges>"
        else:
            value = repr(value)
        texts.append(f"{key}={value}")
    return f"create_metric({', '.join(texts)})"
