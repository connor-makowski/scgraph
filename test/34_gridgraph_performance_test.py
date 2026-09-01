import time
import pytest
from scgraph import GridGraph
from scgraph.graph import Graph as PyGraph

try:
    from scgraph.cpp import Graph as CppGraph

    HAS_CPP = True
except ImportError:
    from scgraph.graph import Graph as CppGraph

    HAS_CPP = False


def _run_performance_test(graph_class, is_cpp):
    # 1. Test Contraction Hierarchy on 100x100 grid graph
    grid_ch = GridGraph(
        x_size=100,
        y_size=100,
        blocks=[],
        add_exterior_walls=True,
    )
    grid_ch.graph_object = graph_class(grid_ch.graph)

    t0 = time.perf_counter()
    grid_ch.graph_object.create_contraction_hierarchy()
    elapsed_ch = time.perf_counter() - t0
    assert (
        elapsed_ch < 10.0
    ), f"CH build took too long: {elapsed_ch:.2f} seconds"

    # 2. Test Transit Node Routing
    # Python TNR build is too slow for 100x100 under 10s, so we scale it down for Python
    tnr_size = 100 if is_cpp else 20
    grid_tnr = GridGraph(
        x_size=tnr_size,
        y_size=tnr_size,
        blocks=[],
        add_exterior_walls=True,
    )
    grid_tnr.graph_object = graph_class(grid_tnr.graph)

    t1 = time.perf_counter()
    # Build CH and TNR
    grid_tnr.graph_object.create_contraction_hierarchy()
    grid_tnr.graph_object.create_tnr_hierarchy(num_transit_nodes=20)
    elapsed_tnr = time.perf_counter() - t1
    assert (
        elapsed_tnr < 10.0
    ), f"TNR build ({tnr_size}x{tnr_size}) took too long: {elapsed_tnr:.2f} seconds"


def test_python_gridgraph_performance():
    _run_performance_test(PyGraph, is_cpp=False)


@pytest.mark.skipif(
    not HAS_CPP or CppGraph == PyGraph, reason="C++ extension not available"
)
def test_cpp_gridgraph_performance():
    _run_performance_test(CppGraph, is_cpp=True)
