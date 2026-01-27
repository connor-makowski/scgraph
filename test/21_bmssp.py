import time
from pamda import pamda
from scgraph import Graph
from scgraph.utils import hard_round
from scgraph.geographs.marnet import marnet_geograph
from scgraph.geographs.us_freeway import us_freeway_geograph

# from scgraph_data.world_highways_and_marnet import world_highways_and_marnet_graph


print("\n===============\nBMSSP Tests:\n===============")


def validate(name, realized, expected):
    # Custom lenth rounding for floating point precision issues
    if isinstance(realized, dict):
        if "length" in realized:
            realized["length"] = hard_round(3, realized["length"])
    if isinstance(expected, dict):
        if "length" in expected:
            expected["length"] = hard_round(3, expected["length"])
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

marnet_graph = marnet_geograph.graph_object
us_freeway_graph = us_freeway_geograph.graph_object
# world_highways_and_marnet_graph = world_highways_and_marnet_graph.geograph_object

validate(
    name="BMSSP 1 (marnet)",
    realized=marnet_graph.bmssp(0, 5),
    expected=marnet_graph.dijkstra(0, 5),
)

validate(
    name="BMSSP 2 (marnet)",
    realized=marnet_graph.bmssp(100, 7999),
    expected=marnet_graph.dijkstra(100, 7999),
)

validate(
    name="BMSSP 3 (marnet)",
    realized=marnet_graph.bmssp(4022, 8342),
    expected=marnet_graph.dijkstra(4022, 8342),
)

validate(
    name="BMSSP 4 (us_freeway)",
    realized=us_freeway_graph.bmssp(0, 5),
    expected=us_freeway_graph.dijkstra(0, 5),
)

validate(
    name="BMSSP 5 (us_freeway)",
    realized=us_freeway_graph.bmssp(4022, 8342),
    expected=us_freeway_graph.dijkstra(4022, 8342),
)

# validate(
#     name="BMSSP 6 (world_highways_and_marnet)",
#     realized=world_highways_and_marnet_graph.bmssp(0, 5),
#     expected=world_highways_and_marnet_graph.dijkstra(0, 5),
# )

print("\n===============\nBMSSP Time Tests:\n===============")

time_test(
    "BMSSP 1 (marnet)",
    pamda.thunkify(marnet_graph.bmssp)(
        origin_id=0, destination_id=5
    ),
)
time_test(
    "BMSSP 2 (marnet)",
    pamda.thunkify(marnet_graph.bmssp)(
origin_id=100, destination_id=7999
    ),
)
time_test(
    "BMSSP 3 (marnet)",
    pamda.thunkify(marnet_graph.bmssp)(
       origin_id=4022, destination_id=8342
    ),
)

time_test(
    "BMSSP 4 (us_freeway)",
    pamda.thunkify(us_freeway_graph.bmssp)(
        origin_id=0, destination_id=5
    ),
)

time_test(
    "BMSSP 5 (us_freeway)",
    pamda.thunkify(us_freeway_graph.bmssp)(
        origin_id=4022, destination_id=8342
    ),
)

# time_test(
#     "BMSSP 6 (world_highways_and_marnet)",
#     pamda.thunkify(world_highways_and_marnet_graph.bmssp)(
#         origin_id=0,
#         destination_id=5
#     ),
# )

time_test(
    "Shortest Path Tree Comparison (marnet)",
    pamda.thunkify(marnet_graph.get_shortest_path_tree)(origin_id=0),
)

time_test(
    "Shortest Path Tree Comparison (us_freeway)",
    pamda.thunkify(us_freeway_graph.get_shortest_path_tree)(origin_id=0),
)

# time_test(
#     "Shortest Path Tree Comparison (world_highways)",
#     pamda.thunkify(ShortestPathTree.shortest_path_tree)(
#         graph=world_highways_and_marnet_graph,
#         node_id=0
#     ),
# )
