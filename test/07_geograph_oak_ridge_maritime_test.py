from scgraph.geographs.oak_ridge_maritime import oak_ridge_maritime_geograph
from scgraph.utils import validate, time_test


print("\n===============\nOak Ridge GeoGraph Tests:\n===============")

expected = {
    "length": 3894.053,
    "coordinate_path": [
        [30, 160],
        [30.0, 160.0],
        [30.0935, 165.0005],
        [30.0, 170.0],
        [28.5, -178.5],
        [29.3168, -174.2807],
        [30.0, -170.0],
        [30.0935, -164.9995],
        [30.0, -160.0],
        [30, -160],
    ],
}

origin_node = {"latitude": 30, "longitude": 160}
destination_node = {"latitude": 30, "longitude": -160}

validate(
    name="Graph Validation",
    realized=oak_ridge_maritime_geograph.validate(
        check_symmetry=True, check_connected=False
    ),
    expected=None,
)
validate(
    name="Node Validation",
    realized=oak_ridge_maritime_geograph.validate_nodes(),
    expected=None,
)

validate(
    name="Dijkstra",
    realized=oak_ridge_maritime_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="dijkstra",
    ),
    expected=expected,
)

validate(
    name="A*-haversine",
    realized=oak_ridge_maritime_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="a_star",
        algorithm_kwargs={
            "heuristic_fn": oak_ridge_maritime_geograph.haversine
        },
    ),
    expected=expected,
)

validate(
    name="A*-cheap_ruler",
    realized=oak_ridge_maritime_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="a_star",
        algorithm_kwargs={
            "heuristic_fn": oak_ridge_maritime_geograph.cheap_ruler
        },
    ),
    expected=expected,
)

validate(
    name="BMSSP",
    realized=oak_ridge_maritime_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="bmssp",
    ),
    expected=expected,
)

print("\n===============\nOak Ridge GeoGraph Time Tests:\n===============")

time_test(
    "Graph Validation",
    oak_ridge_maritime_geograph.validate, kwargs ={
        "check_symmetry": True, "check_connected": False
    },
)
time_test(
    "Node Validation",
    oak_ridge_maritime_geograph.validate_nodes,
)

origin_node = {"latitude": 31.23, "longitude": 121.47}
destination_node = {"latitude": 32.08, "longitude": -81.09}


def dijkstra():
    oak_ridge_maritime_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="dijkstra",
    )


def a_star_haversine():
    oak_ridge_maritime_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="a_star",
        algorithm_kwargs={
            "heuristic_fn": oak_ridge_maritime_geograph.haversine
        },
    )


def a_star_cheap_ruler():
    oak_ridge_maritime_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="a_star",
        algorithm_kwargs={
            "heuristic_fn": oak_ridge_maritime_geograph.cheap_ruler
        },
    )


def bmssp():
    oak_ridge_maritime_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn="bmssp",
    )


time_test("Dijkstra", dijkstra)
time_test("A*-haversine", a_star_haversine)
time_test("A*-cheap_ruler", a_star_cheap_ruler)
time_test("BMSSP", bmssp)
# oak_ridge_maritime_geograph.save_as_geojson('oak_ridge_maritime.geojson')
