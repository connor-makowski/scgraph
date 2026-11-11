import pytest
from scgraph import Graph
from helpers import assert_result

# The tests of this file search the graph of a built-in network between nodes
# named by their ids, and compare the route with the route of Dijkstra. The
# pairs of ids are arbitrary.


# The graphs are copies for this file: a contraction hierarchy built by a query
# would stay on the network of the session.
@pytest.fixture(scope="module")
def marnet_graph(marnet):
    return Graph(marnet.graph_object.graph)


@pytest.fixture(scope="module")
def us_freeway_graph(us_freeway):
    return Graph(us_freeway.graph_object.graph)


@pytest.mark.parametrize(
    "origin_id, destination_id", [(0, 5), (100, 7999), (4022, 8342)]
)
def test_bmssp_finds_the_route_of_dijkstra_on_marnet(
    marnet_graph, origin_id, destination_id
):
    found = marnet_graph.bmssp(origin_id, destination_id)

    assert_result(found, marnet_graph.dijkstra(origin_id, destination_id))


@pytest.mark.parametrize("origin_id, destination_id", [(0, 5), (4022, 8342)])
def test_bmssp_finds_the_route_of_dijkstra_on_us_freeway(
    us_freeway_graph, origin_id, destination_id
):
    found = us_freeway_graph.bmssp(origin_id, destination_id)

    assert_result(found, us_freeway_graph.dijkstra(origin_id, destination_id))


@pytest.mark.parametrize("origin_id, destination_id", [(0, 5), (4022, 8342)])
def test_contraction_hierarchy_finds_the_route_of_dijkstra_on_us_freeway(
    us_freeway_graph, origin_id, destination_id
):
    found = us_freeway_graph.contraction_hierarchy(origin_id, destination_id)

    assert_result(found, us_freeway_graph.dijkstra(origin_id, destination_id))
