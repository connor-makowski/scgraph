import time
from pamda import pamda
from scgraph import Graph
from scgraph.geographs.us_freeway import us_freeway_geograph


def validate(name, realized, expected):
    if realized == expected:
        print(f"{name}: PASS")
    else:
        print(f"{name}: FAIL")
        print("Expected:", expected)
        print("Realized:", realized)


def time_test(name, thunk):
    start = time.time()
    thunk()
    print(f"{name}: {round((time.time()-start)*1000, 4)}ms")


print("\n===============\nUS Freeway GeoGraph Tests:\n===============")

expected = {
    "length": 138.6748,
    "coordinate_path": [
        [41.129, -85.158],
        [41.129, -85.163],
        [41.151, -85.114],
        [41.171, -85.104],
        [41.179, -85.103],
        [41.25, -85.091],
        [41.501, -85.055],
        [41.671, -85.011],
        [41.71, -85.005],
        [41.72, -85.001],
        [41.736, -85.0],
        [41.847, -84.998],
        [41.971, -84.973],
        [42.0, -84.972],
        [42.082, -84.995],
        [42.155, -84.991],
        [42.235, -84.986],
        [42.266, -84.989],
        [42.271, -84.991],
        [42.286, -84.997],
        [42.297, -84.997],
        [42.297, -84.996],
        [42.297, -84.996],
    ],
}


# Fort Wayne IN
origin_node = {"longitude": -85.158, "latitude": 41.129}
# Marshall MI
destination_node = {"longitude": -84.996, "latitude": 42.297}

validate(
    name="Graph Validation",
    realized=us_freeway_geograph.validate_graph(
        check_symmetry=True, check_connected=False
    ),
    expected=None,
)
validate(
    name="Node Validation",
    realized=us_freeway_geograph.validate_nodes(),
    expected=None,
)

validate(
    name="Dijkstra-Modified",
    realized=us_freeway_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.dijkstra_makowski,
    ),
    expected=expected,
)

validate(
    name="A*-haversine",
    realized=us_freeway_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.a_star,
        algorithm_kwargs={"heuristic_fn": us_freeway_geograph.haversine},
    ),
    expected=expected,
)

validate(
    name="A*-cheap_ruler",
    realized=us_freeway_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.a_star,
        algorithm_kwargs={"heuristic_fn": us_freeway_geograph.cheap_ruler},
    ),
    expected=expected,
)

validate(
    name="BMSSP",
    realized=us_freeway_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.bmssp,
    ),
    expected=expected,
)


print("\n===============\nUS Freeway GeoGraph Time Tests:\n===============")

time_test(
    "Graph Validation",
    pamda.thunkify(us_freeway_geograph.validate_graph)(
        check_symmetry=True, check_connected=False
    ),
)
time_test("Node Validation", pamda.thunkify(us_freeway_geograph.validate_nodes))

# Seattle
origin_node = {"latitude": 47.6, "longitude": -122.33}
# Miami
destination_node = {"latitude": 25.78, "longitude": -80.21}


def dijkstra_makowski():
    us_freeway_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.dijkstra_makowski,
    )


def a_star_haversine():
    us_freeway_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.a_star,
        algorithm_kwargs={"heuristic_fn": us_freeway_geograph.haversine},
    )


def a_star_cheap_ruler():
    us_freeway_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.a_star,
        algorithm_kwargs={"heuristic_fn": us_freeway_geograph.cheap_ruler},
    )

def bmssp():
    us_freeway_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.bmssp,
    )


time_test("Dijkstra-Modified", dijkstra_makowski)
time_test("A*-haversine", a_star_haversine)
time_test("A*-cheap_ruler", a_star_cheap_ruler)
time_test("BMSSP", bmssp)


# us_freeway_geograph.save_as_geojson('us_freeway_geograph.geojson')
