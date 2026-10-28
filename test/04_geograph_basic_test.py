import copy
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


def _shape(u, v):
    """Two shape points on the link u -> v, ordered from u to v, offset by direction"""
    (lat_u, lon_u), (lat_v, lon_v) = _NODES[u], _NODES[v]
    offset = 0.01 if u < v else -0.01
    return [
        [lat_u + (lat_v - lat_u) * t + offset, lon_u + (lon_v - lon_u) * t]
        for t in (1 / 3, 2 / 3)
    ]


# Every directed link has a shape, except 3 <-> 5 (node 5 is only reached through it)
_INTERMEDIATE_NODES = [
    {v: _shape(u, v) for v in links if {u, v} != {3, 5}}
    for u, links in enumerate(_GRAPH)
]


def _shaped_geograph():
    return GeoGraph(
        nodes=copy.deepcopy(_NODES),
        graph=copy.deepcopy(_GRAPH),
        intermediate_nodes=copy.deepcopy(_INTERMEDIATE_NODES),
    )


@pytest.mark.parametrize("reduce_iterations", [0, 1])
def test_coordinate_path_follows_path_and_link_shapes(reduce_iterations):
    # For every route: origin, then each path node with the shape of each link
    # between consecutive nodes, then destination; reduction must not change it.
    # A direct route (no network search) is just origin and destination.
    geograph = _shaped_geograph()
    geograph.reduce(iterations=reduce_iterations)
    for o, origin in enumerate(_NODES):
        for d, destination in enumerate(_NODES):
            if o == d:
                continue
            output = geograph.get_shortest_path(
                origin_node={"latitude": origin[0], "longitude": origin[1]},
                destination_node={
                    "latitude": destination[0],
                    "longitude": destination[1],
                },
                output_path=True,
            )
            path = output["path"]
            assert path[0] == o and path[-1] == d
            links = list(zip(path, path[1:]))
            assert output["length"] == pytest.approx(
                sum(_GRAPH[u][v] for u, v in links)
            )
            expected = [origin, _NODES[o]]
            for u, v in links:
                expected += _INTERMEDIATE_NODES[u].get(v, []) + [_NODES[v]]
            expected.append(destination)
            assert output["coordinate_path"] == expected, (o, d)
    # Origin and destination closer to each other than to the network: no search
    output = geograph.get_shortest_path(
        origin_node={"latitude": 10, "longitude": 10},
        destination_node={"latitude": 10, "longitude": 10.01},
    )
    assert output["coordinate_path"] == [[10, 10], [10, 10.01]]
    # Route from a node added after loading, which has no shapes
    point = {"latitude": 3, "longitude": 1.5}
    geograph.add_coord_node(point)
    output = geograph.get_shortest_path(
        point, {"latitude": 0, "longitude": 1.5}, node_addition_type="all"
    )
    assert output["coordinate_path"][:2] == [[3, 1.5], [3, 1.5]]


def test_custom_algorithm_on_reduced_geograph():
    # A custom algorithm must route every pair the same on the reduced graph
    def custom_dijkstra(origin_id, destination_id, graph):
        return Graph(graph).dijkstra(origin_id, destination_id)

    unreduced = GeoGraph(nodes=_NODES, graph=_GRAPH)
    reduced = GeoGraph(nodes=_NODES, graph=_GRAPH)
    reduced.reduce()
    for origin in _NODES:
        for destination in _NODES:
            if origin == destination:
                continue
            query = {
                "origin_node": {"latitude": origin[0], "longitude": origin[1]},
                "destination_node": {
                    "latitude": destination[0],
                    "longitude": destination[1],
                },
                "algorithm_fn": custom_dijkstra,
            }
            expected = unreduced.get_shortest_path(**query)
            assert reduced.get_shortest_path(**query) == expected
