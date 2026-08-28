import json
import tempfile
from scgraph import GeoGraph


class MockOSMNxGraph:
    class MockNodes:
        def __iter__(self):
            return iter([1, 2, 3])

        def __call__(self, data=False):
            if data:
                return [
                    (1, {"y": 42.0, "x": -71.0}),
                    (2, {"y": 42.1, "x": -71.1}),
                    (3, {"y": 42.2, "x": -71.2}),
                ]
            return [1, 2, 3]

    def __init__(self):
        self.nodes = self.MockNodes()

    def edges(self, data=False):
        if data:
            return [(1, 2, {"length": 5000}), (2, 3, {"length": 5000})]
        return [(1, 2), (2, 3)]


def test_reduce_load_geograph_default_false():
    with tempfile.TemporaryDirectory() as tmp:
        geo = GeoGraph.load_geograph("marnet", cache_dir=tmp)
        assert getattr(geo.graph_object, "reduced_graph", None) is None


def test_reduce_load_geograph_true():
    with tempfile.TemporaryDirectory() as tmp:
        geo = GeoGraph.load_geograph("marnet", cache_dir=tmp, reduce_iterations=1)
        assert getattr(geo.graph_object, "reduced_graph", None) is not None


def test_reduce_load_from_graphjson_default_false():
    with tempfile.TemporaryDirectory() as tmp:
        sample = GeoGraph(
            nodes=[[10.0, 20.0], [10.0, 21.0], [10.0, 22.0]],
            graph=[{1: 100}, {2: 100}, {}],
        )
        filepath = f"{tmp}/sample.graphjson"
        sample.save_as_graphjson(filepath)

        geo = GeoGraph.load_from_graphjson(filepath)
        assert getattr(geo.graph_object, "reduced_graph", None) is None


def test_reduce_load_from_graphjson_true():
    with tempfile.TemporaryDirectory() as tmp:
        sample = GeoGraph(
            nodes=[[10.0, 20.0], [10.0, 21.0], [10.0, 22.0]],
            graph=[{1: 100}, {2: 100}, {}],
        )
        filepath = f"{tmp}/sample.graphjson"
        sample.save_as_graphjson(filepath)

        geo = GeoGraph.load_from_graphjson(filepath, reduce_iterations=1)
        assert getattr(geo.graph_object, "reduced_graph", None) is not None


def test_reduce_load_from_geojson_default_false():
    geojson_data = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [-74.0, 40.7],
                        [-73.9, 40.8],
                        [-73.8, 40.9],
                    ],
                },
                "properties": {},
            }
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        filepath = f"{tmp}/sample.geojson"
        with open(filepath, "w") as f:
            json.dump(geojson_data, f)

        geo = GeoGraph.load_from_geojson(filepath)
        assert getattr(geo.graph_object, "reduced_graph", None) is None


def test_reduce_load_from_geojson_true():
    geojson_data = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [-74.0, 40.7],
                        [-73.9, 40.8],
                        [-73.8, 40.9],
                    ],
                },
                "properties": {},
            }
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        filepath = f"{tmp}/sample.geojson"
        with open(filepath, "w") as f:
            json.dump(geojson_data, f)

        geo = GeoGraph.load_from_geojson(filepath, reduce_iterations=1)
        assert getattr(geo.graph_object, "reduced_graph", None) is not None


def test_reduce_load_from_osmnx_default_false():
    mock_g = MockOSMNxGraph()
    geo = GeoGraph.load_from_osmnx_graph(mock_g)
    assert getattr(geo.graph_object, "reduced_graph", None) is None


def test_reduce_load_from_osmnx_true():
    mock_g = MockOSMNxGraph()
    geo = GeoGraph.load_from_osmnx_graph(mock_g, reduce_iterations=1)
    assert getattr(geo.graph_object, "reduced_graph", None) is not None


def test_geograph_reduce_method():
    with tempfile.TemporaryDirectory() as tmp:
        geo = GeoGraph.load_geograph("marnet", cache_dir=tmp, reduce_iterations=0)
        assert getattr(geo.graph_object, "reduced_graph", None) is None
        geo.reduce()
        assert getattr(geo.graph_object, "reduced_graph", None) is not None
