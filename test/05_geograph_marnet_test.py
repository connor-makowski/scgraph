from helpers import assert_result

_ORIGIN = {"latitude": 30, "longitude": 160}
_DESTINATION = {"latitude": 30, "longitude": -160}
_EXPECTED = {
    "length": 4477.148,
    "coordinate_path": [
        [30, 160],
        [30.0, 160.0],
        [35.1041, 164.6948],
        [35.3857, 165.0],
        [36.6002, 166.316],
        [37.695, 169.999],
        [38.2345, 171.814],
        [40.0, 180.0],
        [40.0, -180.0],
        [40.1067, -174.9996],
        [40.0, -170.0],
        [35.3857, -165.0],
        [35.1023, -164.6929],
        [30.0, -160.0],
        [30, -160],
    ],
}


def test_graph_validation(marnet):
    marnet.validate(check_symmetry=True, check_connected=True)


def test_node_validation(marnet):
    marnet.validate_nodes()


def test_dijkstra(marnet):
    assert_result(
        marnet.get_shortest_path(
            origin_node=_ORIGIN,
            destination_node=_DESTINATION,
            algorithm_fn="dijkstra",
        ),
        _EXPECTED,
    )


def test_a_star_haversine(marnet):
    assert_result(
        marnet.get_shortest_path(
            origin_node=_ORIGIN,
            destination_node=_DESTINATION,
            algorithm_fn="a_star",
            algorithm_kwargs={"heuristic_fn": marnet.haversine},
        ),
        _EXPECTED,
    )


def test_a_star_cheap_ruler(marnet):
    assert_result(
        marnet.get_shortest_path(
            origin_node=_ORIGIN,
            destination_node=_DESTINATION,
            algorithm_fn="a_star",
            algorithm_kwargs={"heuristic_fn": marnet.cheap_ruler},
        ),
        _EXPECTED,
    )


def test_cached_shortest_path_first_call(marnet):
    assert_result(
        marnet.get_shortest_path(
            origin_node=_ORIGIN,
            destination_node=_DESTINATION,
            algorithm_fn="cached_shortest_path",
        ),
        _EXPECTED,
    )


def test_cached_shortest_path_second_call(marnet):
    assert_result(
        marnet.get_shortest_path(
            origin_node=_ORIGIN,
            destination_node=_DESTINATION,
            algorithm_fn="cached_shortest_path",
        ),
        _EXPECTED,
    )


def test_bmssp(marnet):
    assert_result(
        marnet.get_shortest_path(
            origin_node=_ORIGIN,
            destination_node=_DESTINATION,
            algorithm_fn="bmssp",
        ),
        _EXPECTED,
    )


def test_bidirectional_dijkstra(marnet):
    assert_result(
        marnet.get_shortest_path(
            origin_node=_ORIGIN,
            destination_node=_DESTINATION,
            algorithm_fn="bidirectional_dijkstra",
        ),
        _EXPECTED,
    )
