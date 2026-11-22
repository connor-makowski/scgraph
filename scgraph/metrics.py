"""The metrics of a GeoGraph: what a metric is, and how its weights are computed.

This module is internal. `GeoGraph.create_metric` calls it, and a geograph keeps its
metrics by name in `GeoGraph._metrics`.

A "metric" is one weight for every edge, under a name: an array of float64 values,
"lined up with the edges". Its value number `i` is the weight of the edge of index
`i`: the edge at the position `i` in the heads of the graph (`Graph._csr`). A search
by a metric adds up these weights in place of the lengths. The lengths are the metric `length`, which the
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
changes no other metric. So no code moves the weights of a metric or computes them
again: the caller creates the metric again.

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

from scgraph.edge_classes import find_edge_index

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
        the edges longer than zero, or 0.0 without such an edge. A route of `d` km
        by the metric weighs `d` times this value at least: it scales the bound of
        an A* search by the metric."""
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
    """Turn `per_km` and `at_hub` of `GeoGraph.create_metric` into the arrays of
    the kernel `compute_weights_from_rates`: `class_rates_per_km`, `hub_weights`,
    and the weight of 1 km of access leg.

    In both dicts, the key of a class is its name, or the mode of its edges. The
    name wins: `{"road": 0.02, "motorway": 0.01}` gives 0.01 to the motorways and
    0.02 to the other classes of the mode `road`.

    Args:
        classes: The entry `{"name", "mode"}` of each class. Empty for a geograph
            without classes: every edge then has the row 0.
        modes: The entry of each node mode (`GeoGraph.modes`).
        edge_classes: The row of the class of each edge: the position of the
            entry of the class in `classes`.

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
        count_edges_of_class_row = bytes(edge_classes).count
        class_rates_per_km = array("d")
        for class_row, class_entry in enumerate(classes):
            key = _find_key(per_km, class_entry)
            if (
                key is None
                and class_entry["name"] is not None
                and count_edges_of_class_row(class_row)
            ):
                raise ValueError(
                    "per_km gives no rate for the class "
                    f"{class_entry['name']!r}, which has edges: name it, or its "
                    f"mode {class_entry['mode']!r}"
                )
            # Without a key, the class has no edge, or it is the class without a
            # name: an edge without a class takes the rate of the access legs.
            rate = off_graph_per_km if key is None else per_km[key]
            class_rates_per_km.append(inf if rate is None else rate)
    else:
        off_graph_per_km = per_km
        class_rates_per_km = array("d", [per_km]) * class_count

    mode_names = [mode.get("name") for mode in modes]
    hub_weights = array("d", bytes(8 * len(modes) * class_count))
    for hub_mode, weights_of_hub in (at_hub or {}).items():
        if hub_mode not in mode_names:
            raise ValueError(
                f"at_hub has the key {hub_mode!r}, which is no mode of a node: "
                f"the modes of this geograph are {mode_names}"
            )
        _check_keys(weights_of_hub, f"at_hub[{hub_mode!r}]", classes, ())
        for class_row, class_entry in enumerate(classes):
            key = _find_key(weights_of_hub, class_entry)
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
                    hub_weights[mode_row * class_count + class_row] = weight
    return class_rates_per_km, hub_weights, off_graph_per_km


def compute_weights_from_sum(
    weighted_sum_of: dict[str, float],
    metrics: dict[str, Metric],
    lengths: array | memoryview,
    units_per_km: float,
) -> tuple[array | memoryview, float]:
    """Return the weights of a weighted sum of metrics, and its weight of 1 km of
    access leg: the same sum of the weights of 1 km of access leg of the metrics.

    Args:
        weighted_sum_of: `{name of a metric: coefficient}`. `length` may be one of
            the metrics.
        metrics: The metrics of the geograph other than `length`, by name.
        lengths: The length of each edge: the weights of the metric `length`.
        units_per_km: 1 km in the unit of `lengths`.

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
    """Return the weights that a function of the caller gives, and its weight of
    1 km of access leg: the value of the function for 1 km of the mode `off_graph`.

    Args:
        edge_weight_fn: Takes the dict of an edge and returns its weight, or None
            to close it.
        edges: The dict of each edge, in the order of the edges (see
            `GeoGraph.get_edges`).
        metrics: The metrics of the geograph other than `length`, by name.
        units_per_km: 1 km in the unit of the lengths.

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


def _find_key(values_by_class: dict, class_entry: dict) -> str | None:
    # The key of a class in a dict of rates or of hub weights: its name, else the
    # mode of its edges, else None
    for key in (class_entry["name"], class_entry["mode"]):
        if key is not None and key in values_by_class:
            return key
    return None


def _check_keys(
    values_by_class: dict,
    argument: str,
    classes: list[dict],
    other_keys: tuple,
) -> None:
    # Refuse a key of a dict of rates or of hub weights that is no class, no mode
    # of edges and no other key. `argument` names the dict in the message.
    known_keys = {
        class_entry[key] for class_entry in classes for key in ("name", "mode")
    }
    for key in values_by_class:
        if key not in known_keys and key not in other_keys:
            edge_modes = sorted(
                {class_entry["mode"] for class_entry in classes} - {None}
            )
            raise ValueError(
                f"{argument} has the key {key!r}, which is no class and no "
                "mode of the edges of this geograph: the modes of its edges are "
                f"{edge_modes}, and `classes` gives its classes"
            )


def check_weight(
    weight: float | None, origin_id: int, destination_id: int
) -> float:
    """Return the weight that a caller gives for an edge as a float: infinity for
    None, which closes the edge.

    Raises:
        ValueError: The weight is below zero or not a number. The message names the
            two nodes of the edge.
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
    offsets: array | memoryview,
    heads: array | memoryview,
) -> array:
    """Return a copy of the weights of a metric with the weights of some edges set.

    Args:
        weights: One weight for each edge.
        edge_weights: `{(origin id, destination id): weight}`. None closes the
            edge.
        offsets: The offsets of the edges, one for each node plus one.
        heads: The destination of each edge.

    Raises:
        ValueError: A pair of nodes is not an edge, or a weight is below zero or
            not a number.
    """
    new_weights = array("d")
    new_weights.frombytes(memoryview(weights).cast("B"))
    for (origin_id, destination_id), weight in edge_weights.items():
        edge_index = find_edge_index(offsets, heads, origin_id, destination_id)
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
    """Return the weight of 1 km of access leg in a new metric as a float.

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


def build_default_description(**arguments: object) -> str:
    """Return the description of a metric that the caller did not describe:
    the text of its `create_metric` call, for example
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
