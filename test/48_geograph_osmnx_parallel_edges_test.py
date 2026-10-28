import pytest
from types import SimpleNamespace
from scgraph import GeoGraph

# Two OSMnx nodes 1 -> 2, about 1.112 km apart, linked by parallel edges
_STRAIGHT = {
    "length": 1112,
    "geometry": SimpleNamespace(coords=[(0.0, 0.0), (0.01, 0.0)]),
}
_DETOUR = {
    "length": 3000,
    "geometry": SimpleNamespace(
        coords=[(0.0, 0.0), (0.005, 0.01), (0.01, 0.0)]
    ),
}
_SHORT_NO_GEOMETRY = {"length": 1112}


class _OSMnxGraph:
    """Minimal stand-in for an OSMnx MultiDiGraph (osmnx is not a dependency)"""

    def __init__(self, parallel_edges):
        self.parallel_edges = parallel_edges
        self.nodes = self

    def __iter__(self):
        return iter([1, 2])

    def __call__(self, data=False):
        return [(1, {"y": 0.0, "x": 0.0}), (2, {"y": 0.0, "x": 0.01})]

    def edges(self, data=False):
        return [(1, 2, edge_data) for edge_data in self.parallel_edges]


@pytest.mark.parametrize(
    "parallel_edges, expected_shape",
    [
        ([_STRAIGHT, _DETOUR], [[0.0, 0.0], [0.0, 0.01]]),
        ([_DETOUR, _STRAIGHT], [[0.0, 0.0], [0.0, 0.01]]),
        ([_DETOUR, _SHORT_NO_GEOMETRY], None),
    ],
    ids=["shortest-first", "shortest-last", "shortest-without-geometry"],
)
def test_parallel_edges_keep_the_geometry_of_the_kept_edge(
    parallel_edges, expected_shape
):
    # Only the shortest parallel edge is kept: its weight and its own geometry
    geograph = GeoGraph.load_from_osmnx_graph(
        _OSMnxGraph(parallel_edges), silent=True
    )
    assert geograph.graph_object.graph[0] == {1: 1.112}
    assert geograph.intermediate_nodes[0].get(1) == expected_shape
