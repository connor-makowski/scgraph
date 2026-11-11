import pytest
from scgraph import Graph
from helpers import assert_result

_PAIRS = {
    "marnet": [(0, 5), (100, 7999), (4022, 8342)],
    "us_freeway": [(0, 5), (4022, 8342)],
}


# On the graph of a built-in network, between nodes named by their ids, a search
# finds the route of Dijkstra, whatever the algorithm.
@pytest.mark.parametrize(
    "name, algorithm",
    [
        ("marnet", "bmssp"),
        ("us_freeway", "bmssp"),
        ("us_freeway", "contraction_hierarchy"),
    ],
)
def test_graph_search_finds_the_route_of_dijkstra(name, algorithm, request):
    # A graph of its own: the contraction hierarchy would stay on the fixture
    graph = Graph(request.getfixturevalue(name).graph_object.graph)
    for origin_id, destination_id in _PAIRS[name]:
        assert_result(
            getattr(graph, algorithm)(origin_id, destination_id),
            graph.dijkstra(origin_id, destination_id),
        )
