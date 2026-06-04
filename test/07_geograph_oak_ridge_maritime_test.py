from helpers import assert_result

_ORIGIN = {"latitude": 30, "longitude": 160}
_DESTINATION = {"latitude": 30, "longitude": -160}
_EXPECTED = {
    "length": 3894.053,
    "coordinate_path": [
        [30, 160],
        [30.0, 160.0],
        [30.0935, 165.0005],
        [30.0, 170.0],
        [28.5, -178.5],
        [29.3168, -174.2807],
        [30.0, -170.0],
        [30.0935, -164.9995],
        [30.0, -160.0],
        [30, -160],
    ],
}


def test_graph_validation(oak_ridge_maritime):
    oak_ridge_maritime.validate(check_symmetry=True, check_connected=False)


def test_node_validation(oak_ridge_maritime):
    oak_ridge_maritime.validate_nodes()


def test_dijkstra(oak_ridge_maritime):
    assert_result(
        oak_ridge_maritime.get_shortest_path(
            origin_node=_ORIGIN,
            destination_node=_DESTINATION,
            algorithm_fn="dijkstra",
        ),
        _EXPECTED,
    )


def test_a_star_haversine(oak_ridge_maritime):
    assert_result(
        oak_ridge_maritime.get_shortest_path(
            origin_node=_ORIGIN,
            destination_node=_DESTINATION,
            algorithm_fn="a_star",
            algorithm_kwargs={"heuristic_fn": oak_ridge_maritime.haversine},
        ),
        _EXPECTED,
    )


def test_a_star_cheap_ruler(oak_ridge_maritime):
    assert_result(
        oak_ridge_maritime.get_shortest_path(
            origin_node=_ORIGIN,
            destination_node=_DESTINATION,
            algorithm_fn="a_star",
            algorithm_kwargs={"heuristic_fn": oak_ridge_maritime.cheap_ruler},
        ),
        _EXPECTED,
    )


def test_bmssp(oak_ridge_maritime):
    assert_result(
        oak_ridge_maritime.get_shortest_path(
            origin_node=_ORIGIN,
            destination_node=_DESTINATION,
            algorithm_fn="bmssp",
        ),
        _EXPECTED,
    )
