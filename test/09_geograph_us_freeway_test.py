from helpers import assert_result

_ORIGIN = {"longitude": -85.158, "latitude": 41.129}
_DESTINATION = {"longitude": -84.996, "latitude": 42.297}
_EXPECTED = {
    "length": 138.6748,
    "coordinate_path": [
        [41.129, -85.158],
        [41.129, -85.163],
        [41.151, -85.114],
        [41.171, -85.104],
        [41.179, -85.103],
        [41.25, -85.091],
        [41.501, -85.055],
        [41.671, -85.011],
        [41.71, -85.005],
        [41.72, -85.001],
        [41.736, -85.0],
        [41.847, -84.998],
        [41.971, -84.973],
        [42.0, -84.972],
        [42.082, -84.995],
        [42.155, -84.991],
        [42.235, -84.986],
        [42.266, -84.989],
        [42.271, -84.991],
        [42.286, -84.997],
        [42.297, -84.997],
        [42.297, -84.996],
        [42.297, -84.996],
    ],
}


def test_graph_validation(us_freeway):
    us_freeway.validate(check_symmetry=True, check_connected=False)


def test_node_validation(us_freeway):
    us_freeway.validate_nodes()


def test_dijkstra(us_freeway):
    assert_result(
        us_freeway.get_shortest_path(
            origin_node=_ORIGIN,
            destination_node=_DESTINATION,
            algorithm_fn="dijkstra",
        ),
        _EXPECTED,
    )


def test_a_star_haversine(us_freeway):
    assert_result(
        us_freeway.get_shortest_path(
            origin_node=_ORIGIN,
            destination_node=_DESTINATION,
            algorithm_fn="a_star",
            algorithm_kwargs={"heuristic_fn": us_freeway.haversine},
        ),
        _EXPECTED,
    )


def test_a_star_cheap_ruler(us_freeway):
    assert_result(
        us_freeway.get_shortest_path(
            origin_node=_ORIGIN,
            destination_node=_DESTINATION,
            algorithm_fn="a_star",
            algorithm_kwargs={"heuristic_fn": us_freeway.cheap_ruler},
        ),
        _EXPECTED,
    )


def test_bmssp(us_freeway):
    assert_result(
        us_freeway.get_shortest_path(
            origin_node=_ORIGIN,
            destination_node=_DESTINATION,
            algorithm_fn="bmssp",
        ),
        _EXPECTED,
    )
