"""The metrics of a GeoGraph: what a metric is, and how its weights are computed.

This module is internal. `GeoGraph.create_metric` calls it. A geograph keeps one
`Metric` record for each metric other than `length`, by name, in
`GeoGraph._metrics`. The record of `length` has no weights: they are the lengths
of its graph.

WORDS

- A "metric" gives one weight to each edge, under a name such as `hours`. A search
  by a metric adds these weights in place of the lengths.
- An edge is "closed" in a metric when its weight is infinity. No route by this
  metric takes it.
- An "edge id" is the position of an edge in the arrays of a graph (`Graph._get_edge_arrays`).
  The node `u` has the edges of ids `node_first_edge_ids[u]` to
  `node_first_edge_ids[u + 1] - 1`, and `edge_destination_node_ids[edge_id]` is the node
  that the edge goes to. An array "by edge id" has one value for each edge, at its id.
- A "class" is the category of an edge, such as `motorway`. Each class has an
  "edge mode", such as `road`. A "class id" is the position of a class in
  `GeoGraph.classes`, and the class id 255 means "no class".
- A "weight per km" is the weight of 1 km of an edge.
- A "hub" is a node whose node mode has a weight in `weight_at_hub`, such as a port.
- An "off-graph leg" is the straight line between a query point and its node.

HOW THE WEIGHTS ARE COMPUTED

- From weights per km. The weight of an edge is the weight per km of its class
  times its km, plus the weight of each hub that the edge leaves or enters.
  `resolve_weights_per_km` gives its arrays to the kernel `compute_weights_from_km`.
- As a weighted sum of other metrics (`compute_weights_from_weighted_sum`).
- From a function of the caller (`compute_weights_from_function`).

`copy_with_edge_weights` then replaces the weights of the edges that the caller
names. A "kernel" is a loop over all the edges, in C++ and in pure Python.
`scgraph/cpp/src/metric_weights.hpp` explains the kernels of the metrics.

THE RULE: A METRIC KEEPS THE WEIGHTS OF ITS CREATION

An edit of the network removes every metric other than `length`, and a metric that
is created again changes no other metric. So no code corrects the weights of a
metric after an edit: the caller creates the metric again.

EXAMPLE

A graph has the edges 0 -> 1, 0 -> 2 and 2 -> 0, with lengths of 10, 20 and 20 km.
The first two edges have the class `primary` and the third the class `motorway`,
both of the edge mode `road`. The metric `hours` has `weight_per_km={"road": 0.02,
"off_graph": 0.05}` and `class_weight_per_km={"motorway": 0.01}`. The metric `cost`
is the weighted sum `{"hours": 30, "length": 0.5}`:

    hours = [0.02 * 10, 0.02 * 20, 0.01 * 20] = [0.2, 0.4, 0.2]
    cost = [30 * 0.2 + 0.5 * 10, ...] = [11, 22, 16]
"""

from array import array
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from itertools import compress
from math import inf, isfinite, nan
from operator import truediv
from typing import TYPE_CHECKING

from scgraph.edge_classes import find_edge_id
from scgraph.network_file import NO_CLASS_ID

try:
    from scgraph.cpp import check_edge_weights, compute_weighted_sum
except ImportError:
    from scgraph.helpers.metric_weights import (
        check_edge_weights,
        compute_weighted_sum,
    )

if TYPE_CHECKING:  # Only for an annotation
    from scgraph.graph import Graph


@dataclass
class Metric:
    """A metric of a geograph. The record of `length` is built on demand by
    `GeoGraph._read_metric`, without reading the edges."""

    name: str
    # The unit of the weights as free text, such as `h` or `kg CO2e`, or None
    unit: str | None
    # Where the weights come from, as free text, or None
    description: str | None
    # The float64 weight of each edge, by edge id. Never changed in place: the
    # graph of the metric reads this array. None for `length`: its weights are
    # the lengths of `graph_object`.
    weights: array | memoryview | None
    # The weight of 1 km of an off-graph leg
    off_graph_weight_per_km: float
    # The result of `get_min_weight_per_length_unit`, at the first A* search.
    min_weight_per_length_unit: float | None = None
    # The Graph that a search by this metric runs on. Built at the first query.
    graph_object: "Graph | None" = None

    def get_info(self) -> dict:
        """Return the info of the metric: what describes it, without its weights."""
        info = {
            "name": self.name,
            "unit": self.unit,
            "description": self.description,
            "off_graph_weight_per_km": self.off_graph_weight_per_km,
        }
        return {key: value for key, value in info.items() if value is not None}

    def get_min_weight_per_length_unit(
        self, read_lengths: Callable[[], array | memoryview]
    ) -> float:
        """Return the smallest weight of one unit of length: the weight of an edge
        divided by its length, over the open edges longer than zero. Return 0.0
        without such an edge. The total of a route of length `d` is at least `d`
        times this value, so an A* search by the metric multiplies its bound by it.
        `read_lengths` returns the lengths; it is called at the first call only.
        """
        if self.min_weight_per_length_unit is None:
            lengths = read_lengths()
            # `compress` removes the edges of length zero. The loops run in C.
            ratios = map(
                truediv,
                compress(self.weights, lengths),
                compress(lengths, lengths),
            )
            self.min_weight_per_length_unit = min(
                filter(isfinite, ratios), default=0.0
            )
        return self.min_weight_per_length_unit


