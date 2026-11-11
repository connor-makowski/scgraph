from itertools import combinations

import pytest

# Sixteen cities across the United States. The tests route between every two
# of them (120 pairs): a city is the origin of several routes, and the tree
# kept for an origin serves several destinations.
CITIES = {
    "Los Angeles": {"latitude": 34.0522, "longitude": -118.2437},
    "New York City": {"latitude": 40.7128, "longitude": -74.0060},
    "Chicago": {"latitude": 41.8781, "longitude": -87.6298},
    "Houston": {"latitude": 29.7604, "longitude": -95.3698},
    "Phoenix": {"latitude": 33.4484, "longitude": -112.0740},
    "Denver": {"latitude": 39.7392, "longitude": -104.9903},
    "Seattle": {"latitude": 47.6062, "longitude": -122.3321},
    "Miami": {"latitude": 25.7617, "longitude": -80.1918},
    "Washington D.C.": {"latitude": 38.9072, "longitude": -77.0369},
    "San Francisco": {"latitude": 37.7749, "longitude": -122.4194},
    "Omaha": {"latitude": 41.2565, "longitude": -95.9345},
    "Atlanta": {"latitude": 33.7490, "longitude": -84.3880},
    "Austin": {"latitude": 30.2672, "longitude": -97.7431},
    "Boston": {"latitude": 42.3601, "longitude": -71.0589},
    "Las Vegas": {"latitude": 36.1699, "longitude": -115.1398},
    "Detroit": {"latitude": 42.3314, "longitude": -83.0458},
}


def test_cached_route_has_the_length_of_the_computed_route(us_freeway):
    for origin, destination in combinations(CITIES.values(), 2):
        cached = us_freeway.get_shortest_path(
            origin, destination, algorithm_fn="cached_shortest_path"
        )

        computed = us_freeway.get_shortest_path(origin, destination)
        # The lengths are in km: equal to half a metre
        assert cached["length"] == pytest.approx(
            computed["length"], abs=0.0005
        ), (origin, destination)


def test_cached_length_alone_is_the_length_of_the_computed_route(us_freeway):
    for origin, destination in combinations(CITIES.values(), 2):
        cached = us_freeway.get_shortest_path(
            origin,
            destination,
            algorithm_fn="cached_shortest_path",
            length_only=True,
        )

        computed = us_freeway.get_shortest_path(origin, destination)
        # The lengths are in km: equal to half a metre
        assert cached["length"] == pytest.approx(
            computed["length"], abs=0.0005
        ), (origin, destination)
