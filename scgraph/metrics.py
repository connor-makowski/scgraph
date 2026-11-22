"""The metrics of a GeoGraph: what a metric is, and how its weights are computed.

This module is internal. `GeoGraph.create_metric` calls it, and a geograph keeps its
metrics by name in `GeoGraph._metrics`.

A "metric" is one weight for every edge, under a name: an array of float64 values,
"lined up with the edges". Its value number `i` is the weight of the edge of id `i`:
the edge at the position `i` in the heads of the graph (`Graph._csr`). A search by a
metric adds up these weights in place of the lengths. The lengths are the metric
`length`, which the graph of the geograph holds. A `Metric` record holds each other
metric. An edge is "closed" in a metric when its weight is infinity: no route by
this metric takes it.

The weights of a metric are computed in one of three ways:

- from weights per km: the weight per km of the class of an edge times its km,
  plus the weight of each hub that the edge leaves or enters.
  `GeoGraph.create_metric` gives the result of `resolve_weights_per_km` to the
  kernel `compute_weights_from_km`;
- as a weighted sum of other metrics (`compute_weights_from_sum`);
- from a function of the caller, called once for each edge
  (`compute_weights_from_function`). The caller gives the weight of 1 km of an
  off-graph leg beside the function.

`set_edge_weights` then writes the weights that the caller gives for some edges.

THE RULE: A METRIC KEEPS THE WEIGHTS OF ITS CREATION

An edit of the network removes every metric, and a metric that is created again
changes no other metric. So no code moves the weights of a metric or computes them
again: the caller creates the metric again.

Example, a graph with the edges 0 -> 1, 0 -> 2 and 2 -> 0, with lengths of 10, 20
and 20 km. The first two edges have the class `primary` and the third the class
`motorway`. Both classes have the edge mode `road`. The weights per km
`weight_per_km={"road": 0.02, "off_graph": 0.05}` and
`class_weight_per_km={"motorway": 0.01}` give the metric `hours`, and the sum
`{"hours": 30, "length": 0.5}` gives the metric `cost`:

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

from scgraph.edge_classes import find_edge_id

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
    # The weight of 1 km of an off-graph leg: the straight line between a query
    # point and its node
    off_graph_weight_per_km: float
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
            "off_graph_weight_per_km": self.off_graph_weight_per_km,
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


def resolve_weights_per_km(
    weight_per_km: float | dict,
    class_weight_per_km: dict | None,
    weight_at_hub: dict | None,
    classes: list[dict],
    node_modes: list[dict],
    edge_class_ids: array | memoryview,
) -> tuple[array, array, float]:
    """Turn `weight_per_km`, `class_weight_per_km` and `weight_at_hub` of
    `GeoGraph.create_metric` into the arrays of the kernel
    `compute_weights_from_km`: `class_weights_per_km`, `hub_weights`, and the
    weight of 1 km of an off-graph leg.

    A class takes the weight per km of its name in `class_weight_per_km`, else of
    its edge mode in `weight_per_km`. `weight_per_km={"road": 0.02, ...}` with
    `class_weight_per_km={"motorway": 0.01}` gives 0.01 to the motorways and 0.02
    to the other classes of the edge mode `road`.

    Args:
        classes: The row `{"name", "edge_mode"}` of each class. Empty for a
            geograph without classes: every edge then has the class id 0.
        node_modes: The row of each node mode (`GeoGraph.node_modes`).
        edge_class_ids: The class id of each edge: the position of the row of
            its class in `classes`.

    Raises:
        ValueError: A dict has a key that it may not have, or lacks a weight per
            km, or a hub weight is not a number.
    """
    class_count = max(len(classes), 1)
    class_weight_per_km = class_weight_per_km or {}
    edge_modes = sorted(
        {class_row["edge_mode"] for class_row in classes} - {None}
    )
    class_names = [class_row["name"] for class_row in classes]
    for class_name in class_weight_per_km:
        if class_name is None or class_name not in class_names:
            raise ValueError(
                f"class_weight_per_km has the key {class_name!r}, which is no "
                "class of this geograph: `classes` gives its classes"
            )
    if isinstance(weight_per_km, dict):
        if not classes:
            raise ValueError(
                "weight_per_km must be a number: this geograph has no classes"
            )
        _check_edge_modes(
            set(weight_per_km) - {"off_graph"}, "weight_per_km", edge_modes
        )
        if weight_per_km.get("off_graph") is None:
            raise ValueError(
                "weight_per_km must give a weight for 'off_graph': the weight "
                "of 1 km between a query point and its node"
            )
        off_graph_weight_per_km = weight_per_km["off_graph"]
        weight_per_km_of_edge_mode = weight_per_km
    else:
        off_graph_weight_per_km = weight_per_km
        weight_per_km_of_edge_mode = dict.fromkeys(
            [*edge_modes, None], weight_per_km
        )
    count_edges_of_class_id = bytes(edge_class_ids).count
    class_weights_per_km = array("d")
    for class_id, class_row in enumerate(classes):
        class_name, edge_mode = class_row["name"], class_row["edge_mode"]
        if class_name is not None and class_name in class_weight_per_km:
            weight = class_weight_per_km[class_name]
        elif edge_mode in weight_per_km_of_edge_mode:
            weight = weight_per_km_of_edge_mode[edge_mode]
        elif class_name is not None and count_edges_of_class_id(class_id):
            raise ValueError(
                "weight_per_km gives no weight for the edge mode "
                f"{edge_mode!r} of the class {class_name!r}, which has edges: "
                "name the edge mode, or name the class in class_weight_per_km"
            )
        else:
            # The class has no edge, or it is the class without a name: an edge
            # without a class takes the weight per km of the off-graph legs.
            weight = off_graph_weight_per_km
        class_weights_per_km.append(inf if weight is None else weight)
    if not classes:
        class_weights_per_km.append(weight_per_km)

    node_mode_names = [mode.get("name") for mode in node_modes]
    hub_weights = array("d", bytes(8 * len(node_modes) * class_count))
    for hub_mode, weights_of_hub in (weight_at_hub or {}).items():
        if hub_mode not in node_mode_names:
            raise ValueError(
                f"weight_at_hub has the key {hub_mode!r}, which is no node "
                f"mode: the node modes of this geograph are {node_mode_names}"
            )
        _check_edge_modes(
            weights_of_hub, f"weight_at_hub[{hub_mode!r}]", edge_modes
        )
        for class_id, class_row in enumerate(classes):
            edge_mode = class_row["edge_mode"]
            if edge_mode not in weights_of_hub:
                continue
            weight = weights_of_hub[edge_mode]
            if not isinstance(weight, (int, float)):
                raise ValueError(
                    f"weight_at_hub[{hub_mode!r}][{edge_mode!r}] must be a "
                    "number, which an edge pays when it enters the hub and "
                    f"when it leaves the hub: got {weight!r}"
                )
            # Two node modes may have the same name, after a merge
            for node_mode_id, mode_name in enumerate(node_mode_names):
                if mode_name == hub_mode:
                    hub_weights[node_mode_id * class_count + class_id] = weight
    return class_weights_per_km, hub_weights, off_graph_weight_per_km


def compute_weights_from_sum(
    weighted_sum_of: dict[str, float],
    metrics: dict[str, Metric],
    lengths: array | memoryview,
    units_per_km: float,
) -> tuple[array | memoryview, float]:
    """Return the weights of a weighted sum of metrics, and its weight of 1 km of
    an off-graph leg: the same sum of the weights of 1 km of an off-graph leg of
    the metrics.

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
    weights_of_metrics, off_graph_weight_per_km = [], 0.0
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
            off_graph_weight_per_km += coefficient * units_per_km
        else:
            weights_of_metrics.append(metrics[summed_name].weights)
            off_graph_weight_per_km += (
                coefficient * metrics[summed_name].off_graph_weight_per_km
            )
    weights = compute_weighted_sum(
        weights_of_metrics, array("d", weighted_sum_of.values())
    )
    return weights, off_graph_weight_per_km


