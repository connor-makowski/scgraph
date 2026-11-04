import tempfile
from pathlib import Path

import pytest

from scgraph import GeoGraph, geograph


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


def test_cache_directory_is_cache_dir_else_the_environment_variable(
    tmp_path, monkeypatch
):
    # The platform directory moves under tmp_path too: no call may reach the real cache
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "home"))
    shared, mine = tmp_path / "shared", tmp_path / "mine"
    monkeypatch.setenv("SCGRAPH_CACHE_DIR", str(shared))
    for folder, nodes in (
        (shared, [[0, 0], [0, 1]]),
        (mine, [[0, 0], [1, 0], [2, 0]]),
    ):
        folder.mkdir()
        graph = [{} for _ in nodes]
        GeoGraph(graph=graph, nodes=nodes).save_as_graphjson(
            str(folder / "marnet.graphjson")
        )
    (shared / "networks" / "us_freeway").mkdir(parents=True)
    (shared / "networks" / "us_freeway" / "manifest.json").write_text(
        '{"file": "built.scgraph"}'
    )
    (shared / "networks" / "us_freeway" / "built.scgraph").write_bytes(b"")
    assert len(GeoGraph.load_geograph("marnet").nodes) == 2
    assert len(GeoGraph.load_geograph("marnet", cache_dir=str(mine)).nodes) == 3
    listing = {n["name"]: n for n in GeoGraph.list_downloadable_geographs()}
    assert listing["us_freeway"]["cached"]
    (shared / "notes.txt").write_text("the user's own file")
    GeoGraph.clear_geograph_cache()
    # Only scgraph's files go, from the cache the variable names
    assert sorted(p.name for p in shared.iterdir()) == ["notes.txt"]
    assert (mine / "marnet.graphjson").exists()


def test_a_download_that_fails_while_written_leaves_nothing_in_the_cache(
    tmp_path, monkeypatch
):
    class Response:
        status_code, ok, content = (
            200,
            True,
            b'{"type": "GeoGraph"' + b" " * 1000,
        )

    monkeypatch.setattr(geograph.requests, "get", lambda *a, **k: Response())
    write = Path.write_bytes

    def disk_full(self, data):
        write(self, data[: len(data) // 2])
        raise OSError("No space left on device")

    monkeypatch.setattr(Path, "write_bytes", disk_full)
    with pytest.raises(OSError):
        GeoGraph.load_geograph("marnet", cache_dir=str(tmp_path))
    # A later load would take any file named marnet.graphjson for the network
    assert list(tmp_path.iterdir()) == []
