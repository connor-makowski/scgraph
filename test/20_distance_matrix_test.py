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


def test_distance_matrix_matches_shortest_path(us_freeway):
    city_nodes = [
        {"longitude": coord[1], "latitude": coord[0]}
        for coord in _CITIES.values()
    ]
    dm = us_freeway.distance_matrix(city_nodes, off_graph_circuity=1, output_units="km")
    direct = us_freeway.get_shortest_path(
        origin_node=city_nodes[0], destination_node=city_nodes[1]
    )
    assert abs(dm[0][1] - direct["length"]) < 0.001
