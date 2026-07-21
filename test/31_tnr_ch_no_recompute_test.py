import time
import pytest
from scgraph import GeoGraph
from scgraph.graph import Graph as PyGraph

try:
    from scgraph.cpp import Graph as CppGraph
    HAS_CPP = True
except ImportError:
    HAS_CPP = False


def _make_dummy_geograph(rows=12, cols=12):
    nodes = []
    graph = []
    for r in range(rows):
        for c in range(cols):
            # Coordinates range from 0.0 to 1.1
            nodes.append([float(r) / 10.0, float(c) / 10.0])
            edges = {}
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    neighbor_id = nr * cols + nc
                    edges[neighbor_id] = 1.0
            graph.append(edges)
    return GeoGraph(nodes=nodes, graph=graph)


def _run_no_recompute_test(graph_class):
    geo = _make_dummy_geograph(rows=12, cols=12)
    # Wrap in the target graph class (Python or C++)
    geo.graph_object = graph_class(graph=geo.graph)

    origin = {"latitude": 0.0, "longitude": 0.0}
    destination = {"latitude": 1.1, "longitude": 1.1}

    # 1. Test Contraction Hierarchy (CH)
    t0 = time.perf_counter()
    geo.graph_object.create_contraction_hierarchy()
    t_ch_preprocess = time.perf_counter() - t0

    t1 = time.perf_counter()
    res_ch = geo.get_shortest_path(
        origin, destination, algorithm_fn="contraction_hierarchy"
    )
    t_ch_query = time.perf_counter() - t1

    # Query must be significantly faster than preprocessing (at least 5x faster)
    assert (
        t_ch_query < t_ch_preprocess / 5
    ), f"CH query took {t_ch_query}s, preprocessing took {t_ch_preprocess}s (recomputed?)"

    # 2. Test Transit Node Routing (TNR)
    t2 = time.perf_counter()
    geo.graph_object.create_tnr_hierarchy(num_transit_nodes=20)
    t_tnr_preprocess = time.perf_counter() - t2

    t3 = time.perf_counter()
    res_tnr = geo.get_shortest_path(origin, destination, algorithm_fn="tnr")
    t_tnr_query = time.perf_counter() - t3

    # Query must be significantly faster than preprocessing (at least 5x faster)
    assert (
        t_tnr_query < t_tnr_preprocess / 5
    ), f"TNR query took {t_tnr_query}s, preprocessing took {t_tnr_preprocess}s (recomputed?)"

    # Verify correctness
    dijkstra = geo.get_shortest_path(
        origin, destination, algorithm_fn="dijkstra"
    )
    assert abs(res_ch["length"] - dijkstra["length"]) < 1e-3
    assert abs(res_tnr["length"] - dijkstra["length"]) < 1e-3


def test_python_no_recompute():
    _run_no_recompute_test(PyGraph)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_no_recompute():
    _run_no_recompute_test(CppGraph)
