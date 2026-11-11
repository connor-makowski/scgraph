import json
import os
import tempfile
from pathlib import Path

import pytest

from scgraph import GeoGraph, geograph, network_file


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
    (shared / "networks" / "us_freeway" / "cache.json").write_text(
        '{"file": "built.scgraph"}'
    )
    (shared / "networks" / "us_freeway" / "built.scgraph").write_bytes(b"")
    assert len(GeoGraph.load_geograph("marnet").nodes) == 2
    assert len(GeoGraph.load_geograph("marnet", cache_dir=str(mine)).nodes) == 3
    listing = {n["name"]: n for n in GeoGraph.list_buildable_geographs()}
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


# Converted at the first load, then read by later ones; a damaged conversion (here,
# truncated) is made again; a cache that can't be written keeps reading the .graphjson
@pytest.mark.parametrize("case", ["first", "damaged", "read_only"])
def test_load_geograph_converts_a_published_geograph_once(
    tmp_path, monkeypatch, case
):
    published, converted = (
        tmp_path / "marnet.graphjson",
        tmp_path / "marnet.scgraph",
    )
    original = GeoGraph(
        graph=[{1: 1.5, 2: 3.0}, {0: 1.5, 2: 2.0}, {1: 2.0}],
        # 9 decimals, read back to 1e-7 degree as OSM stores them
        nodes=[[45.000000001, 90], [-45, -90], [45, -90]],
    )
    original.save_as_graphjson(str(published))
    if case == "damaged":
        original.save_as_scgraph(str(converted))
        converted.write_bytes(converted.read_bytes()[:-8])
    if case == "read_only":

        def refused(*args, **kwargs):
            raise PermissionError("read-only")

        monkeypatch.setattr(network_file, "write", refused)
    geo = GeoGraph.load_geograph("marnet", cache_dir=str(tmp_path))
    # In Hilbert order (old nodes 1, 2, 0, their node ids), the arcs renumbered
    assert geo.nodes == [[-45, -90], [45, -90], [45, 90]]
    assert list(geo.node_ids) == [1, 2, 0]
    assert geo.coordinate_dtype == "int32"
    assert geo.graph_object.graph == [
        {2: 1.5, 1: 2.0},
        {0: 2.0},
        {0: 1.5, 1: 3.0},
    ]
    assert published.exists() and converted.exists() != (case == "read_only")
    if case == "read_only":
        return
    # Stored as int32 in 1e-7 degree; the published file is the source of the node ids
    assert (
        GeoGraph.get_scgraph_info(str(converted))["coordinate_dtype"] == "int32"
    )
    metadata = network_file.read(str(converted))[1]
    assert metadata["modes"] == [{"name": None, "source": "marnet.graphjson"}]
    assert [s["name"] for s in metadata["sources"]] == ["marnet.graphjson"]
    published.write_text("no longer read")
    again = GeoGraph.load_geograph("marnet", cache_dir=str(tmp_path))
    assert again.nodes == geo.nodes
    assert again.graph_object.graph == geo.graph_object.graph


# local_files_only=True, or SCGRAPH_OFFLINE=1 unless the argument says otherwise
@pytest.mark.parametrize(
    "environment, options, offline",
    [
        (None, {"local_files_only": True}, True),
        ("1", {}, True),
        ("1", {"local_files_only": False}, False),
    ],
)
def test_load_geograph_downloads_nothing_with_local_files_only(
    tmp_path, monkeypatch, environment, options, offline
):
    class Response:
        status_code, ok = 200, True
        content = json.dumps(
            {"type": "GeoGraph", "graph": [{}], "nodes": [[0, 0]]}
        ).encode()

    requested = []
    monkeypatch.setattr(
        geograph.requests,
        "get",
        lambda url, **kwargs: requested.append(url) or Response(),
    )
    monkeypatch.delenv("SCGRAPH_OFFLINE", raising=False)
    if environment:
        monkeypatch.setenv("SCGRAPH_OFFLINE", environment)
    if offline:
        with pytest.raises(FileNotFoundError, match="local_files_only"):
            GeoGraph.load_geograph("marnet", cache_dir=str(tmp_path), **options)
        GeoGraph(graph=[{}], nodes=[[0, 0]]).save_as_graphjson(
            str(tmp_path / "marnet.graphjson")
        )
    geo = GeoGraph.load_geograph("marnet", cache_dir=str(tmp_path), **options)
    assert len(geo.nodes) == 1
    assert len(requested) == (0 if offline else 1)


def test_list_geographs_reads_contents_txt_only_for_another_url(
    tmp_path, monkeypatch
):
    class Response:
        ok, text = True, "mine.graphjson\nREADME.md\n"

    requested = []
    monkeypatch.setattr(
        geograph.requests,
        "get",
        lambda url, **kwargs: requested.append(url) or Response(),
    )
    # The published geographs are a fixed list: no request
    GeoGraph.list_geographs(cache_dir=str(tmp_path))
    assert requested == []
    mirror = GeoGraph.list_geographs(
        cache_dir=str(tmp_path), geograph_url="https://example.org/geographs/"
    )
    assert [g["name"] for g in mirror] == ["mine"]
    assert requested == ["https://example.org/geographs/contents.txt"]


