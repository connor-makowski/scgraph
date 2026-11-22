"""Tests of a multimodal network on a GeoGraph: its nodes, its edges, their
classes and its metrics."""

import math
from array import array
from itertools import accumulate

import pytest

from scgraph import GeoGraph, PathNotFoundError, network_file

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
# The nodes are listed node mode by node mode, as in a network file: (node
# mode, latitude, longitude). The id of a node is its position. No edge is
# shorter than the straight line between its two nodes.
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
# The edge mode of each class. A hub joins a network by connectors.
CLASSES = {
    "primary": "road",
    "motorway": "road",
    "road_connector": "road",
    "rail_main": "rail",
    "rail_connector": "rail",
    "open_sea": "sea",
    "sea_connector": "sea",
}
# (a node, another node, km, class). The edges of a node are stored in the
# order of this list.
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
    for node, other_node, _, edge_class in TWO_WAY_EDGES
    for nodes in ((node, other_node), (other_node, node))
}
KM_OF_EACH_EDGE = {
    nodes: km
    for node, other_node, km, _ in TWO_WAY_EDGES
    for nodes in ((node, other_node), (other_node, node))
}

# The weights per km of the metric `minutes`: the minutes that 1 km takes. A
# lorry drives at 40 km/h on a primary road, at 120 km/h on the motorway and
# at 30 km/h on the other roads, which are the connectors. A train runs at
# 240 km/h and a ship sails at 30 km/h. A lorry needs 4 minutes for 1 km of
# an off-graph leg: the straight line between a query point and its node.
# Each weight per km is exact in binary, so that an expected weight is exact.
MINUTES_PER_KM = {"road": 2.0, "rail": 0.25, "sea": 2.0, "off_graph": 4.0}
CLASS_MINUTES_PER_KM = {"primary": 1.5, "motorway": 0.5}
# The two dicts are the arguments of `create_metric`.
MINUTES = {
    "weight_per_km": MINUTES_PER_KM,
    "class_weight_per_km": CLASS_MINUTES_PER_KM,
}
# The weight per km that MINUTES gives to each class: the weight of a class
# replaces the weight of its edge mode.
MINUTES_PER_KM_OF_EACH_CLASS = {
    "primary": 1.5,
    "motorway": 0.5,
    "road_connector": 2.0,
    "rail_main": 0.25,
    "rail_connector": 0.25,
    "open_sea": 2.0,
    "sea_connector": 2.0,
}
MINUTES_OF_EACH_EDGE = {
    nodes: MINUTES_PER_KM_OF_EACH_CLASS[edge_class] * KM_OF_EACH_EDGE[nodes]
    for nodes, edge_class in CLASS_OF_EACH_EDGE.items()
}
# Between the two towns, the railway is the fastest route: 2 × 2 + 1 × 0.25 +
# 90 × 0.25 + 1 × 0.25 + 2 × 2 = 31 minutes, for 96 km. The motorway takes 50
# minutes, and the primary road, the shortest route, 120 minutes.
RAILWAY_PATH = [
    WEST_TOWN,
    WEST_TERMINAL,
    WEST_STATION,
    EAST_STATION,
    EAST_TERMINAL,
    EAST_TOWN,
]
# The two points of a query from the west to the east. Each point is on the
# equator, 0.1 degree of longitude beyond its town, which is its closest node.
# An off-graph leg is 6371 km × 0.1 degree in radians = 11.12 km.
WEST_POINT = {"latitude": 0.0, "longitude": -0.1}
EAST_POINT = {"latitude": 0.0, "longitude": 0.8}
OFF_GRAPH_LEG_KM = 6371 * math.radians(0.1)

# A ferry line of 30 km, one degree north of the two towns. Its class is not a
# class of their network.
FERRY_NODES = [("road", 1.0, 0.0), ("road", 1.0, 0.3)]
FERRY_EDGES = [(0, 1, 30.0, "ferry")]


