"""
Pure-Python version of the two C++ kernels that compute the weight of each edge in a
metric: `compute_weights_from_km` and `compute_weighted_sum`. This module is internal.
`scgraph/cpp/src/metric_weights.hpp` explains the kernels, their parameters and their
steps. Read it first.

Both versions make the same operations on each weight, in the same order. So they
return the same weights, bit for bit.

This version differs in one way: a pass over all the edges runs in C (`map`,
`compress`, `translate`), not in a Python loop. Step 1 multiplies every edge, then
writes infinity on the edges of a closed class. Steps 2 and 3 visit only the edges
that leave or enter a hub. Step 4 checks the weights at the end.
"""

from array import array
from bisect import bisect_right
from itertools import compress, count, repeat
from math import inf
from operator import add, mul


def compute_weights_from_km(
    node_first_edge_ids: array | memoryview,
    edge_destination_node_ids: array | memoryview,
    lengths_km: array | memoryview,
    edge_class_ids: array | memoryview,
    node_mode_ids: array | memoryview,
    class_weights_per_km: array | memoryview,
    hub_weights: array | memoryview,
) -> array:
    """
    Return the float64 weight of each edge, in the order of the edge ids: the weight
    per km of its class times its km, plus the weight of each hub that it leaves or
    enters. A closed edge has the weight infinity.

    Raises:
        ValueError: The lengths of the arrays do not agree, or a weight is below zero
            or not a number.
    """
    node_count, edge_count = len(node_first_edge_ids) - 1, len(
        edge_destination_node_ids
    )
    class_count = len(class_weights_per_km)
    if (
        node_count < 0
        or len(node_mode_ids) != node_count
        or len(lengths_km) != edge_count
        or len(edge_class_ids) != edge_count
    ):
        raise ValueError(
            "expected one node mode per node, and one length and one class per edge"
        )
    if class_count == 0 or len(hub_weights) % class_count != 0:
        raise ValueError("expected one hub weight per node mode and per class")
    if max(node_mode_ids, default=-1) >= len(hub_weights) // class_count:
        raise ValueError(
            "an edge has a class without a weight per km, or a node has a node mode without hub weights"
        )
    try:
        # 1. The weight per km of the class times the km, or infinity for a closed class
        # A list holds the weights per km as Python floats: an array would make a new
        # float at each read
        weights_per_km = map(
            list(class_weights_per_km).__getitem__, edge_class_ids
        )
        weights = array("d", map(mul, lengths_km, weights_per_km))
        is_closed = bytes(
            weight_per_km == inf for weight_per_km in class_weights_per_km
        )
        if 1 in is_closed:
            closed_edges = bytes(edge_class_ids).translate(
                is_closed.ljust(256, b"\0")
            )
            for edge_id in compress(count(), closed_edges):
                weights[edge_id] = inf

        # For each node, 1 if a class has a weight at a hub of the node mode of the
        # node, else 0. `translate` maps the node mode of each node in C.
        is_hub_mode = bytes(
            any(hub_weights[first : first + class_count])
            for first in range(0, len(hub_weights), class_count)
        )
        is_hub = bytes(node_mode_ids).translate(is_hub_mode.ljust(256, b"\0"))
        if 1 in is_hub:
            # 2. The weight of the hub that the edge leaves
            for origin_id in compress(count(), is_hub):
                hub_weights_start = node_mode_ids[origin_id] * class_count
                for edge_id in range(
                    node_first_edge_ids[origin_id],
                    node_first_edge_ids[origin_id + 1],
                ):
                    weight = hub_weights[
                        hub_weights_start + edge_class_ids[edge_id]
                    ]
                    if weight != 0.0:
                        weights[edge_id] += weight
            # 3. The weight of the hub that the edge enters
            for edge_id in compress(
                count(), map(is_hub.__getitem__, edge_destination_node_ids)
            ):
                hub_weights_start = (
                    node_mode_ids[edge_destination_node_ids[edge_id]]
                    * class_count
                )
                weight = hub_weights[
                    hub_weights_start + edge_class_ids[edge_id]
                ]
                if weight != 0.0:
                    weights[edge_id] += weight
    except IndexError:
        raise ValueError(
            "an edge has a class without a weight per km, or a node has a node mode without hub weights"
        ) from None

    # 4. `0.0 <= weight` is false for a weight that is not a number.
    if not all(map((0.0).__le__, weights)):
        edge_id = next(
            i for i, weight in enumerate(weights) if not weight >= 0.0
        )
        origin_id = bisect_right(node_first_edge_ids, edge_id) - 1
        raise ValueError(
            f"The weight of the edge from node {origin_id} to node "
            f"{edge_destination_node_ids[edge_id]} is below zero or not a number"
        )
    return weights


def compute_weighted_sum(
    weights_of_metrics: list[array | memoryview],
    coefficients: array | memoryview,
) -> array:
    """
    Return the float64 weight of each edge in a weighted sum of metrics: the sum of
    its weight in each metric times the coefficient of the metric. An edge that is
    closed in one of the metrics has the weight infinity.

    Raises:
        ValueError: The lengths of the arrays do not agree.
    """
    if not weights_of_metrics or len(coefficients) != len(weights_of_metrics):
        raise ValueError(
            "expected one coefficient per metric, and one metric at least"
        )
    edge_count = len(weights_of_metrics[0])
    if any(len(weights) != edge_count for weights in weights_of_metrics):
        raise ValueError("expected one weight per edge in each metric")
    terms = (
        map(mul, repeat(coefficient), weights)
        for coefficient, weights in zip(coefficients, weights_of_metrics)
    )
    sums = array("d", next(terms))
    for term in terms:
        sums = array("d", map(add, sums, term))
    return sums
