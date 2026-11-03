import pytest
from helpers import assert_result
from scgraph.graph import Graph as PyGraph

try:
    from scgraph.cpp import Graph as CppGraph

    GRAPH_CLASSES = [PyGraph, CppGraph]
except ImportError:
    GRAPH_CLASSES = [PyGraph]


def test_bmssp_marnet_0_5(marnet):
    graph = marnet.graph_object
    assert_result(graph.bmssp(0, 5), graph.dijkstra(0, 5))


def test_bmssp_marnet_100_7999(marnet):
    graph = marnet.graph_object
    assert_result(graph.bmssp(100, 7999), graph.dijkstra(100, 7999))


def test_bmssp_marnet_4022_8342(marnet):
    graph = marnet.graph_object
    assert_result(graph.bmssp(4022, 8342), graph.dijkstra(4022, 8342))


def test_bmssp_us_freeway_0_5(us_freeway):
    graph = us_freeway.graph_object
    assert_result(graph.bmssp(0, 5), graph.dijkstra(0, 5))


def test_bmssp_us_freeway_4022_8342(us_freeway):
    graph = us_freeway.graph_object
    assert_result(graph.bmssp(4022, 8342), graph.dijkstra(4022, 8342))


@pytest.mark.parametrize("GraphClass", GRAPH_CLASSES)
def test_bmssp_sees_graph_changes(GraphClass):
    # bmssp keeps its solver between queries: a changed graph must not reuse it
    g = GraphClass([{1: 5}, {2: 5}, {}])
    assert g.bmssp(0, 2)["length"] == 10
    g.add_edge(0, 2, 1)
    assert g.bmssp(0, 2)["length"] == 1
