_ITERATIONS = [
    [
        {"latitude": 35.1799528, "longitude": 129.0752365},
        {"latitude": 36.0638034, "longitude": 120.3781372},
    ],
    [
        {"latitude": 36.0638034, "longitude": 120.3781372},
        {"latitude": 31.2312707, "longitude": 121.4700152},
    ],
    [
        {"latitude": 31.2312707, "longitude": 121.4700152},
        {"latitude": 22.5590503, "longitude": 114.2324407},
    ],
    [
        {"latitude": 22.5590503, "longitude": 114.2324407},
        {"latitude": 47.6038321, "longitude": -122.330062},
    ],
]


def test_iteration(marnet):
    for origin, destination in _ITERATIONS:
        output = marnet.get_shortest_path(
            origin_node=origin, destination_node=destination
        )
        assert len(output["coordinate_path"]) >= 3
