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
