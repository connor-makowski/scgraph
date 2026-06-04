import tempfile
from scgraph import GeoGraph


def test_list_geographs_returns_list():
    with tempfile.TemporaryDirectory() as tmp:
        geograph_list = GeoGraph.list_geographs(cache_dir=tmp)
        assert isinstance(geograph_list, list) and len(geograph_list) > 0


def test_list_geographs_have_expected_keys():
    with tempfile.TemporaryDirectory() as tmp:
        geograph_list = GeoGraph.list_geographs(cache_dir=tmp)
        assert all("name" in g and "cached" in g for g in geograph_list)


def test_marnet_listed():
    with tempfile.TemporaryDirectory() as tmp:
        geograph_list = GeoGraph.list_geographs(cache_dir=tmp)
        assert any(g["name"] == "marnet" for g in geograph_list)


def test_marnet_not_cached_before_load():
    with tempfile.TemporaryDirectory() as tmp:
        geograph_list = GeoGraph.list_geographs(cache_dir=tmp)
        entry = next(g for g in geograph_list if g["name"] == "marnet")
        assert entry["cached"] is False


def test_load_geograph_returns_geograph():
    with tempfile.TemporaryDirectory() as tmp:
        geo = GeoGraph.load_geograph("marnet", cache_dir=tmp)
        assert isinstance(geo, GeoGraph)


def test_marnet_cached_after_load():
    with tempfile.TemporaryDirectory() as tmp:
        GeoGraph.load_geograph("marnet", cache_dir=tmp)
        geograph_list = GeoGraph.list_geographs(cache_dir=tmp)
        entry = next(g for g in geograph_list if g["name"] == "marnet")
        assert entry["cached"] is True


def test_load_from_cache():
    with tempfile.TemporaryDirectory() as tmp:
        GeoGraph.load_geograph("marnet", cache_dir=tmp)
        geo = GeoGraph.load_geograph("marnet", cache_dir=tmp)
        assert isinstance(geo, GeoGraph)


def test_clear_cache():
    with tempfile.TemporaryDirectory() as tmp:
        GeoGraph.load_geograph("marnet", cache_dir=tmp)
        GeoGraph.clear_geograph_cache(cache_dir=tmp)
        geograph_list = GeoGraph.list_geographs(cache_dir=tmp)
        entry = next(g for g in geograph_list if g["name"] == "marnet")
        assert entry["cached"] is False
