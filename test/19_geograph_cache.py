from scgraph.geographs.us_freeway import us_freeway_geograph
from time import time


def validate(name, realized, expected):
    if realized == expected:
        print(f"{name}: PASS")
    else:
        print(f"{name}: FAIL")
        print("Expected:", expected)
        print("Realized:", realized)


def time_test(name, thunk):
    start = time()
    thunk()
    print(f"{name}: {round((time()-start)*1000, 4)}ms")


cities = {
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

print("\n===============\nGeoGraph Cache Tests:\n===============")


success = True
cities_fully_visited = []
for city1, coord1 in cities.items():
    for city2, coord2 in cities.items():
        if city2 in cities_fully_visited:
            continue
        if city1 != city2 and city2 not in cities_fully_visited:
            length = us_freeway_geograph.get_shortest_path(
                origin_node={"longitude": coord1[1], "latitude": coord1[0]},
                destination_node={
                    "longitude": coord2[1],
                    "latitude": coord2[0],
                },
            )["length"]
            cached_length = us_freeway_geograph.get_shortest_path(
                origin_node={"longitude": coord1[1], "latitude": coord1[0]},
                destination_node={
                    "longitude": coord2[1],
                    "latitude": coord2[0],
                },
                cache=True,
            )["length"]
            cached_len_only = us_freeway_geograph.get_shortest_path(
                origin_node={"longitude": coord1[1], "latitude": coord1[0]},
                destination_node={
                    "longitude": coord2[1],
                    "latitude": coord2[0],
                },
                cache=True,
                length_only=True,
            )["length"]
            if abs(length - cached_length) + abs(length - cached_len_only) > 0.001:
                print(
                    f"Length mismatch between uncached and cached for {city1} to {city2}: {length} vs {cached_length} vs {cached_len_only}"
                )
                success = False
    cities_fully_visited.append(city1)

if not success:
    print("Geograph Cache Test: FAIL")
else:
    print("Geograph Cache Test: PASS")


def uncached_time():
    for city1, coord1 in cities.items():
        for city2, coord2 in cities.items():
            if city1 != city2:
                us_freeway_geograph.get_shortest_path(
                    origin_node={"longitude": coord1[1], "latitude": coord1[0]},
                    destination_node={
                        "longitude": coord2[1],
                        "latitude": coord2[0],
                    },
                )


def cached_time():
    for city1, coord1 in cities.items():
        for city2, coord2 in cities.items():
            if city1 != city2:
                us_freeway_geograph.get_shortest_path(
                    origin_node={"longitude": coord1[1], "latitude": coord1[0]},
                    destination_node={
                        "longitude": coord2[1],
                        "latitude": coord2[0],
                    },
                    cache=True,
                )

def cached_len_only_time():
    for city1, coord1 in cities.items():
        for city2, coord2 in cities.items():
            if city1 != city2:
                us_freeway_geograph.get_shortest_path(
                    origin_node={"longitude": coord1[1], "latitude": coord1[0]},
                    destination_node={
                        "longitude": coord2[1],
                        "latitude": coord2[0],
                    },
                    cache=True,
                    length_only=True,
                )

def single_uncached_time():
    us_freeway_geograph.get_shortest_path(
        origin_node={"longitude": -118.2437, "latitude": 34.0522},
        destination_node={
            "longitude": -74.0060,
            "latitude": 40.7128,
        },
    )
def single_cached_time():
    us_freeway_geograph.get_shortest_path(
        origin_node={"longitude": -118.2437, "latitude": 34.0522},
        destination_node={
            "longitude": -74.0060,
            "latitude": 40.7128,
        },
        cache=True,
    )
def single_cached_len_only_time():
    us_freeway_geograph.get_shortest_path(
        origin_node={"longitude": -118.2437, "latitude": 34.0522},
        destination_node={
            "longitude": -74.0060,
            "latitude": 40.7128,
        },
        cache=True,
        length_only=True,
    )

print("\n===============\nGeoGraph Cache Timing Tests:\n===============")
time_test(name="GeoGraph single uncached time", thunk=single_uncached_time)
time_test(name="GeoGraph single cached time", thunk=single_cached_time)
time_test(name="GeoGraph single cached length only time", thunk=single_cached_len_only_time)

time_test(name="GeoGraph uncached time", thunk=uncached_time)
time_test(name="GeoGraph cached time", thunk=cached_time)
time_test(name="GeoGraph cached length only time", thunk=cached_len_only_time)
