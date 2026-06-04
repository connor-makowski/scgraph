import os
import pytest
from scgraph import GeoGraph
from scgraph.transit_node_routing import TNRGraph as PyTNRGraph
from scgraph.graph import Graph as PyGraph

try:
    from scgraph.cpp import TNRGraph as CppTNRGraph
    from scgraph.cpp import Graph as CppGraph

    HAS_CPP = True
except ImportError:
    HAS_CPP = False

_SMALL_GRAPH = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
]


def _test_basic(tnr_class):
    tnr = tnr_class(graph=_SMALL_GRAPH, num_transit_nodes=2)
    res = tnr.get_shortest_path(0, 5)
    assert res["length"] == 10
    assert res["path"] == [0, 2, 1, 3, 5]


def _test_geograph(graph_class):
    geo = GeoGraph.load_geograph("marnet")
    geo.graph_object = graph_class(graph=geo.graph)
    geo.graph_object.create_tnr_hierarchy(num_transit_nodes=100)
    geo.graph_object.create_contraction_hierarchy()
    origin = {"latitude": 31.23, "longitude": 121.47}
    destination = {"latitude": 32.08, "longitude": -81.09}
    dijkstra = geo.get_shortest_path(
        origin, destination, algorithm_fn="dijkstra"
    )
    ch = geo.get_shortest_path(
        origin, destination, algorithm_fn="contraction_hierarchy"
    )
    tnr = geo.get_shortest_path(origin, destination, algorithm_fn="tnr")
    tnr_len = geo.get_shortest_path(
        origin, destination, algorithm_fn="tnr", length_only=True
    )
    assert abs(dijkstra["length"] - tnr["length"]) < 1e-3
    assert abs(dijkstra["length"] - ch["length"]) < 1e-3
    assert abs(dijkstra["length"] - tnr_len["length"]) < 1e-3


def _test_save_load(tnr_class, tmp_path):
    tnr = tnr_class(graph=_SMALL_GRAPH, num_transit_nodes=2)
    path = str(tmp_path / "test.tnrjson")
    tnr.save_as_tnrjson(path)
    loaded = tnr_class.load_from_tnrjson(path)
    assert loaded.get_shortest_path(0, 5)["length"] == 10


def test_python_tnr_basic():
    _test_basic(PyTNRGraph)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_tnr_basic():
    _test_basic(CppTNRGraph)


def test_python_tnr_geograph():
    _test_geograph(PyGraph)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_tnr_geograph():
    _test_geograph(CppGraph)


def test_python_tnr_save_load(tmp_path):
    _test_save_load(PyTNRGraph, tmp_path)


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_tnr_save_load(tmp_path):
    _test_save_load(CppTNRGraph, tmp_path)
