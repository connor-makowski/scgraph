import time
from pamda import pamda
from scgraph import Graph
from scgraph.utils import hard_round
from scgraph.geographs.marnet import graph as marnet_graph


def validate(name, realized, expected):
    if realized == expected:
        if isinstance(realized, dict):
            if "length" in realized:
                realized["length"] = hard_round(4, realized["length"])
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

graph = marnet_graph

expected = {"path": [0, 1, 5695, 64, 2213, 10152, 6749, 5], "length": 1134.729}

validate(
    name="Graph Validation",
    realized=Graph.validate_graph(graph=graph),
    expected=None,
)

validate(
    name="Dijkstra",
    realized=Graph.dijkstra(graph=graph, origin_id=0, destination_id=5),
    expected=expected,
)

validate(
    name="Dijkstra-Makowski",
    realized=Graph.dijkstra_makowski(
        graph=graph, origin_id=0, destination_id=5
    ),
    expected=expected,
)

validate(
    name="A*-Makowski",
    realized=Graph.a_star_makowski(graph=graph, origin_id=0, destination_id=5),
    expected=expected,
)

print("\n===============\nMarnet Time Tests:\n===============")

time_test(
    "Graph Validation",
    pamda.thunkify(Graph.validate_graph)(
        graph=graph, check_symmetry=True, check_connected=True
    ),
)

time_test(
    "Dijkstra 1",
    pamda.thunkify(Graph.dijkstra)(graph=graph, origin_id=0, destination_id=5),
)
time_test(
    "Dijkstra 2",
    pamda.thunkify(Graph.dijkstra)(
        graph=graph, origin_id=100, destination_id=7999
    ),
)
time_test(
    "Dijkstra 3",
    pamda.thunkify(Graph.dijkstra)(
        graph=graph, origin_id=4022, destination_id=8342
    ),
)

time_test(
    "Dijkstra-Makowski 1",
    pamda.thunkify(Graph.dijkstra_makowski)(
        graph=graph, origin_id=0, destination_id=5
    ),
)
time_test(
    "Dijkstra-Makowski 2",
    pamda.thunkify(Graph.dijkstra_makowski)(
        graph=graph, origin_id=100, destination_id=7999
    ),
)
time_test(
    "Dijkstra-Makowski 3",
    pamda.thunkify(Graph.dijkstra_makowski)(
        graph=graph, origin_id=4022, destination_id=8342
    ),
)

time_test(
    "A*-Makowski 1",
    pamda.thunkify(Graph.a_star_makowski)(
        graph=graph, origin_id=0, destination_id=5, heuristic_fn=lambda x, y: 0
    ),
)
time_test(
    "A*-Makowski 2",
    pamda.thunkify(Graph.a_star_makowski)(
        graph=graph, origin_id=100, destination_id=7999, heuristic_fn=lambda x, y: 0
    ),
)
time_test(
    "A*-Makowski 3",
    pamda.thunkify(Graph.a_star_makowski)(
        graph=graph, origin_id=4022, destination_id=8342, heuristic_fn=lambda x, y: 0
    ),
)