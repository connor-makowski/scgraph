from helpers import assert_result

_ORIGIN = {"longitude": -102.352, "latitude": 48.325}
_DESTINATION = {"longitude": -102.651, "latitude": 48.561}
_EXPECTED = {
    "length": 39.9236,
    "coordinate_path": [
        [48.325, -102.352],
        [48.325, -102.352],
        [48.328, -102.354],
        [48.561, -102.652],
        [48.561, -102.651],
    ],
}


def test_graph_validation(north_america_rail):
    north_america_rail.validate(check_symmetry=True, check_connected=False)


def test_node_validation(north_america_rail):
    north_america_rail.validate_nodes()


def test_dijkstra(north_america_rail):
    assert_result(
        north_america_rail.get_shortest_path(
            origin_node=_ORIGIN,
            destination_node=_DESTINATION,
            algorithm_fn="dijkstra",
        ),
        _EXPECTED,
    )


def test_a_star_haversine(north_america_rail):
    assert_result(
        north_america_rail.get_shortest_path(
            origin_node=_ORIGIN,
            destination_node=_DESTINATION,
            algorithm_fn="a_star",
            algorithm_kwargs={"heuristic_fn": north_america_rail.haversine},
        ),
        _EXPECTED,
    )


def test_a_star_cheap_ruler(north_america_rail):
    assert_result(
        north_america_rail.get_shortest_path(
            origin_node=_ORIGIN,
            destination_node=_DESTINATION,
            algorithm_fn="a_star",
            algorithm_kwargs={"heuristic_fn": north_america_rail.cheap_ruler},
        ),
        _EXPECTED,
    )


def test_bmssp(north_america_rail):
    assert_result(
        north_america_rail.get_shortest_path(
            origin_node=_ORIGIN,
            destination_node=_DESTINATION,
            algorithm_fn="bmssp",
        ),
        _EXPECTED,
    )
