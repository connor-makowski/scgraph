import json
import os
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


def _save_as_cached_marnet(cache, nodes):
    # Writes the file that a download of marnet leaves in a cache. The nodes
    # have no links: the tests only count them to tell two caches apart.
    cache.mkdir(exist_ok=True)
    GeoGraph(graph=[{} for _ in nodes], nodes=nodes).save_as_graphjson(
        str(cache / "marnet.graphjson")
    )


def _list_files(cache):
    # The files of a cache, as paths relative to it.
    return {
        path.relative_to(cache).as_posix()
        for path in cache.rglob("*")
        if path.is_file()
    }


@pytest.fixture
def environment_cache(tmp_path, monkeypatch):
    """The folder that SCGRAPH_CACHE_DIR names. The home folder moves under
    tmp_path too, so that no call can reach the real cache of the user."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "home"))
    monkeypatch.setenv("SCGRAPH_CACHE_DIR", str(tmp_path / "environment"))
    return tmp_path / "environment"


def test_load_geograph_reads_the_cache_that_scgraph_cache_dir_names(
    environment_cache,
):
    _save_as_cached_marnet(environment_cache, nodes=[[0, 0], [0, 1]])
    geo = GeoGraph.load_geograph("marnet")
    assert len(geo.nodes) == 2


# Each cache holds a marnet of its own size. The number of nodes tells which
# cache was read.
def test_cache_dir_argument_wins_over_scgraph_cache_dir(
    environment_cache, tmp_path
):
    _save_as_cached_marnet(environment_cache, nodes=[[0, 0], [0, 1]])
    _save_as_cached_marnet(
        tmp_path / "argument", nodes=[[0, 0], [1, 0], [2, 0]]
    )
    geo = GeoGraph.load_geograph("marnet", cache_dir=str(tmp_path / "argument"))
    assert len(geo.nodes) == 3


# A built network is a folder whose cache.json names a file that exists.
def test_list_buildable_geographs_looks_in_scgraph_cache_dir(
    environment_cache,
):
    built = environment_cache / "networks" / "us_freeway"
    built.mkdir(parents=True)
    (built / "cache.json").write_text('{"file": "built.scgraph"}')
    (built / "built.scgraph").write_bytes(b"")
    listing = {n["name"]: n for n in GeoGraph.list_buildable_geographs()}
    assert listing["us_freeway"]["cached"]


def test_clear_geograph_cache_clears_only_the_cache_of_scgraph_cache_dir(
    environment_cache, tmp_path
):
    _save_as_cached_marnet(environment_cache, nodes=[[0, 0], [0, 1]])
    _save_as_cached_marnet(tmp_path / "other", nodes=[[0, 0], [0, 1]])
    GeoGraph.clear_geograph_cache()
    assert not (environment_cache / "marnet.graphjson").exists()
    assert (tmp_path / "other" / "marnet.graphjson").exists()


# During the load, the process may write 500 bytes per file and no more. The
# write of the 1000 bytes downloaded stops midway, as it does on a full disk.
def test_a_download_that_fails_while_written_leaves_nothing_in_the_cache(
    tmp_path, monkeypatch
):
    resource = pytest.importorskip("resource")  # Windows has no such limit.

    class Response:
        status_code, ok, content = (
            200,
            True,
            b'{"type": "GeoGraph"' + b" " * 1000,
        )

    monkeypatch.setattr(geograph.requests, "get", lambda *a, **k: Response())
    soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_FSIZE)
    resource.setrlimit(resource.RLIMIT_FSIZE, (500, hard_limit))
    try:
        with pytest.raises(OSError):
            GeoGraph.load_geograph("marnet", cache_dir=str(tmp_path))
    finally:
        resource.setrlimit(resource.RLIMIT_FSIZE, (soft_limit, hard_limit))
    # A later load would take any file named marnet.graphjson for the network.
    assert list(tmp_path.iterdir()) == []


@pytest.fixture
def cache_with_marnet(tmp_path):
    """A cache that holds marnet.graphjson, as a download leaves it.

    The Hilbert curve visits its three nodes in the order 1, 2, 0: a load must
    renumber them. The first latitude has 9 decimals: a load must round it to
    1e-7 degree, the precision of a network file.
    """
    GeoGraph(
        graph=[{1: 1.5, 2: 3.0}, {0: 1.5, 2: 2.0}, {1: 2.0}],
        nodes=[[45.000000001, 90], [-45, -90], [45, -90]],
    ).save_as_graphjson(str(tmp_path / "marnet.graphjson"))
    return tmp_path


def test_load_geograph_numbers_the_nodes_along_the_hilbert_curve(
    cache_with_marnet,
):
    geo = GeoGraph.load_geograph("marnet", cache_dir=str(cache_with_marnet))
    # Nodes 1, 2, 0 of the .graphjson become nodes 0, 1, 2. The links follow.
    assert geo.nodes == [[-45, -90], [45, -90], [45, 90]]
    assert list(geo.node_ids) == [1, 2, 0]
    assert geo.graph_object.graph == [
        {2: 1.5, 1: 2.0},
        {0: 2.0},
        {0: 1.5, 1: 3.0},
    ]


def test_first_load_converts_the_published_geograph_into_a_network_file(
    cache_with_marnet,
):
    GeoGraph.load_geograph("marnet", cache_dir=str(cache_with_marnet))
    info = GeoGraph.get_scgraph_info(str(cache_with_marnet / "marnet.scgraph"))
    # The file stores coordinates as int32, in 1e-7 degree. It names the
    # .graphjson as its source.
    assert info["coordinate_dtype"] == "int32"
    assert info["modes"] == [{"name": None, "source": "marnet.graphjson"}]
    assert [s["name"] for s in info["sources"]] == ["marnet.graphjson"]


# The .graphjson is overwritten after the first load: a second load that still
# read it would fail.
def test_later_loads_read_the_network_file_and_not_the_graphjson(
    cache_with_marnet,
):
    first = GeoGraph.load_geograph("marnet", cache_dir=str(cache_with_marnet))
    (cache_with_marnet / "marnet.graphjson").write_text("no longer read")
    again = GeoGraph.load_geograph("marnet", cache_dir=str(cache_with_marnet))
    assert again.nodes == first.nodes
    assert again.graph_object.graph == first.graph_object.graph


# A network file cut short stands for a conversion that was interrupted.
def test_load_geograph_converts_again_a_damaged_network_file(
    cache_with_marnet,
):
    converted = cache_with_marnet / "marnet.scgraph"
    GeoGraph.load_geograph("marnet", cache_dir=str(cache_with_marnet))
    converted.write_bytes(converted.read_bytes()[:-8])
    geo = GeoGraph.load_geograph("marnet", cache_dir=str(cache_with_marnet))
    assert geo.nodes == [[-45, -90], [45, -90], [45, 90]]
    assert GeoGraph.load_from_scgraph(str(converted)).nodes == geo.nodes


# The cache folder is made read-only: the network file cannot be written. The
# load must still give the network, in the same node order.
@pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="Only POSIX has folders that their owner cannot write, except root",
)
def test_load_geograph_reads_the_graphjson_when_the_cache_is_read_only(
    cache_with_marnet,
):
    cache_with_marnet.chmod(0o555)
    try:
        geo = GeoGraph.load_geograph("marnet", cache_dir=str(cache_with_marnet))
    finally:
        cache_with_marnet.chmod(0o755)  # The folder can be removed again.
    assert geo.nodes == [[-45, -90], [45, -90], [45, 90]]
    assert geo.coordinate_dtype == "int32"
    assert not (cache_with_marnet / "marnet.scgraph").exists()


@pytest.fixture
def requested(monkeypatch):
    """The URLs that scgraph requests. The fake download answers each request
    with a geograph of one node. SCGRAPH_OFFLINE is unset."""

    class OneNodeGeograph:
        status_code, ok = 200, True
        content = json.dumps(
            {"type": "GeoGraph", "graph": [{}], "nodes": [[0, 0]]}
        ).encode()

    urls = []
    monkeypatch.setattr(
        geograph.requests,
        "get",
        lambda url, **kwargs: urls.append(url) or OneNodeGeograph(),
    )
    monkeypatch.delenv("SCGRAPH_OFFLINE", raising=False)
    return urls


def test_local_files_only_refuses_a_network_that_is_not_in_the_cache(
    tmp_path, requested
):
    with pytest.raises(FileNotFoundError, match="local_files_only"):
        GeoGraph.load_geograph(
            "marnet", cache_dir=str(tmp_path), local_files_only=True
        )
    assert requested == []


# The cached marnet has two nodes, the downloaded one would have one node.
def test_local_files_only_loads_a_cached_network_without_a_request(
    tmp_path, requested
):
    _save_as_cached_marnet(tmp_path, nodes=[[0, 0], [0, 1]])
    geo = GeoGraph.load_geograph(
        "marnet", cache_dir=str(tmp_path), local_files_only=True
    )
    assert len(geo.nodes) == 2
    assert requested == []


def test_scgraph_offline_forbids_the_download(tmp_path, monkeypatch, requested):
    monkeypatch.setenv("SCGRAPH_OFFLINE", "1")
    with pytest.raises(FileNotFoundError, match="SCGRAPH_OFFLINE"):
        GeoGraph.load_geograph("marnet", cache_dir=str(tmp_path))
    assert requested == []


def test_local_files_only_false_downloads_despite_scgraph_offline(
    tmp_path, monkeypatch, requested
):
    monkeypatch.setenv("SCGRAPH_OFFLINE", "1")
    geo = GeoGraph.load_geograph(
        "marnet", cache_dir=str(tmp_path), local_files_only=False
    )
    assert len(geo.nodes) == 1
    assert len(requested) == 1


# The names of the published geographs are a fixed list in scgraph.
def test_list_geographs_makes_no_request_for_the_published_geographs(
    tmp_path, requested
):
    GeoGraph.list_geographs(cache_dir=str(tmp_path))
    assert requested == []


# Another URL is a mirror with its own geographs. Its contents.txt lists its
# files, and only the .graphjson files are geographs.
def test_list_geographs_reads_contents_txt_of_another_url(
    tmp_path, monkeypatch
):
    class ContentsTxt:
        ok, text = True, "mine.graphjson\nREADME.md\n"

    requested = []
    monkeypatch.setattr(
        geograph.requests,
        "get",
        lambda url, **kwargs: requested.append(url) or ContentsTxt(),
    )
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


def test_clear_geograph_cache_keeps_the_files_that_scgraph_did_not_write(
    filled_cache,
):
    GeoGraph.clear_geograph_cache(str(filled_cache))
    assert _list_files(filled_cache) == {"notes.txt"}


def test_clear_geograph_cache_removes_the_published_and_built_files_of_a_name(
    filled_cache,
):
    before = _list_files(filled_cache)
    GeoGraph.clear_geograph_cache(str(filled_cache), name="marnet")
    assert before - _list_files(filled_cache) == {
        "marnet.graphjson",
        "marnet.scgraph",
        "networks/marnet/m.scgraph",
        "networks/marnet/cache.json",
    }


def test_clear_geograph_cache_removes_every_region_of_a_name_without_region(
    filled_cache,
):
    before = _list_files(filled_cache)
    GeoGraph.clear_geograph_cache(str(filled_cache), name="osm_rail")
    assert before - _list_files(filled_cache) == {
        "networks/osm_rail/europe/e.scgraph",
        "networks/osm_rail/europe/cache.json",
        "networks/osm_rail/europe/france/f.scgraph",
        "networks/osm_rail/europe/france/cache.json",
    }


# France is a sub-region of Europe, and a network of its own.
def test_clear_geograph_cache_of_a_region_keeps_its_sub_regions(filled_cache):
    before = _list_files(filled_cache)
    GeoGraph.clear_geograph_cache(
        str(filled_cache), name="osm_rail", region="europe"
    )
    assert before - _list_files(filled_cache) == {
        "networks/osm_rail/europe/e.scgraph",
        "networks/osm_rail/europe/cache.json",
    }


# Each selector would reach files outside the folder of one network: a name
# or a region that climbs with "..", and a region without a name.
@pytest.mark.parametrize(
    "selector",
    [
        {"name": "../networks"},
        {"name": "osm_rail", "region": "../.."},
        {"region": "europe"},
    ],
)
def test_clear_geograph_cache_refuses_a_selector_that_leaves_the_network(
    filled_cache, selector
):
    before = _list_files(filled_cache)
    with pytest.raises(ValueError):
        GeoGraph.clear_geograph_cache(str(filled_cache), **selector)
    assert _list_files(filled_cache) == before


# The folder of the built marnet is made read-only: its files cannot be
# removed. On Windows, the file of a network that is still loaded behaves so.
@pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="Only POSIX has folders that their owner cannot write, except root",
)
def test_clear_geograph_cache_leaves_a_file_it_cannot_remove_with_a_warning(
    filled_cache, caplog
):
    before = _list_files(filled_cache)
    (filled_cache / "networks/marnet").chmod(0o555)
    try:
        GeoGraph.clear_geograph_cache(str(filled_cache), name="marnet")
    finally:
        (filled_cache / "networks/marnet").chmod(0o755)
    assert before - _list_files(filled_cache) == {
        "marnet.graphjson",
        "marnet.scgraph",
    }
    assert "m.scgraph" in caplog.text
