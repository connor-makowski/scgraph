import time
from pamda import pamda
from scgraph import Graph
from scgraph.utils import hard_round
from scgraph.geographs.marnet import marnet_geograph


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
    realized=graph.dijkstra(
        origin_id=0, destination_id=5
    ),
    expected=expected,
)

validate(
    name="A*",
    realized=graph.a_star(origin_id=0, destination_id=5),
    expected=expected,
)

validate(
    name="BMSSP",
    realized=graph.bmssp(origin_id=0, destination_id=5),
    expected=expected,
)


print("\n===============\nMarnet Time Tests:\n===============")

time_test(
    "Graph Validation",
    pamda.thunkify(graph.validate)(
       check_symmetry=True, check_connected=True
    ),
)


time_test(
    "Dijkstra 1",
    pamda.thunkify(graph.dijkstra)(
        origin_id=0, destination_id=5
    ),
)
time_test(
    "Dijkstra 2",
    pamda.thunkify(graph.dijkstra)(
        origin_id=100, destination_id=7999
    ),
)
time_test(
    "Dijkstra 3",
    pamda.thunkify(graph.dijkstra)(
        origin_id=4022, destination_id=8342
    ),
)

time_test(
    "A* 1",
    pamda.thunkify(graph.a_star)(
        origin_id=0, destination_id=5, heuristic_fn=lambda x, y: 0
    ),
)
time_test(
    "A* 2",
    pamda.thunkify(graph.a_star)(
        
        origin_id=100,
        destination_id=7999,
        heuristic_fn=lambda x, y: 0,
    ),
)
time_test(
    "A* 3",
    pamda.thunkify(graph.a_star)(
        
        origin_id=4022,
        destination_id=8342,
        heuristic_fn=lambda x, y: 0,
    ),
)

time_test(
    "BMSSP 1",
    pamda.thunkify(graph.bmssp)(origin_id=0, destination_id=5),
)

time_test(
    "BMSSP 2",
    pamda.thunkify(graph.bmssp)(
        origin_id=100, destination_id=7999
    ),
)

time_test(
    "BMSSP 3",
    pamda.thunkify(graph.bmssp)(
        origin_id=4022, destination_id=8342
    ),
)
