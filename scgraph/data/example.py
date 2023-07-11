example_data = {
    "nodes": {
        "1": {"latitude": 0.0, "longitude": 0.0},
        "2": {"latitude": 0.0, "longitude": 1.0},
        "3": {"latitude": 1.0, "longitude": 0.0},
        "4": {"latitude": 1.0, "longitude": 1.0},
    },
    "graph": {
        "1": {"2": 1.0, "3": 1.0},
        "2": {"1": 1.0, "4": 1.0},
        "3": {"1": 1.0, "4": 1.0},
        "4": {"2": 1.0, "3": 1.0},
    },
}
