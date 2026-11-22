"""Tests of a multimodal network on a GeoGraph: its nodes, its edges and their
classes."""

from array import array
from itertools import accumulate

import pytest

from scgraph import GeoGraph, network_file

# The network of these tests joins two towns on the equator, 0.7 degree of
# longitude apart. A line of the drawing is one edge each way, with its km.
#
#   8 TERMINAL ..1.. 3 STATION ====== 90 ====== 4 STATION ..1.. 9 TERMINAL
#         :                                                         :
#         2                                                         2
#         :                                                         :
#   0 WEST_TOWN ---- 40 ---- 1 JUNCTION ---- 40 ---- 2 EAST_TOWN ....
#          \                                         /   :
#           '------------------ 100 ----------------'    3
#                                                        :
#       6 OPEN_SEA ------- 200 ------- 5 COAST ..5.. 7 PORT
#
# The primary road through the junction is the shortest way between the towns:
# 80 km. The motorway is longer and faster: 100 km. The railway needs the two
# terminals: 2 + 1 + 90 + 1 + 2 = 96 km. The sea lane starts at the port of
# the east town.
#
# The nodes are listed mode by mode, as in a network file: (mode, latitude,
# longitude). The id of a node is its position. No edge is shorter than the
# straight line between its two nodes.
WEST_TOWN, JUNCTION, EAST_TOWN = 0, 1, 2
WEST_STATION, EAST_STATION = 3, 4
COAST, OPEN_SEA = 5, 6
PORT = 7
WEST_TERMINAL, EAST_TERMINAL = 8, 9
NODES = [
    ("road", 0.0, 0.0),
    ("road", 0.0, 0.35),
    ("road", 0.0, 0.7),
    ("rail", 0.02, 0.0),
    ("rail", 0.02, 0.7),
    ("sea", -0.065, 0.7),
    ("sea", -0.065, 2.45),
    ("port", -0.025, 0.7),
    ("rail_terminal", 0.015, 0.0),
    ("rail_terminal", 0.015, 0.7),
]
# The mode of the edges of each class. A hub joins a network by connectors.
CLASSES = {
    "primary": "road",
    "motorway": "road",
    "road_connector": "road",
    "rail_main": "rail",
    "rail_connector": "rail",
    "open_sea": "sea",
    "sea_connector": "sea",
}
# (a node, another node, km, class). A node lists its edges in this order.
TWO_WAY_EDGES = [
    (WEST_TOWN, JUNCTION, 40.0, "primary"),
    (JUNCTION, EAST_TOWN, 40.0, "primary"),
    (WEST_TOWN, EAST_TOWN, 100.0, "motorway"),
    (WEST_TOWN, WEST_TERMINAL, 2.0, "road_connector"),
    (WEST_TERMINAL, WEST_STATION, 1.0, "rail_connector"),
    (WEST_STATION, EAST_STATION, 90.0, "rail_main"),
    (EAST_STATION, EAST_TERMINAL, 1.0, "rail_connector"),
    (EAST_TERMINAL, EAST_TOWN, 2.0, "road_connector"),
    (EAST_TOWN, PORT, 3.0, "road_connector"),
    (PORT, COAST, 5.0, "sea_connector"),
    (COAST, OPEN_SEA, 200.0, "open_sea"),
]
# The class of each edge, by (origin, destination)
CLASS_OF_EACH_EDGE = {
    nodes: edge_class
    for a, b, _, edge_class in TWO_WAY_EDGES
    for nodes in ((a, b), (b, a))
}


