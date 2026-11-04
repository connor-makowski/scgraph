import os
import pytest
from scgraph import GeoGraph

_NODES = [
    [0, 0],
    [0, 1],
    [1, 0],
    [1, 1],
    [1, 2],
    [2, 1],
]
_GRAPH = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
]


@pytest.fixture
def tmp_graph(tmp_path):
    return GeoGraph(nodes=list(_NODES), graph=list(_GRAPH)), tmp_path


# Saving must write the original graph, whether or not the geograph was reduced
@pytest.mark.parametrize("reduce", [False, True])
def test_save_load_geojson(tmp_graph, reduce):
    geo, tmp = tmp_graph
    if reduce:
        geo.reduce()
    geojson_path = str(tmp / "test.geojson")
    geo.save_as_geojson(geojson_path)
    loaded = GeoGraph.load_from_geojson(geojson_path, silent=True)
    assert loaded.nodes == _NODES
    # GeoJSON stores geometries: compare edges, not their recomputed lengths
    edges = [set(d) for d in loaded.graph_object.graph]
    assert edges == [set(d) for d in _GRAPH]


@pytest.mark.parametrize("reduce", [False, True])
def test_save_load_graphjson(tmp_graph, reduce):
    geo, tmp = tmp_graph
    if reduce:
        geo.reduce()
    graphjson_path = str(tmp / "test.graphjson")
    geo.save_as_graphjson(graphjson_path)
    loaded = GeoGraph.load_from_graphjson(graphjson_path)
    assert loaded.graph_object.graph == _GRAPH
    assert loaded.nodes == _NODES


def test_save_load_graphjson_keeps_route_geometry(tmp_path):
    # Routes on a reloaded GeoGraph follow the same shapes as before saving
    nodes = [[0.0, 0.0], [0.0, 0.01], [0.0, 0.02]]

    def shape(a, b):
        return [nodes[a], [0.003, (nodes[a][1] + nodes[b][1]) / 2], nodes[b]]

    geo = GeoGraph(
        nodes=nodes,
        graph=[{1: 1.5}, {0: 1.5, 2: 1.5}, {1: 1.5}],
        intermediate_nodes=[
            {1: shape(0, 1)},
            {0: shape(1, 0), 2: shape(1, 2)},
            {1: shape(2, 1)},
        ],
    )
    path = str(tmp_path / "shaped.graphjson")
    geo.save_as_graphjson(path)
    loaded = GeoGraph.load_from_graphjson(path)
    origin = {"latitude": 0.0, "longitude": 0.0}
    destination = {"latitude": 0.0, "longitude": 0.02}
    assert loaded.get_shortest_path(
        origin, destination, output_coordinate_path="list_of_lists"
    ) == geo.get_shortest_path(
        origin, destination, output_coordinate_path="list_of_lists"
    )