@pytest.fixture
def filled_cache(tmp_path):
    """A cache holding a published geograph, built networks (marnet, a real network
    file, and osm_rail of a region and of a sub-region), a cache.json that names no file,
    a build's work folder and a user file.
    """
    files = {
        "marnet.graphjson": b"x" * 10,
        "marnet.scgraph": b"x" * 5,
        "notes.txt": b"x",
        "networks/marnet/cache.json": "m.scgraph",
        "networks/osm_rail/europe/e.scgraph": b"x" * 30,
        "networks/osm_rail/europe/cache.json": "e.scgraph",
        "networks/osm_rail/europe/france/f.scgraph": b"x" * 40,
        "networks/osm_rail/europe/france/cache.json": "f.scgraph",
        "networks/us_freeway/cache.json": "gone.scgraph",
        ".work/osm_rail/europe/sources/rail.osm.pbf": b"x" * 50,
    }
    for path, content in files.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            content = json.dumps({"file": content}).encode()
        (tmp_path / path).write_bytes(content)
    built = GeoGraph(graph=[{1: 1.0}, {0: 1.0}], nodes=[[0, 0], [0, 1]])
    pipeline = {"name": "marnet", "region": None, "version": 3}
    built.save_as_scgraph(
        str(tmp_path / "networks/marnet/m.scgraph"),
        metadata={"pipeline": pipeline, "software": {"scgraph": "9.9"}},
    )
    return tmp_path


def test_cache_info_lists_what_scgraph_keeps_on_disk(filled_cache):
    info = GeoGraph.get_cache_info(str(filled_cache))
    marnet_bytes = (filled_cache / "networks/marnet/m.scgraph").stat().st_size
    assert [
        (i["kind"], i["name"], i["region"], Path(i["file"]).name, i["bytes"])
        for i in info
    ] == [
        ("published", "marnet", None, "marnet.graphjson", 10),
        ("published", "marnet", None, "marnet.scgraph", 5),
        ("built", "marnet", None, "m.scgraph", marnet_bytes),
        ("built", "osm_rail", "europe", "e.scgraph", 30),
        ("built", "osm_rail", "europe/france", "f.scgraph", 40),
        ("building", "osm_rail", None, "osm_rail", 50),
    ]
    # Versions read from the file; None for a file that can't be read
    assert (info[2]["pipeline_version"], info[2]["scgraph"]) == (3, "9.9")
    assert (info[3]["pipeline_version"], info[3]["scgraph"]) == (None, None)


_RAIL = "networks/osm_rail/europe/"


# None: a selector refused, with nothing removed. A locked file can't be removed (as on
# Windows, a network still loaded): it is left, with a warning that names it
@pytest.mark.parametrize(
    "selector, locked, removed",
    [
        (
            {"name": "marnet"},
            None,
            {
                "marnet.graphjson",
                "marnet.scgraph",
                "networks/marnet/m.scgraph",
                "networks/marnet/cache.json",
            },
        ),
        (
            {"name": "marnet"},
            "m.scgraph",
            {
                "marnet.graphjson",
                "marnet.scgraph",
                "networks/marnet/cache.json",
            },
        ),
        (
            {"name": "osm_rail"},
            None,
            {
                _RAIL + "e.scgraph",
                _RAIL + "cache.json",
                _RAIL + "france/f.scgraph",
                _RAIL + "france/cache.json",
            },
        ),
        # A sub-region is an entry of its own
        (
            {"name": "osm_rail", "region": "europe"},
            "e.scgraph",
            {_RAIL + "cache.json"},
        ),
        ({"name": "../networks"}, None, None),
        ({"name": "osm_rail", "region": "../.."}, None, None),
        ({"region": "europe"}, None, None),
    ],
)
def test_clear_geograph_cache_removes_only_the_selected_network(
    filled_cache, monkeypatch, caplog, selector, locked, removed
):
    def files():
        return {
            p.relative_to(filled_cache).as_posix()
            for p in filled_cache.rglob("*")
            if p.is_file()
        }

    unlink = os.unlink

    def unless_locked(path, **kwargs):
        if locked and os.fspath(path).endswith(locked):
            raise PermissionError(f"{path} is in use")
        unlink(path, **kwargs)

    monkeypatch.setattr(os, "unlink", unless_locked)
    before = files()
    if removed is None:
        with pytest.raises(ValueError):
            GeoGraph.clear_geograph_cache(str(filled_cache), **selector)
    else:
        GeoGraph.clear_geograph_cache(str(filled_cache), **selector)
    assert before - files() == (removed or set())
    if locked:  # named in a warning
        assert locked in caplog.text