def _write_network(path, nodes, two_way_edges, classes):
    """Write the network file of `nodes` and `two_way_edges`, which have the
    form of NODES and TWO_WAY_EDGES. `classes` gives the mode of the edges of
    each class. A query point snaps to a road node by default."""
    # The edges of each node: (destination, km, row of the class)
    rows = [[] for _ in nodes]
    for a, b, km, edge_class in two_way_edges:
        rows[a].append((b, km, list(classes).index(edge_class)))
        rows[b].append((a, km, list(classes).index(edge_class)))
    heads, lengths, edge_classes = zip(*(edge for row in rows for edge in row))
    modes = list(dict.fromkeys(mode for mode, _, _ in nodes))
    arrays = {
        "offsets": array("i", accumulate(map(len, rows), initial=0)),
        "heads": array("i", heads),
        "weights_length": array("d", lengths),
        "edge_classes": array("B", edge_classes),
        "node_points": array("d", [x for _, *point in nodes for x in point]),
        "node_modes": array("B", [modes.index(mode) for mode, _, _ in nodes]),
    }
    metadata = {
        "metrics": [{"name": "length", "unit": "km"}],
        "modes": [{"name": name} for name in modes],
        "classes": [{"name": n, "mode": mode} for n, mode in classes.items()],
        "node_addition_modes": ["road"],
    }
    network_file.write(path, arrays, metadata)


@pytest.fixture(scope="module")
def network_path(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("network") / "two_towns.scgraph")
    _write_network(path, NODES, TWO_WAY_EDGES, CLASSES)
    return path


@pytest.fixture
def network(network_path):
    """The network of the two towns. A test may edit it: each test loads it."""
    return GeoGraph.load_from_scgraph(network_path)


def _get_class_of_each_edge(geograph):
    return {
        (edge["origin_id"], edge["destination_id"]): edge["class"]
        for edge in geograph.get_edges()
    }


def test_get_nodes_gives_the_nodes_of_one_mode(network):
    assert network.get_nodes(mode="port") == [
        {"node_id": PORT, "latitude": -0.025, "longitude": 0.7, "mode": "port"}
    ]


def test_get_nodes_gives_the_nodes_inside_a_bounding_box(network):
    # The box goes from the equator to 0.1 N and from 0.5 E to 1 E. The east
    # town is on its south side. The port is south of the equator.
    nodes = network.get_nodes(bbox=(0.0, 0.5, 0.1, 1.0))

    node_ids = [node["node_id"] for node in nodes]
    assert node_ids == [EAST_TOWN, EAST_STATION, EAST_TERMINAL]


def test_get_edges_gives_the_edges_that_leave_one_node(network):
    assert network.get_edges(origin_id=JUNCTION) == [
        {
            "origin_id": JUNCTION,
            "destination_id": destination_id,
            "length": 40.0,
            "class": "primary",
            "mode": "road",
            "metrics": {},
        }
        for destination_id in (WEST_TOWN, EAST_TOWN)
    ]


def test_get_edges_gives_the_edges_of_one_class(network):
    edges = network.get_edges(edge_class="motorway")

    nodes = [(edge["origin_id"], edge["destination_id"]) for edge in edges]
    assert nodes == [(WEST_TOWN, EAST_TOWN), (EAST_TOWN, WEST_TOWN)]


def test_get_path_edges_gives_the_edges_of_a_path_in_its_order(network):
    # From the west town to the east station, by the railway
    path = [WEST_TOWN, WEST_TERMINAL, WEST_STATION, EAST_STATION]

    edges = network.get_path_edges(path)

    assert [
        (edge["class"], edge["mode"], edge["length"]) for edge in edges
    ] == [
        ("road_connector", "road", 2.0),
        ("rail_connector", "rail", 1.0),
        ("rail_main", "rail", 90.0),
    ]


# The network has no mode `air`, no class `canal`, no node 10 and no edge from
# the junction to the port.
@pytest.mark.parametrize(
    "method, argument",
    [
        ("get_nodes", {"mode": "air"}),
        ("get_edges", {"edge_class": "canal"}),
        ("get_edges", {"origin_id": 10}),
        ("get_path_edges", {"path": [WEST_TOWN, JUNCTION, PORT]}),
        ("get_path_edges", {"path": [10, WEST_TOWN]}),
    ],
)
def test_a_read_of_what_the_network_lacks_is_refused(network, method, argument):
    with pytest.raises(ValueError):
        getattr(network, method)(**argument)


