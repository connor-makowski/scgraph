from scgraph.geographs.us_freeway import us_freeway_geograph
from scgraph.utils import haversine
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

city_nodes = [
    {"longitude": coord[1], "latitude": coord[0]} for coord in cities.values()
]

print("\n===============\nGeoGraph Distance Matrix Tests:\n===============")


success = True
distance_matrix = us_freeway_geograph.distance_matrix(city_nodes, off_graph_circuity=1, geograph_units="km", output_units="km")

la_nyc = us_freeway_geograph.get_shortest_path(
    origin_node=city_nodes[0],
    destination_node=city_nodes[1],
)

if abs(distance_matrix['distance_matrix'][0][1] - la_nyc["length"]) < 0.001:
    print("Distance matrix test: PASS")
else:
    print("Distance matrix test: FAIL")
    print("Expected:", la_nyc["length"])
    print("Realized:", distance_matrix['distance_matrix'][0][1])
    success = False


print("\n===============\nGeoGraph Distance Matrix Timing Tests:\n===============")


# Create a bounding box that more or less captures the interior of the US without spilling into Canada or Mexico or the oceans
us_bounding_box = {"min_latitude": 34.1, "max_latitude": 47.0, "min_longitude": -118.0, "max_longitude": -80.0}

# Get a set of nxn nodes equally spaced within the bounding box
def get_nodes(n, box):
    assert n > 2
    latitudes = [box['min_latitude'] + i * (box['max_latitude'] - box['min_latitude']) / n for i in range(n)]
    longitudes = [box['min_longitude'] + i * (box['max_longitude'] - box['min_longitude']) / n for i in range(n)]
    return [{"latitude": lat, "longitude": lon} for lat in latitudes for lon in longitudes]

def distance_matrix_time(nodes):
    start = time()
    dm = us_freeway_geograph.distance_matrix(
        nodes=nodes,
        off_graph_circuity=1,
        geograph_units="km",
        output_units="km",
    )
    time_taken = time() - start
    time_per_calc = time_taken / (len(nodes) * len(nodes))
    time_ms = round(time_taken * 1000, 4)
    time_per_calc_us = round(time_per_calc * 1e6, 4)

    print(f"Distance matrix ({len(nodes)} nodes, {len(nodes)**2} distances): {time_ms}ms total, {time_per_calc_us}us/distance")

def naive_distance_matrix_time(nodes):
    start = time()
    out = []
    for i in nodes:
        out_sub = []
        for j in nodes:
            out_sub.append(us_freeway_geograph.get_shortest_path(i, j)["length"])
        out.append(out_sub)
    time_taken = time() - start
    time_per_calc = time_taken / (len(nodes) * len(nodes))
    time_ms = round(time_taken * 1000, 4)
    time_per_calc_us = round(time_per_calc * 1e6, 4)
    print(f"Naive distance matrix ({len(nodes)} nodes, {len(nodes)**2} distances): {time_ms}ms total, {time_per_calc_us}us/distance")

def haversine_time(nodes):
    nodes = [(node["latitude"], node["longitude"]) for node in nodes]
    start = time()
    out = []
    for i in nodes:
        out_sub = []
        for j in nodes:
            out_sub.append(haversine(i, j))
        out.append(out_sub)
    time_taken = time() - start
    time_per_calc = time_taken / (len(nodes) * len(nodes))
    time_ms = round(time_taken * 1000, 4)
    time_per_calc_us = round(time_per_calc * 1e6, 4)
    print(f"Haversine distance ({len(nodes)} nodes, {len(nodes)*len(nodes)} distances): {time_ms}ms total, {time_per_calc_us}us/distance")

haversine_time(get_nodes(5, us_bounding_box))
distance_matrix_time(get_nodes(5, us_bounding_box))
# naive_distance_matrix_time(get_nodes(5, us_bounding_box))

haversine_time(get_nodes(10, us_bounding_box))
distance_matrix_time(get_nodes(10, us_bounding_box))
# naive_distance_matrix_time(get_nodes(10, us_bounding_box))

haversine_time(get_nodes(20, us_bounding_box))
distance_matrix_time(get_nodes(20, us_bounding_box))
# naive_distance_matrix_time(get_nodes(20, us_bounding_box))

# distance_matrix_time(get_nodes(30, us_bounding_box)) 
# distance_matrix_time(get_nodes(40, us_bounding_box))
# distance_matrix_time(get_nodes(50, us_bounding_box)) # 12s
# distance_matrix_time(get_nodes(60, us_bounding_box)) # 20s
# distance_matrix_time(get_nodes(70, us_bounding_box)) # 30s
# distance_matrix_time(get_nodes(80, us_bounding_box)) # 42s
# distance_matrix_time(get_nodes(90, us_bounding_box)) # 56s

# haversine_time(get_nodes(100, us_bounding_box)) # 76s
# distance_matrix_time(get_nodes(100, us_bounding_box)) # 76s

# distance_matrix_time(get_nodes(130, us_bounding_box)) # 3m 10s