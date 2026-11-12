import copy
from itertools import permutations
import pytest
from scgraph import GeoGraph, Graph
from helpers import assert_result

_NODES = [
    [0, 0],
    [0, 1],
    [1, 0],
    [1, 1],
    [1, 2],
    [2, 1],
]
_GRAPH = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
]
_EXPECTED = {
    "coordinate_path": [[0, 0], [0, 0], [1, 0], [0, 1], [1, 1], [2, 1], [2, 1]],
    "length": 10,
}


@pytest.fixture(scope="module")
def basic_geograph():
    return GeoGraph(nodes=_NODES, graph=_GRAPH)


def test_graph_validation(basic_geograph):
    basic_geograph.validate()


def test_node_validation(basic_geograph):
    basic_geograph.validate_nodes()


def test_shortest_path(basic_geograph):
    assert_result(
        basic_geograph.get_shortest_path(
            origin_node={"latitude": 0, "longitude": 0},
            destination_node={"latitude": 2, "longitude": 1},
        ),
        _EXPECTED,
    )


def test_coordinate_path_holds_each_node_and_the_shape_of_each_link():
    # Three nodes on the equator, linked 0 - 1 - 2. The shape of a link is the
    # list of the points that the link passes between its two nodes.
    nodes = [[0, 0], [0, 1], [0, 2]]
    links = [{1: 1}, {0: 1, 2: 1}, {1: 1}]
    # The link 0 -> 1 bends to the north and the link 1 -> 0 bends to the
    # south. The links between nodes 1 and 2 have no shape.
    link_shapes = [{1: [[0.1, 0.5]]}, {0: [[-0.1, 0.5]]}, {}]
    geograph = GeoGraph(
        nodes=nodes, graph=links, intermediate_nodes=link_shapes
    )

    route = geograph.get_shortest_path(
        origin_node={"latitude": 0, "longitude": 0},
        destination_node={"latitude": 0, "longitude": 2},
    )

    assert route["coordinate_path"] == [
        [0, 0],  # the requested origin
        [0, 0],  # node 0, which is at the same place
        [0.1, 0.5],  # the shape of the link 0 -> 1
        [0, 1],  # node 1
        [0, 2],  # node 2
        [0, 2],  # the requested destination
    ]


def _point(node):
    return {"latitude": node[0], "longitude": node[1]}


def _shape_of_link(u, v):
    """Two points on the link u -> v, at one third and at two thirds of the way.
    They are moved 0.01 degree north when u < v and south when u > v, so the
    shapes of u -> v and of v -> u differ. They are rounded to 1e-7 degree, as
    a network file stores them."""
    (lat_u, lon_u), (lat_v, lon_v) = _NODES[u], _NODES[v]
    offset = 0.01 if u < v else -0.01
    return [
        [
            round(lat_u + (lat_v - lat_u) * t + offset, 7),
            round(lon_u + (lon_v - lon_u) * t, 7),
        ]
        for t in (1 / 3, 2 / 3)
    ]


# The shape of every link of _GRAPH, in each direction. The links 3 -> 5 and
# 5 -> 3 have none: every route to node 5 ends with a link without a shape.
_LINK_SHAPES = [
    {v: _shape_of_link(u, v) for v in links if {u, v} != {3, 5}}
    for u, links in enumerate(_GRAPH)
]


def _geograph_with_link_shapes():
    return GeoGraph(
        nodes=copy.deepcopy(_NODES),
        graph=copy.deepcopy(_GRAPH),
        intermediate_nodes=copy.deepcopy(_LINK_SHAPES),
    )


def _save_and_read_back(geograph, tmp_path):
    """Save the geograph to a network file and return the geograph read from
    that file."""
    filename = str(tmp_path / "shaped.scgraph")
    geograph.save_as_scgraph(filename)
    return GeoGraph.load_from_scgraph(filename)


def test_every_coordinate_path_follows_the_links_of_its_path():
    geograph = _geograph_with_link_shapes()

    for origin_id, destination_id in permutations(range(6), 2):
        route = geograph.get_shortest_path(
            origin_node=_point(_NODES[origin_id]),
            destination_node=_point(_NODES[destination_id]),
            output_path=True,
        )

        # The requested origin and the first node, which are at the same place.
        # Then, for each link of the path, the shape of the link and the node
        # at its end. Then the requested destination.
        expected = [_NODES[origin_id], _NODES[origin_id]]
        for u, v in zip(route["path"], route["path"][1:]):
            expected += _LINK_SHAPES[u].get(v, []) + [_NODES[v]]
        expected.append(_NODES[destination_id])
        assert route["path"][-1] == destination_id
        assert route["coordinate_path"] == expected


