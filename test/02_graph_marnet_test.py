from scgraph import Graph
from scgraph.utils import validate, time_test
from scgraph.geographs.marnet import marnet_geograph

print("\n===============\nMarnet Graph Tests:\n===============")

graph = Graph(marnet_geograph.graph_object.graph)

expected = {"path": [0, 1, 5695, 64, 2213, 10152, 6749, 5], "length": 1134.729}

validate(
    name="Graph Validation",
    realized=graph.validate(),
    expected=None,
)

validate(
    name="Dijkstra",
    realized=graph.dijkstra(origin_id=0, destination_id=5),
    expected=expected,
)

validate(
    name="A*",
    realized=graph.a_star(origin_id=0, destination_id=5),
    expected=expected,
)

# validate(
#     name="BMSSP",
#     realized=graph.bmssp(origin_id=0, destination_id=5),
#     expected=expected,
# )


print("\n===============\nMarnet Time Tests:\n===============")

time_test(
    "Graph Validation",
    graph.validate,
    kwargs={"check_symmetry": True, "check_connected": True},
)


time_test(
    "Dijkstra 1",
    graph.dijkstra,
    kwargs={"origin_id": 0, "destination_id": 5},
)
time_test(
    "Dijkstra 2",
    graph.dijkstra,
    kwargs={"origin_id": 100, "destination_id": 7999},
)
time_test(
    "Dijkstra 3",
    graph.dijkstra,
    kwargs={"origin_id": 4022, "destination_id": 8342},
)

time_test(
    "A* 1",
    graph.a_star,
    kwargs={
        "origin_id": 0,
        "destination_id": 5,
        "heuristic_fn": lambda x, y: 0,
    },
)
time_test(
    "A* 2",
    graph.a_star,
    kwargs={
        "origin_id": 100,
        "destination_id": 7999,
        "heuristic_fn": lambda x, y: 0,
    },
)
time_test(
    "A* 3",
    graph.a_star,
    kwargs={
        "origin_id": 4022,
        "destination_id": 8342,
        "heuristic_fn": lambda x, y: 0,
    },
)

# time_test(
#     "BMSSP 1",
#     pamda.thunkify(graph.bmssp)(origin_id=0, destination_id=5),
# )

# time_test(
#     "BMSSP 2",
#     pamda.thunkify(graph.bmssp)(
#         origin_id=100, destination_id=7999
#     ),
# )

# time_test(
#     "BMSSP 3",
#     pamda.thunkify(graph.bmssp)(
#         origin_id=4022, destination_id=8342
#     ),
# )
