"""
Pure-Python version of the C++ kernel `find_pareto_paths`: every Pareto path between
two sets of nodes, for several metrics. This module is internal.
`scgraph/cpp/src/pareto_paths.hpp` explains the algorithm, its data and its steps,
with an example. Read it first.

Both versions take the labels from the queue in the same order, visit the edges of a
node in the same order and add the weights in the same order. So they return the same
paths, in the same order, with the same totals, bit for bit.

This version differs in one way: a label holds its keys and its totals in its entry of
the queue, not in an array of labels, because a Python tuple is already one object.
"""

from array import array
from heapq import heapify, heappop, heappush
from itertools import accumulate, repeat
from math import inf
from operator import le

from scgraph.array_checks import is_sorted_from_zero


def find_pareto_paths(
    node_first_edge_ids: array | memoryview,
    edge_destination_node_ids: array | memoryview,
    weights_of_metrics: list[array | memoryview],
    origin_node_ids: list[int],
    destination_node_ids: list[int],
    *,
    max_paths: int,
    relative_tolerance: float,
    max_labels: int,
) -> list[tuple[list[int], list[float]]]:
    """
    Return every Pareto path from a node of `origin_node_ids` to a node of
    `destination_node_ids`: every path that no other path dominates. A path
    dominates another when its total is not above the other's in any metric and
    its totals differ. Of several paths with the same totals, one is returned.

    Args:
        node_first_edge_ids: The edges of the node u have the ids
            node_first_edge_ids[u] to node_first_edge_ids[u + 1] - 1 (int32).
        edge_destination_node_ids: The node that each edge goes to (int32).
        weights_of_metrics: For each metric, two at least, the weight of each
            edge by edge id (float64, zero or more: the caller checks it).
            Infinity closes an edge.
        origin_node_ids: The nodes where a path may start.
        destination_node_ids: The nodes where a path may end.
        max_paths: The largest count of paths to return, 0 for no limit. The
            search then stops at the paths with the smallest totals.
        relative_tolerance: A path is not returned when a returned path has, in
            every metric, a total at most `1 + relative_tolerance` times its own.
        max_labels: The largest count of labels that the search makes, 0 for no
            limit. A label is a path from an origin node to one node.

    Returns:
        One pair (node ids of the path, total of each metric) for each Pareto
        path, sorted by the total of the first metric, then of the next ones.

    The caller checks `max_paths`, `relative_tolerance` and `max_labels`.

    Raises:
        ValueError: There are fewer than two metrics, an array has a wrong
            length or a wrong value, or a node id is not a node.
        MemoryError: The search made more than `max_labels` labels.
    """
    node_count = len(node_first_edge_ids) - 1
    edge_count = len(edge_destination_node_ids)
    _check_arguments(
        node_first_edge_ids,
        edge_destination_node_ids,
        weights_of_metrics,
        [*origin_node_ids, *destination_node_ids],
    )
    label_limit = max_labels or inf
    # 1. The lower bound of each node in each metric
    edge_origin_node_ids = array("i")
    for node_id in range(node_count):
        edge_origin_node_ids.extend(
            repeat(
                node_id,
                node_first_edge_ids[node_id + 1] - node_first_edge_ids[node_id],
            )
        )
    # The edges sorted by the node that they go to, then by edge id
    reverse_edge_ids = array(
        "i",
        sorted(range(edge_count), key=edge_destination_node_ids.__getitem__),
    )
    reverse_edge_counts = [0] * (node_count + 1)
    for node_id in edge_destination_node_ids:
        reverse_edge_counts[node_id + 1] += 1
    reverse_first_edge_ids = list(accumulate(reverse_edge_counts))
    lower_bounds_of_metrics = [
        _find_lower_bounds(
            destination_node_ids,
            weights,
            reverse_first_edge_ids,
            reverse_edge_ids,
            edge_origin_node_ids,
        )
        for weights in weights_of_metrics
    ]

    # 2. One label at each origin node, with zero totals
    label_node_ids, label_predecessor_ids = array("i"), array("i")
    zero_totals = (0.0,) * len(weights_of_metrics)
    queue = []
    for node_id in origin_node_ids:
        key = tuple(
            lower_bounds[node_id] for lower_bounds in lower_bounds_of_metrics
        )
        if inf not in key:
            queue.append((key, len(label_node_ids), zero_totals))
            label_node_ids.append(node_id)
            label_predecessor_ids.append(-1)
            if len(label_node_ids) > label_limit:
                raise MemoryError(_get_label_limit_message(max_labels))
    heapify(queue)

    # 3. to 5. Take the smallest key, make the label permanent, extend it
    is_destination = bytearray(node_count)
    for node_id in destination_node_ids:
        is_destination[node_id] = 1
    tolerance_factor = 1.0 + relative_tolerance
    # The last totals of the permanent labels of each node, by node id
    permanent_totals = {}
    found_label_ids, found_totals, paths = [], [], []
    while queue:
        key, label_id, totals = heappop(queue)
        node_id = label_node_ids[label_id]
        node_totals = permanent_totals.get(node_id)
        if node_totals and _is_dominated(node_totals, totals[1:], 1.0):
            continue
        if found_totals and _is_dominated(
            found_totals, key[1:], tolerance_factor
        ):
            continue
        permanent_totals.setdefault(node_id, []).append(totals[1:])
        if is_destination[node_id]:
            found_label_ids.append(label_id)
            found_totals.append(totals[1:])
            paths.append(([], list(totals)))
            if len(paths) == max_paths:
                break
            continue
        for edge_id in range(
            node_first_edge_ids[node_id], node_first_edge_ids[node_id + 1]
        ):
            next_node_id = edge_destination_node_ids[edge_id]
            next_totals = tuple(
                [
                    total + weights[edge_id]
                    for total, weights in zip(totals, weights_of_metrics)
                ]
            )
            next_key = tuple(
                [
                    total + lower_bounds[next_node_id]
                    for total, lower_bounds in zip(
                        next_totals, lower_bounds_of_metrics
                    )
                ]
            )
            # A closed edge, or a node from which no path reaches a destination
            if inf in next_key:
                continue
            next_node_totals = permanent_totals.get(next_node_id)
            if next_node_totals and _is_dominated(
                next_node_totals, next_totals[1:], 1.0
            ):
                continue
            if found_totals and _is_dominated(
                found_totals, next_key[1:], tolerance_factor
            ):
                continue
            heappush(queue, (next_key, len(label_node_ids), next_totals))
            label_node_ids.append(next_node_id)
            label_predecessor_ids.append(label_id)
            if len(label_node_ids) > label_limit:
                raise MemoryError(_get_label_limit_message(max_labels))

    # 6. The node ids of each path, from its predecessor labels
    for label_id, (path, _) in zip(found_label_ids, paths):
        while label_id != -1:
            path.append(label_node_ids[label_id])
            label_id = label_predecessor_ids[label_id]
        path.reverse()
    return paths


