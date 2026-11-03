import pytest
from scgraph.graph import Graph as PyGraph
from scgraph.graph_utils import normalize_node_input
from heapq import heapify, heappop, heappush

try:
    from scgraph.cpp import Graph as CppGraph

    GRAPH_CLASSES = [PyGraph, CppGraph]
except ImportError:
    GRAPH_CLASSES = [PyGraph]


def _build_test_graph():
    # Chain A: 0 - 1 - 2 - 3 (pass-throughs: 1, 2)
    # Chain B: 3 - 4 - 5 - 6 (pass-throughs: 4, 5)
    # Junction: 3 (with leaf 7)
    # Leaf: 6
    return [
        {1: 2.0},  # 0
        {0: 2.0, 2: 3.0},  # 1 (pass-through)
        {1: 3.0, 3: 4.0},  # 2 (pass-through)
        {2: 4.0, 4: 1.5, 7: 1.0},  # 3 (junction)
        {3: 1.5, 5: 2.5},  # 4 (pass-through)
        {4: 2.5, 6: 1.0},  # 5 (pass-through)
        {5: 1.0},  # 6
        {3: 1.0},  # 7: leaf on the junction, so that 3 stays after reduce()
    ]


def _tree(graph, ends):
    """Dijkstra from every entry of ends (a node id, or node id -> start distance, as the
    decorator passes them): distances and predecessors."""
    dist, pred = [float("inf")] * len(graph), [-1] * len(graph)
    heap = [(d, n) for n, d in normalize_node_input(ends).items()]
    for d, n in heap:
        dist[n] = d
    heapify(heap)
    while heap:
        d, u = heappop(heap)
        if d > dist[u]:
            continue
        for v, w in graph[u].items():
            if d + w < dist[v]:
                dist[v], pred[v] = d + w, u
                heappush(heap, (d + w, v))
    return dist, pred


def _walk(pred, node):
    path = []
    while node != -1:
        path.append(node)
        node = pred[node]
    return path


# Custom algorithms written as the README shows: they read search_graph and
# search_inverse_graph, and accept dicts of nodes with distances
@PyGraph.algorithm
def _custom(self, origin_id, destination_id):
    dist, pred = _tree(self.search_graph, origin_id)
    targets = normalize_node_input(destination_id)
    end = min(targets, key=lambda t: dist[t] + targets[t])
    return {"path": _walk(pred, end)[::-1], "length": dist[end] + targets[end]}


@PyGraph.algorithm(bidirectional=True)
def _custom_bidirectional(self, origin_id, destination_id):
    forward, forward_pred = _tree(self.search_graph, origin_id)
    backward, backward_pred = _tree(self.search_inverse_graph, destination_id)
    meet = min(range(len(forward)), key=lambda v: forward[v] + backward[v])
    return {
        "path": _walk(forward_pred, meet)[::-1]
        + _walk(backward_pred, meet)[1:],
        "length": forward[meet] + backward[meet],
    }


@pytest.mark.parametrize("algorithm", [_custom, _custom_bidirectional])
@pytest.mark.parametrize(
    "GraphClass", GRAPH_CLASSES, ids=lambda cls: cls.__module__.split(".")[-1]
)
def test_custom_algorithm_decorator(GraphClass, algorithm):
    g = GraphClass(_build_test_graph())
    across = {"path": [1, 2, 3, 4, 5], "length": pytest.approx(11.0)}
    assert algorithm(g, 1, 5) == across
    g.reduce()
    assert algorithm(g, 1, 2) == {"path": [1, 2], "length": pytest.approx(3.0)}
    assert algorithm(g, 1, 5) == across  # from one chain to another, through 3


def test_registered_algorithm():
    @PyGraph.algorithm(name="my_plugin_algo")
    def my_plugin(self, origin_id: int, destination_id: int) -> dict:
        return self.dijkstra(origin_id, destination_id)

    g = PyGraph(_build_test_graph())
    assert hasattr(g, "my_plugin_algo")
    res = g.my_plugin_algo(0, 6)
    assert abs(res["length"] - 14.0) < 1e-6
    assert res["path"] == [0, 1, 2, 3, 4, 5, 6]

    g.reduce()
    res_red = g.my_plugin_algo(1, 5)
    assert abs(res_red["length"] - 11.0) < 1e-6
    assert res_red["path"] == [1, 2, 3, 4, 5]