def test_a_geograph_made_from_a_graph_has_edges_without_a_class():
    geograph = GeoGraph(graph=[{1: 2.5}, {}], nodes=[[0, 0], [0, 1]])

    assert _get_class_of_each_edge(geograph) == {(0, 1): None}


# Each call adds an edge both ways between the west town and the port.
@pytest.mark.parametrize(
    "method, arguments",
    [
        ("add_edge", (WEST_TOWN, PORT, 85.0, True)),
        ("add_haversine_edge", (WEST_TOWN, PORT)),
        (
            "add_coord_edge",
            (
                {"latitude": 0.0, "longitude": 0.0},
                {"latitude": -0.025, "longitude": 0.7},
            ),
        ),
    ],
)
def test_an_added_edge_has_its_class_and_the_other_edges_keep_theirs(
    network, method, arguments
):
    getattr(network, method)(*arguments, edge_class="primary")

    assert _get_class_of_each_edge(network) == {
        **CLASS_OF_EACH_EDGE,
        (WEST_TOWN, PORT): "primary",
        (PORT, WEST_TOWN): "primary",
    }


def test_a_node_added_with_a_class_gives_this_class_to_its_edges(network):
    # The west town is the closest node: 0.01 degree north of the new node.
    node_id = network.add_coord_node(
        {"latitude": -0.01, "longitude": 0.0},
        node_addition_type="closest",
        edge_class="road_connector",
    )

    assert _get_class_of_each_edge(network) == {
        **CLASS_OF_EACH_EDGE,
        (node_id, WEST_TOWN): "road_connector",
        (WEST_TOWN, node_id): "road_connector",
    }


def test_an_edit_made_on_the_graph_object_keeps_the_classes_lined_up(network):
    # The motorway is the second edge of each town: the edges after it move.
    network.graph_object.remove_edge(WEST_TOWN, EAST_TOWN, symmetric=True)

    assert _get_class_of_each_edge(network) == {
        nodes: edge_class
        for nodes, edge_class in CLASS_OF_EACH_EDGE.items()
        if edge_class != "motorway"
    }


def test_a_removed_node_leaves_the_classes_of_the_other_edges(network):
    # The last node is the east terminal.
    network.remove_node()

    assert _get_class_of_each_edge(network) == {
        nodes: edge_class
        for nodes, edge_class in CLASS_OF_EACH_EDGE.items()
        if EAST_TERMINAL not in nodes
    }


# A ferry line of 30 km, one degree north of the two towns. Its class is not a
# class of their network.
FERRY_NODES = [("road", 1.0, 0.0), ("road", 1.0, 0.3)]
FERRY_EDGES = [(0, 1, 30.0, "ferry")]


def test_a_merge_keeps_the_classes_of_both_geographs(network, tmp_path):
    ferry_path = str(tmp_path / "ferry.scgraph")
    _write_network(ferry_path, FERRY_NODES, FERRY_EDGES, {"ferry": "road"})
    ferry = GeoGraph.load_from_scgraph(ferry_path)

    # The connection node is the node 10. It joins the closest node of each
    # geograph: the west station and the first node of the ferry. The two
    # nodes of the ferry become the nodes 11 and 12.
    network.merge_with_other_geograph(ferry, connection_nodes=[[0.5, 0.0]])

    assert _get_class_of_each_edge(network) == {
        **CLASS_OF_EACH_EDGE,
        (10, WEST_STATION): None,
        (WEST_STATION, 10): None,
        (10, 11): None,
        (11, 10): None,
        (11, 12): "ferry",
        (12, 11): "ferry",
    }


def test_a_save_keeps_the_default_node_addition_modes(network, tmp_path):
    saved_path = str(tmp_path / "saved.scgraph")

    network.save_as_scgraph(saved_path)

    saved = GeoGraph.load_from_scgraph(saved_path)
    assert saved.default_node_addition_modes == ["road"]