def _is_dominated(
    kept_totals: list[tuple], totals_after_first: tuple, tolerance_factor: float
) -> bool:
    # Whether a point of `kept_totals` is not above `totals_after_first` times
    # `tolerance_factor` in any metric after the first. The points came in the
    # order of their first total, so the first metric needs no test. With two
    # metrics, the second totals of the points decrease, so the last point
    # decides.
    if len(totals_after_first) == 1:
        return kept_totals[-1][0] <= totals_after_first[0] * tolerance_factor
    limits = [total * tolerance_factor for total in totals_after_first]
    return any(all(map(le, point, limits)) for point in kept_totals)


def _find_lower_bounds(
    destination_node_ids: list[int],
    weights: array | memoryview,
    reverse_first_edge_ids: list[int],
    reverse_edge_ids: array,
    edge_origin_node_ids: array,
) -> list[float]:
    # Dijkstra's algorithm on the reversed edges, from every destination node at 0:
    # the smallest total from each node to a destination, or infinity
    lower_bounds = [inf] * (len(reverse_first_edge_ids) - 1)
    queue = []
    for node_id in destination_node_ids:
        lower_bounds[node_id] = 0.0
        queue.append((0.0, node_id))
    heapify(queue)
    while queue:
        lower_bound, node_id = heappop(queue)
        if lower_bound > lower_bounds[node_id]:
            continue
        for reverse_id in range(
            reverse_first_edge_ids[node_id], reverse_first_edge_ids[node_id + 1]
        ):
            edge_id = reverse_edge_ids[reverse_id]
            origin_id = edge_origin_node_ids[edge_id]
            next_lower_bound = lower_bound + weights[edge_id]
            if next_lower_bound < lower_bounds[origin_id]:
                lower_bounds[origin_id] = next_lower_bound
                heappush(queue, (next_lower_bound, origin_id))
    return lower_bounds


def _check_arguments(
    node_first_edge_ids: array | memoryview,
    edge_destination_node_ids: array | memoryview,
    weights_of_metrics: list[array | memoryview],
    node_ids: list[int],
) -> None:
    # The checks of the C++ kernel, with the same messages. The arrays may come
    # from a mapped file that nothing has checked.
    node_count = len(node_first_edge_ids) - 1
    edge_count = len(edge_destination_node_ids)
    if len(weights_of_metrics) < 2 or any(
        len(weights) != edge_count for weights in weights_of_metrics
    ):
        raise ValueError(
            "expected two metrics at least, and one weight per edge"
        )
    if (
        node_count < 0
        or not is_sorted_from_zero(node_first_edge_ids)
        or node_first_edge_ids[-1] != edge_count
    ):
        raise ValueError("invalid node_first_edge_ids")
    if edge_count and not (
        0 <= min(edge_destination_node_ids)
        and max(edge_destination_node_ids) < node_count
    ):
        raise ValueError("edge to a missing node")
    if not all(0 <= node_id < node_count for node_id in node_ids):
        raise ValueError("an origin or a destination id is not a node")


def _get_label_limit_message(max_labels: int) -> str:
    # The message of the C++ kernel
    return f"the search made more than max_labels={max_labels} labels"