def compute_weights_from_function(
    edge_weight_fn: Callable, edges: Iterable[dict]
) -> array:
    """Return the weights that a function of the caller gives. The function is
    called once for each edge, and for no other dict.

    Args:
        edge_weight_fn: Takes the dict of an edge and returns its weight, or None
            to close it.
        edges: The dict of each edge, in the order of the edges (see
            `GeoGraph.get_edges`).

    Raises:
        ValueError: A weight is below zero or not a number.
    """
    return array(
        "d",
        (
            check_weight(
                edge_weight_fn(edge), edge["origin_id"], edge["destination_id"]
            )
            for edge in edges
        ),
    )


def _check_edge_modes(
    keys: Iterable, argument: str, edge_modes: list[str]
) -> None:
    # Refuse a key of `weight_per_km` or of a dict of hub weights that is no edge
    # mode. `argument` names the dict in the message.
    for key in keys:
        if key not in edge_modes:
            raise ValueError(
                f"{argument} has the key {key!r}, which is no edge mode of "
                f"this geograph: its edge modes are {edge_modes}"
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
        edge_id = find_edge_id(offsets, heads, origin_id, destination_id)
        if edge_id is None:
            raise ValueError(
                f"edge_weights names an edge from node {origin_id} to node "
                f"{destination_id}: the geograph has no such edge"
            )
        new_weights[edge_id] = check_weight(weight, origin_id, destination_id)
    return new_weights


def check_off_graph_weight_per_km(
    name: str, off_graph_weight_per_km: float | None
) -> float:
    """Return the weight of 1 km of an off-graph leg in a new metric as a float.

    Raises:
        ValueError: The weight is not a finite number of zero or more.
    """
    # A comparison with a value that is not a number is false
    if (
        off_graph_weight_per_km is None
        or not 0 <= off_graph_weight_per_km < inf
    ):
        raise ValueError(
            f"The weight of 1 km of an off-graph leg in the metric {name!r} "
            "must be a finite number of zero or more: got "
            f"{off_graph_weight_per_km!r}"
        )
    return float(off_graph_weight_per_km)


def build_default_description(**arguments: object) -> str:
    """Return the description of a metric that the caller did not describe:
    the text of its `create_metric` call, for example
    `create_metric(weight_per_km={'road': 0.02, 'off_graph': 0.05},
    edge_weights=<12 edges>)`. A function is written by its name."""
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
