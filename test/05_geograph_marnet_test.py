import time
from pamda import pamda
from scgraph import Graph
from scgraph.geographs.marnet import marnet_geograph
from scgraph.utils import hard_round


def validate(name, realized, expected):
    if isinstance(realized, dict) and "length" in realized:
        realized["length"] = hard_round(3, realized["length"])
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


print("\n===============\nMarnet GeoGraph Tests:\n===============")

expected = {
    "length": 4477.148,
    "coordinate_path": [
        [30, 160],
        [30.0, 160.0],
        [35.1041, 164.6948],
        [35.3857, 165.0],
        [36.6002, 166.316],
        [37.695, 169.999],
        [38.2345, 171.814],
        [40.0, 180.0],
        [40.0, -180.0],
        [40.1067, -174.9996],
        [40.0, -170.0],
        [35.3857, -165.0],
        [35.1023, -164.6929],
        [30.0, -160.0],
        [30, -160],
    ],
}

origin_node = {"latitude": 30, "longitude": 160}
destination_node = {"latitude": 30, "longitude": -160}

validate(
    name="Graph Validation",
    realized=marnet_geograph.validate_graph(
        check_symmetry=True, check_connected=True
    ),
    expected=None,
)
validate(
    name="Node Validation",
    realized=marnet_geograph.validate_nodes(),
    expected=None,
)

validate(
    name="Dijkstra-Modified",
    realized=marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.dijkstra_makowski,
    ),
    expected=expected,
)

validate(
    name="A*-haversine",
    realized=marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.a_star,
        algorithm_kwargs={"heuristic_fn": marnet_geograph.haversine},
    ),
    expected=expected,
)

validate(
    name="A*-cheap_ruler",
    realized=marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.a_star,
        algorithm_kwargs={"heuristic_fn": marnet_geograph.cheap_ruler},
    ),
    expected=expected,
)

validate(
    name="Cached Spanning Tree First Call",
    realized=marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        cache=True,
    ),
    expected=expected,
)

validate(
    name="Cached Spanning Tree Second Call",
    realized=marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        cache=True,
    ),
    expected=expected,
)

print("\n===============\nMarnet GeoGraph Time Tests:\n===============")

time_test(
    "Graph Validation",
    pamda.thunkify(marnet_geograph.validate_graph)(
        check_symmetry=True, check_connected=True
    ),
)
time_test("Node Validation", pamda.thunkify(marnet_geograph.validate_nodes))

# Note: These must be different than the above calls to ensure caching testing works correctly
origin_node = {"latitude": 31.23, "longitude": 121.47}
destination_node = {"latitude": 32.08, "longitude": -81.09}


def dijkstra_makowski():
    marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.dijkstra_makowski,
    )


def a_star_haversine():
    marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.a_star,
        algorithm_kwargs={"heuristic_fn": marnet_geograph.haversine},
    )


def a_star_cheap_ruler():
    marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.a_star,
        algorithm_kwargs={"heuristic_fn": marnet_geograph.cheap_ruler},
    )


def cached_spanning_tree_first_call():
    marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        cache=True,
    )


def cached_spanning_tree_second_call():
    marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        cache=True,
    )


time_test("Dijkstra-Modified", dijkstra_makowski)
time_test("A*-haversine", a_star_haversine)
time_test("A*-cheap_ruler", a_star_cheap_ruler)
time_test("Cached Spanning Tree First Call", cached_spanning_tree_first_call)
time_test("Cached Spanning Tree Second Call", cached_spanning_tree_second_call)

# marnet_geograph.save_as_geojson('marnet.geojson')
