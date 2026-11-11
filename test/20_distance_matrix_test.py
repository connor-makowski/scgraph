from itertools import permutations

import pytest

CITIES = [
    {"latitude": 34.0522, "longitude": -118.2437},  # Los Angeles
    {"latitude": 40.7128, "longitude": -74.0060},  # New York City
    {"latitude": 41.8781, "longitude": -87.6298},  # Chicago
    {"latitude": 29.7604, "longitude": -95.3698},  # Houston
]


def test_distance_matrix_holds_the_length_of_the_route_between_two_points(
    us_freeway,
):
    matrix = us_freeway.distance_matrix(
        CITIES, off_graph_circuity=1, output_units="km"
    )

    # The cell of row i and column j is the route from city i to city j
    for i, j in permutations(range(4), 2):
        route = us_freeway.get_shortest_path(CITIES[i], CITIES[j])
        assert matrix[i][j] == pytest.approx(route["length"], abs=0.001)


def test_distance_matrix_is_zero_from_a_point_to_itself(us_freeway):
    matrix = us_freeway.distance_matrix(
        CITIES, off_graph_circuity=1, output_units="km"
    )

    diagonal = [matrix[i][i] for i in range(4)]
    assert diagonal == pytest.approx([0, 0, 0, 0], abs=0.001)
