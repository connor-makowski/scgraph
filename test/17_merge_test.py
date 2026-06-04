from scgraph import GeoGraph

_PORTS = [
    [42.3601, -71.0589],
    [40.7128, -74.0060],
    [39.9526, -75.1652],
    [39.2904, -76.6122],
    [38.9072, -77.0369],
    [32.0835, -81.0998],
    [32.7765, -79.9311],
    [30.3322, -81.6557],
    [25.7617, -80.1918],
    [27.9506, -82.4572],
    [29.9511, -90.0715],
    [29.7604, -95.3698],
    [34.0522, -118.2437],
    [37.7749, -122.4194],
    [47.6062, -122.3321],
    [45.5152, -122.6784],
]
_ATLANTA = {"latitude": 33.7490, "longitude": -84.3880}
_LONDON = {"latitude": 51.5074, "longitude": -0.1278}
_EXPECTED_FREEWAY_LENGTH = 7094.0603
_EXPECTED_MARNET_LENGTH = 8820.8927


def test_merge_and_route():
    freeway = GeoGraph.load_geograph("us_freeway")
    marnet = GeoGraph.load_geograph("marnet")
    freeway.merge_with_other_geograph(
        other_geograph=marnet,
        connection_nodes=_PORTS,
        circuity_to_current_geograph=1.1,
        circuity_to_other_geograph=1.3,
        node_addition_type_current_geograph="closest",
        node_addition_type_other_geograph="closest",
        node_addition_math="euclidean",
    )
    freeway_result = freeway.get_shortest_path(
        origin_node=_ATLANTA, destination_node=_LONDON
    )
    marnet_result = marnet.get_shortest_path(
        origin_node=_ATLANTA, destination_node=_LONDON
    )
    assert abs(freeway_result["length"] - _EXPECTED_FREEWAY_LENGTH) < 0.1
    assert abs(marnet_result["length"] - _EXPECTED_MARNET_LENGTH) < 0.1
