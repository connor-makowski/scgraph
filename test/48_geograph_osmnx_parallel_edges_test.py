import pytest
from types import SimpleNamespace
from scgraph import GeoGraph

# Two OSMnx nodes 1 -> 2 (about 1.112 km apart unless at the same place), linked by one
# edge or by parallel edges
_STRAIGHT = {
    "length": 1112,
    "geometry": SimpleNamespace(coords=[(0.0, 0.0), (0.005, 0.0), (0.01, 0.0)]),
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

    def __init__(self, parallel_edges, second_node_x=0.01):
        self.parallel_edges = parallel_edges
        self.second_node_x = second_node_x
        self.nodes = self

    def __iter__(self):
        return iter([1, 2])

    def __call__(self, data=False):
        return [
            (1, {"y": 0.0, "x": 0.0}),
            (2, {"y": 0.0, "x": self.second_node_x}),
        ]

    def edges(self, data=False):
        return [(1, 2, edge_data) for edge_data in self.parallel_edges]


_NO_POINT_BETWEEN = {
    "length": 1112,
    "geometry": SimpleNamespace(coords=[(0.0, 0.0), (0.01, 0.0)]),
}
# Listed from node 2 to node 1
_BACKWARDS = {
    "length": 1112,
    "geometry": SimpleNamespace(
        coords=[(0.01, 0.0), (0.007, 0.001), (0.003, 0.002), (0.0, 0.0)]
    ),
}
# The second and the last but one points are the nodes once rounded to coord_precision
_ROUNDED_ONTO_THE_NODES = {
    "length": 1112,
    "geometry": SimpleNamespace(
        coords=[
            (0.0, 0.0),
            (0.000001, 0.0),
            (0.005, 0.0),
            (0.009999, 0.0),
            (0.01, 0.0),
        ]
    ),
}
# From node 1 back to node 2, which is at the same place
_ROUND_TRIP = {
    "length": 1112,
    "geometry": SimpleNamespace(
        coords=[(0.0, 0.0), (0.003, 0.002), (0.007, 0.001), (0.0, 0.0)]
    ),
}


@pytest.mark.parametrize(
    "osmnx_graph, expected_shapes",
    [
        (_OSMnxGraph([_STRAIGHT, _DETOUR]), {1: [[0.0, 0.005]]}),
        (_OSMnxGraph([_DETOUR, _STRAIGHT]), {1: [[0.0, 0.005]]}),
        (_OSMnxGraph([_DETOUR, _SHORT_NO_GEOMETRY]), {}),
        (_OSMnxGraph([_NO_POINT_BETWEEN]), {}),
        (_OSMnxGraph([_BACKWARDS]), {1: [[0.002, 0.003], [0.001, 0.007]]}),
        (_OSMnxGraph([_ROUNDED_ONTO_THE_NODES]), {1: [[0.0, 0.005]]}),
        (
            _OSMnxGraph([_ROUND_TRIP], second_node_x=0.0),
            {1: [[0.002, 0.003], [0.001, 0.007]]},
        ),
    ],
    ids=[
        "shortest-first",
        "shortest-last",
        "shortest-without-geometry",
        "no-point-between",
        "listed-backwards",
        "points-rounded-onto-the-nodes",
        "nodes-at-the-same-place",
    ],
)
def test_an_osmnx_edge_shape_is_the_points_between_its_nodes(
    osmnx_graph, expected_shapes
):
    # Only the shortest parallel edge is kept, with its own geometry: its shape is the
    # points between its two nodes, from origin to destination (none: no shape)
    geograph = GeoGraph.load_from_osmnx_graph(osmnx_graph, silent=True)
    assert geograph.graph_object.graph[0] == {1: 1.112}
    assert geograph.intermediate_nodes[0] == expected_shapes
