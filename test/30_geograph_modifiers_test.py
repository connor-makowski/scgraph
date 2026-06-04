from copy import deepcopy
from scgraph import GeoGraph
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
        {"coordinate_path": [[0, 0], [0, 0], [1, 0], [1, 1], [1, 1]], "length": 300},
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
        coord_dict={"latitude": 0.5, "longitude": 0.5}, auto_edge=True, circuity=1.1
    )
    assert len(g.graph_object.graph) == 5


def test_add_coord_node_auto_edge_shortens_path():
    g = _fresh()
    g.add_coord_node(
        coord_dict={"latitude": 0.5, "longitude": 0.5}, auto_edge=True, circuity=1.1
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


def test_add_haversine_edge():
    g = _fresh()
    g.add_haversine_edge(origin_idx=0, destination_idx=3, symmetric=True)
    expected_dist = haversine(_NODES[0], _NODES[3])
    assert_result(
        g.get_shortest_path(origin_node=_ORIGIN, destination_node=_DEST),
        {"coordinate_path": [[0, 0], [0, 0], [1, 1], [1, 1]], "length": expected_dist},
    )
