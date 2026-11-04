import json
import os
import pytest
from helpers import great_circle_km
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


# Coordinates on or beyond the antimeridian keep their place on the globe
@pytest.mark.parametrize(
    "longitude, latitude, expected",
    [
        (180, 0, [0, 180]),
        (-180, 0, [0, -180]),
        (190.5, 0, [0, -169.5]),
        (190.8498, 0, [0, -169.1502]),
        (-180.5, 0, [0, 179.5]),
        (12.5, 90, [90, 12.5]),
        (12.5, 95, ValueError),  # no latitude beyond the poles
    ],
)
def test_load_from_geojson_keeps_coordinates_on_the_globe(
    tmp_path, longitude, latitude, expected
):
    path = tmp_path / "line.geojson"
    line = [[longitude - 0.5, 89.5], [longitude, latitude]]
    path.write_text(
        json.dumps(
            {
                "type": "GeometryCollection",
                "geometries": [{"type": "LineString", "coordinates": line}],
            }
        )
    )
    if expected is ValueError:
        with pytest.raises(ValueError, match="Latitude"):
            GeoGraph.load_from_geojson(str(path), silent=True)
        return
    loaded = GeoGraph.load_from_geojson(str(path), silent=True)
    assert expected in loaded.nodes


def test_load_from_geojson_lengths(tmp_path):
    # Far from the equator and from Greenwich, where swapping latitude and longitude shows
    path = tmp_path / "line.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "GeometryCollection",
                "geometries": [
                    {
                        "type": "LineString",
                        "coordinates": [[100, 50], [101, 51]],
                    }
                ],
            }
        )
    )
    loaded = GeoGraph.load_from_geojson(str(path), silent=True)
    expected = great_circle_km([50, 100], [51, 101])
    assert loaded.graph_object.graph[0][1] == pytest.approx(expected, abs=0.001)
