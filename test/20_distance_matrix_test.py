import pytest

# Los Angeles, New York City, Chicago, Houston
_CITIES = [
    {"latitude": 34.0522, "longitude": -118.2437},
    {"latitude": 40.7128, "longitude": -74.0060},
    {"latitude": 41.8781, "longitude": -87.6298},
    {"latitude": 29.7604, "longitude": -95.3698},
]


# Each cell of the distance matrix is the length of the route between its two
# points, and zero from a point to itself.
def test_distance_matrix_holds_the_length_of_every_route(us_freeway):
    matrix = us_freeway.distance_matrix(
        _CITIES, off_graph_circuity=1, output_units="km"
    )
    for row, origin in zip(matrix, _CITIES):
        for cell, destination in zip(row, _CITIES):
            expected = (
                us_freeway.get_shortest_path(origin, destination)["length"]
                if origin != destination
                else 0
            )
            assert cell == pytest.approx(expected, abs=0.001)