def test_reduction_changes_no_route_of_a_geograph_with_link_shapes():
    unreduced = _geograph_with_link_shapes()
    reduced = _geograph_with_link_shapes()

    reduced.reduce(iterations=1)

    for origin, destination in permutations(_NODES, 2):
        query = {
            "origin_node": _point(origin),
            "destination_node": _point(destination),
            "output_path": True,
        }
        expected = unreduced.get_shortest_path(**query)
        assert reduced.get_shortest_path(**query) == expected


def test_network_file_changes_no_route_of_a_geograph_with_link_shapes(
    tmp_path,
):
    saved = _geograph_with_link_shapes()

    read_back = _save_and_read_back(saved, tmp_path)

    for origin, destination in permutations(_NODES, 2):
        query = {
            "origin_node": _point(origin),
            "destination_node": _point(destination),
            "output_path": True,
        }
        expected = saved.get_shortest_path(**query)
        assert read_back.get_shortest_path(**query) == expected


def test_reduction_changes_no_route_of_a_geograph_read_from_a_network_file(
    tmp_path,
):
    # A geograph read from a network file reads the shapes of its links from
    # the file. The reduction must work on these shapes too.
    unreduced = _geograph_with_link_shapes()
    reduced = _save_and_read_back(unreduced, tmp_path)

    reduced.reduce(iterations=1)

    for origin, destination in permutations(_NODES, 2):
        query = {
            "origin_node": _point(origin),
            "destination_node": _point(destination),
            "output_path": True,
        }
        expected = unreduced.get_shortest_path(**query)
        assert reduced.get_shortest_path(**query) == expected


def test_route_between_two_points_far_from_the_network_is_a_straight_line():
    geograph = _geograph_with_link_shapes()

    # The two points are 0.01 degree apart and about 12 degrees away from the
    # nearest node: the route does not enter the network.
    route = geograph.get_shortest_path(
        origin_node={"latitude": 10, "longitude": 10},
        destination_node={"latitude": 10, "longitude": 10.01},
    )

    assert route["coordinate_path"] == [[10, 10], [10, 10.01]]


def test_route_from_an_added_node_starts_with_that_node():
    geograph = _geograph_with_link_shapes()
    # add_coord_node links the new node to the nodes around it. These new
    # links have no shape.
    added_point = {"latitude": 3, "longitude": 1.5}
    geograph.add_coord_node(added_point)

    # node_addition_type="all" joins the requested origin to every node
    # around it, so also to the added node, which is at the same place.
    route = geograph.get_shortest_path(
        origin_node=added_point,
        destination_node={"latitude": 0, "longitude": 1.5},
        node_addition_type="all",
    )

    # The requested origin, then the added node. The rest of the route follows
    # links that have a shape, which the tests above check.
    assert route["coordinate_path"][:2] == [[3, 1.5], [3, 1.5]]


def test_route_from_a_node_added_to_a_reduced_geograph_read_from_a_file(
    tmp_path,
):
    # The same requirement as the test above, on a geograph that was read
    # from a network file and then reduced: both change how the geograph
    # stores its nodes and links.
    geograph = _save_and_read_back(_geograph_with_link_shapes(), tmp_path)
    geograph.reduce(iterations=1)
    added_point = {"latitude": 3, "longitude": 1.5}
    geograph.add_coord_node(added_point)

    route = geograph.get_shortest_path(
        origin_node=added_point,
        destination_node={"latitude": 0, "longitude": 1.5},
        node_addition_type="all",
    )

    assert route["coordinate_path"][:2] == [[3, 1.5], [3, 1.5]]


def test_custom_algorithm_finds_the_same_routes_on_a_reduced_geograph():
    # The custom algorithm receives the graph as a list of dictionaries and
    # runs Dijkstra on it.
    def custom_dijkstra(origin_id, destination_id, graph):
        return Graph(graph).dijkstra(origin_id, destination_id)

    unreduced = GeoGraph(nodes=_NODES, graph=_GRAPH)
    reduced = GeoGraph(nodes=_NODES, graph=_GRAPH)

    reduced.reduce()

    for origin, destination in permutations(_NODES, 2):
        query = {
            "origin_node": _point(origin),
            "destination_node": _point(destination),
            "algorithm_fn": custom_dijkstra,
        }
        expected = unreduced.get_shortest_path(**query)
        assert reduced.get_shortest_path(**query) == expected
