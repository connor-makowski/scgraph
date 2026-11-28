"""Tests of `GeoGraph.get_pareto_paths`: every path between two points that no other
path dominates, for several metrics."""

import random
from array import array

import pytest

from helpers import great_circle_km, needs_the_cpp_extension

from scgraph import GeoGraph
from scgraph.helpers.pareto_paths import find_pareto_paths

# The network of the example of scgraph/cpp/src/pareto_paths.hpp: four nodes, and
# each edge with its (hours, euros). From node 0 to node 3, the paths are
# A = 0-1-3 (1, 10), B = 0-2-3 (6, 6), C = 0-3 (10, 1) and D = 0-1-2-3 (5.5, 10).
# A dominates D. No weighted sum of hours and euros finds B: for any coefficient,
# A or C has a smaller score.
EDGES = {
    (0, 1): (0.5, 5),
    (0, 2): (3, 3),
    (0, 3): (10, 1),
    (1, 2): (2, 2),
    (1, 3): (0.5, 5),
    (2, 3): (3, 3),
}
ORIGIN = {"latitude": 0, "longitude": 0}  # the point of node 0
DESTINATION = {"latitude": 1, "longitude": 1}  # the point of node 3


def _example_geograph():
    graph = [{}, {}, {}, {}]
    for origin_id, destination_id in EDGES:
        graph[origin_id][destination_id] = 1.0
    geograph = GeoGraph(graph=graph, nodes=[[0, 0], [0, 1], [1, 0], [1, 1]])
    for metric_id, name in enumerate(["hours", "euros"]):
        geograph.create_metric(
            name,
            weight_per_km=1,
            edge_weights={
                edge: weights[metric_id] for edge, weights in EDGES.items()
            },
        )
    return geograph


def _paths_and_totals(results):
    return [
        (
            result["path"],
            result["metric_totals"]["hours"],
            result["metric_totals"]["euros"],
        )
        for result in results
    ]


def test_pareto_paths_include_the_path_that_no_weighted_sum_finds():
    results = _example_geograph().get_pareto_paths(
        ORIGIN, DESTINATION, ["hours", "euros"], output_path=True
    )

    assert _paths_and_totals(results) == [
        ([0, 1, 3], 1, 10),
        ([0, 2, 3], 6, 6),
        ([0, 3], 10, 1),
    ]


def test_max_paths_keeps_the_paths_with_the_smallest_first_total():
    results = _example_geograph().get_pareto_paths(
        ORIGIN, DESTINATION, ["hours", "euros"], max_paths=2, output_path=True
    )

    assert _paths_and_totals(results) == [([0, 1, 3], 1, 10), ([0, 2, 3], 6, 6)]


def test_relative_tolerance_drops_a_path_close_to_a_returned_path():
    # A (1, 10) is at most twice B (6, 6) in hours and in euros
    results = _example_geograph().get_pareto_paths(
        ORIGIN,
        DESTINATION,
        ["hours", "euros"],
        relative_tolerance=1,
        output_path=True,
    )

    assert _paths_and_totals(results) == [([0, 1, 3], 1, 10), ([0, 3], 10, 1)]


def test_max_labels_stops_the_search_with_a_memory_error():
    # The search of the example makes 7 labels
    with pytest.raises(MemoryError, match="max_labels=3"):
        _example_geograph().get_pareto_paths(
            ORIGIN, DESTINATION, ["hours", "euros"], max_labels=3
        )


@needs_the_cpp_extension
def test_both_builds_return_the_same_pareto_paths(us_freeway):
    from scgraph.cpp import find_pareto_paths as find_pareto_paths_in_cpp

    # Three metrics: the km, and two metrics of km times a random factor per edge
    node_first_edge_ids, edge_destination_node_ids, lengths = (
        us_freeway._read_edge_arrays()
    )
    generator = random.Random(1)
    weights_of_metrics = [lengths] + [
        array("d", (km * generator.uniform(0.5, 1.5) for km in lengths))
        for _ in range(2)
    ]
    nodes = us_freeway.nodes
    seattle, miami = [
        min(
            range(len(nodes)),
            key=lambda node_id: great_circle_km(nodes[node_id], point),
        )
        for point in ([47.6, -122.33], [25.76, -80.19])
    ]
    arguments = (
        node_first_edge_ids,
        edge_destination_node_ids,
        weights_of_metrics,
        [seattle],
        [miami],
        0,
        0.0,
        0,
    )

    python_paths = find_pareto_paths(*arguments)
    cpp_paths = [
        (path, totals) for path, totals in find_pareto_paths_in_cpp(*arguments)
    ]

    assert len(python_paths) > 2
    assert cpp_paths == python_paths