def resolve_weights_per_km(
    weight_per_km: float | dict,
    class_weight_per_km: dict | None,
    weight_at_hub: dict | None,
    classes: list[dict],
    node_modes: list[dict],
    edge_class_ids: array | memoryview,
) -> tuple[array, array, float]:
    """Return the arrays that the kernel `compute_weights_from_km` reads, from the
    first three arguments, which `GeoGraph.create_metric` describes.

    A class takes the weight per km of its name in `class_weight_per_km`, else of
    its edge mode in `weight_per_km` (see the example of the module docstring).

    Args:
        classes: The row `{"name", "edge_mode"}` of each class (`GeoGraph.classes`).
        node_modes: The row of each node mode (`GeoGraph.node_modes`).
        edge_class_ids: The class id of each edge, by edge id.

    Returns:
        `class_weights_per_km`, `hub_weights` and the weight of 1 km of an
        off-graph leg. The arrays have values for each of the 256 values of a
        class id. So the kernel needs no rule for an edge without a class: the
        class id 255 has the weight per km of an off-graph leg, and no weight at
        a hub. An id that is above the last class and below 255 has a weight per
        km that is not a number, which the kernel refuses.

    Raises:
        ValueError: A dict has a key that it may not have, a weight per km is
            missing, or a hub weight is below zero or not a number.
    """
    class_id_count = NO_CLASS_ID + 1
    class_weight_per_km = class_weight_per_km or {}
    edge_modes = sorted(
        {class_row["edge_mode"] for class_row in classes} - {None}
    )
    class_names = [class_row["name"] for class_row in classes]
    for class_name in class_weight_per_km:
        if class_name not in class_names:
            raise ValueError(
                f"class_weight_per_km has the key {class_name!r}, which is no "
                "class of this geograph: `classes` gives its classes"
            )
    if isinstance(weight_per_km, dict):
        if not classes:
            raise ValueError(
                "weight_per_km must be a number: this geograph has no classes"
            )
        _refuse_unknown_edge_modes(
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
    class_weights_per_km = array("d", [nan] * class_id_count)
    # An edge without a class takes the weight per km of the off-graph legs.
    class_weights_per_km[NO_CLASS_ID] = off_graph_weight_per_km
    for class_id, class_row in enumerate(classes):
        class_name, edge_mode = class_row["name"], class_row["edge_mode"]
        if class_name in class_weight_per_km:
            weight = class_weight_per_km[class_name]
        elif edge_mode in weight_per_km_of_edge_mode:
            weight = weight_per_km_of_edge_mode[edge_mode]
        elif count_edges_of_class_id(class_id):
            raise ValueError(
                "weight_per_km gives no weight for the edge mode "
                f"{edge_mode!r} of the class {class_name!r}, which has edges: "
                "name the edge mode, or name the class in class_weight_per_km"
            )
        else:
            # The class has no edge: its weight per km is never read.
            weight = off_graph_weight_per_km
        class_weights_per_km[class_id] = inf if weight is None else weight

    node_mode_names = [mode.get("name") for mode in node_modes]
    hub_weights = array("d", bytes(8 * len(node_modes) * class_id_count))
    for hub_mode, weights_of_hub in (weight_at_hub or {}).items():
        if hub_mode not in node_mode_names:
            raise ValueError(
                f"weight_at_hub has the key {hub_mode!r}, which is no node "
                f"mode: the node modes of this geograph are {node_mode_names}"
            )
        _refuse_unknown_edge_modes(
            weights_of_hub, f"weight_at_hub[{hub_mode!r}]", edge_modes
        )
        for class_id, class_row in enumerate(classes):
            edge_mode = class_row["edge_mode"]
            if edge_mode not in weights_of_hub:
                continue
            weight = weights_of_hub[edge_mode]
            # `not >=` also refuses a value that is not a number.
            if not isinstance(weight, (int, float)) or not weight >= 0:
                raise ValueError(
                    f"weight_at_hub[{hub_mode!r}][{edge_mode!r}] must be a "
                    "number of zero or more, added to an edge that enters the "
                    f"hub or leaves it: got {weight!r}"
                )
            # Two node modes may have the same name, after a merge
            for node_mode_id, mode_name in enumerate(node_mode_names):
                if mode_name == hub_mode:
                    hub_weights[node_mode_id * class_id_count + class_id] = (
                        weight
                    )
    return class_weights_per_km, hub_weights, off_graph_weight_per_km


def compute_weights_from_weighted_sum(
    weighted_sum_of: dict[str, float],
    metrics: dict[str, Metric],
) -> tuple[array | memoryview, float]:
    """Return the weights of a weighted sum of metrics, and the weight of 1 km of
    an off-graph leg in the sum. Each one is the sum of its value in each metric
    times the coefficient of the metric.

    Args:
        weighted_sum_of: `{name of a metric: coefficient}`.
        metrics: The metrics of the geograph, `length` first, by name, each
            with its weights.

    Raises:
        ValueError: The sum names no metric or an unknown metric, or a coefficient
            is not a finite number above zero.
    """
    weights_of_metrics, off_graph_weight_per_km = [], 0.0
    for summed_name, coefficient in weighted_sum_of.items():
        if summed_name not in metrics:
            raise ValueError(
                f"weighted_sum_of names the unknown metric {summed_name!r}: the "
                f"metrics of this geograph are {list(metrics)}. An edit of "
                "the network removes the metrics other than 'length'"
            )
        if not (isfinite(coefficient) and coefficient > 0):
            raise ValueError(
                f"The coefficient of {summed_name!r} in weighted_sum_of must be "
                f"a finite number above zero: got {coefficient!r}"
            )
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
    """Return the weight that a function of the caller gives to each edge, by edge
    id. The function is called once for each edge.

    Args:
        edge_weight_fn: Takes the dict of an edge and returns its weight, or None
            to close the edge.
        edges: The dict of each edge, in the order of the edge ids (see
            `GeoGraph.get_edges`).
    """
    return array(
        "d",
        (parse_weight(edge_weight_fn(edge)) for edge in edges),
    )


def _refuse_unknown_edge_modes(
    keys: Iterable, argument_name: str, edge_modes: list[str]
) -> None:
    # Refuse a key of `weight_per_km` or of a dict of hub weights that is no edge
    # mode. `argument_name` names the dict in the message.
    for key in keys:
        if key not in edge_modes:
            raise ValueError(
                f"{argument_name} has the key {key!r}, which is no edge mode of "
                f"this geograph: its edge modes are {edge_modes}"
            )


def parse_weight(weight: float | None) -> float:
    """Return the weight that a caller gives to an edge, as a float. None gives
    infinity, which closes the edge. `check_weights` checks the value later."""
    return inf if weight is None else float(weight)


def check_weights(
    name: str,
    weights: array | memoryview,
    node_first_edge_ids: array | memoryview,
    edge_destination_node_ids: array | memoryview,
) -> None:
    """Raise a ValueError when a weight of a metric is below zero or not a
    number. A search needs weights of zero or more. Infinity closes an edge.

    The kernel `check_edge_weights` holds the rule
    (`scgraph/cpp/src/metric_weights.hpp`). The loader of a network file calls this
    function. `create_metric` calls it for the weights that no kernel checked:
    those of a function and of `edge_weights`.

    Args:
        name: The name of the metric, for the message.
        weights: The weight of each edge, by edge id.
        node_first_edge_ids: The id of the first edge of each node (module docstring).
        edge_destination_node_ids: The destination of each edge.

    Raises:
        ValueError: A weight is below zero or not a number. The message names the
            metric and the two nodes of the first such edge.
    """
    try:
        check_edge_weights(
            node_first_edge_ids, edge_destination_node_ids, weights
        )
    except ValueError as error:
        raise ValueError(f"{error}, in the metric {name!r}") from None


def copy_with_edge_weights(
    weights: array | memoryview,
    edge_weights: dict,
    node_first_edge_ids: array | memoryview,
    edge_destination_node_ids: array | memoryview,
) -> array:
    """Return a copy of the weights of a metric with the weights of `edge_weights`.

    Args:
        weights: The weight of each edge, by edge id.
        edge_weights: `{(origin id, destination id): weight}`. None closes an edge.
        node_first_edge_ids: The id of the first edge of each node (module docstring).
        edge_destination_node_ids: The destination of each edge.

    Raises:
        ValueError: A pair of nodes is not an edge.
    """
    weights_with_edge_weights = array("d")
    weights_with_edge_weights.frombytes(memoryview(weights).cast("B"))
    for (origin_id, destination_id), weight in edge_weights.items():
        edge_id = find_edge_id(
            node_first_edge_ids,
            edge_destination_node_ids,
            origin_id,
            destination_id,
        )
        if edge_id is None:
            raise ValueError(
                f"edge_weights names an edge from node {origin_id} to node "
                f"{destination_id}: the geograph has no such edge"
            )
        weights_with_edge_weights[edge_id] = parse_weight(weight)
    return weights_with_edge_weights


def parse_off_graph_weight_per_km(
    name: str, off_graph_weight_per_km: float | None
) -> float:
    """Return the weight of 1 km of an off-graph leg in a new metric as a float.

    Raises:
        ValueError: The weight is not a finite number of zero or more.
    """
    # The range test also refuses a value that is not a number.
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
    edge_weights=<12 edges>)`. The text gives a function by its name."""
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
