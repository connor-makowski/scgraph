import time
from pamda import pamda
from scgraph import Graph
from scgraph.geographs.oak_ridge_maritime import oak_ridge_maritime_geograph


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
    realized=oak_ridge_maritime_geograph.validate_graph(
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
    name="Dijkstra-Modified",
    realized=oak_ridge_maritime_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.dijkstra_makowski,
    ),
    expected=expected,
)

validate(
    name="A*-haversine",
    realized=oak_ridge_maritime_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.a_star,
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
        algorithm_fn=Graph.a_star,
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
        algorithm_fn=Graph.bmssp,
    ),
    expected=expected,
)

print("\n===============\nOak Ridge GeoGraph Time Tests:\n===============")

time_test(
    "Graph Validation",
    pamda.thunkify(oak_ridge_maritime_geograph.validate_graph)(
        check_symmetry=True, check_connected=False
    ),
)
time_test(
    "Node Validation",
    pamda.thunkify(oak_ridge_maritime_geograph.validate_nodes),
)

origin_node = {"latitude": 31.23, "longitude": 121.47}
destination_node = {"latitude": 32.08, "longitude": -81.09}


def dijkstra_makowski():
    oak_ridge_maritime_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.dijkstra_makowski,
    )


def a_star_haversine():
    oak_ridge_maritime_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.a_star,
        algorithm_kwargs={
            "heuristic_fn": oak_ridge_maritime_geograph.haversine
        },
    )


def a_star_cheap_ruler():
    oak_ridge_maritime_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.a_star,
        algorithm_kwargs={
            "heuristic_fn": oak_ridge_maritime_geograph.cheap_ruler
        },
    )


def bmssp():
    oak_ridge_maritime_geograph.get_shortest_path(
        origin_node=origin_node,
        destination_node=destination_node,
        algorithm_fn=Graph.bmssp,
    )


time_test("Dijkstra-Modified", dijkstra_makowski)
time_test("A*-haversine", a_star_haversine)
time_test("A*-cheap_ruler", a_star_cheap_ruler)
time_test("BMSSP", bmssp)
# oak_ridge_maritime_geograph.save_as_geojson('oak_ridge_maritime.geojson')
