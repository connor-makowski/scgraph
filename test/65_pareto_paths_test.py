"""Tests of `GeoGraph.get_pareto_paths`: every path between two points that no other
path dominates, for several metrics."""

import random
from array import array
from math import inf

import pytest

from helpers import great_circle_km, needs_the_cpp_extension

from scgraph import GeoGraph, PathNotFoundError
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


def _example_geograph(edges_closed_in_euros=()):
    """The example network, with a length of 1 km for each edge. An edge of
    `edges_closed_in_euros` gets an infinite weight in the metric `euros`."""
    graph = [{}, {}, {}, {}]
    for origin_id, destination_id in EDGES:
        graph[origin_id][destination_id] = 1.0
    geograph = GeoGraph(graph=graph, nodes=[[0, 0], [0, 1], [1, 0], [1, 1]])
    for metric_id, name in enumerate(["hours", "euros"]):
        edge_weights = {
            edge: weights[metric_id] for edge, weights in EDGES.items()
        }
        if name == "euros":
            edge_weights.update(dict.fromkeys(edges_closed_in_euros, inf))
        geograph.create_metric(name, weight_per_km=1, edge_weights=edge_weights)
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


def test_max_labels_stops_a_search_that_makes_more_labels():
    # The search of the example makes 7 labels
    geograph = _example_geograph()

    results = geograph.get_pareto_paths(
        ORIGIN, DESTINATION, ["hours", "euros"], max_labels=7
    )

    assert len(results) == 3
    with pytest.raises(MemoryError, match="max_labels=6"):
        geograph.get_pareto_paths(
            ORIGIN, DESTINATION, ["hours", "euros"], max_labels=6
        )


def test_pareto_paths_take_no_edge_that_a_metric_closes():
    # Without the edge 0 -> 3, C = 0-3 is no longer a path
    results = _example_geograph(
        edges_closed_in_euros=[(0, 3)]
    ).get_pareto_paths(
        ORIGIN, DESTINATION, ["hours", "euros"], output_path=True
    )

    assert _paths_and_totals(results) == [([0, 1, 3], 1, 10), ([0, 2, 3], 6, 6)]


def test_no_path_with_open_edges_raises_path_not_found():
    geograph = _example_geograph(edges_closed_in_euros=[(0, 3), (1, 3), (2, 3)])

    with pytest.raises(PathNotFoundError):
        geograph.get_pareto_paths(ORIGIN, DESTINATION, ["hours", "euros"])


def test_length_is_a_metric_of_the_pareto_paths():
    # Each edge is 1 km long: C = 0-3 is the shortest path and the cheapest
    results = _example_geograph().get_pareto_paths(
        ORIGIN, DESTINATION, ["length", "euros"], output_path=True
    )

    assert [
        (result["path"], result["length"], result["metric_totals"]["euros"])
        for result in results
    ] == [([0, 3], 1, 1)]


@pytest.mark.parametrize(
    "wrong_argument",
    [
        {"metrics": ["hours", "hours"]},
        {"max_paths": 0},
        {"relative_tolerance": -1},
        {"max_labels": 0},
    ],
)
def test_a_wrong_argument_raises_a_value_error_that_names_it(wrong_argument):
    arguments = {"metrics": ["hours", "euros"], **wrong_argument}
    (name,) = wrong_argument

    with pytest.raises(ValueError, match=name):
        _example_geograph().get_pareto_paths(ORIGIN, DESTINATION, **arguments)


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
    )
    # 0 sets no limit
    limits = {"max_paths": 0, "relative_tolerance": 0.0, "max_labels": 0}

    python_paths = find_pareto_paths(*arguments, **limits)
    cpp_paths = [
        (path, totals)
        for path, totals in find_pareto_paths_in_cpp(*arguments, **limits)
    ]

    assert len(python_paths) > 2
    assert cpp_paths == python_paths
