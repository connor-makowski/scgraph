import pytest
from scgraph import Graph
from helpers import assert_result

_GRAPH_DATA = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
]
_DISCONNECTED_DATA = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
    {7: 1},
    {8: 1},
    {6: 1},
]
_EXPECTED = {"path": [0, 2, 1, 3, 5], "length": 10}


@pytest.fixture(scope="module")
def graph():
    return Graph(_GRAPH_DATA)


@pytest.fixture(scope="module")
def disconnected_graph():
    return Graph(_DISCONNECTED_DATA)


def test_validation(graph):
    graph.validate()


def test_dijkstra(graph):
    assert_result(graph.dijkstra(origin_id=0, destination_id=5), _EXPECTED)


def test_bellman_ford(graph):
    assert_result(graph.bellman_ford(origin_id=0, destination_id=5), _EXPECTED)


def test_a_star(graph):
    assert_result(
        graph.a_star(origin_id=0, destination_id=5, heuristic_fn=lambda x, y: 0),
        _EXPECTED,
    )


def test_bmssp(graph):
    assert_result(graph.bmssp(0, 5), _EXPECTED)


def test_shortest_path_tree(graph):
    assert_result(
        graph.get_tree_path(
            origin_id=0,
            destination_id=5,
            tree_data=graph.get_shortest_path_tree(origin_id=0),
        ),
        _EXPECTED,
    )


def test_contraction_hierarchy(graph):
    assert_result(
        graph.contraction_hierarchy(origin_id=0, destination_id=5), _EXPECTED
    )


def test_tnr(graph):
    assert_result(graph.tnr(origin_id=0, destination_id=5), _EXPECTED)


def test_dijkstra_buckets(graph):
    assert_result(graph.dijkstra_buckets(origin_id=0, destination_id=5), _EXPECTED)


def test_disconnected_connection_raises(disconnected_graph):
    with pytest.raises(Exception):
        disconnected_graph.validate(check_connected=True, check_symmetry=False)


def test_disconnected_symmetry_raises(disconnected_graph):
    with pytest.raises(Exception):
        disconnected_graph.validate(check_connected=False, check_symmetry=True)


def test_disconnected_dijkstra(disconnected_graph):
    assert_result(
        disconnected_graph.dijkstra(origin_id=0, destination_id=5), _EXPECTED
    )


def test_disconnected_bellman_ford(disconnected_graph):
    assert_result(
        disconnected_graph.bellman_ford(origin_id=0, destination_id=5), _EXPECTED
    )


def test_disconnected_a_star(disconnected_graph):
    assert_result(
        disconnected_graph.a_star(
            origin_id=0, destination_id=5, heuristic_fn=lambda x, y: 0
        ),
        _EXPECTED,
    )


def test_disconnected_bmssp(disconnected_graph):
    assert_result(disconnected_graph.bmssp(0, 5), _EXPECTED)


def test_disconnected_shortest_path_tree(disconnected_graph):
    assert_result(
        disconnected_graph.get_tree_path(
            origin_id=0,
            destination_id=5,
            tree_data=disconnected_graph.get_shortest_path_tree(origin_id=0),
        ),
        _EXPECTED,
    )


def test_disconnected_contraction_hierarchy(disconnected_graph):
    assert_result(
        disconnected_graph.contraction_hierarchy(origin_id=0, destination_id=5),
        _EXPECTED,
    )


def test_disconnected_tnr(disconnected_graph):
    assert_result(
        disconnected_graph.tnr(origin_id=0, destination_id=5), _EXPECTED
    )


def test_disconnected_dijkstra_buckets(disconnected_graph):
    assert_result(
        disconnected_graph.dijkstra_buckets(origin_id=0, destination_id=5), _EXPECTED
    )


def test_empty_graph_validation_raises():
    with pytest.raises(Exception):
        Graph([]).validate(check_symmetry=True, check_connected=True)
