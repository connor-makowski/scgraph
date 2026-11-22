"""
Pure-Python version of the C++ kernels `compute_weights_from_rates` and
`compute_weighted_sum`, with the same result, bit for bit. The kernels are described
in `scgraph/cpp/src/metric_weights.hpp`. Read it first.

Same as in C++: the steps, the order of the operations on each weight, and the
messages of the errors.

Different: a pass over all the edges runs in C (`map`, `compress`, `translate`), not
in a Python loop. Step 1 multiplies every edge, then writes infinity on the edges of
a closed class. Steps 2 and 3 visit only the edges that leave or enter a hub. Step 4
checks the weights at the end.
"""

from array import array
from bisect import bisect_right
from itertools import compress, count, repeat
from math import inf
from operator import add, mul


def compute_weights_from_rates(
    offsets: array | memoryview,
    heads: array | memoryview,
    lengths: array | memoryview,
    edge_classes: array | memoryview,
    node_modes: array | memoryview,
    class_rates_per_km: array | memoryview,
    hub_weights: array | memoryview,
) -> array:
    """
    Compute the weight of each edge from a rate for each class and from the weight
    that it pays at a hub.

    Args:
        offsets: The edges of node u are at the positions offsets[u] to
            offsets[u + 1] - 1 (int32).
        heads: The node that each edge goes to (int32).
        lengths: The km of each edge (float64).
        edge_classes: The class of each edge, as a row of the classes (uint8).
        node_modes: The mode of each node, as a row of the modes (uint8).
        class_rates_per_km: The weight of 1 km of an edge of each class (float64).
            Infinity closes the class.
        hub_weights: The weight that an edge of the class c pays when it leaves a
            node of the mode m, and when it goes to a node of the mode m, at the
            position m * number of classes + c (float64).

    Returns:
        One float64 weight for each edge, of zero or more. Infinity for a closed
        edge.

    Raises:
        ValueError: The arrays do not fit together, or a weight is below zero or
            not a number.
    """
    node_count, edge_count = len(offsets) - 1, len(heads)
    class_count = len(class_rates_per_km)
    if (
        node_count < 0
        or len(node_modes) != node_count
        or len(lengths) != edge_count
        or len(edge_classes) != edge_count
    ):
        raise ValueError(
            "expected one mode per node, and one length and one class per edge"
        )
    if class_count == 0 or len(hub_weights) % class_count != 0:
        raise ValueError("expected one hub weight per mode and per class")
    if max(node_modes, default=-1) >= len(hub_weights) // class_count:
        raise ValueError(
            "an edge has a class without a rate, or a node has a mode without hub weights"
        )
    try:
        # 1. The rate of the class times the km, or infinity for a closed class
        # A list holds the rates as Python floats: an array would make a new float
        # at each read
        rates = map(list(class_rates_per_km).__getitem__, edge_classes)
        weights = array("d", map(mul, lengths, rates))
        is_closed = bytes(rate == inf for rate in class_rates_per_km)
        if 1 in is_closed:
            closed_edges = bytes(edge_classes).translate(
                is_closed.ljust(256, b"\0")
            )
            for edge_index in compress(count(), closed_edges):
                weights[edge_index] = inf

        # For each node, 1 if a class has a weight at a hub of the mode of the
        # node, else 0. `translate` maps the mode of each node in C.
        is_hub_mode = bytes(
            any(hub_weights[first : first + class_count])
            for first in range(0, len(hub_weights), class_count)
        )
        is_hub = bytes(node_modes).translate(is_hub_mode.ljust(256, b"\0"))
        if 1 in is_hub:
            # 2. The weight of the hub that the edge leaves
            for origin_id in compress(count(), is_hub):
                row = node_modes[origin_id] * class_count
                for edge_index in range(
                    offsets[origin_id], offsets[origin_id + 1]
                ):
                    weight = hub_weights[row + edge_classes[edge_index]]
                    if weight != 0.0:
                        weights[edge_index] += weight
            # 3. The weight of the hub that the edge enters
            for edge_index in compress(count(), map(is_hub.__getitem__, heads)):
                row = node_modes[heads[edge_index]] * class_count
                weight = hub_weights[row + edge_classes[edge_index]]
                if weight != 0.0:
                    weights[edge_index] += weight
    except IndexError:
        raise ValueError(
            "an edge has a class without a rate, or a node has a mode without hub weights"
        ) from None

    # 4. A comparison with a value that is not a number is false
    if not all(map((0.0).__le__, weights)):
        edge_index = next(
            i for i, weight in enumerate(weights) if not weight >= 0.0
        )
        origin_id = bisect_right(offsets, edge_index) - 1
        raise ValueError(
            f"The weight of the edge from node {origin_id} to node "
            f"{heads[edge_index]} is below zero or not a number"
        )
    return weights


def compute_weighted_sum(
    weights_of_metrics: list[array | memoryview],
    coefficients: array | memoryview,
) -> array:
    """
    Compute the weight of each edge as the sum of its weight in each metric times
    the coefficient of the metric.

    Args:
        weights_of_metrics: The weights of each metric, one float64 value for each
            edge.
        coefficients: The coefficient of each metric, a finite number above zero
            (float64).

    Returns:
        One float64 weight for each edge. Infinity for an edge that is closed in
        one of the metrics.

    Raises:
        ValueError: The arrays do not fit together.
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
