import pytest
from scgraph.graph import Graph as PyGraph
from scgraph import GeoGraph
from heapq import heappop, heappush

try:
    from scgraph.cpp import Graph as CppGraph

    HAS_CPP = True
except ImportError:
    HAS_CPP = False


def _build_test_graph():
    # Chain A: 0 - 1 - 2 - 3 (pass-throughs: 1, 2)
    # Chain B: 3 - 4 - 5 - 6 (pass-throughs: 4, 5)
    # Junction: 3
    # Leaf: 6
    return [
        {1: 2.0},  # 0
        {0: 2.0, 2: 3.0},  # 1 (pass-through)
        {1: 3.0, 3: 4.0},  # 2 (pass-through)
        {2: 4.0, 4: 1.5},  # 3 (junction)
        {3: 1.5, 5: 2.5},  # 4 (pass-through)
        {4: 2.5, 6: 1.0},  # 5 (pass-through)
        {5: 1.0},  # 6
    ]


def test_custom_algorithm_decorator():
    # Define a custom 1-sided Dijkstra using @PyGraph.algorithm
    @PyGraph.algorithm
    def my_dijkstra(self, origin_id: int, destination_id: int) -> dict:
        graph = self.graph
        dist = [float("inf")] * len(graph)
        pred = [-1] * len(graph)
        pq = [(0.0, origin_id)]
        dist[origin_id] = 0.0

        while pq:
            d, u = heappop(pq)
            if u == destination_id:
                break
            if d == dist[u]:
                for v, w in graph[u].items():
                    if d + w < dist[v]:
                        dist[v] = d + w
                        pred[v] = u
                        heappush(pq, (d + w, v))

        path = []
        curr = destination_id
        while curr != -1:
            path.append(curr)
            curr = pred[curr]
        path.reverse()
        return {"path": path, "length": dist[destination_id]}

    g = PyGraph(_build_test_graph())

    # 1. Unreduced query
    res = my_dijkstra(g, 1, 5)
    assert abs(res["length"] - 11.0) < 1e-6
    assert res["path"] == [1, 2, 3, 4, 5]

    # 2. Reduced query
    g.reduce()
    # Same chain: 1 -> 2
    res_same = my_dijkstra(g, 1, 2)
    assert abs(res_same["length"] - 3.0) < 1e-6
    assert res_same["path"] == [1, 2]

    # Cross chain: 1 -> 5 (automatically solves boundary exit/entry and expands path!)
    res_cross = my_dijkstra(g, 1, 5)
    assert abs(res_cross["length"] - 11.0) < 1e-6
    assert res_cross["path"] == [1, 2, 3, 4, 5]


def test_custom_bidirectional_algorithm_decorator():
    # Define a custom bidirectional algorithm using @PyGraph.algorithm(bidirectional=True)
    @PyGraph.algorithm(bidirectional=True)
    def my_bidirectional(self, origin_id: int, destination_id: int) -> dict:
        # Standard bidirectional Dijkstra implementation using self.graph and self.inverse_graph
        graph = self.graph
        inverse_graph = self.inverse_graph
        f_dist = [float("inf")] * len(graph)
        b_dist = [float("inf")] * len(graph)
        f_pred = [-1] * len(graph)
        b_pred = [-1] * len(graph)
        f_pq = [(0.0, origin_id)]
        b_pq = [(0.0, destination_id)]
        f_dist[origin_id] = 0.0
        b_dist[destination_id] = 0.0

        best_dist = float("inf")
        meeting = -1

        while f_pq and b_pq:
            fd, u = heappop(f_pq)
            if fd > best_dist:
                break
            for v, w in graph[u].items():
                if fd + w < f_dist[v]:
                    f_dist[v] = fd + w
                    f_pred[v] = u
                    heappush(f_pq, (fd + w, v))
                    if b_dist[v] + f_dist[v] < best_dist:
                        best_dist = b_dist[v] + f_dist[v]
                        meeting = v

            bd, u = heappop(b_pq)
            if bd > best_dist:
                break
            for v, w in inverse_graph[u].items():
                if bd + w < b_dist[v]:
                    b_dist[v] = bd + w
                    b_pred[v] = u
                    heappush(b_pq, (bd + w, v))
                    if f_dist[v] + b_dist[v] < best_dist:
                        best_dist = f_dist[v] + b_dist[v]
                        meeting = v

        f_path = []
        curr = meeting
        while curr != -1:
            f_path.append(curr)
            curr = f_pred[curr]
        f_path.reverse()

        b_path = []
        curr = b_pred[meeting]
        while curr != -1:
            b_path.append(curr)
            curr = b_pred[curr]

        return {"path": f_path + b_path, "length": best_dist}

    g = PyGraph(_build_test_graph())
    g.reduce()

    # Query 1 -> 5: runs directly on reduced graphs and expands path automatically!
    res = my_bidirectional(g, 1, 5)
    assert abs(res["length"] - 11.0) < 1e-6
    assert res["path"] == [1, 2, 3, 4, 5]


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


@pytest.mark.skipif(not HAS_CPP, reason="C++ extension not available")
def test_cpp_graph_algorithm_decorator():
    from scgraph import Graph

    @Graph.algorithm
    def my_cpp_dijkstra(self, origin_id: int, destination_id: int) -> dict:
        graph = self.graph
        dist = [float("inf")] * len(graph)
        pred = [-1] * len(graph)
        pq = [(0.0, origin_id)]
        dist[origin_id] = 0.0

        while pq:
            d, u = heappop(pq)
            if u == destination_id:
                break
            if d == dist[u]:
                for v, w in graph[u].items():
                    if d + w < dist[v]:
                        dist[v] = d + w
                        pred[v] = u
                        heappush(pq, (d + w, v))

        path = []
        curr = destination_id
        while curr != -1:
            path.append(curr)
            curr = pred[curr]
        path.reverse()
        return {"path": path, "length": dist[destination_id]}

    g = CppGraph(_build_test_graph())

    # Unreduced
    res = my_cpp_dijkstra(g, 1, 5)
    assert abs(res["length"] - 11.0) < 1e-6
    assert res["path"] == [1, 2, 3, 4, 5]

    # Reduced
    g.reduce()
    # Same chain: 1 -> 2
    res_same = my_cpp_dijkstra(g, 1, 2)
    assert abs(res_same["length"] - 3.0) < 1e-6
    assert res_same["path"] == [1, 2]

    # Cross chain: 1 -> 5
    res_cross = my_cpp_dijkstra(g, 1, 5)
    assert abs(res_cross["length"] - 11.0) < 1e-6
    assert res_cross["path"] == [1, 2, 3, 4, 5]
