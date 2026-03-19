from scgraph import GeoGraph
from scgraph.utils import validate, time_test

world_highways_and_marnet_geograph = GeoGraph.load_geograph("world_highways_and_marnet")

print("\n===============\nWorld Highways and Marnet GeoGraph Tests:\n===============")

expected = {
    'length': 134.478, 
    'coordinate_path': [
        [41.129, -85.158],
        [41.129, -85.158],
        [41.138, -85.136],
        [41.138, -85.135],
        [41.176, -85.103],
        [41.179, -85.103],
        [41.189, -85.104],
        [41.236, -85.094],
        [41.367, -85.082],
        [41.44, -85.054],
        [41.442, -85.054],
        [41.635, -85.048],
        [41.699, -85.004],
        [41.706, -85.005],
        [41.736, -85.0],
        [41.898, -84.991],
        [41.936, -84.973],
        [42.106, -84.996],
        [42.262, -84.988],
        [42.27, -84.991],
        [42.297, -84.997],
        [42.297, -84.996]
    ]
}



# Fort Wayne IN
origin_node = {"longitude": -85.158, "latitude": 41.129}
# Marshall MI
destination_node = {"longitude": -84.996, "latitude": 42.297}

validate(
    name="Graph Validation",
    realized=world_highways_and_marnet_geograph.validate(
        check_symmetry=True, check_connected=False
    ),
    expected=None,
)
validate(
    name="Node Validation",
    realized=world_highways_and_marnet_geograph.validate_nodes(),
    expected=None,
)

validate(
    name="Dijkstra",
    realized=world_highways_and_marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="dijkstra",
    ),
    expected=expected,
)

validate(
    name="A*-haversine",
    realized=world_highways_and_marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="a_star",
        algorithm_kwargs={"heuristic_fn": world_highways_and_marnet_geograph.haversine},
    ),
    expected=expected,
)

validate(
    name="A*-cheap_ruler",
    realized=world_highways_and_marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="a_star",
        algorithm_kwargs={"heuristic_fn": world_highways_and_marnet_geograph.cheap_ruler},
    ),
    expected=expected,
)

validate(
    name="BMSSP",
    realized=world_highways_and_marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="bmssp",
    ),
    expected=expected,
)


print("\n===============\nWorld Highways and Marnet GeoGraph Time Tests:\n===============")

time_test(
    "Graph Validation",
    world_highways_and_marnet_geograph.validate,
    kwargs={"check_symmetry": True, "check_connected": False},
)
time_test("Node Validation", world_highways_and_marnet_geograph.validate_nodes)

# Seattle
origin_node = {"latitude": 47.6, "longitude": -122.33}
# Miami
destination_node = {"latitude": 25.78, "longitude": -80.21}


def dijkstra():
    world_highways_and_marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="dijkstra",
    )


def a_star_haversine():
    world_highways_and_marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="a_star",
        algorithm_kwargs={"heuristic_fn": world_highways_and_marnet_geograph.haversine},
    )


def a_star_cheap_ruler():
    world_highways_and_marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="a_star",
        algorithm_kwargs={"heuristic_fn": world_highways_and_marnet_geograph.cheap_ruler},
    )


def bmssp():
    world_highways_and_marnet_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="bmssp",
    )


time_test("Dijkstra", dijkstra)
time_test("A*-haversine", a_star_haversine)
time_test("A*-cheap_ruler", a_star_cheap_ruler)
time_test("BMSSP", bmssp)
