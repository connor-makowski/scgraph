from scgraph.utils import validate, time_test
from scgraph.geographs.marnet import marnet_geograph
from scgraph.geographs.us_freeway import us_freeway_geograph

# from scgraph_data.world_highways_and_marnet import world_highways_and_marnet_graph


print("\n===============\nBMSSP Tests:\n===============")


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
    marnet_graph.bmssp, kwargs={
        "origin_id": 0, "destination_id": 5
    },
)
time_test(
    "BMSSP 2 (marnet)",
    marnet_graph.bmssp, kwargs={
        "origin_id": 100, "destination_id": 7999
    },
)
time_test(
    "BMSSP 3 (marnet)",
    marnet_graph.bmssp, kwargs={
       "origin_id": 4022, "destination_id": 8342
    },
)

time_test(
    "BMSSP 4 (us_freeway)",
    us_freeway_graph.bmssp, kwargs={
        "origin_id": 0, "destination_id": 5
    },
)

time_test(
    "BMSSP 5 (us_freeway)",
    us_freeway_graph.bmssp, kwargs={
        "origin_id": 4022, "destination_id": 8342
    },
)

# time_test(
#     "BMSSP 6 (world_highways_and_marnet)",
#     world_highways_and_marnet_graph.bmssp, kwargs={
#         "origin_id": 0, "destination_id": 5
#     },
# )

time_test(
    "Shortest Path Tree Comparison (marnet)",
    marnet_graph.get_shortest_path_tree, kwargs={
        "origin_id": 0
    },
)

time_test(
    "Shortest Path Tree Comparison (us_freeway)",
    us_freeway_graph.get_shortest_path_tree, kwargs={
        "origin_id": 0
    },
)

# time_test(
#     "Shortest Path Tree Comparison (world_highways)",
#     ShortestPathTree.shortest_path_tree, kwargs={
#         "graph": world_highways_and_marnet_graph,
#         "node_id": 0
#     },
# )
