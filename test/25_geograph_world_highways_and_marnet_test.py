from helpers import assert_result

_ORIGIN = {"longitude": -85.158, "latitude": 41.129}
_DESTINATION = {"longitude": -84.996, "latitude": 42.297}
_EXPECTED = {
    "length": 134.478,
    "coordinate_path": [
        [41.129, -85.158],
        [41.129, -85.158],
        [41.138, -85.136],
        [41.138, -85.135],
        [41.176, -85.103],
        [41.179, -85.103],
        [41.189, -85.104],
        [41.236, -85.094],
        [41.367, -85.082],
        [41.44, -85.054],
        [41.442, -85.054],
        [41.635, -85.048],
        [41.699, -85.004],
        [41.706, -85.005],
        [41.736, -85.0],
        [41.898, -84.991],
        [41.936, -84.973],
        [42.106, -84.996],
        [42.262, -84.988],
        [42.27, -84.991],
        [42.297, -84.997],
        [42.297, -84.996],
    ],
}


def test_graph_validation(world_highways_and_marnet):
    world_highways_and_marnet.validate(check_symmetry=True, check_connected=False)


def test_node_validation(world_highways_and_marnet):
    world_highways_and_marnet.validate_nodes()


def test_dijkstra(world_highways_and_marnet):
    assert_result(
        world_highways_and_marnet.get_shortest_path(
            origin_node=_ORIGIN,
            destination_node=_DESTINATION,
            algorithm_fn="dijkstra",
        ),
        _EXPECTED,
    )


def test_a_star_haversine(world_highways_and_marnet):
    assert_result(
        world_highways_and_marnet.get_shortest_path(
            origin_node=_ORIGIN,
            destination_node=_DESTINATION,
            algorithm_fn="a_star",
            algorithm_kwargs={"heuristic_fn": world_highways_and_marnet.haversine},
        ),
        _EXPECTED,
    )


def test_a_star_cheap_ruler(world_highways_and_marnet):
    assert_result(
        world_highways_and_marnet.get_shortest_path(
            origin_node=_ORIGIN,
            destination_node=_DESTINATION,
            algorithm_fn="a_star",
            algorithm_kwargs={"heuristic_fn": world_highways_and_marnet.cheap_ruler},
        ),
        _EXPECTED,
    )


def test_bmssp(world_highways_and_marnet):
    assert_result(
        world_highways_and_marnet.get_shortest_path(
            origin_node=_ORIGIN,
            destination_node=_DESTINATION,
            algorithm_fn="bmssp",
        ),
        _EXPECTED,
    )
