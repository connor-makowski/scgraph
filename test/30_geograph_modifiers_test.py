import pytest
from copy import deepcopy
from scgraph import GeoGraph, Graph
from scgraph.utils import haversine
from helpers import assert_result

_NODES = [[0, 0], [0, 1], [1, 0], [1, 1]]
_GRAPH = [
    {1: 100, 2: 200},
    {0: 100, 3: 100},
    {0: 200, 3: 100},
    {1: 100, 2: 100},
]
_ORIGIN = {"latitude": 0, "longitude": 0}
_DEST = {"latitude": 1, "longitude": 1}


def _fresh():
    return GeoGraph(nodes=deepcopy(_NODES), graph=deepcopy(_GRAPH))


def test_add_edge():
    g = _fresh()
    g.add_edge(origin_id=0, destination_id=3, distance=50, symmetric=True)
    assert_result(
        g.get_shortest_path(origin_node=_ORIGIN, destination_node=_DEST),
        {"coordinate_path": [[0, 0], [0, 0], [1, 1], [1, 1]], "length": 50},
    )


def test_remove_edge():
    g = _fresh()
    g.remove_edge(origin_id=0, destination_id=1, symmetric=True)
    assert_result(
        g.get_shortest_path(origin_node=_ORIGIN, destination_node=_DEST),
        {
            "coordinate_path": [[0, 0], [0, 0], [1, 0], [1, 1], [1, 1]],
            "length": 300,
        },
    )


def test_add_coord_edge():
    g = _fresh()
    g.add_coord_edge(
        origin_coord_dict={"latitude": 0.1, "longitude": 0.1},
        destination_coord_dict={"latitude": 0.9, "longitude": 0.9},
        distance=50,
        symmetric=True,
    )
    assert_result(
        g.get_shortest_path(origin_node=_ORIGIN, destination_node=_DEST),
        {"coordinate_path": [[0, 0], [0, 0], [1, 1], [1, 1]], "length": 50},
    )


def test_add_coord_node_returns_id():
    g = _fresh()
    new_id = g.add_coord_node(
        coord_dict={"latitude": 0.5, "longitude": 0.5}, auto_edge=False
    )
    assert new_id == 4


def test_add_coord_node_grows_graph():
    g = _fresh()
    g.add_coord_node(
        coord_dict={"latitude": 0.5, "longitude": 0.5}, auto_edge=False
    )
    assert len(g.graph_object.graph) == 5


def test_add_coord_node_isolated_path_unchanged():
    g = _fresh()
    g.add_coord_node(
        coord_dict={"latitude": 0.5, "longitude": 0.5}, auto_edge=False
    )
    assert_result(
        g.get_shortest_path(origin_node=_ORIGIN, destination_node=_DEST),
        {
            "coordinate_path": [[0, 0], [0, 0], [0, 1], [1, 1], [1, 1]],
            "length": 200,
        },
    )


def test_add_coord_node_auto_edge_grows_graph():
    g = _fresh()
    g.add_coord_node(
        coord_dict={"latitude": 0.5, "longitude": 0.5},
        auto_edge=True,
        circuity=1.1,
    )
    assert len(g.graph_object.graph) == 5


def test_add_coord_node_auto_edge_shortens_path():
    g = _fresh()
    g.add_coord_node(
        coord_dict={"latitude": 0.5, "longitude": 0.5},
        auto_edge=True,
        circuity=1.1,
    )
    result = g.get_shortest_path(origin_node=_ORIGIN, destination_node=_DEST)
    assert result["length"] < 200


def test_remove_coord_node_restores_size():
    g = _fresh()
    g.add_coord_node(
        coord_dict={"latitude": 0.5, "longitude": 0.5}, auto_edge=False
    )
    g.remove_coord_node()
    assert len(g.graph_object.graph) == 4


def test_remove_coord_node_restores_path():
    g = _fresh()
    g.add_coord_node(
        coord_dict={"latitude": 0.5, "longitude": 0.5}, auto_edge=False
    )
    g.remove_coord_node()
    assert_result(
        g.get_shortest_path(origin_node=_ORIGIN, destination_node=_DEST),
        {
            "coordinate_path": [[0, 0], [0, 0], [0, 1], [1, 1], [1, 1]],
            "length": 200,
        },
    )


def _snapped(g, point):
    # Node a point is connected to when snapping to the closest node only
    return g.get_shortest_path(
        origin_node=point,
        destination_node=_DEST,
        node_addition_type="closest",
        output_path=True,
    )["path"][0]


# The point is next to the added node 4, in the middle of the four nodes.
def test_snapping_finds_an_added_node():
    g = _fresh()
    g.add_coord_node({"latitude": 0.5, "longitude": 0.5})
    assert _snapped(g, {"latitude": 0.45, "longitude": 0.55}) == 4


# The first query snaps to node 4 while it exists. After the removal, node 1
# at [0, 1] is the closest node to the same point.
def test_snapping_forgets_a_removed_node():
    g = _fresh()
    near_node_4 = {"latitude": 0.45, "longitude": 0.55}
    g.add_coord_node({"latitude": 0.5, "longitude": 0.5})
    _snapped(g, near_node_4)
    g.remove_coord_node()
    assert _snapped(g, near_node_4) == 1


# The second node 4 is far from the first one. The graph has five nodes both
# times: the number of nodes does not tell that node 4 moved.
def test_snapping_finds_a_node_added_in_place_of_a_removed_node():
    g = _fresh()
    near_first_node_4 = {"latitude": 0.45, "longitude": 0.55}
    near_second_node_4 = {"latitude": 0.95, "longitude": -0.95}
    g.add_coord_node({"latitude": 0.5, "longitude": 0.5})
    _snapped(g, near_first_node_4)
    g.remove_coord_node()
    g.add_coord_node(
        {"latitude": 1, "longitude": -1},
        node_addition_type="all",
        lat_lon_bound=180,
    )
    assert _snapped(g, near_second_node_4) == 4
    assert _snapped(g, near_first_node_4) == 1


def test_add_haversine_edge():
    g = _fresh()
    g.add_haversine_edge(origin_idx=0, destination_idx=3, symmetric=True)
    expected_dist = haversine(_NODES[0], _NODES[3])
    assert_result(
        g.get_shortest_path(origin_node=_ORIGIN, destination_node=_DEST),
        {
            "coordinate_path": [[0, 0], [0, 0], [1, 1], [1, 1]],
            "length": expected_dist,
        },
    )


# A graph of two nodes joined both ways. Its node ids are 0 and 1.
def _two_joined_nodes():
    return Graph([{1: 1.0}, {0: 1.0}])


def test_add_edge_refuses_an_origin_that_is_not_in_the_graph():
    with pytest.raises(IndexError):
        _two_joined_nodes().add_edge(5, 0, 1.0)


def test_add_edge_refuses_a_destination_that_is_not_in_the_graph():
    with pytest.raises(IndexError):
        _two_joined_nodes().add_edge(0, 5, 1.0)


def test_remove_edge_refuses_an_origin_that_is_not_in_the_graph():
    with pytest.raises(IndexError):
        _two_joined_nodes().remove_edge(5, 0)


def test_remove_edge_refuses_a_destination_that_is_not_in_the_graph():
    with pytest.raises(IndexError):
        _two_joined_nodes().remove_edge(0, 5)


def test_remove_node_refuses_a_graph_without_nodes():
    graph = Graph([{}])
    graph.remove_node()

    with pytest.raises(RuntimeError):
        graph.remove_node()
