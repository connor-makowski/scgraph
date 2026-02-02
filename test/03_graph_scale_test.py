from scgraph import Graph
from scgraph.utils import time_test


def gen_graph(size, avg_connections=10):
    return Graph([
        {i + j: 1 for j in range(1, avg_connections) if i + j < size}
        for i in range(size)
    ])


print("\n===============\nScale Time Tests:\n===============")

for size in [100, 1000, 10000, 100000]:
    graph = gen_graph(size)
    print(f"\nGraph Size: {size}")
    time_test(
        f"Graph Validation ({size})",
        graph.validate,
        kwargs={"check_symmetry": False, "check_connected": False},
    )
    time_test(
        f"Dijkstra ({size})",
        graph.dijkstra,
        kwargs={"origin_id": 0, "destination_id": size - 1},
    )
    time_test(
        f"A* ({size})",
        graph.a_star,
        kwargs={
            "origin_id": 0,
            "destination_id": size - 1,
            "heuristic_fn": lambda x, y: 0,
        },
    )
    # time_test(
    #     f"BMSSP ({size})",
    #     graph.bmssp,
    #     kwargs={
    #         "origin_id": 0, "destination_id": size - 1, "constant_degree_graph": False
    #     },
    # )
