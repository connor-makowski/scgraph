from copy import deepcopy
import pytest
from scgraph import GeoGraph

# Sixteen cities of the coasts of the United States, where the road network and
# the maritime network are joined
PORT_CITIES = [
    [42.3601, -71.0589],
    [40.7128, -74.0060],
    [39.9526, -75.1652],
    [39.2904, -76.6122],
    [38.9072, -77.0369],
    [32.0835, -81.0998],
    [32.7765, -79.9311],
    [30.3322, -81.6557],
    [25.7617, -80.1918],
    [27.9506, -82.4572],
    [29.9511, -90.0715],
    [29.7604, -95.3698],
    [34.0522, -118.2437],
    [37.7749, -122.4194],
    [47.6062, -122.3321],
    [45.5152, -122.6784],
]
# An inland city and a city overseas: a route between them needs both networks
ATLANTA = {"latitude": 33.7490, "longitude": -84.3880}
LONDON = {"latitude": 51.5074, "longitude": -0.1278}


# us_freeway with marnet merged into it at the port cities, and that marnet.
# They are loaded for this file: the merge changes the geograph that receives
# the other one, which must not be a fixture of the session.
@pytest.fixture(scope="module")
def freeway_with_marnet_and_marnet():
    freeway = GeoGraph.load_geograph("us_freeway")
    marnet = GeoGraph.load_geograph("marnet")
    freeway.merge_with_other_geograph(
        other_geograph=marnet,
        connection_nodes=PORT_CITIES,
        circuity_to_current_geograph=1.1,
        circuity_to_other_geograph=1.3,
        node_addition_type_current_geograph="closest",
        node_addition_type_other_geograph="closest",
        node_addition_math="euclidean",
    )
    return freeway, marnet


def test_merged_geograph_gives_the_published_distance_by_road_and_sea(
    freeway_with_marnet_and_marnet,
):
    merged, _ = freeway_with_marnet_and_marnet

    route = merged.get_shortest_path(
        origin_node=ATLANTA, destination_node=LONDON
    )

    assert route["length"] == pytest.approx(7459.1121, abs=0.1)


def test_merged_geograph_routes_as_a_geograph_built_from_the_merged_network(
    freeway_with_marnet_and_marnet,
):
    merged, _ = freeway_with_marnet_and_marnet
    # The constructor indexes every node for snapping; the merge must have
    # done as much for the nodes it added
    rebuilt = GeoGraph(
        graph=deepcopy(merged.graph_object.graph),
        nodes=deepcopy(merged.nodes),
        default_off_graph_circuity=merged.default_off_graph_circuity,
        default_node_addition_circuity=merged.default_node_addition_circuity,
        geograph_units=merged.geograph_units,
    )

    route = merged.get_shortest_path(
        origin_node=ATLANTA, destination_node=LONDON
    )

    assert route == rebuilt.get_shortest_path(
        origin_node=ATLANTA, destination_node=LONDON
    )


def test_geograph_merged_into_another_still_gives_its_own_distance(
    freeway_with_marnet_and_marnet,
):
    _, marnet = freeway_with_marnet_and_marnet

    route = marnet.get_shortest_path(
        origin_node=ATLANTA, destination_node=LONDON
    )

    # The length of the route on marnet alone (by sea from the coast south of
    # Atlanta), which the merge must not change
    assert route["length"] == pytest.approx(8820.8927, abs=0.1)


def chain_of_four_nodes(start_longitude):
    """Four nodes in a line on the equator, one degree (111.2 km) apart from
    `start_longitude`: reduce() contracts the two interior nodes."""
    nodes = [[0, start_longitude + i] for i in range(4)]
    graph = [{1: 111.2}, {0: 111.2, 2: 111.2}, {1: 111.2, 3: 111.2}, {2: 111.2}]
    return GeoGraph(nodes=nodes, graph=graph)


# In the two tests below, the merge has no connection nodes: adding a node
# would already undo reduce(). The expected graph is the merge of the same two
# chains, neither reduced.


def test_merge_of_a_reduced_geograph_holds_its_graph_before_reduction():
    expected = chain_of_four_nodes(0)
    expected.merge_with_other_geograph(
        chain_of_four_nodes(10), connection_nodes=[]
    )
    reduced = chain_of_four_nodes(0)
    reduced.reduce()

    reduced.merge_with_other_geograph(
        chain_of_four_nodes(10), connection_nodes=[]
    )

    assert reduced.graph_object.graph == expected.graph_object.graph
    assert reduced.nodes == expected.nodes


def test_merge_with_a_reduced_geograph_holds_its_graph_before_reduction():
    expected = chain_of_four_nodes(0)
    expected.merge_with_other_geograph(
        chain_of_four_nodes(10), connection_nodes=[]
    )
    current = chain_of_four_nodes(0)
    reduced_other = chain_of_four_nodes(10)
    reduced_other.reduce()

    current.merge_with_other_geograph(reduced_other, connection_nodes=[])

    assert current.graph_object.graph == expected.graph_object.graph
    assert current.nodes == expected.nodes


def test_added_and_merged_nodes_get_ids_that_collide_with_none():
    # Two graphs of two nodes, each with a third node added after: an added
    # node gets a negative id, so both graphs hold a node -1
    road = GeoGraph(
        graph=[{1: 1.0}, {0: 1.0}],
        nodes=[[0, 0], [0, 1]],
        node_ids=[10, 20],
    )
    road.add_coord_node({"latitude": 0, "longitude": 2})
    sea = GeoGraph(graph=[{1: 1.0}, {0: 1.0}], nodes=[[1, 0], [1, 1]])
    sea.add_coord_node({"latitude": 1, "longitude": 2})

    road.merge_with_other_geograph(sea, connection_nodes=[[0.5, 0.5]])

    # The nodes of road with their ids (10, 20, -1), the connection node
    # (-2), then the nodes of sea: 0 and 1 keep their ids, and its added node
    # moves from -1 to -3
    assert list(road.node_ids) == [10, 20, -1, -2, 0, 1, -3]
    # A node added after the merge gets the next id below
    road.add_coord_node({"latitude": 2, "longitude": 2})
    assert road.node_ids[-1] == -4


def test_merge_keeps_the_finer_coordinate_type_of_the_two_geographs():
    # Coordinates as 32-bit integers on one side, as 64-bit floats (the
    # default) on the other
    road = GeoGraph(
        graph=[{1: 1.0}, {0: 1.0}],
        nodes=[[0, 0], [0, 1]],
        coordinate_dtype="int32",
    )
    sea = GeoGraph(graph=[{1: 1.0}, {0: 1.0}], nodes=[[1, 0], [1, 1]])

    road.merge_with_other_geograph(sea, connection_nodes=[[0.5, 0.5]])

    assert road.coordinate_dtype == "float64"
