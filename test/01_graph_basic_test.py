import pytest
from scgraph import PathNotFoundError
from helpers import GRAPH_CLASSES, assert_result

_GRAPH_DATA = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
]
# The same graph with a one-way cycle that node 0 cannot reach
_DISCONNECTED_DATA = [*_GRAPH_DATA, {7: 1}, {8: 1}, {6: 1}]
_EXPECTED = {"path": [0, 2, 1, 3, 5], "length": 10}


# Every algorithm finds the shortest path from 0 to 5, which is found by hand,
# also when the graph has a component that the origin cannot reach.
@pytest.mark.parametrize(
    "algorithm",
    [
        "dijkstra",
        "bidirectional_dijkstra",
        "dijkstra_buckets",
        "bellman_ford",
        "a_star",
        "bmssp",
        "contraction_hierarchy",
        "tnr",
    ],
)
@pytest.mark.parametrize(
    "graph_data", [_GRAPH_DATA, _DISCONNECTED_DATA], ids=["connected", "apart"]
)
@pytest.mark.parametrize(
    "GraphClass", GRAPH_CLASSES, ids=lambda cls: cls.__module__.split(".")[-1]
)
def test_shortest_path_whatever_the_algorithm(
    GraphClass, graph_data, algorithm
):
    graph = GraphClass(graph_data)
    assert_result(
        getattr(graph, algorithm)(origin_id=0, destination_id=5), _EXPECTED
    )


# The path read in the shortest path tree of the origin is the shortest path.
@pytest.mark.parametrize(
    "graph_data", [_GRAPH_DATA, _DISCONNECTED_DATA], ids=["connected", "apart"]
)
@pytest.mark.parametrize(
    "GraphClass", GRAPH_CLASSES, ids=lambda cls: cls.__module__.split(".")[-1]
)
def test_shortest_path_from_the_tree_of_the_origin(GraphClass, graph_data):
    graph = GraphClass(graph_data)
    assert_result(
        graph.get_tree_path(
            origin_id=0,
            destination_id=5,
            tree_data=graph.get_shortest_path_tree(origin_id=0),
        ),
        _EXPECTED,
    )


# An edge to a node id outside the graph raises instead of being indexed out
# of bounds, also without validation.
@pytest.mark.parametrize(
    "GraphClass", GRAPH_CLASSES, ids=lambda cls: cls.__module__.split(".")[-1]
)
def test_edge_to_missing_node_raises(GraphClass):
    with pytest.raises(IndexError):
        GraphClass([{5: 1}]).reduce(1)


# A query between two nodes that no path joins raises PathNotFoundError.
@pytest.mark.parametrize(
    "GraphClass", GRAPH_CLASSES, ids=lambda cls: cls.__module__.split(".")[-1]
)
def test_no_path_raises(GraphClass):
    graph = GraphClass([{1: 1.0}, {0: 1.0}, {3: 1.0}, {2: 1.0}])
    with pytest.raises(PathNotFoundError):
        graph.dijkstra(0, 3)
