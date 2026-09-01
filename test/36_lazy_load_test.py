import json
import tempfile
from pathlib import Path
from scgraph import GeoGraph
from scgraph.geograph import LazyGeoGraph
from helpers import assert_result


def test_lazy_load_geograph_defers_download():
    with tempfile.TemporaryDirectory() as tmp:
        geo = GeoGraph.load_geograph("marnet", cache_dir=tmp, lazy=True)
        assert isinstance(geo, GeoGraph)
        assert isinstance(geo, LazyGeoGraph)
        assert geo._initialized is False

        # Verify nothing was downloaded yet
        cached_file = Path(tmp).joinpath("marnet.graphjson")
        assert not cached_file.exists()

        # Query shortest path - triggers load
        result = geo.get_shortest_path(
            origin_node={"latitude": 30, "longitude": 160},
            destination_node={"latitude": 30, "longitude": -160},
        )
        assert geo._initialized is True
        assert cached_file.exists()
        assert_result(
            result,
            {
                "length": 4477.148,
                "coordinate_path": [
                    [30, 160],
                    [30.0, 160.0],
                    [35.1041, 164.6948],
                    [35.3857, 165.0],
                    [36.6002, 166.316],
                    [37.695, 169.999],
                    [38.2345, 171.814],
                    [40.0, 180.0],
                    [40.0, -180.0],
                    [40.1067, -174.9996],
                    [40.0, -170.0],
                    [35.3857, -165.0],
                    [35.1023, -164.6929],
                    [30.0, -160.0],
                    [30, -160],
                ],
            },
        )


def test_lazy_load_explicit_load():
    with tempfile.TemporaryDirectory() as tmp:
        geo = GeoGraph.load_geograph("marnet", cache_dir=tmp, lazy=True)
        assert geo._initialized is False
        loaded = geo.load()
        assert loaded is geo
        assert geo._initialized is True
        assert len(geo.nodes) > 0


def test_lazy_load_attribute_access():
    with tempfile.TemporaryDirectory() as tmp:
        geo = GeoGraph.load_geograph("marnet", cache_dir=tmp, lazy=True)
        assert geo._initialized is False
        # Direct attribute access triggers load
        nodes = geo.nodes
        assert geo._initialized is True
        assert isinstance(nodes, list)
        assert len(nodes) > 0
        assert geo.graph_object is not None
        assert geo.geokdtree is not None


def test_lazy_load_distance_matrix():
    with tempfile.TemporaryDirectory() as tmp:
        geo = GeoGraph.load_geograph("marnet", cache_dir=tmp, lazy=True)
        matrix = geo.distance_matrix(
            [
                {"latitude": 30, "longitude": 160},
                {"latitude": 30, "longitude": -160},
            ]
        )
        assert geo._initialized is True
        assert len(matrix) == 2
        assert len(matrix[0]) == 2
        assert round(matrix[0][1], 3) == 4477.148


def test_lazy_load_repr_and_dir():
    with tempfile.TemporaryDirectory() as tmp:
        geo = GeoGraph.load_geograph("marnet", cache_dir=tmp, lazy=True)
        # repr should NOT trigger load
        r = repr(geo)
        assert "not loaded" in r
        assert geo._initialized is False

        # dir SHOULD trigger load
        d = dir(geo)
        assert "get_shortest_path" in d
        assert "nodes" in d
        assert geo._initialized is True

        # repr after load
        r2 = repr(geo)
        assert "loaded" in r2
        assert "not loaded" not in r2


def test_lazy_load_from_graphjson():
    with tempfile.TemporaryDirectory() as tmp:
        # First save a graphjson
        marnet_sample = GeoGraph(
            nodes=[[10.0, 20.0], [10.0, 21.0]],
            graph=[{1: 100}, {0: 100}],
        )
        filepath = f"{tmp}/sample.graphjson"
        marnet_sample.save_as_graphjson(filepath)

        # Load lazily
        geo = GeoGraph.load_from_graphjson(filepath, lazy=True)
        assert isinstance(geo, GeoGraph)
        assert geo._initialized is False

        # Query
        res = geo.get_shortest_path(
            origin_node={"latitude": 10.0, "longitude": 20.0},
            destination_node={"latitude": 10.0, "longitude": 21.0},
        )
        assert geo._initialized is True
        assert res["length"] == 100


def test_lazy_load_from_geojson():
    geojson_data = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-74.0, 40.7], [-73.9, 40.8]],
                },
                "properties": {},
            }
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        filepath = f"{tmp}/sample.geojson"
        with open(filepath, "w") as f:
            json.dump(geojson_data, f)

        geo = GeoGraph.load_from_geojson(filepath, lazy=True)
        assert isinstance(geo, GeoGraph)
        assert geo._initialized is False

        # Query
        assert len(geo.nodes) == 2
        assert geo._initialized is True


def test_lazy_load_multi_path_geojson():
    with tempfile.TemporaryDirectory() as tmp:
        geo = GeoGraph.load_geograph("marnet", cache_dir=tmp, lazy=True)
        routes = [
            {
                "geograph": geo,
                "origin": {"latitude": 30, "longitude": 160},
                "destination": {"latitude": 30, "longitude": -160},
                "properties": {"id": "route1"},
            }
        ]
        geojson = GeoGraph.get_multi_path_geojson(routes)
        assert geo._initialized is True
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 1


def test_lazy_load_merge():
    with tempfile.TemporaryDirectory() as tmp:
        geo1 = GeoGraph(
            nodes=[[10.0, 20.0], [10.0, 21.0]],
            graph=[{1: 100}, {0: 100}],
        )
        geo2 = GeoGraph.load_geograph("marnet", cache_dir=tmp, lazy=True)
        assert geo2._initialized is False

        geo1.merge_with_other_geograph(
            other_geograph=geo2,
            connection_nodes=[[30, 160]],
        )
        assert geo2._initialized is True


def test_lazy_load_setattr():
    with tempfile.TemporaryDirectory() as tmp:
        geo = GeoGraph.load_geograph("marnet", cache_dir=tmp, lazy=True)
        assert geo._initialized is False
        geo.default_off_graph_circuity = 2.5
        assert geo._initialized is True
        assert geo.default_off_graph_circuity == 2.5


class MockOSMNxGraph:
    class MockNodes:
        def __iter__(self):
            return iter([1, 2])

        def __call__(self, data=False):
            if data:
                return [
                    (1, {"y": 42.0, "x": -71.0}),
                    (2, {"y": 42.1, "x": -71.1}),
                ]
            return [1, 2]

    def __init__(self):
        self.nodes = self.MockNodes()

    def edges(self, data=False):
        if data:
            return [(1, 2, {"length": 5000})]
        return [(1, 2)]


def test_lazy_load_from_osmnx():
    mock_g = MockOSMNxGraph()
    geo = GeoGraph.load_from_osmnx_graph(mock_g, lazy=True)
    assert isinstance(geo, GeoGraph)
    assert geo._initialized is False
    assert len(geo.nodes) == 2
    assert geo._initialized is True


def test_lazy_load_error_deferred():
    import pytest

    # Non-existent file should not raise error on load
    geo = GeoGraph.load_from_graphjson("/nonexistent/file.graphjson", lazy=True)
    assert geo._initialized is False

    # Error is raised upon first attribute access / query
    with pytest.raises(FileNotFoundError):
        _ = geo.nodes
