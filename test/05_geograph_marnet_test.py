from scgraph import GeoGraph
from scgraph.utils import validate, time_test

marnet_geograph = GeoGraph.load_geograph("marnet")
marnet_geograph.warmup()


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
    realized=marnet_geograph.validate(
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
    name="Dijkstra",
    realized=marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="dijkstra",
    ),
    expected=expected,
)

validate(
    name="A*-haversine",
    realized=marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="a_star",
        algorithm_kwargs={"heuristic_fn": marnet_geograph.haversine},
    ),
    expected=expected,
)

validate(
    name="A*-cheap_ruler",
    realized=marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="a_star",
        algorithm_kwargs={"heuristic_fn": marnet_geograph.cheap_ruler},
    ),
    expected=expected,
)

validate(
    name="Cached Shortest Path Tree First Call",
    realized=marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="cached_shortest_path",
    ),
    expected=expected,
)

validate(
    name="Cached Shortest Path Tree Second Call",
    realized=marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="cached_shortest_path",
    ),
    expected=expected,
)

validate(
    name="BMSSP",
    realized=marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="bmssp",
    ),
    expected=expected,
)

print("\n===============\nMarnet GeoGraph Time Tests:\n===============")

time_test(
    "Graph Validation",
    marnet_geograph.validate,
    kwargs={"check_symmetry": True, "check_connected": True},
)
time_test("Node Validation", marnet_geograph.validate_nodes)

# Note: These must be different than the above calls to ensure caching testing works correctly
origin_node = {"latitude": 31.23, "longitude": 121.47}
destination_node = {"latitude": 32.08, "longitude": -81.09}


def dijkstra():
    marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="dijkstra",
    )


def a_star_haversine():
    marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="a_star",
        algorithm_kwargs={"heuristic_fn": marnet_geograph.haversine},
    )


def a_star_cheap_ruler():
    marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="a_star",
        algorithm_kwargs={"heuristic_fn": marnet_geograph.cheap_ruler},
    )


def cached_shortest_path_tree_first_call():
    marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="cached_shortest_path",
    )


def cached_shortest_path_tree_second_call():
    marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="cached_shortest_path",
    )


def bmssp():
    marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="bmssp",
    )


time_test("Dijkstra", dijkstra)
time_test("A*-haversine", a_star_haversine)
time_test("A*-cheap_ruler", a_star_cheap_ruler)
time_test(
    "Cached Shortest Path Tree First Call", cached_shortest_path_tree_first_call
)
time_test(
    "Cached Shortest Path Tree Second Call",
    cached_shortest_path_tree_second_call,
)
time_test("BMSSP", bmssp)

# marnet_geograph.save_as_geojson('marnet.geojson')
