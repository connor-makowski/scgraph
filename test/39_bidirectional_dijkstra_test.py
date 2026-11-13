from copy import deepcopy
import pytest
from scgraph import PathNotFoundError
from scgraph.graph import Graph as PyGraph
from helpers import assert_result

try:
    from scgraph.cpp import Graph as CppGraph

    HAS_CPP = True
except ImportError:
    HAS_CPP = False

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


def _run_basic_bidirectional_tests(graph_cls):
    g = graph_cls(_GRAPH_DATA)

    # Basic test
    res = g.bidirectional_dijkstra(origin_id=0, destination_id=5)
    assert_result(res, _EXPECTED)

    # Origin == Destination
    res_same = g.bidirectional_dijkstra(origin_id=3, destination_id=3)
    assert res_same["length"] == 0
    assert res_same["path"] == [3]

    # Multi-origin
    res_multi = g.bidirectional_dijkstra(origin_id={0, 4}, destination_id=5)
    assert res_multi["length"] == 9  # 4 -> 3 (3) + 3 -> 5 (6) = 9
    assert res_multi["path"] == [4, 3, 5]

    # All-pairs equivalence with standard Dijkstra
    for u in range(len(_GRAPH_DATA)):
        for v in range(len(_GRAPH_DATA)):
            d_res = g.dijkstra(u, v)
            bi_res = g.bidirectional_dijkstra(u, v)
            assert abs(d_res["length"] - bi_res["length"]) < 1e-6
            # Path weight verification
            assert (
                abs(g.get_path_weight(bi_res["path"]) - d_res["length"]) < 1e-6
            )


def _run_disconnected_tests(graph_cls):
    g = graph_cls(_DISCONNECTED_DATA)
    with pytest.raises(PathNotFoundError):
        g.bidirectional_dijkstra(origin_id=0, destination_id=7)


def _run_directed_asymmetric_tests(graph_cls):
    # Directed graph with asymmetric weights
    # 0 -> 1 (1) -> 2 (2) -> 3 (3)
    # 0 -> 2 (10)
    # 3 -> 0 (100)
    data = [
        {1: 1.0, 2: 10.0},
        {2: 2.0},
        {3: 3.0},
        {0: 100.0},
    ]
    g = graph_cls(data)

    res = g.bidirectional_dijkstra(0, 3)
    assert res["length"] == 6.0
    assert res["path"] == [0, 1, 2, 3]

    res_back = g.bidirectional_dijkstra(3, 1)
    assert res_back["length"] == 101.0
    assert res_back["path"] == [3, 0, 1]


def test_python_basic_bidirectional():
    _run_basic_bidirectional_tests(PyGraph)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_basic_bidirectional():
    _run_basic_bidirectional_tests(CppGraph)


def test_python_disconnected():
    _run_disconnected_tests(PyGraph)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_disconnected():
    _run_disconnected_tests(CppGraph)


def test_python_directed_asymmetric():
    _run_directed_asymmetric_tests(PyGraph)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_directed_asymmetric():
    _run_directed_asymmetric_tests(CppGraph)


def test_bidirectional_dijkstra_on_marnet(marnet):
    g = marnet.graph_object
    test_pairs = [(0, 100), (50, 200), (300, 400), (10, 500)]
    for u, v in test_pairs:
        d_res = g.dijkstra(u, v)
        bi_res = g.bidirectional_dijkstra(u, v)
        assert abs(d_res["length"] - bi_res["length"]) < 1e-5
        assert abs(g.get_path_weight(bi_res["path"]) - d_res["length"]) < 1e-5


def test_bidirectional_dijkstra_on_us_freeway(published):
    g = published("us_freeway").graph_object
    test_pairs = [(0, 500), (1000, 2000), (3000, 4000)]
    for u, v in test_pairs:
        d_res = g.dijkstra(u, v)
        bi_res = g.bidirectional_dijkstra(u, v)
        assert abs(d_res["length"] - bi_res["length"]) < 1e-5
        assert abs(g.get_path_weight(bi_res["path"]) - d_res["length"]) < 1e-5


# A search from both ends, and reduce(), read the inverse graph. The tests below
# change a graph after its inverse graph is built. The changed graph must then
# answer as a graph built from scratch with the same links.
def _build_graph_with_its_inverse(Graph):
    # The links are one-way: the inverse graph differs from the graph. Each
    # change made by a test below changes a shortest path and keeps every
    # node reachable.
    graph = Graph([{1: 10, 3: 1}, {2: 10}, {0: 10}, {2: 1, 1: 20}])
    graph.bidirectional_dijkstra(0, 2)  # This search builds the inverse graph.
    return graph


def _search_every_pair(graph, algorithm):
    nodes = range(len(graph.graph))
    search = getattr(graph, algorithm)
    return {(o, d): search(o, d) for o in nodes for d in nodes}


_SEARCHES_FROM_BOTH_ENDS = ["bidirectional_dijkstra", "bidirectional_buckets"]


@pytest.mark.parametrize("algorithm", _SEARCHES_FROM_BOTH_ENDS)
def test_search_from_both_ends_sees_an_added_node(Graph, algorithm):
    graph = _build_graph_with_its_inverse(Graph)
    graph.add_node({0: 1}, symmetric=True)
    rebuilt = Graph(deepcopy(graph.graph))
    assert _search_every_pair(graph, algorithm) == _search_every_pair(
        rebuilt, algorithm
    )


@pytest.mark.parametrize("algorithm", _SEARCHES_FROM_BOTH_ENDS)
def test_search_from_both_ends_sees_an_added_edge(Graph, algorithm):
    graph = _build_graph_with_its_inverse(Graph)
    graph.add_edge(2, 0, 1)
    rebuilt = Graph(deepcopy(graph.graph))
    assert _search_every_pair(graph, algorithm) == _search_every_pair(
        rebuilt, algorithm
    )


@pytest.mark.parametrize("algorithm", _SEARCHES_FROM_BOTH_ENDS)
def test_search_from_both_ends_forgets_a_removed_node(Graph, algorithm):
    graph = _build_graph_with_its_inverse(Graph)
    graph.remove_node()
    rebuilt = Graph(deepcopy(graph.graph))
    assert _search_every_pair(graph, algorithm) == _search_every_pair(
        rebuilt, algorithm
    )


@pytest.mark.parametrize("algorithm", _SEARCHES_FROM_BOTH_ENDS)
def test_search_from_both_ends_forgets_a_removed_edge(Graph, algorithm):
    graph = _build_graph_with_its_inverse(Graph)
    graph.remove_edge(3, 2)
    rebuilt = Graph(deepcopy(graph.graph))
    assert _search_every_pair(graph, algorithm) == _search_every_pair(
        rebuilt, algorithm
    )


def test_reduce_forgets_a_removed_edge(Graph):
    graph = _build_graph_with_its_inverse(Graph)
    graph.remove_edge(3, 2)
    rebuilt = Graph(deepcopy(graph.graph))
    graph.reduce()
    rebuilt.reduce()
    assert _search_every_pair(graph, "dijkstra") == _search_every_pair(
        rebuilt, "dijkstra"
    )


def test_contraction_hierarchy_sees_an_added_edge(Graph):
    graph = _build_graph_with_its_inverse(Graph)
    graph.add_edge(2, 0, 1)
    rebuilt = Graph(deepcopy(graph.graph))
    assert _search_every_pair(
        graph, "contraction_hierarchy"
    ) == _search_every_pair(rebuilt, "contraction_hierarchy")
