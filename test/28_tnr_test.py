from scgraph import GeoGraph
from scgraph.transit_node_routing import TNRGraph as PyTNRGraph
from scgraph.graph import Graph as PyGraph
import time, os

try:
    from scgraph.cpp import TNRGraph as CppTNRGraph
    from scgraph.cpp import Graph as CppGraph

    has_cpp = True
except ImportError:
    has_cpp = False

print("\n===============\nTNR Tests:\n===============")


def test_tnr_basic():
    def run_basic(TNRGraphClass, name):
        print(f"\nTesting TNR Basic ({name})...")
        # Small test graph
        graph = [
            {1: 5, 2: 1},
            {0: 5, 2: 2, 3: 1},
            {0: 1, 1: 2, 3: 4, 4: 8},
            {1: 1, 2: 4, 4: 3, 5: 6},
            {2: 8, 3: 3},
            {3: 6},
        ]
        tnr = TNRGraphClass(graph=graph, num_transit_nodes=2)

        # Test point to point
        res = tnr.get_shortest_path(0, 5)
        print(f"Path: {res['path']}, Length: {res['length']}")
        assert res["length"] == 10
        assert res["path"] == [0, 2, 1, 3, 5]
        print(f"TNR Basic Passed ({name})!")

    run_basic(PyTNRGraph, "Python")
    if has_cpp:
        run_basic(CppTNRGraph, "C++")


def test_tnr_geograph():
    def run_geograph(GraphClass, name):
        print(f"\nTesting TNR with GeoGraph (Marnet) - {name}...")
        marnet = GeoGraph.load_geograph("marnet")
        marnet.graph_object = GraphClass(graph=marnet.graph)

        # Preprocess TNR with 100 transit nodes
        start_time = time.time()
        marnet.graph_object.create_tnr_hierarchy(num_transit_nodes=100)
        print(f"TNR Preprocessing took: {time.time() - start_time:.2f}s")

        # Shanghai to Savannah
        origin = {"latitude": 31.23, "longitude": 121.47}
        destination = {"latitude": 32.08, "longitude": -81.09}

        # Standard Dijkstra for baseline
        start_time = time.time()
        dijkstra_res = marnet.get_shortest_path(
            origin, destination, algorithm_fn="dijkstra"
        )
        dijkstra_time = time.time() - start_time
        print(
            f"Dijkstra took: {dijkstra_time:.4f}s, Length: {dijkstra_res['length']}"
        )

        # Contraction Hierarchy for comparison
        marnet.graph_object.create_contraction_hierarchy()
        start_time = time.time()
        ch_res = marnet.get_shortest_path(
            origin, destination, algorithm_fn="contraction_hierarchy"
        )
        ch_time = time.time() - start_time
        print(f"CH (path) took: {ch_time:.4f}s, Length: {ch_res['length']}")

        # TNR
        start_time = time.time()
        tnr_res = marnet.get_shortest_path(
            origin, destination, algorithm_fn="tnr"
        )
        tnr_time = time.time() - start_time
        print(f"TNR (path) took: {tnr_time:.4f}s, Length: {tnr_res['length']}")

        # TNR length only (should be ~O(1))
        start_time = time.time()
        tnr_len_res = marnet.get_shortest_path(
            origin, destination, algorithm_fn="tnr", length_only=True
        )
        tnr_len_time = time.time() - start_time
        print(
            f"TNR (length_only) took: {tnr_len_time:.4f}s, Length: {tnr_len_res['length']}"
        )

        # Verify results are close (floating point)
        assert abs(dijkstra_res["length"] - tnr_res["length"]) < 1e-3
        assert abs(dijkstra_res["length"] - ch_res["length"]) < 1e-3
        assert abs(dijkstra_res["length"] - tnr_len_res["length"]) < 1e-3
        print(
            f"TNR Speedup over Dijkstra (path): {dijkstra_time / tnr_time:.2f}x"
        )
        print(f"TNR Speedup over CH (path): {ch_time / tnr_time:.2f}x")
        print(
            f"TNR Speedup over CH (length_only): {ch_time / tnr_len_time:.2f}x"
        )
        print(f"TNR GeoGraph Passed ({name})!")

    run_geograph(PyGraph, "Python")
    if has_cpp:
        run_geograph(CppGraph, "C++")


def test_tnr_save_load():
    def run_save_load(TNRGraphClass, name):
        print(f"\nTesting TNR Save/Load ({name})...")
        graph = [
            {1: 5, 2: 1},
            {0: 5, 2: 2, 3: 1},
            {0: 1, 1: 2, 3: 4, 4: 8},
            {1: 1, 2: 4, 4: 3, 5: 6},
            {2: 8, 3: 3},
            {3: 6},
        ]
        tnr = TNRGraphClass(graph=graph, num_transit_nodes=2)
        filename = f"test_tnr_{name}.tnrjson"
        tnr.save_as_tnrjson(filename)

        tnr_loaded = TNRGraphClass.load_from_tnrjson(filename)
        res = tnr_loaded.get_shortest_path(0, 5)
        assert res["length"] == 10
        os.remove(filename)
        print(f"TNR Save/Load Passed ({name})!")

    run_save_load(PyTNRGraph, "Python")
    if has_cpp:
        run_save_load(CppTNRGraph, "C++")


if __name__ == "__main__":
    test_tnr_basic()
    test_tnr_geograph()
    test_tnr_save_load()
