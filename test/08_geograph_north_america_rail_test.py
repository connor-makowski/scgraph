from pamda import pamda
from scgraph.geographs.north_america_rail import north_america_rail_geograph
from scgraph.utils import validate, time_test

print("\n===============\nNorth America Rail GeoGraph Tests:\n===============")

expected = {
    "length": 39.9236,
    "coordinate_path": [
        [48.325, -102.352],
        [48.325, -102.352],
        [48.328, -102.354],
        [48.561, -102.652],
        [48.561, -102.651],
    ],
}


# Stanley ND
origin_node = {"longitude": -102.352, "latitude": 48.325}
# Powers Lake ND
destination_node = {"longitude": -102.651, "latitude": 48.561}

validate(
    name="Graph Validation",
    realized=north_america_rail_geograph.validate(
        check_symmetry=True, check_connected=False
    ),
    expected=None,
)
validate(
    name="Node Validation",
    realized=north_america_rail_geograph.validate_nodes(),
    expected=None,
)

validate(
    name="Dijkstra",
    realized=north_america_rail_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="dijkstra",
    ),
    expected=expected,
)

validate(
    name="A*-haversine",
    realized=north_america_rail_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="a_star",
        algorithm_kwargs={
            "heuristic_fn": north_america_rail_geograph.haversine
        },
    ),
    expected=expected,
)

validate(
    name="A*-cheap_ruler",
    realized=north_america_rail_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="a_star",
        algorithm_kwargs={
            "heuristic_fn": north_america_rail_geograph.cheap_ruler
        },
    ),
    expected=expected,
)

validate(
    name="BMSSP",
    realized=north_america_rail_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="bmssp",
    ),
    expected=expected,
)

print(
    "\n===============\nNorth America Rail GeoGraph Time Tests:\n==============="
)

time_test(
    "Graph Validation",
    north_america_rail_geograph.validate,
    kwargs={"check_symmetry": True, "check_connected": False},
)
time_test(
    "Node Validation",
    north_america_rail_geograph.validate_nodes,
)

# Seattle
origin_node = {"latitude": 47.6, "longitude": -122.33}
# Miami
destination_node = {"latitude": 25.78, "longitude": -80.21}


def dijkstra():
    north_america_rail_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="dijkstra",
    )


def a_star_haversine():
    north_america_rail_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="a_star",
        algorithm_kwargs={
            "heuristic_fn": north_america_rail_geograph.haversine
        },
    )


def a_star_cheap_ruler():
    north_america_rail_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="a_star",
        algorithm_kwargs={
            "heuristic_fn": north_america_rail_geograph.cheap_ruler
        },
    )


def bmssp():
    north_america_rail_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="bmssp",
    )


time_test("Dijkstra", dijkstra)
time_test("A*-haversine", a_star_haversine)
time_test("A*-cheap_ruler", a_star_cheap_ruler)
time_test("BMSSP", bmssp)

# north_america_rail_geograph.save_as_geojson('north_america_rail.geojson')
