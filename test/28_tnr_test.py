from scgraph import GeoGraph

_SMALL_GRAPH = [
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
]


def test_tnr_basic(tnr_class):
    tnr = tnr_class(graph=_SMALL_GRAPH, num_transit_nodes=2)
    res = tnr.get_shortest_path(0, 5)
    assert res["length"] == 10
    assert res["path"] == [0, 2, 1, 3, 5]


def test_tnr_geograph(graph_class):
    geo = GeoGraph.load_geograph("us_freeway")
    geo.graph_object = graph_class(graph=geo.graph)
    geo.graph_object.create_tnr_hierarchy(num_transit_nodes=100)
    geo.graph_object.create_contraction_hierarchy()
    # Boston to NYC
    origin = {"latitude": 42.36, "longitude": -71.06}
    destination = {"latitude": 40.71, "longitude": -74.01}
    dijkstra = geo.get_shortest_path(
        origin, destination, algorithm_fn="dijkstra"
    )
    ch = geo.get_shortest_path(
        origin, destination, algorithm_fn="contraction_hierarchy"
    )
    tnr = geo.get_shortest_path(origin, destination, algorithm_fn="tnr")
    tnr_len = geo.get_shortest_path(
        origin, destination, algorithm_fn="tnr", length_only=True
    )
    assert abs(dijkstra["length"] - tnr["length"]) < 1e-3
    assert abs(dijkstra["length"] - ch["length"]) < 1e-3
    assert abs(dijkstra["length"] - tnr_len["length"]) < 1e-3


def _test_save_load(tnr_class, tmp_path):
    tnr = tnr_class(graph=_SMALL_GRAPH, num_transit_nodes=2)
    path = str(tmp_path / "test.tnrjson")
    tnr.save_as_tnrjson(path)
    loaded = tnr_class.load_from_tnrjson(path)
    assert loaded.get_shortest_path(0, 5)["length"] == 10


def test_tnr_save_load(tnr_class, tmp_path):
    _test_save_load(tnr_class, tmp_path)


# A saved hierarchy is loaded with the class that the package exports, whatever
# the build
def test_tnr_save_load_with_the_exported_class(tmp_path):
    from scgraph import TNRGraph

    _test_save_load(TNRGraph, tmp_path)
