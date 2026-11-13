import random
from scgraph.graph import Graph as PythonGraph

from helpers import CppGraph, needs_the_cpp_extension

random.seed(42)


def _make_int_grid(size):
    data = []
    for y in range(size):
        for x in range(size):
            node_id = x + y * size
            edges = {}
            if x + 1 < size:
                edges[node_id + 1] = random.randint(1, 10)
            if y + 1 < size:
                edges[node_id + size] = random.randint(1, 10)
            data.append(edges)
    return data


def _make_float_grid(size):
    data = []
    for y in range(size):
        for x in range(size):
            node_id = x + y * size
            edges = {}
            if x + 1 < size:
                edges[node_id + 1] = random.uniform(0.1, 10.0)
            if y + 1 < size:
                edges[node_id + size] = random.uniform(0.1, 10.0)
            data.append(edges)
    return data


def test_buckets_matches_dijkstra_int(graph_class):
    data = _make_int_grid(200)
    g = graph_class(data)
    dijkstra = g.dijkstra(0, len(data) - 1)
    buckets = g.dijkstra_buckets(0, len(data) - 1)
    assert round(buckets["length"], 6) == round(dijkstra["length"], 6)


def test_buckets_matches_dijkstra_float(graph_class):
    data = _make_float_grid(200)
    g = graph_class(data)
    dijkstra = g.dijkstra(0, len(data) - 1)
    buckets = g.dijkstra_buckets(0, len(data) - 1)
    assert round(buckets["length"], 6) == round(dijkstra["length"], 6)


@needs_the_cpp_extension
def test_cpp_vs_python_buckets_agree_int():
    data = _make_int_grid(200)
    py = PythonGraph(data).dijkstra_buckets(0, len(data) - 1)
    cpp = CppGraph(data).dijkstra_buckets(0, len(data) - 1)
    assert round(py["length"], 6) == round(cpp["length"], 6)


def test_buckets_on_marnet(marnet):
    graph = marnet.graph_object
    buckets = graph.dijkstra_buckets(0, 5)
    dijkstra = graph.dijkstra(0, 5)
    assert round(buckets["length"], 6) == round(dijkstra["length"], 6)


def test_buckets_on_us_freeway(us_freeway):
    graph = us_freeway.graph_object
    buckets = graph.dijkstra_buckets(0, 5)
    dijkstra = graph.dijkstra(0, 5)
    assert round(buckets["length"], 6) == round(dijkstra["length"], 6)
