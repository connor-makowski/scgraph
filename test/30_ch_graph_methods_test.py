from scgraph.graph import Graph as PythonGraph
from scgraph.cpp import Graph as CPPGraph
import math


def run_ch_test(GraphClass, name):
    print(f"\n--- Testing {name} Graph ---")
    # Define a simple graph
    graph_data = [
        {1: 5, 2: 1},
        {0: 5, 2: 2, 3: 1},
        {0: 1, 1: 2, 3: 4, 4: 8},
        {1: 1, 2: 4, 4: 3, 5: 6},
        {2: 8, 3: 3},
        {3: 6},
    ]

    g = GraphClass(graph=graph_data)

    print(f"[{name}] Testing create_ch...")
    try:
        ch = g.create_ch()
        print(f"[{name}] create_ch successful")
    except Exception as e:
        print(f"[{name}] create_ch failed: {e}")
        return

    print(f"[{name}] Testing ch_shortest_path with multiple queries...")
    queries = [
        (0, 5, [0, 2, 1, 3, 5], 10),
        (0, 4, [0, 2, 1, 3, 4], 7),  # 0->2(1), 2->1(2), 1->3(1), 3->4(3) = 7
        (5, 0, [5, 3, 1, 2, 0], 10),
    ]
    for start, end, expected_path, expected_len in queries:
        output = g.ch_shortest_path(origin_id=start, destination_id=end)
        assert (
            list(output["path"]) == expected_path
        ), f"[{name}] Query {start}->{end}: Expected path {expected_path}, got {output['path']}"
        assert math.isclose(
            output["length"], expected_len
        ), f"[{name}] Query {start}->{end}: Expected length {expected_len}, got {output['length']}"
    print(f"[{name}] Multiple queries successful")

    print(f"[{name}] Testing create_ch with custom heuristic...")

    def custom_heuristic(graph, node_id):
        return float(-node_id)  # Reverse order of nodes

    try:
        ch_custom = g.create_ch(heuristic_fn=custom_heuristic)
        assert ch_custom is not None
        output = g.ch_shortest_path(origin_id=0, destination_id=5)
        assert math.isclose(output["length"], 10)
        print(f"[{name}] create_ch with custom heuristic successful")
    except Exception as e:
        print(f"[{name}] create_ch with custom heuristic failed: {e}")
        import traceback

        traceback.print_exc()


def test_geograph_ch():
    print("\n--- Testing GeoGraph with CH ---")
    from scgraph.geographs.marnet import marnet_geograph
    from scgraph.graph import Graph as PythonGraph

    # Original GeoGraph test (likely uses whatever default graph object it has, usually CPP if available)
    print(
        "Testing GeoGraph with default graph (likely CPP) and ch_shortest_path..."
    )
    # Shanghai to Savannah
    origin = {"latitude": 31.23, "longitude": 121.47}
    dest = {"latitude": 32.08, "longitude": -81.09}

    try:
        output = marnet_geograph.get_shortest_path(
            origin_node=origin,
            destination_node=dest,
            algorithm_fn="ch_shortest_path",
        )
        print(f"GeoGraph CH length: {output['length']}")
        assert output["length"] > 0
        print("GeoGraph with default graph and ch_shortest_path successful")
    except Exception as e:
        print(f"GeoGraph with default graph and ch_shortest_path failed: {e}")
        import traceback

        traceback.print_exc()

    # Force marnet_geograph to use the Python Graph object
    print("Testing GeoGraph with forced Python graph and ch_shortest_path...")
    marnet_geograph.graph_object = PythonGraph(
        graph=marnet_geograph.graph_object.graph
    )

    try:
        output = marnet_geograph.get_shortest_path(
            origin_node=origin,
            destination_node=dest,
            algorithm_fn="ch_shortest_path",
        )
        print(f"GeoGraph (Python) CH length: {output['length']}")
        assert output["length"] > 0
        print("GeoGraph with Python graph and ch_shortest_path successful")
    except Exception as e:
        print(f"GeoGraph with Python graph and ch_shortest_path failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    run_ch_test(PythonGraph, "Python")
    run_ch_test(CPPGraph, "CPP")
    test_geograph_ch()
