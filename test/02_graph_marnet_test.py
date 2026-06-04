import pytest
from scgraph import Graph
from helpers import assert_result

_EXPECTED = {"path": [0, 1, 5695, 64, 2213, 10152, 6749, 5], "length": 1134.729}


@pytest.fixture(scope="module")
def marnet_graph(marnet):
    return Graph(marnet.graph_object.graph)


def test_graph_validation(marnet_graph):
    marnet_graph.validate()


def test_dijkstra(marnet_graph):
    assert_result(marnet_graph.dijkstra(origin_id=0, destination_id=5), _EXPECTED)


def test_a_star(marnet_graph):
    assert_result(marnet_graph.a_star(origin_id=0, destination_id=5), _EXPECTED)


def test_contraction_hierarchy(marnet_graph):
    marnet_graph.create_contraction_hierarchy()
    assert_result(
        marnet_graph.contraction_hierarchy(origin_id=0, destination_id=5), _EXPECTED
    )
