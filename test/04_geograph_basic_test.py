import copy
from itertools import permutations

import pytest
from scgraph import GeoGraph, Graph
from helpers import assert_result

# The [latitude, longitude] of six nodes one degree apart
NODES = [
    [0, 0],
    [0, 1],
    [1, 0],
    [1, 1],
    [1, 2],
    [2, 1],
]
# The links of the six nodes, in both directions with the same weight (the
# weights are not the distances between the nodes)
LINKS = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
]


def as_point(node):
    return {"latitude": node[0], "longitude": node[1]}


def test_geograph_of_valid_links_and_coordinates_is_valid():
    geograph = GeoGraph(nodes=NODES, graph=LINKS)

    geograph.validate()
    geograph.validate_nodes()


def test_route_gives_its_length_and_the_coordinates_of_its_nodes():
    geograph = GeoGraph(nodes=NODES, graph=LINKS)

    route = geograph.get_shortest_path(
        origin_node={"latitude": 0, "longitude": 0},
        destination_node={"latitude": 2, "longitude": 1},
    )

    # The path of least weight from node 0 to node 5 is 0 -> 2 -> 1 -> 3 -> 5
    # (1 + 2 + 1 + 6). The requested origin and destination come first and
    # last; here they are the points of nodes 0 and 5, which follow them.
    assert_result(
        route,
        {
            "coordinate_path": [
                [0, 0],
                [0, 0],
                [1, 0],
                [0, 1],
                [1, 1],
                [2, 1],
                [2, 1],
            ],
            "length": 10,
        },
    )


def shape_of_link(u, v):
    """Two points on the link u -> v, at one third and two thirds of the way,
    moved north from a lower to a higher node id and south the other way: the
    shapes of u -> v and v -> u differ. Rounded to 1e-7 degree, as a network
    file stores them."""
    (lat_u, lon_u), (lat_v, lon_v) = NODES[u], NODES[v]
    offset = 0.01 if u < v else -0.01
    return [
        [
            round(lat_u + (lat_v - lat_u) * t + offset, 7),
            round(lon_u + (lon_v - lon_u) * t, 7),
        ]
        for t in (1 / 3, 2 / 3)
    ]


# Every directed link has a shape, except 3 <-> 5: node 5 is only reached
# through that link, so routes to node 5 end with a link without a shape
LINK_SHAPES = [
    {v: shape_of_link(u, v) for v in links if {u, v} != {3, 5}}
    for u, links in enumerate(LINKS)
]


# A route must be the same on a geograph built in memory and on the same
# geograph saved to a network file and read back: a test that takes this
# fixture runs once with each.
@pytest.fixture(params=["built", "read_from_a_network_file"])
def geograph_with_link_shapes(request, tmp_path):
    geograph = GeoGraph(
        nodes=copy.deepcopy(NODES),
        graph=copy.deepcopy(LINKS),
        intermediate_nodes=copy.deepcopy(LINK_SHAPES),
    )
    if request.param == "built":
        return geograph
    path = str(tmp_path / "shaped.scgraph")
    geograph.save_as_scgraph(path)
    return GeoGraph.load_from_scgraph(path)


# The tests below run on the graph as it is (0) and after one pass of
# reduction (1), which must not change a route.
with_and_without_reduction = pytest.mark.parametrize(
    "reduce_iterations", [0, 1]
)


@with_and_without_reduction
def test_route_joins_its_two_nodes_and_has_the_weight_of_its_links(
    geograph_with_link_shapes, reduce_iterations
):
    geograph_with_link_shapes.reduce(iterations=reduce_iterations)

    for origin_id, destination_id in permutations(range(6), 2):
        route = geograph_with_link_shapes.get_shortest_path(
            origin_node=as_point(NODES[origin_id]),
            destination_node=as_point(NODES[destination_id]),
            output_path=True,
        )

        path = route["path"]
        assert path[0] == origin_id
        assert path[-1] == destination_id
        assert route["length"] == pytest.approx(
            sum(LINKS[u][v] for u, v in zip(path, path[1:]))
        )


@with_and_without_reduction
def test_coordinate_path_holds_each_node_and_the_shape_of_each_link(
    geograph_with_link_shapes, reduce_iterations
):
    geograph_with_link_shapes.reduce(iterations=reduce_iterations)

    for origin_id, destination_id in permutations(range(6), 2):
        route = geograph_with_link_shapes.get_shortest_path(
            origin_node=as_point(NODES[origin_id]),
            destination_node=as_point(NODES[destination_id]),
            output_path=True,
        )

        # The requested origin, the first node, then for each link of the path
        # its shape (if it has one) and the node it leads to, then the
        # requested destination
        path = route["path"]
        expected = [NODES[origin_id], NODES[origin_id]]
        for u, v in zip(path, path[1:]):
            expected += LINK_SHAPES[u].get(v, []) + [NODES[v]]
        expected.append(NODES[destination_id])
        assert route["coordinate_path"] == expected, (origin_id, destination_id)


@with_and_without_reduction
def test_route_between_two_points_far_from_the_network_is_a_straight_line(
    geograph_with_link_shapes, reduce_iterations
):
    geograph_with_link_shapes.reduce(iterations=reduce_iterations)

    # The two points are much closer to each other (0.01 degree) than to any
    # node: no search of the network
    route = geograph_with_link_shapes.get_shortest_path(
        origin_node={"latitude": 10, "longitude": 10},
        destination_node={"latitude": 10, "longitude": 10.01},
    )

    assert route["coordinate_path"] == [[10, 10], [10, 10.01]]


@with_and_without_reduction
def test_route_starts_at_a_node_added_after_loading(
    geograph_with_link_shapes, reduce_iterations
):
    geograph_with_link_shapes.reduce(iterations=reduce_iterations)
    # The added node has links to the network, and those links have no shape
    added_point = {"latitude": 3, "longitude": 1.5}
    geograph_with_link_shapes.add_coord_node(added_point)

    route = geograph_with_link_shapes.get_shortest_path(
        added_point,
        {"latitude": 0, "longitude": 1.5},
        node_addition_type="all",
    )

    # The requested origin, then the added node at the same place
    assert route["coordinate_path"][:2] == [[3, 1.5], [3, 1.5]]


def test_custom_algorithm_finds_the_same_routes_on_a_reduced_geograph():
    def custom_dijkstra(origin_id, destination_id, graph):
        return Graph(graph).dijkstra(origin_id, destination_id)

    unreduced = GeoGraph(nodes=NODES, graph=LINKS)
    reduced = GeoGraph(nodes=NODES, graph=LINKS)
    reduced.reduce()

    for origin, destination in permutations(NODES, 2):
        query = {
            "origin_node": as_point(origin),
            "destination_node": as_point(destination),
            "algorithm_fn": custom_dijkstra,
        }
        expected = unreduced.get_shortest_path(**query)
        assert reduced.get_shortest_path(**query) == expected
