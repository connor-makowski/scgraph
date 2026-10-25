import pytest
from scgraph import GeoGraph, Graph
from helpers import assert_result

_NODES = [
    [0, 0],
    [0, 1],
    [1, 0],
    [1, 1],
    [1, 2],
    [2, 1],
]
_GRAPH = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
]
_EXPECTED = {
    "coordinate_path": [[0, 0], [0, 0], [1, 0], [0, 1], [1, 1], [2, 1], [2, 1]],
    "length": 10,
}


@pytest.fixture(scope="module")
def basic_geograph():
    return GeoGraph(nodes=_NODES, graph=_GRAPH)


def test_graph_validation(basic_geograph):
    basic_geograph.validate()


def test_node_validation(basic_geograph):
    basic_geograph.validate_nodes()


def test_shortest_path(basic_geograph):
    assert_result(
        basic_geograph.get_shortest_path(
            origin_node={"latitude": 0, "longitude": 0},
            destination_node={"latitude": 2, "longitude": 1},
        ),
        _EXPECTED,
    )


def test_custom_algorithm_on_reduced_geograph():
    # A custom algorithm must route every pair the same on the reduced graph
    def custom_dijkstra(origin_id, destination_id, graph):
        return Graph(graph).dijkstra(origin_id, destination_id)

    unreduced = GeoGraph(nodes=_NODES, graph=_GRAPH)
    reduced = GeoGraph(nodes=_NODES, graph=_GRAPH)
    reduced.reduce()
    for origin in _NODES:
        for destination in _NODES:
            if origin == destination:
                continue
            query = {
                "origin_node": {"latitude": origin[0], "longitude": origin[1]},
                "destination_node": {
                    "latitude": destination[0],
                    "longitude": destination[1],
                },
                "algorithm_fn": custom_dijkstra,
            }
            expected = unreduced.get_shortest_path(**query)
            assert reduced.get_shortest_path(**query) == expected
