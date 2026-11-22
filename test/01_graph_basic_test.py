import math

import pytest
from scgraph import Graph, PathNotFoundError
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


def test_bidirectional_dijkstra(graph):
    assert_result(
        graph.bidirectional_dijkstra(origin_id=0, destination_id=5), _EXPECTED
    )


def test_bellman_ford(graph):
    assert_result(graph.bellman_ford(origin_id=0, destination_id=5), _EXPECTED)


def test_a_star(graph):
    assert_result(
        graph.a_star(
            origin_id=0, destination_id=5, heuristic_fn=lambda x, y: 0
        ),
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
    assert_result(
        graph.dijkstra_buckets(origin_id=0, destination_id=5), _EXPECTED
    )


def test_disconnected_connection_raises(disconnected_graph):
    with pytest.raises(RuntimeError, match="not fully connected"):
        disconnected_graph.validate(check_connected=True, check_symmetry=False)


def test_disconnected_symmetry_raises(disconnected_graph):
    with pytest.raises(ValueError, match="not symmetric"):
        disconnected_graph.validate(check_connected=False, check_symmetry=True)


def test_disconnected_dijkstra(disconnected_graph):
    assert_result(
        disconnected_graph.dijkstra(origin_id=0, destination_id=5), _EXPECTED
    )


def test_disconnected_bellman_ford(disconnected_graph):
    assert_result(
        disconnected_graph.bellman_ford(origin_id=0, destination_id=5),
        _EXPECTED,
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
        disconnected_graph.dijkstra_buckets(origin_id=0, destination_id=5),
        _EXPECTED,
    )


def test_empty_graph_validation_raises(graph_class):
    with pytest.raises(ValueError):
        graph_class([]).validate(check_symmetry=True, check_connected=True)


def test_link_to_a_missing_node_raises_at_construction_or_at_validation(
    graph_class,
):
    # The only node of this graph has a link to node 5, which does not exist.
    # The C++ class raises when the graph is built. The Python class raises
    # when the graph is validated.
    graph_with_a_link_to_a_missing_node = [{5: 1}]

    with pytest.raises(ValueError):
        graph_class(graph_with_a_link_to_a_missing_node).validate()


@pytest.mark.parametrize(
    "algorithm",
    [
        "dijkstra",
        "bidirectional_dijkstra",
        "dijkstra_buckets",
        "bidirectional_buckets",
        "dijkstra_negative",
        "a_star",
        "bellman_ford",
        "bmssp",
        "cached_shortest_path",
    ],
)
def test_a_search_raises_path_not_found_between_two_parts_of_a_graph(
    graph_class, algorithm
):
    # Nodes 0 and 1 are linked, and nodes 2 and 3 are linked. No link joins
    # the two pairs.
    graph_in_two_parts = graph_class([{1: 1.0}, {0: 1.0}, {3: 1.0}, {2: 1.0}])
    search = getattr(graph_in_two_parts, algorithm)

    with pytest.raises(PathNotFoundError):
        search(origin_id=0, destination_id=3)


# Every search of a graph, by the name of its method.
_SEARCHES = [
    "dijkstra",
    "bidirectional_dijkstra",
    "dijkstra_buckets",
    "bidirectional_buckets",
    "dijkstra_negative",
    "a_star",
    "bellman_ford",
    "bmssp",
    "cached_shortest_path",
    "contraction_hierarchy",
    "tnr",
]


@pytest.mark.parametrize("algorithm", _SEARCHES)
def test_a_search_never_takes_an_edge_whose_weight_is_infinite(
    graph_class, algorithm
):
    # The two edges between nodes 0 and 3 have an infinite weight. The detour
    # 0 -> 1 -> 2 -> 3 costs 1 + 2 + 3 = 6.
    graph_with_a_closed_shortcut = graph_class(
        [
            {1: 1.0, 3: math.inf},
            {0: 1.0, 2: 2.0},
            {1: 2.0, 3: 3.0},
            {2: 3.0, 0: math.inf},
        ]
    )
    search = getattr(graph_with_a_closed_shortcut, algorithm)

    found = search(origin_id=0, destination_id=3)

    assert_result(found, {"path": [0, 1, 2, 3], "length": 6})


@pytest.mark.parametrize("algorithm", _SEARCHES)
def test_a_search_raises_path_not_found_when_every_route_takes_an_infinite_edge(
    graph_class, algorithm
):
    # Node 1 is the only neighbour of node 2, and the two edges between them
    # have an infinite weight.
    graph_with_a_closed_dead_end = graph_class(
        [{1: 1.0}, {0: 1.0, 2: math.inf}, {1: math.inf}]
    )
    search = getattr(graph_with_a_closed_dead_end, algorithm)

    with pytest.raises(PathNotFoundError):
        search(origin_id=0, destination_id=2)


def test_get_path_weight_raises_for_a_path_that_uses_a_missing_link(
    graph_class,
):
    # The graph has the links 0 -> 1 and 1 -> 2, and no link 0 -> 2.
    graph = graph_class([{1: 1.0}, {2: 1.0}, {}])

    with pytest.raises(ValueError, match="No edge from node 0 to node 2"):
        graph.get_path_weight([0, 2])


def test_bmssp_takes_the_option_of_the_constant_degree_graph(graph_class):
    graph = graph_class(_GRAPH_DATA)

    found = graph.bmssp(
        origin_id=0, destination_id=5, use_constant_degree_graph=False
    )

    assert found["length"] == 10