def _write_network(path, nodes, two_way_edges, classes):
    """Write the network file of `nodes` and `two_way_edges`, which have the
    form of NODES and TWO_WAY_EDGES. `classes` gives the edge mode of each
    class. A query point snaps to a road node by default."""
    # The edges of each node: (destination, km, id of the class)
    edges_of_each_node = [[] for _ in nodes]
    for node, other_node, km, edge_class in two_way_edges:
        class_id = list(classes).index(edge_class)
        edges_of_each_node[node].append((other_node, km, class_id))
        edges_of_each_node[other_node].append((node, km, class_id))
    heads, lengths, edge_class_ids = zip(
        *(edge for edges in edges_of_each_node for edge in edges)
    )
    node_modes = list(dict.fromkeys(mode for mode, _, _ in nodes))
    arrays = {
        "offsets": array(
            "i", accumulate(map(len, edges_of_each_node), initial=0)
        ),
        "heads": array("i", heads),
        "weights_length": array("d", lengths),
        "edge_class_ids": array("B", edge_class_ids),
        "node_points": array("d", [x for _, *point in nodes for x in point]),
        "node_mode_ids": array(
            "B", [node_modes.index(mode) for mode, _, _ in nodes]
        ),
    }
    metadata = {
        "metrics": [{"name": "length", "unit": "km"}],
        "node_modes": [{"name": name} for name in node_modes],
        "classes": [
            {"name": name, "edge_mode": edge_mode}
            for name, edge_mode in classes.items()
        ],
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


@pytest.fixture
def network_with_minutes(network):
    """The network of the two towns, with the metric `minutes` of the weights
    per km MINUTES."""
    network.create_metric("minutes", **MINUTES)
    return network


@pytest.fixture
def network_read_with_minutes(network_path, tmp_path):
    """The network of the two towns, read from a file that holds the metric
    `minutes`: the geograph has the weights of the metric, and not the weights
    per km that made them. The file lists the open sea before the coast: only
    these two nodes change their ids."""
    network = GeoGraph.load_from_scgraph(network_path)
    network.create_metric("minutes", **MINUTES)
    path = str(tmp_path / "with_minutes.scgraph")
    network.save_as_scgraph(path)
    return GeoGraph.load_from_scgraph(path)


@pytest.fixture
def sea_network(network_path):
    """The sea lanes and the port of the network, read alone. The file names
    the node mode `road` for the query points, and this geograph has no road
    node."""
    return GeoGraph.load_from_scgraph(network_path, node_modes=["sea", "port"])


@pytest.fixture
def ferry(tmp_path):
    """The ferry line, read from its network file."""
    path = str(tmp_path / "ferry.scgraph")
    _write_network(path, FERRY_NODES, FERRY_EDGES, {"ferry": "road"})
    return GeoGraph.load_from_scgraph(path)


@pytest.fixture
def geograph_without_classes():
    """A geograph made from a graph: one edge of 2.5 km, from the node 0 to
    the node 1, one degree east of it. The edge has no class, and the one node
    mode of the nodes has no name."""
    return GeoGraph(graph=[{1: 2.5}, {}], nodes=[[0, 0], [0, 1]])


def _get_class_of_each_edge(geograph):
    return {
        (edge["origin_id"], edge["destination_id"]): edge["edge_class"]
        for edge in geograph.get_edges()
    }


def _get_weight_of_each_edge(geograph, metric):
    return {
        (edge["origin_id"], edge["destination_id"]): edge["metric_weights"][
            metric
        ]
        for edge in geograph.get_edges()
    }


# Reading the nodes and the edges


def test_get_nodes_gives_the_nodes_of_one_node_mode(network):
    assert network.get_nodes(node_mode="port") == [
        {
            "node_id": PORT,
            "latitude": -0.025,
            "longitude": 0.7,
            "node_mode": "port",
        }
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
            "edge_class": "primary",
            "edge_mode": "road",
            "metric_weights": {},
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
        (edge["edge_class"], edge["edge_mode"], edge["length"])
        for edge in edges
    ] == [
        ("road_connector", "road", 2.0),
        ("rail_connector", "rail", 1.0),
        ("rail_main", "rail", 90.0),
    ]


# A table of cases is a dict. The key of a case says what the case checks, and
# is the id of the case in a test run. The value holds the inputs of the case,
# then the result that the test expects, when the cases have different results.

# Each case names something that the network lacks: a method that reads the
# network, and its argument. The network has no node mode `air`, no class
# `canal`, no node 10 and no edge from the junction to the port.
REFUSED_READS = {
    "a node mode": ("get_nodes", {"node_mode": "air"}),
    "a class": ("get_edges", {"edge_class": "canal"}),
    "a node": ("get_edges", {"origin_id": 10}),
    "an edge of a path": (
        "get_path_edges",
        {"path": [WEST_TOWN, JUNCTION, PORT]},
    ),
    "a node of a path": ("get_path_edges", {"path": [10, WEST_TOWN]}),
}


@pytest.mark.parametrize(
    "method, argument", REFUSED_READS.values(), ids=REFUSED_READS
)
def test_reading_a_node_mode_a_class_a_node_or_an_edge_that_the_network_lacks_is_refused(
    network, method, argument
):
    with pytest.raises(ValueError):
        getattr(network, method)(**argument)


# The classes of the edges after an edit


def test_the_other_edges_keep_their_classes_when_the_graph_object_removes_an_edge(
    network,
):
    # The motorway is the second edge of each town: the edges after it move.
    network.graph_object.remove_edge(WEST_TOWN, EAST_TOWN, symmetric=True)

    assert _get_class_of_each_edge(network) == {
        nodes: edge_class
        for nodes, edge_class in CLASS_OF_EACH_EDGE.items()
        if edge_class != "motorway"
    }


def test_the_other_edges_keep_their_classes_when_a_node_is_removed(network):
    # The last node is the east terminal.
    network.remove_node()

    assert _get_class_of_each_edge(network) == {
        nodes: edge_class
        for nodes, edge_class in CLASS_OF_EACH_EDGE.items()
        if EAST_TERMINAL not in nodes
    }


def test_the_edges_of_a_node_added_on_the_graph_object_have_no_class(network):
    # The new node is the node 10.
    network.graph_object.add_node({JUNCTION: 30.0}, symmetric=True)

    classes = _get_class_of_each_edge(network)
    assert [classes[10, JUNCTION], classes[JUNCTION, 10]] == [None, None]


def test_a_merge_keeps_the_classes_of_both_geographs(network, ferry):
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


# Each case adds an edge both ways: a method, its arguments, and the two nodes
# of the new edge. The west town and the port had no edge. The two towns had
# the motorway.
ADDED_EDGES = {
    "add_edge": ("add_edge", (WEST_TOWN, PORT, 85.0, True), (WEST_TOWN, PORT)),
    "add_haversine_edge": (
        "add_haversine_edge",
        (WEST_TOWN, PORT),
        (WEST_TOWN, PORT),
    ),
    "add_coord_edge": (
        "add_coord_edge",
        (
            {"latitude": 0.0, "longitude": 0.0},
            {"latitude": -0.025, "longitude": 0.7},
        ),
        (WEST_TOWN, PORT),
    ),
    "add_edge in place of the motorway": (
        "add_edge",
        (WEST_TOWN, EAST_TOWN, 100.0, True),
        (WEST_TOWN, EAST_TOWN),
    ),
}


@pytest.mark.parametrize(
    "method, arguments, nodes", ADDED_EDGES.values(), ids=ADDED_EDGES
)
def test_an_added_edge_has_the_class_of_its_call(
    network, method, arguments, nodes
):
    getattr(network, method)(*arguments, edge_class="primary")

    # The railway was there: it keeps its class. The new edge of the west
    # town moves the edges of every node after it.
    classes = _get_class_of_each_edge(network)
    assert [
        classes[edge]
        for edge in [nodes, nodes[::-1], (WEST_STATION, EAST_STATION)]
    ] == ["primary", "primary", "rail_main"]


def test_a_node_added_with_a_class_gives_it_to_its_edges(network):
    # The west town is the closest node: 0.01 degree north of the new node.
    node_id = network.add_coord_node(
        {"latitude": -0.01, "longitude": 0.0},
        node_addition_type="closest",
        edge_class="road_connector",
    )

    classes = _get_class_of_each_edge(network)
    assert [
        classes[edge] for edge in [(node_id, WEST_TOWN), (WEST_TOWN, node_id)]
    ] == ["road_connector", "road_connector"]


def test_a_merge_keeps_the_class_of_an_edge_that_was_added_to_the_other_geograph(
    network, ferry
):
    # The new edge of the ferry has no class. It replaces the edge from the
    # node 1 to the node 0.
    ferry.add_edge(1, 0, 30.0)

    network.merge_with_other_geograph(ferry, connection_nodes=[[0.5, 0.0]])

    # The two nodes of the ferry become the nodes 11 and 12.
    classes = _get_class_of_each_edge(network)
    assert [classes[11, 12], classes[12, 11]] == ["ferry", None]


def test_an_edge_added_without_a_class_adds_no_class_to_the_geograph(network):
    network.add_edge(WEST_TOWN, PORT, 85.0, symmetric=True)

    # A read of every edge reads the class of the two new edges.
    network.get_edges()

    assert network.classes == [
        {"name": name, "edge_mode": edge_mode}
        for name, edge_mode in CLASSES.items()
    ]


def test_a_saved_and_loaded_geograph_gives_no_class_to_an_edge_without_a_class(
    network, tmp_path
):
    network.add_edge(WEST_TOWN, PORT, 85.0, symmetric=True)
    path = str(tmp_path / "saved.scgraph")

    network.save_as_scgraph(path)

    # The file has the classes of the network, and no class for the two new
    # edges, which are the only edges of 85 km.
    loaded = GeoGraph.load_from_scgraph(path)
    assert loaded.classes == network.classes
    assert [
        edge["length"]
        for edge in loaded.get_edges()
        if edge["edge_class"] is None
    ] == [85.0, 85.0]


def test_a_merge_that_is_refused_changes_nothing(
    network_with_minutes, tmp_path
):
    # A geograph holds 255 classes at most. The network has 7 classes. With
    # the 249 classes of the other geograph, the merged geograph would have
    # 256 classes.
    many_classes = {f"class_{class_id}": "road" for class_id in range(249)}
    other_path = str(tmp_path / "many_classes.scgraph")
    _write_network(
        other_path, FERRY_NODES, [(0, 1, 30.0, "class_0")], many_classes
    )
    other = GeoGraph.load_from_scgraph(other_path)

    with pytest.raises(ValueError, match="255 classes"):
        network_with_minutes.merge_with_other_geograph(
            other, connection_nodes=[[0.5, 0.0]]
        )

    # The network keeps its metric.
    assert [row["name"] for row in network_with_minutes.metrics] == [
        "length",
        "minutes",
    ]


def test_a_network_file_with_a_256th_class_is_refused(tmp_path):
    # The ferry line, in a network file with 256 classes. The class id 255 is
    # the id of no class, so a network holds 255 classes at most.
    classes = {f"class_{class_id}": "road" for class_id in range(256)}
    path = str(tmp_path / "256_classes.scgraph")
    _write_network(path, FERRY_NODES, [(0, 1, 30.0, "class_0")], classes)

    with pytest.raises(ValueError, match="255 classes"):
        GeoGraph.load_from_scgraph(path)


# create_metric: the weights of a metric


def test_weights_per_km_give_each_edge_the_weight_per_km_of_its_class_times_its_km(
    network_with_minutes,
):
    weights = _get_weight_of_each_edge(network_with_minutes, "minutes")

    assert weights == MINUTES_OF_EACH_EDGE


def test_an_edge_pays_the_weight_of_a_hub_that_it_enters_or_leaves(network):
    # A train waits 15 minutes at a rail terminal.
    network.create_metric(
        "minutes", **MINUTES, weight_at_hub={"rail_terminal": {"rail": 15.0}}
    )

    # The rail connector of 1 km between the west station and its terminal
    # takes 0.25 minute. The road connector of 2 km between the terminal and
    # the town takes 4 minutes: the hub weight does not name the edge mode
    # `road`.
    weights = _get_weight_of_each_edge(network, "minutes")
    assert (
        weights[WEST_STATION, WEST_TERMINAL],
        weights[WEST_TERMINAL, WEST_STATION],
        weights[WEST_TERMINAL, WEST_TOWN],
    ) == (0.25 + 15.0, 0.25 + 15.0, 4.0)


# The toll of each class: 7 on the motorway. The dict has the classes of the
# network only.
TOLL_OF_EACH_CLASS = {**dict.fromkeys(CLASSES, 0.0), "motorway": 7.0}


def _get_toll(edge):
    """The toll of the class of an edge. The function knows the edges of the
    network only: it fails for a dict that is no edge of the network."""
    return TOLL_OF_EACH_CLASS[edge["edge_class"]]


def test_a_function_gives_its_result_to_each_edge(network):
    network.create_metric(
        "toll", edge_weight_fn=_get_toll, off_graph_weight_per_km=0.25
    )

    assert _get_weight_of_each_edge(network, "toll") == {
        nodes: 7.0 if edge_class == "motorway" else 0.0
        for nodes, edge_class in CLASS_OF_EACH_EDGE.items()
    }


def test_edge_weights_set_the_weight_of_an_edge_and_none_closes_it(network):
    network.create_metric(
        "minutes",
        **MINUTES,
        edge_weights={
            (WEST_TOWN, EAST_TOWN): 75.0,
            (EAST_TOWN, WEST_TOWN): None,
        },
    )

    assert _get_weight_of_each_edge(network, "minutes") == {
        **MINUTES_OF_EACH_EDGE,
        (WEST_TOWN, EAST_TOWN): 75.0,
        (EAST_TOWN, WEST_TOWN): math.inf,
    }


def test_a_closed_class_closes_an_edge_of_zero_km(network):
    network.add_edge(WEST_TOWN, PORT, 0.0, edge_class="open_sea")

    network.create_metric(
        "minutes", weight_per_km={**MINUTES_PER_KM, "sea": None}
    )

    # Infinity times 0 km is not a number: the edge weighs infinity.
    weights = _get_weight_of_each_edge(network, "minutes")
    assert weights[WEST_TOWN, PORT] == math.inf


def test_a_geograph_without_classes_takes_one_weight_per_km_for_every_edge(
    geograph_without_classes,
):
    geograph_without_classes.create_metric("minutes", weight_per_km=2.0)

    # The one edge of 2.5 km has no class and no edge mode.
    assert geograph_without_classes.get_edges() == [
        {
            "origin_id": 0,
            "destination_id": 1,
            "length": 2.5,
            "edge_class": None,
            "edge_mode": None,
            "metric_weights": {"minutes": 5.0},
        }
    ]


def test_metrics_lists_the_row_of_each_metric_after_the_length(network):
    network.create_metric(
        "minutes",
        weight_per_km=3.0,
        unit="min",
        description="Three minutes per km.",
    )
    network.create_metric("cost", weighted_sum_of={"minutes": 2, "length": 0.5})
    network.create_metric(
        "toll", edge_weight_fn=_get_toll, off_graph_weight_per_km=0.25
    )

    # A metric without a description gets the text of its call.
    # `off_graph_weight_per_km` is the weight of 1 km of an off-graph leg. For
    # the cost, it is 2 × 3 minutes + 0.5 × 1 km. For the toll, the call gives
    # it.
    cost_call = "create_metric(weighted_sum_of={'minutes': 2, 'length': 0.5})"
    toll_call = (
        "create_metric(edge_weight_fn=_get_toll, off_graph_weight_per_km=0.25)"
    )
    assert network.metrics == [
        {"name": "length", "unit": "km"},
        {
            "name": "minutes",
            "unit": "min",
            "description": "Three minutes per km.",
            "off_graph_weight_per_km": 3.0,
        },
        {
            "name": "cost",
            "description": cost_call,
            "off_graph_weight_per_km": 6.5,
        },
        {
            "name": "toll",
            "description": toll_call,
            "off_graph_weight_per_km": 0.25,
        },
    ]


def _get_cost(edge):
    """The cost of an edge: 2 for each of its minutes, and 0.5 for each of its
    km."""
    return 2 * edge["metric_weights"]["minutes"] + 0.5 * edge["length"]


# Each case computes the metric `cost` from the metric `minutes`: the
# arguments of `create_metric`. The function reads the minutes of each edge.
# It is called for the edges only: the call gives the cost of 1 km of an
# off-graph leg, which takes 4 minutes.
COSTS_FROM_THE_MINUTES = {
    "a weighted sum": {"weighted_sum_of": {"minutes": 2, "length": 0.5}},
    "a function": {
        "edge_weight_fn": _get_cost,
        "off_graph_weight_per_km": 8.5,
    },
}


@pytest.mark.parametrize(
    "cost", COSTS_FROM_THE_MINUTES.values(), ids=COSTS_FROM_THE_MINUTES
)
def test_a_metric_keeps_its_weights_when_a_metric_that_it_was_computed_from_is_created_again(
    network_with_minutes, cost
):
    network_with_minutes.create_metric("cost", **cost)

    network_with_minutes.create_metric("minutes", weight_per_km=1.0)

    # The cost of an edge stays 2 times the minutes that the edge had when the
    # cost was created, plus 0.5 times its km.
    assert _get_weight_of_each_edge(network_with_minutes, "cost") == {
        nodes: 2 * minutes + 0.5 * KM_OF_EACH_EDGE[nodes]
        for nodes, minutes in MINUTES_OF_EACH_EDGE.items()
    }


def test_weights_per_km_weigh_an_edge_without_a_class_as_an_off_graph_leg(
    network,
):
    network.add_edge(WEST_TOWN, PORT, 80.0)

    network.create_metric("minutes", **MINUTES)

    # The new road has no class, so it takes the weight per km `off_graph`:
    # 80 km × 4 minutes = 320 minutes.
    weights = _get_weight_of_each_edge(network, "minutes")
    assert weights[WEST_TOWN, PORT] == 320.0


# create_metric: the calls that it refuses


def _get_negative_toll(edge):
    return -7.0 if edge["edge_class"] == "motorway" else 0.0


# Each case is a call that breaks one rule of `create_metric`: its arguments,
# and words of the error. The network has the metric `minutes`, for the sums.
REFUSED_METRICS = {
    # The call names something that the network lacks, or leaves out a weight
    # per km that the network needs: the error names it. The network has no
    # class and no edge mode `canal`, no node of a node mode `airport`, and no
    # edge from the junction to the port.
    "no weight per km for off_graph": (
        {"weight_per_km": {"road": 2.0, "rail": 0.25, "sea": 2.0}},
        "off_graph",
    ),
    "no weight per km for a class that has edges": (
        {"weight_per_km": {"road": 2.0, "rail": 0.25, "off_graph": 4.0}},
        "open_sea",
    ),
    "a weight per km for an edge mode that the network lacks": (
        {"weight_per_km": {**MINUTES_PER_KM, "canal": 2.0}},
        "canal",
    ),
    "a weight per km for a class that the network lacks": (
        {"weight_per_km": 2.0, "class_weight_per_km": {"canal": 2.0}},
        "canal",
    ),
    "a hub of a node mode that the network lacks": (
        {"weight_per_km": 2.0, "weight_at_hub": {"airport": {"road": 30.0}}},
        "airport",
    ),
    "a hub weight for an edge mode that the network lacks": (
        {"weight_per_km": 2.0, "weight_at_hub": {"port": {"canal": 30.0}}},
        "canal",
    ),
    "a hub weight for a class": (
        {"weight_per_km": 2.0, "weight_at_hub": {"port": {"open_sea": 30.0}}},
        "open_sea",
    ),
    "a hub weight that is not a number": (
        {
            "weight_per_km": 2.0,
            "weight_at_hub": {"port": {"sea": (10.0, 20.0)}},
        },
        "must be a number",
    ),
    "a weight for an edge that the network lacks": (
        {"weight_per_km": 2.0, "edge_weights": {(1, 7): 5.0}},
        "node 1 to node 7",
    ),
    # The three ways to compute a metric are the weights per km, a weighted
    # sum and a function. The weights of the classes and of the hubs go with
    # the weights per km.
    "no way to compute the metric": ({}, "exactly one of"),
    "weights per km and a sum": (
        {"weight_per_km": 2.0, "weighted_sum_of": {"length": 2}},
        "exactly one of",
    ),
    "a sum and the weights per km of classes": (
        {
            "weighted_sum_of": {"length": 2},
            "class_weight_per_km": {"motorway": 0.5},
        },
        "class_weight_per_km needs weight_per_km",
    ),
    "a sum and the weights at hubs": (
        {
            "weighted_sum_of": {"length": 2},
            "weight_at_hub": {"port": {"sea": 30.0}},
        },
        "weight_at_hub needs weight_per_km",
    ),
    # The sum cannot be computed.
    "a sum of a metric that the geograph lacks": (
        {"weighted_sum_of": {"speed": 2}},
        "unknown metric 'speed'",
    ),
    "a sum with a coefficient of zero": (
        {"weighted_sum_of": {"minutes": 0}},
        "coefficient of 'minutes'",
    ),
    "a sum with an infinite coefficient": (
        {"weighted_sum_of": {"minutes": math.inf}},
        "coefficient of 'minutes'",
    ),
    # The call gives a weight below zero or not a number: to every edge, to
    # the motorway, to the edge from the junction to the east town. The error
    # names the first such edge.
    "a weight per km below zero": ({"weight_per_km": -2.0}, "node 0 to node 1"),
    "a function that gives a toll below zero": (
        {"edge_weight_fn": _get_negative_toll, "off_graph_weight_per_km": 0.0},
        "node 0 to node 2",
    ),
    "an edge weight that is not a number": (
        {"weight_per_km": 2.0, "edge_weights": {(1, 2): math.nan}},
        "node 1 to node 2",
    ),
    # A function is called for the edges only: the call gives the weight of
    # 1 km of an off-graph leg, a finite number of zero or more. The two other
    # ways give this weight themselves.
    "a function without the weight of the off-graph legs": (
        {"edge_weight_fn": _get_toll},
        "edge_weight_fn needs off_graph_weight_per_km",
    ),
    "a function with a weight of the off-graph legs below zero": (
        {"edge_weight_fn": _get_toll, "off_graph_weight_per_km": -0.25},
        "off-graph leg",
    ),
    "weights per km and the weight of the off-graph legs": (
        {"weight_per_km": 2.0, "off_graph_weight_per_km": 4.0},
        "off_graph_weight_per_km needs edge_weight_fn",
    ),
    "a sum and the weight of the off-graph legs": (
        {"weighted_sum_of": {"length": 2}, "off_graph_weight_per_km": 4.0},
        "off_graph_weight_per_km needs edge_weight_fn",
    ),
}


@pytest.mark.parametrize(
    "arguments, cause", REFUSED_METRICS.values(), ids=REFUSED_METRICS
)
def test_create_metric_refuses_a_call_that_breaks_one_of_its_rules(
    network_with_minutes, arguments, cause
):
    with pytest.raises(ValueError, match=cause):
        network_with_minutes.create_metric("fare", **arguments)


def test_a_weight_per_km_is_refused_on_a_geograph_in_miles():
    geograph = GeoGraph(
        graph=[{1: 2.5}, {}], nodes=[[0, 0], [0, 1]], geograph_units="mi"
    )

    with pytest.raises(ValueError, match="km"):
        geograph.create_metric("minutes", weight_per_km=2.0)


# `length` is the metric of the lengths. A name has small letters, digits and
# `_`, and starts with a letter.
@pytest.mark.parametrize("name", ["length", "Minutes", "2nd_class"])
def test_a_metric_with_a_name_that_is_not_allowed_is_refused(network, name):
    with pytest.raises(ValueError, match=name):
        network.create_metric(name, weight_per_km=2.0)


# Removing a metric


def test_a_route_has_no_total_of_a_removed_metric(network_with_minutes):
    network_with_minutes.remove_metric("minutes")

    route = network_with_minutes.get_shortest_path(WEST_POINT, EAST_POINT)
    assert "metric_totals" not in route


def test_remove_metric_refuses_a_metric_that_the_geograph_lacks(
    network_with_minutes,
):
    with pytest.raises(ValueError, match="speed"):
        network_with_minutes.remove_metric("speed")


# An edit of the network


# Each case is an edit of the nodes or of the edges of the network.
EDITS = {
    "an added edge": lambda network, ferry: network.add_edge(
        WEST_TOWN, PORT, 85.0
    ),
    "a removed edge": lambda network, ferry: network.remove_edge(
        WEST_TOWN, EAST_TOWN
    ),
    "an added node": lambda network, ferry: network.add_coord_node(WEST_POINT),
    "a removed node": lambda network, ferry: network.remove_node(),
    "a merge": lambda network, ferry: network.merge_with_other_geograph(
        ferry, connection_nodes=[[0.5, 0.0]]
    ),
}


@pytest.mark.parametrize("edit", EDITS.values(), ids=EDITS)
def test_an_edit_removes_the_metrics_and_warns_with_their_names(
    network_read_with_minutes, ferry, edit
):
    # The geograph read the metric `minutes` from its file. It makes the
    # metric `cost` itself.
    network_read_with_minutes.create_metric(
        "cost", weighted_sum_of={"minutes": 2}
    )

    with pytest.warns(UserWarning, match="'minutes', 'cost'.*create_metric"):
        edit(network_read_with_minutes, ferry)

    assert network_read_with_minutes.metrics == [
        {"name": "length", "unit": "km"}
    ]


def test_an_edit_made_on_the_graph_object_removes_the_metrics_at_their_next_read(
    network_with_minutes,
):
    network_with_minutes.graph_object.add_edge(WEST_TOWN, PORT, 85.0)

    # The geograph sees the edit when it reads its metrics.
    with pytest.warns(UserWarning, match="'minutes'.*create_metric"):
        metrics = network_with_minutes.metrics
    assert metrics == [{"name": "length", "unit": "km"}]


def test_a_metric_created_again_after_an_edit_weighs_the_new_edge(
    network_with_minutes,
):
    with pytest.warns(UserWarning, match="minutes"):
        network_with_minutes.add_edge(
            WEST_TOWN, PORT, 80.0, symmetric=True, edge_class="primary"
        )

    network_with_minutes.create_metric("minutes", **MINUTES)

    # The new primary road of 80 km takes 120 minutes.
    assert _get_weight_of_each_edge(network_with_minutes, "minutes") == {
        **MINUTES_OF_EACH_EDGE,
        (WEST_TOWN, PORT): 120.0,
        (PORT, WEST_TOWN): 120.0,
    }


# Queries by a metric


def test_a_route_by_a_metric_has_the_smallest_total_of_this_metric(
    network_with_minutes,
):
    network_with_minutes.create_metric(
        "cost", weighted_sum_of={"minutes": 2, "length": 0.5}
    )

    route = network_with_minutes.get_shortest_path(
        WEST_POINT,
        EAST_POINT,
        metric="minutes",
        off_graph_circuity=2,
        output_path=True,
    )

    # The railway: 31 minutes and 96 km, so a cost of 2 × 31 + 0.5 × 96 = 110.
    # An off-graph leg counts its km times the off-graph circuity, and not
    # times the node addition circuity of the search, which is 4. 1 km of it
    # takes 4 minutes and costs 2 × 4 + 0.5 = 8.5.
    off_graph_km = 2 * OFF_GRAPH_LEG_KM * 2
    assert route["path"] == RAILWAY_PATH
    assert route["length"] == pytest.approx(96 + off_graph_km)
    assert route["metric_totals"] == {
        "minutes": pytest.approx(31 + off_graph_km * 4.0),
        "cost": pytest.approx(110 + off_graph_km * 8.5),
    }


def test_a_route_by_the_length_has_the_total_of_each_metric(
    network_with_minutes,
):
    route = network_with_minutes.get_shortest_path(WEST_POINT, EAST_POINT)

    # The shortest route takes the primary road: 80 km at 1.5 minutes per km.
    assert route["metric_totals"] == {
        "minutes": pytest.approx(120 + 2 * OFF_GRAPH_LEG_KM * 4.0)
    }


# The metric `minutes` closes the railway. The metric `cost` is a sum of the
# minutes and of the length: an edge that is closed in a metric is closed in a
# sum of this metric.
@pytest.mark.parametrize("metric", ["minutes", "cost"])
def test_a_route_by_a_metric_avoids_a_class_that_the_metric_closes(
    network, metric
):
    network.create_metric(
        "minutes",
        weight_per_km={**MINUTES_PER_KM, "rail": None},
        class_weight_per_km=CLASS_MINUTES_PER_KM,
    )
    network.create_metric("cost", weighted_sum_of={"minutes": 2, "length": 0.5})

    route = network.get_shortest_path(
        WEST_POINT, EAST_POINT, metric=metric, output_path=True
    )

    # Without the railway, the motorway is the fastest route. It is also the
    # cheapest: 2 × 50 + 0.5 × 100 = 150, against 2 × 120 + 0.5 × 80 = 280
    # for the primary road.
    assert route["path"] == [WEST_TOWN, EAST_TOWN]


def test_the_error_for_a_route_that_a_metric_closes_names_the_metric(network):
    network.create_metric(
        "minutes", weight_per_km={**MINUTES_PER_KM, "sea": None}
    )

    # The destination snaps to the open sea node, which only sea lanes reach.
    # A route by the length exists: the error names the metric that has none.
    with pytest.raises(PathNotFoundError, match="by the metric 'minutes'"):
        network.get_shortest_path(
            WEST_POINT,
            {"latitude": -0.065, "longitude": 2.5},
            metric="minutes",
            node_addition_modes=["road", "sea"],
        )


def test_off_graph_legs_that_weigh_nothing_do_not_make_a_route_direct(network):
    network.create_metric(
        "minutes",
        weight_per_km={**MINUTES_PER_KM, "off_graph": 0.0},
        class_weight_per_km=CLASS_MINUTES_PER_KM,
    )

    route = network.get_shortest_path(
        WEST_POINT, EAST_POINT, metric="minutes", output_path=True
    )

    assert route["path"] == RAILWAY_PATH


def _get_twice_the_length(edge):
    return 2 * edge["length"]


def test_a_metric_of_a_geograph_in_miles_weighs_an_off_graph_leg_by_its_miles():
    # One edge of 2.5 miles. The metric `cost` is a weighted sum, and the
    # metric `toll` is a function: each gives the weight 2 to 1 mile. The call
    # of the function gives the weight of 1 km of an off-graph leg. 1 km is
    # 3959 / 6371 mile: the radius of the Earth in miles and in km.
    geograph_in_miles = GeoGraph(
        graph=[{1: 2.5}, {}], nodes=[[0, 0], [0, 1]], geograph_units="mi"
    )
    geograph_in_miles.create_metric("cost", weighted_sum_of={"length": 2})
    geograph_in_miles.create_metric(
        "toll",
        edge_weight_fn=_get_twice_the_length,
        off_graph_weight_per_km=2 * 3959 / 6371,
    )

    route = geograph_in_miles.get_shortest_path(
        {"latitude": 0, "longitude": -0.1},
        {"latitude": 0, "longitude": 1.1},
        metric="cost",
        output_units="mi",
    )

    # The length of the route is in miles, with its two off-graph legs.
    two_per_mile = pytest.approx(2 * route["length"])
    assert route["metric_totals"] == {
        "cost": two_per_mile,
        "toll": two_per_mile,
    }


# The two functions of a geograph that give a bound in km between two nodes
@pytest.mark.parametrize("bound", ["haversine", "cheap_ruler"])
def test_a_star_with_a_bound_of_the_geograph_finds_the_best_route(
    network_with_minutes, bound
):
    # The motorway reaches the east town in one edge and 50 minutes. The
    # railway, the best route, has five edges. The bound of a node is its km
    # to the destination times 0.25, the fewest minutes that 1 km of an edge
    # takes. A bound in km would be above the 31 minutes of the railway, and
    # the search would stop at the motorway.
    route = network_with_minutes.get_shortest_path(
        WEST_POINT,
        EAST_POINT,
        metric="minutes",
        algorithm_fn="a_star",
        algorithm_kwargs={"heuristic_fn": getattr(network_with_minutes, bound)},
        output_path=True,
    )

    assert route["path"] == RAILWAY_PATH


def test_length_only_with_a_metric_gives_the_total_of_this_metric_alone(
    network_with_minutes,
):
    result = network_with_minutes.get_shortest_path(
        WEST_POINT, EAST_POINT, metric="minutes", length_only=True
    )

    assert result == {
        "metric_totals": {
            "minutes": pytest.approx(31 + 2 * OFF_GRAPH_LEG_KM * 4.0)
        }
    }


def test_get_path_weight_gives_the_total_of_a_metric_along_a_route(
    network_with_minutes,
):
    shortest_route = network_with_minutes.get_shortest_path(
        WEST_POINT, EAST_POINT, output_path=True
    )

    minutes = network_with_minutes.get_path_weight(
        shortest_route, metric="minutes"
    )

    # The shortest route takes the primary road: 80 km at 1.5 minutes per km.
    assert minutes == pytest.approx(120 + 2 * OFF_GRAPH_LEG_KM * 4.0)


# Each case is a method that takes a metric, and its other arguments. The
# geograph has no metric `speed`.
QUERIES_BY_A_METRIC = {
    "get_shortest_path": (WEST_POINT, EAST_POINT),
    "get_path_weight": ({"path": [0], "coordinate_path": [[0, 0]]},),
}


@pytest.mark.parametrize(
    "method, arguments", QUERIES_BY_A_METRIC.items(), ids=QUERIES_BY_A_METRIC
)
def test_a_query_by_a_metric_that_the_geograph_lacks_is_refused(
    network, method, arguments
):
    with pytest.raises(ValueError, match="speed"):
        getattr(network, method)(*arguments, metric="speed")


def test_reduce_reduces_the_graph_of_each_metric_and_keeps_its_routes(
    network_with_minutes,
):
    network_with_minutes.create_metric(
        "cost", weighted_sum_of={"minutes": 2, "length": 0.5}
    )
    # This query builds the graph of the minutes. The graph of the cost is
    # built after the reduction.
    route = network_with_minutes.get_shortest_path(
        WEST_POINT, EAST_POINT, metric="minutes"
    )

    network_with_minutes.reduce()

    minutes_graph = network_with_minutes.get_graph_object("minutes")
    cost_graph = network_with_minutes.get_graph_object("cost")
    assert minutes_graph.reduced_graph is not None
    assert cost_graph.reduced_graph is not None
    assert (
        network_with_minutes.get_shortest_path(
            WEST_POINT, EAST_POINT, metric="minutes"
        )
        == route
    )


# The distance matrix


# Each case gives the arguments of a matrix between the west point and the
# east point, and the total that it holds from one point to the other. 1 km
# of an off-graph leg takes 4 minutes.
TOTALS_OF_A_MATRIX = {
    # The fastest route is the railway: 31 minutes.
    "the totals of the metric of the routes": (
        {"metric": "minutes"},
        31 + 2 * OFF_GRAPH_LEG_KM * 4.0,
    ),
    # The railway is 96 km long.
    "the lengths of the fastest routes": (
        {"metric": "minutes", "output_metric": "length"},
        96 + 2 * OFF_GRAPH_LEG_KM,
    ),
    # The shortest route is the primary road: 80 km at 1.5 minutes per km.
    "the minutes of the shortest routes": (
        {"metric": "length", "output_metric": "minutes"},
        120 + 2 * OFF_GRAPH_LEG_KM * 4.0,
    ),
    # Each point snaps to the station of its town, 0.02 degree north of the
    # equator and 0.1 degree of longitude away. The shortest route between the
    # two stations takes the primary road: 1 + 2 + 80 + 2 + 1 = 86 km.
    "the lengths between points that snap to the node modes of the call": (
        {"node_addition_modes": ["rail"]},
        86 + 2 * 6371 * math.radians(math.hypot(0.02, 0.1)),
    ),
}


@pytest.mark.parametrize(
    "arguments, total", TOTALS_OF_A_MATRIX.values(), ids=TOTALS_OF_A_MATRIX
)
def test_distance_matrix_gives_the_total_between_each_pair_of_points(
    network_with_minutes, arguments, total
):
    matrix = network_with_minutes.distance_matrix(
        [WEST_POINT, EAST_POINT], **arguments
    )

    assert matrix == [[0.0, pytest.approx(total)], [pytest.approx(total), 0.0]]


# The legs of a route


def test_the_legs_of_a_route_are_its_parts_on_one_mode(network_with_minutes):
    route = network_with_minutes.get_shortest_path(
        WEST_POINT,
        EAST_POINT,
        metric="minutes",
        output_units="m",
        output_legs=True,
    )

    # The fastest route: a road connector from the west town to its terminal,
    # the railway between the two terminals, and a road connector to the east
    # town. An off-graph leg joins each point of the query to its town. The
    # lengths are in metres, the unit of the query: 96 km on the network.
    off_graph_leg = ("off_graph", pytest.approx(1000 * OFF_GRAPH_LEG_KM), {})
    road_leg = ("road", 2000.0, {"road_connector": 2000.0})
    rail_leg = (
        "rail",
        92000.0,
        {"rail_connector": 2000.0, "rail_main": 90000.0},
    )
    assert [
        (leg["mode"], leg["length"], leg["class_lengths"])
        for leg in route["legs"]
    ] == [off_graph_leg, road_leg, rail_leg, road_leg, off_graph_leg]
    assert route["transfers"] == [
        {"node_id": WEST_TERMINAL, "node_mode": "rail_terminal"},
        {"node_id": EAST_TERMINAL, "node_mode": "rail_terminal"},
    ]
    assert route["length"] == pytest.approx(1000 * (96 + 2 * OFF_GRAPH_LEG_KM))


def test_the_legs_of_a_route_add_up_to_its_length_and_to_its_totals(
    network_with_minutes,
):
    network_with_minutes.create_metric(
        "cost", weighted_sum_of={"minutes": 2, "length": 0.5}
    )

    route = network_with_minutes.get_shortest_path(
        WEST_POINT,
        EAST_POINT,
        metric="minutes",
        off_graph_circuity=2,
        output_legs=True,
    )

    legs = route["legs"]
    assert sum(leg["length"] for leg in legs) == pytest.approx(route["length"])
    assert {
        name: sum(leg["metric_totals"][name] for leg in legs)
        for name in ("minutes", "cost")
    } == pytest.approx(route["metric_totals"])


# Each case gives a destination whose route from the west point is direct, and
# the points of this route: it has no edge. The first destination is 0.05
# degree east of the west town: both points of the query snap to this town.
# The second one is 0.01 degree from the origin: the straight line is shorter
# than the way to the town.
DIRECT_ROUTES = {
    "both points snap to one node": (
        [0.0, 0.05],
        [[0.0, -0.1], [0.0, 0.0], [0.0, 0.05]],
    ),
    "the straight line is shorter": ([0.0, -0.11], [[0.0, -0.1], [0.0, -0.11]]),
}


@pytest.mark.parametrize(
    "destination, coordinate_path", DIRECT_ROUTES.values(), ids=DIRECT_ROUTES
)
def test_a_route_without_an_edge_is_one_leg_off_the_graph(
    network, destination, coordinate_path
):
    route = network.get_shortest_path(
        WEST_POINT,
        {"latitude": destination[0], "longitude": destination[1]},
        output_legs=True,
    )

    assert route["legs"] == [
        {
            "mode": "off_graph",
            "length": pytest.approx(route["length"]),
            "class_lengths": {},
            "coordinate_path": coordinate_path,
        }
    ]


def test_the_edges_of_a_geograph_without_classes_make_one_leg_of_no_mode(
    geograph_without_classes,
):
    route = geograph_without_classes.get_shortest_path(
        {"latitude": 0, "longitude": -0.1},
        {"latitude": 0, "longitude": 1.1},
        output_legs=True,
    )

    assert [(leg["mode"], leg["class_lengths"]) for leg in route["legs"]] == [
        ("off_graph", {}),
        (None, {None: 2.5}),
        ("off_graph", {}),
    ]


def test_the_coordinate_paths_of_the_legs_follow_the_one_of_the_route():
    # A road of two edges. The first edge has a bend: one point of its shape.
    road_with_a_bend = GeoGraph(
        graph=[{1: 60.0}, {2: 60.0}, {}],
        nodes=[[0.0, 0.0], [0.0, 0.5], [0.0, 1.0]],
        intermediate_nodes=[{1: [[0.1, 0.25]]}, {}, {}],
    )

    route = road_with_a_bend.get_shortest_path(
        {"latitude": 0.0, "longitude": -0.1},
        {"latitude": 0.0, "longitude": 1.1},
        output_coordinate_path="list_of_dicts",
        output_legs=True,
    )

    # A leg starts at the point where the leg before it ends.
    off_graph_leg, road_leg, last_off_graph_leg = (
        leg["coordinate_path"] for leg in route["legs"]
    )
    assert (
        off_graph_leg + road_leg[1:] + last_off_graph_leg[1:]
        == route["coordinate_path"]
    )


# The node modes that a query point snaps to

# Two points on the equator, each with a road node as its closest node. The
# first one is 0.01 degree west of the east town. Its closest rail node is the
# east station, 0.022 degree away. The second one is 0.05 degree west of the
# junction. Its closest rail node is the west station, 0.3 degree away: the
# east station is 0.4 degree away.
POINT_NEAR_THE_EAST_TOWN = {"latitude": 0.0, "longitude": 0.69}
POINT_NEAR_THE_JUNCTION = {"latitude": 0.0, "longitude": 0.3}


# The other tests snap with the default type, 'closest'.
@pytest.mark.parametrize("node_addition_type", ["quadrant", "all"])
def test_a_query_point_snaps_only_to_nodes_of_the_node_modes_of_the_query(
    network, node_addition_type
):
    route = network.get_shortest_path(
        POINT_NEAR_THE_EAST_TOWN,
        POINT_NEAR_THE_JUNCTION,
        node_addition_modes=["rail"],
        node_addition_type=node_addition_type,
        output_path=True,
    )

    # A route that may start at any node starts at the east town.
    path = route["path"]
    assert (path[0], path[-1]) == (EAST_STATION, WEST_STATION)


def test_a_query_point_snaps_to_the_node_modes_that_the_network_file_names(
    network,
):
    # The file names the node mode `road` (`_write_network`). The point is 0.01
    # degree north of the east station and 0.03 degree north of the east town.
    route = network.get_shortest_path(
        WEST_POINT, {"latitude": 0.03, "longitude": 0.7}, output_path=True
    )

    assert route["path"][-1] == EAST_TOWN


def test_a_query_point_snaps_to_a_node_that_the_user_added(network):
    # The file names the node mode `road` for the query points. This query
    # builds the snapping index of the road nodes.
    network.get_shortest_path(WEST_POINT, EAST_POINT)

    # The new node has no node mode of the file. It is at the origin of the next
    # query, 0.1 degree west of the west town.
    node_id = network.add_coord_node(WEST_POINT)

    route = network.get_shortest_path(WEST_POINT, EAST_POINT, output_path=True)
    assert route["path"][0] == node_id


def test_a_query_point_snaps_to_any_node_when_no_node_has_a_default_node_mode(
    sea_network,
):
    # The origin is 0.01 degree west of the port, and the destination is 0.05
    # degree east of the open sea node.
    route = sea_network.get_shortest_path(
        {"latitude": -0.025, "longitude": 0.69},
        {"latitude": -0.065, "longitude": 2.5},
    )

    # The points of the port, of the coast and of the open sea
    assert route["coordinate_path"][1:-1] == [
        [-0.025, 0.7],
        [-0.065, 0.7],
        [-0.065, 2.45],
    ]


# Each case gives the node modes of a query. No node of the geograph has the
# node mode `road`. Its file has no node mode `canal`.
REFUSED_NODE_MODES = {
    "a node mode that no node has": ["road"],
    "a node mode that the file lacks": ["sea", "canal"],
    "no mode": [],
}


@pytest.mark.parametrize(
    "node_addition_modes", REFUSED_NODE_MODES.values(), ids=REFUSED_NODE_MODES
)
def test_a_query_refuses_node_modes_that_its_points_cannot_snap_to(
    sea_network, node_addition_modes
):
    with pytest.raises(ValueError, match="node_addition_modes"):
        sea_network.get_shortest_path(
            {"latitude": -0.025, "longitude": 0.69},
            {"latitude": -0.065, "longitude": 2.5},
            node_addition_modes=node_addition_modes,
        )


def test_a_query_refuses_node_modes_on_a_geograph_without_node_modes(
    geograph_without_classes,
):
    # The one node mode of this geograph has no name: a query cannot name it.
    with pytest.raises(ValueError, match="node_addition_modes"):
        geograph_without_classes.get_shortest_path(
            {"latitude": 0, "longitude": 0},
            {"latitude": 0, "longitude": 1},
            node_addition_modes=[None],
        )


# A network read from a file with a metric


def test_a_saved_and_loaded_geograph_keeps_its_metrics_and_its_default_node_modes(
    network_with_minutes, network_read_with_minutes
):
    # The fixture `network_read_with_minutes` saved the same network with the
    # same metric, and loaded the file. The file names the node mode `road` for
    # the query points (`_write_network`).
    assert network_read_with_minutes.metrics == network_with_minutes.metrics
    assert network_read_with_minutes.default_node_addition_modes == ["road"]
    assert network_read_with_minutes.get_shortest_path(
        WEST_POINT, EAST_POINT, metric="minutes"
    ) == network_with_minutes.get_shortest_path(
        WEST_POINT, EAST_POINT, metric="minutes"
    )
