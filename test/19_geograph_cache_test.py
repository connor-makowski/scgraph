_CITIES = {
    "Los Angeles": (34.0522, -118.2437),
    "New York City": (40.7128, -74.0060),
    "Chicago": (41.8781, -87.6298),
    "Houston": (29.7604, -95.3698),
    "Phoenix": (33.4484, -112.0740),
    "Denver": (39.7392, -104.9903),
    "Seattle": (47.6062, -122.3321),
    "Miami": (25.7617, -80.1918),
    "Washington D.C.": (38.9072, -77.0369),
    "San Francisco": (37.7749, -122.4194),
    "Omaha": (41.2565, -95.9345),
    "Atlanta": (33.7490, -84.3880),
    "Austin": (30.2672, -97.7431),
    "Boston": (42.3601, -71.0589),
    "Las Vegas": (36.1699, -115.1398),
    "Detroit": (42.3314, -83.0458),
}


def test_cached_results_match_uncached(us_freeway):
    visited = []
    for city1, coord1 in _CITIES.items():
        for city2, coord2 in _CITIES.items():
            if city2 in visited or city1 == city2:
                continue
            origin = {"longitude": coord1[1], "latitude": coord1[0]}
            dest = {"longitude": coord2[1], "latitude": coord2[0]}
            length = us_freeway.get_shortest_path(origin, dest)["length"]
            cached = us_freeway.get_shortest_path(
                origin, dest, algorithm_fn="cached_shortest_path"
            )["length"]
            cached_len_only = us_freeway.get_shortest_path(
                origin, dest, algorithm_fn="cached_shortest_path", length_only=True
            )["length"]
            assert abs(length - cached) + abs(length - cached_len_only) <= 0.001, (
                f"{city1} -> {city2}: uncached={length}, cached={cached}, "
                f"cached_len_only={cached_len_only}"
            )
        visited.append(city1)
