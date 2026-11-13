import contextlib
import hashlib
import importlib.util
import json
import os
import platform
import random
import re
import sqlite3
import struct
import subprocess
import sys
import sysconfig
import threading
import types
import typing
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from helpers import great_circle_km

from scgraph import GeoGraph, pipelines
from scgraph.helpers.hilbert import hilbert_order
from scgraph.pipelines import (
    eurostat_marnet,
    marnet,
    north_america_rail,
    osm_main_roads,
    osm_main_roads_and_marnet,
)
from scgraph.pipelines import build
from scgraph.utils import has_cpp

# Two lines meeting at (0.01, 0): 4 nodes, not read in Hilbert order
_FEATURES = [
    {"type": "Feature", "properties": {}, "geometry": g}
    for g in (
        {"type": "LineString", "coordinates": [[0.02, 0], [0.01, 0], [0, 0]]},
        {"type": "LineString", "coordinates": [[0.01, 0], [0.01, 0.01]]},
    )
]
_GEOJSON = json.dumps(
    {"type": "FeatureCollection", "features": _FEATURES}
).encode()


def _sea_gpkg(lanes):
    """A GeoPackage of sea lanes as Eurostat stores them, as bytes. A lane is
    `(coordinates, passage)`. The coordinates are a flat list: longitude,
    latitude, longitude, latitude... The passage is the name of the Arctic
    passage that the lane belongs to, or None."""
    database = sqlite3.connect(":memory:")
    database.execute('create table "type" (geometry blob, pass text)')
    for xy, passage in lanes:
        # GeoPackage header with an envelope (left empty), then big-endian WKB
        wkb = struct.pack(f">BII{len(xy)}d", 0, 2, len(xy) // 2, *xy)
        database.execute('insert into "type" values (?, ?)', (b"GP\x00\x02" + bytes(36) + wkb, passage))  # fmt: skip
    return database.serialize()


def _polygons(*rings):
    return json.dumps(
        {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}}
            for ring in rings
        ]}
    ).encode()  # fmt: skip


# Roads: from (-0.01, 0) to (0.01, 0) through (-0.004, 0.001), its nodes not read in
# Hilbert order, and a 2-node fragment at (0.005, 0.024) (lat, lon). Land west of
# longitude 0.03, an island at longitude 0.08 to 0.12, a sea lane from (0, 0.2) to
# (0, 0.3). Ports: "Near" (2.2 km from the road, 0.7 km from the fragment) and the open
# roadstead "Anchorage" (3.3 km of water to the road) are joined to the road; "Island"
# (5.5 km of water to any road), "Inland" (14 km from water) and "Far" (on the coast,
# 27 km from the road) are not
_FILES = {
    "/lines.geojson": _GEOJSON,
    "/roads.osm": b"""<osm version="0.6">
<node id="1" version="1" lat="0" lon="0"/>
<node id="2" version="1" lat="-0.01" lon="0"/>
<node id="3" version="1" lat="-0.004" lon="0.001"/>
<node id="4" version="1" lat="0.01" lon="0"/>
<node id="5" version="1" lat="0.004" lon="0.024"/>
<node id="6" version="1" lat="0.006" lon="0.024"/>
<way id="1" version="1"><nd ref="1"/><nd ref="3"/><nd ref="2"/><tag k="highway" v="primary"/></way>
<way id="2" version="1"><nd ref="1"/><nd ref="4"/><tag k="highway" v="primary"/></way>
<way id="3" version="1"><nd ref="5"/><nd ref="6"/><tag k="highway" v="primary"/></way>
</osm>""",
    "/sea.gpkg": _sea_gpkg([([0.2, 0, 0.3, 0], None)]),
    "/land.geojson": _polygons(
        [[-1, -1], [0.03, -1], [0.03, 1], [-1, 1], [-1, -1]],
        [
            [0.08, -0.02],
            [0.12, -0.02],
            [0.12, 0.02],
            [0.08, 0.02],
            [0.08, -0.02],
        ],
    ),
    "/lakes.geojson": _polygons(),
    "/rivers.geojson": _polygons(),
    "/ports.csv": b"""Main Port Name,Latitude,Longitude,Harbor Type
Near,0,0.02,Coastal (Natural)
Anchorage,0.01,0.06,Open Roadstead
Island,0,0.1,Coastal (Natural)
Inland,0,-0.1,River (Natural)
Far,0.25,0.02,Coastal (Natural)
""",
}


def _write_tangled_lines():
    """80 lines through 60 points, drawn at random with a fixed seed, as the
    bytes of a GeoJSON file. The lines share points, so a node has several
    arcs: the order in which a build writes them shows in the file."""
    rng = random.Random(3)
    points = [[rng.uniform(0, 0.3), rng.uniform(0, 0.3)] for _ in range(60)]
    lines = [rng.sample(points, rng.randint(2, 6)) for _ in range(80)]
    geometries = [{"type": "LineString", "coordinates": line} for line in lines]
    return json.dumps(
        {"type": "GeometryCollection", "geometries": geometries}
    ).encode()


_FILES["/tangled_lines.geojson"] = _write_tangled_lines()


class _Source(BaseHTTPRequestHandler):
    """The files of _FILES at their paths, the lines as an ArcGIS layer at /layer
    (one feature per page), and 404 for any other path."""

    served = []

    def do_GET(self):
        url = urlparse(self.path)
        query = {key: value[0] for key, value in parse_qs(url.query).items()}
        self.served.append(url.path)
        if not (url.path in _FILES or url.path.startswith("/layer")):
            self.send_error(404)
            return
        if url.path in _FILES:
            body = _FILES[url.path]
        elif url.path == "/layer":
            body = {
                "objectIdField": "OBJECTID",
                "maxRecordCount": 1,
                "editingInfo": {"lastEditDate": 1704164645000},
            }
        elif "returnCountOnly" in query:
            body = {"count": len(_FEATURES)}
        else:
            offset, count = int(query["resultOffset"]), int(
                query["resultRecordCount"]
            )
            body = {"features": _FEATURES[offset : offset + count]}
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@contextlib.contextmanager
def _local_server():
    """Serve the sources from a local server, and give its base URL."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Source)
    threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    ).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def source(monkeypatch):
    """The base URL of a local server for the sources. `_Source.served` lists
    the paths that the test has requested."""
    monkeypatch.setattr(_Source, "served", [])
    with _local_server() as url:
        yield url


@pytest.fixture
def marnet_reads_the_local_lines(source, monkeypatch):
    """The `marnet` pipeline downloads /lines.geojson of the local server in
    place of its online source. The fixture gives the URL of that file. The
    network of these two lines has 4 nodes."""
    url = f"{source}/lines.geojson"
    monkeypatch.setitem(marnet.SOURCES["sea_lanes"], "url", url)
    return url


def test_build_geograph_downloads_and_builds_a_network_once(
    tmp_path, marnet_reads_the_local_lines
):
    first = GeoGraph.build_geograph("marnet", cache_dir=tmp_path)
    second = GeoGraph.build_geograph("marnet", cache_dir=tmp_path)

    assert len(first.nodes) == 4
    assert second.graph_object.graph == first.graph_object.graph
    assert _Source.served == ["/lines.geojson"]  # the second call is local


def test_build_geograph_numbers_the_nodes_along_the_hilbert_curve(
    tmp_path, marnet_reads_the_local_lines
):
    # The lines of /lines.geojson list their points in another order.
    geo = GeoGraph.build_geograph("marnet", cache_dir=tmp_path)

    assert hilbert_order(geo.nodes) == list(range(len(geo.nodes)))


# The header of a network file says what built the network. The tests below
# read the header of a marnet built from the local lines.
@pytest.fixture
def marnet_file_info(tmp_path, marnet_reads_the_local_lines):
    built_file = build.build_file("marnet", cache_dir=tmp_path)
    return GeoGraph.get_scgraph_info(built_file)


def test_a_network_file_records_what_built_it_and_from_which_sources(
    marnet_file_info, marnet_reads_the_local_lines
):
    source = marnet.SOURCES["sea_lanes"]
    first_line_of_pipeline_docstring = marnet.__doc__.split("\n")[0]

    assert marnet_file_info["pipeline"] == {
        "name": "marnet",
        "region": None,
        "version": marnet.PIPELINE_VERSION,
    }
    assert first_line_of_pipeline_docstring in marnet_file_info["description"]
    assert marnet_file_info["node_order"] == "hilbert"
    software = marnet_file_info["software"]
    assert software["backend"] == ("cpp" if has_cpp() else "python")
    assert software["platform"].startswith(sysconfig.get_platform())
    # The record has no version: a GeoJSON file does not date its data.
    assert marnet_file_info["sources"] == [
        {
            "name": "sea_lanes",
            "url": marnet_reads_the_local_lines,
            "sha256": hashlib.sha256(_GEOJSON).hexdigest(),
            "bytes": len(_GEOJSON),
            "credit": source["credit"],
            "license": "EUPL-1.2",
            "license_url": source["license_url"],
        }
    ]
    assert marnet_file_info["data_up_to"] is None  # no source has a version
    # The credit line to cite
    assert marnet_file_info["attribution"] == f"{source['credit']} (EUPL-1.2)"


# The math functions of the C library decide the last bit of a length. Two
# builds give the same file only with the same C library.
@pytest.mark.skipif(
    not platform.libc_ver()[0],
    reason="Python does not know the C library of this platform",
)
def test_network_file_names_the_c_library_of_the_platform(marnet_file_info):
    library, version = platform.libc_ver()

    assert marnet_file_info["software"]["platform"].endswith(
        f" {library} {version}"
    )


# The time of the download is the only clock time of a build. It stays out of
# the network file, so that the same sources give the same file.
def test_download_time_is_in_cache_json_and_not_in_the_network_file(
    tmp_path, marnet_file_info
):
    cache_json = tmp_path / "networks" / "marnet" / "cache.json"
    download_time = json.loads(cache_json.read_text())["downloaded"]

    assert download_time not in json.dumps(marnet_file_info)


def test_a_built_network_is_a_folder_with_cache_json_and_the_file_it_names(
    tmp_path, marnet_reads_the_local_lines
):
    built_file = Path(build.build_file("marnet", cache_dir=tmp_path))

    folder = tmp_path / "networks" / "marnet"
    cache_json = json.loads((folder / "cache.json").read_text())
    assert cache_json["file"] == built_file.name
    assert {p.name for p in folder.iterdir()} == {"cache.json", built_file.name}
    # The file is named by the SHA-256 of its content. A network file starts
    # with 8 bytes that mark its format and 32 bytes of digest. The digest
    # covers the rest of the file.
    content = built_file.read_bytes()[40:]
    assert built_file.name == hashlib.sha256(content).hexdigest() + ".scgraph"
    # Backup tools skip a folder with this file. The signature comes from
    # the Cache Directory Tagging Specification.
    tag = (tmp_path / "networks" / "CACHEDIR.TAG").read_text()
    assert tag.startswith("Signature: 8a477f597d28d172789f06886806bc55")


def test_list_buildable_geographs_tells_which_networks_are_in_the_cache(
    tmp_path, marnet_reads_the_local_lines
):
    GeoGraph.build_geograph("marnet", cache_dir=tmp_path)

    listing = {
        n["name"]: n for n in GeoGraph.list_buildable_geographs(tmp_path)
    }
    assert listing["marnet"]["cached"]
    assert not listing["us_freeway"]["cached"]


def test_list_buildable_geographs_does_not_count_a_network_without_its_file(
    tmp_path, marnet_reads_the_local_lines
):
    built_file = Path(build.build_file("marnet", cache_dir=tmp_path))
    built_file.unlink()

    listing = {
        n["name"]: n for n in GeoGraph.list_buildable_geographs(tmp_path)
    }
    assert not listing["marnet"]["cached"]


def _cut_short(file):
    file.write_bytes(file.read_bytes()[:100])


# A file cut short stands for every file that scgraph cannot read: a damaged
# file, or a file in the format of another version of scgraph.
@pytest.mark.parametrize(
    "damage",
    [Path.unlink, _cut_short],
    ids=["its file is missing", "its file cannot be read"],
)
def test_build_geograph_builds_again_a_network_without_a_readable_file(
    tmp_path, marnet_reads_the_local_lines, damage
):
    built_file = Path(build.build_file("marnet", cache_dir=tmp_path))
    damage(built_file)

    geo = GeoGraph.build_geograph("marnet", cache_dir=tmp_path)

    assert len(geo.nodes) == 4
    assert _Source.served == ["/lines.geojson"] * 2


# The tests below state when `build_geograph` may download. The argument
# `local_files_only=True` forbids it, and so does SCGRAPH_OFFLINE=1 in the
# environment when the argument is not given. Another value of the variable
# leaves the choice to the argument.
@pytest.mark.parametrize(
    "scgraph_offline, local_files_only",
    [("0", True), ("1", None)],
    ids=["local_files_only=True", "SCGRAPH_OFFLINE=1"],
)
def test_a_network_that_is_not_in_the_cache_is_refused_without_a_download(
    tmp_path,
    marnet_reads_the_local_lines,
    monkeypatch,
    scgraph_offline,
    local_files_only,
):
    monkeypatch.setenv("SCGRAPH_OFFLINE", scgraph_offline)

    # The message names the two ways to forbid the download.
    with pytest.raises(
        FileNotFoundError,
        match=r"local_files_only=True \(or SCGRAPH_OFFLINE=1\)",
    ):
        GeoGraph.build_geograph(
            "marnet", cache_dir=tmp_path, local_files_only=local_files_only
        )

    assert _Source.served == []


def test_scgraph_offline_loads_a_cached_network_without_a_request(
    tmp_path, marnet_reads_the_local_lines, monkeypatch
):
    GeoGraph.build_geograph("marnet", cache_dir=tmp_path)
    monkeypatch.setenv("SCGRAPH_OFFLINE", "1")

    geo = GeoGraph.build_geograph("marnet", cache_dir=tmp_path)

    assert len(geo.nodes) == 4
    assert _Source.served == ["/lines.geojson"]  # the first build only


def test_local_files_only_false_builds_despite_scgraph_offline(
    tmp_path, marnet_reads_the_local_lines, monkeypatch
):
    monkeypatch.setenv("SCGRAPH_OFFLINE", "1")

    geo = GeoGraph.build_geograph(
        "marnet", cache_dir=tmp_path, local_files_only=False
    )

    assert len(geo.nodes) == 4
    assert _Source.served == ["/lines.geojson"]


def test_refresh_downloads_and_builds_again_a_network_that_is_in_the_cache(
    tmp_path, marnet_reads_the_local_lines
):
    GeoGraph.build_geograph("marnet", cache_dir=tmp_path)

    GeoGraph.build_geograph("marnet", cache_dir=tmp_path, refresh=True)

    assert _Source.served == ["/lines.geojson"] * 2


def test_refresh_is_refused_when_scgraph_offline_forbids_the_download(
    tmp_path, marnet_reads_the_local_lines, monkeypatch
):
    GeoGraph.build_geograph("marnet", cache_dir=tmp_path)
    monkeypatch.setenv("SCGRAPH_OFFLINE", "1")

    with pytest.raises(ValueError, match="SCGRAPH_OFFLINE"):
        GeoGraph.build_geograph("marnet", cache_dir=tmp_path, refresh=True)

    assert _Source.served == ["/lines.geojson"]  # the first build only


def test_local_files_only_refuses_a_cached_network_that_cannot_be_read(
    tmp_path, marnet_reads_the_local_lines
):
    built_file = Path(build.build_file("marnet", cache_dir=tmp_path))
    built_file.write_bytes(built_file.read_bytes()[:100])

    with pytest.raises(ValueError, match="can't be read"):
        GeoGraph.build_geograph(
            "marnet", cache_dir=tmp_path, local_files_only=True
        )

    assert _Source.served == ["/lines.geojson"]  # the first build only


def test_a_failed_download_leaves_the_cached_network_and_says_how_to_load_it(
    tmp_path, marnet_reads_the_local_lines, monkeypatch
):
    GeoGraph.build_geograph("marnet", cache_dir=tmp_path)
    # The server now answers 404 for the source.
    monkeypatch.delitem(_FILES, "/lines.geojson")

    with pytest.raises(requests.HTTPError, match="local_files_only=True"):
        GeoGraph.build_geograph("marnet", cache_dir=tmp_path, refresh=True)

    cached = GeoGraph.build_geograph(
        "marnet", cache_dir=tmp_path, local_files_only=True
    )
    assert len(cached.nodes) == 4


def _lines_pipeline(source, build=marnet.build, expected_km=2.22):
    """A pipeline module of one's own, cached as "lines". It builds the network of
    /lines.geojson. Its validation case is the route between the ends of the first
    line, (0, 0) and (0, 0.02) (lat, lon): 0.02 degree of the equator, 2.22 km. The
    validation fails for another `expected_km`."""
    module = types.ModuleType("my_pipelines.lines")
    module.SOURCES = {
        "sea_lanes": {
            **marnet.SOURCES["sea_lanes"],
            "url": f"{source}/lines.geojson",
        }
    }
    module.PIPELINE_VERSION, module.build = 1, build
    module.VALIDATION = {
        "cases": [
            {
                "id": "end_to_end",
                "kind": "route_lengths",
                "origin": (0, 0),
                "destination": (0, 0.02),
                "reference": expected_km,
                "tolerance": None,
            }
        ]
    }
    return module


def test_build_file_caches_a_network_that_passes_its_validation(
    tmp_path, source
):
    network = _lines_pipeline(source)

    built_file = build.build_file(network, cache_dir=tmp_path, validate=True)

    cached = GeoGraph.build_geograph(
        network, cache_dir=tmp_path, local_files_only=True
    )
    assert len(cached.nodes) == 4
    assert built_file.startswith(str(tmp_path / "networks" / "lines"))


def test_build_file_does_not_cache_a_network_that_fails_its_validation(
    tmp_path, source
):
    # No route of this network is 100 km long
    network = _lines_pipeline(source, expected_km=100)

    with pytest.raises(RuntimeError, match="validation failed for lines"):
        build.build_file(network, cache_dir=tmp_path, validate=True)

    assert not (tmp_path / "networks" / "lines").exists()


def test_a_failed_validation_leaves_the_network_of_an_earlier_build_cached(
    tmp_path, source, monkeypatch
):
    earlier_file = build.build_file(_lines_pipeline(source), cache_dir=tmp_path)
    earlier_bytes = Path(earlier_file).read_bytes()
    # The source has changed since, and the network it gives fails its validation
    moved_end = _GEOJSON.replace(b"0.02", b"0.03")
    monkeypatch.setitem(_FILES, "/lines.geojson", moved_end)
    failing = _lines_pipeline(source, expected_km=100)

    with pytest.raises(RuntimeError, match="validation failed for lines"):
        build.build_file(
            failing, cache_dir=tmp_path, refresh=True, validate=True
        )

    cached_file = build.build_file(
        failing, cache_dir=tmp_path, local_files_only=True
    )
    assert cached_file == earlier_file
    assert Path(cached_file).read_bytes() == earlier_bytes


def _fail_to_build(files):
    raise RuntimeError("build failed")


def test_a_failed_build_keeps_its_sources_for_the_next_build(tmp_path, source):
    broken = _lines_pipeline(source, build=_fail_to_build)
    with pytest.raises(RuntimeError, match="build failed"):
        GeoGraph.build_geograph(broken, cache_dir=tmp_path)

    repaired = _lines_pipeline(source)
    geo = GeoGraph.build_geograph(repaired, cache_dir=tmp_path)

    assert len(geo.nodes) == 4
    assert _Source.served == ["/lines.geojson"]  # downloaded once


def test_refresh_downloads_the_sources_again_after_a_failed_build(
    tmp_path, source
):
    broken = _lines_pipeline(source, build=_fail_to_build)
    with pytest.raises(RuntimeError, match="build failed"):
        GeoGraph.build_geograph(broken, cache_dir=tmp_path)

    repaired = _lines_pipeline(source)
    GeoGraph.build_geograph(repaired, cache_dir=tmp_path, refresh=True)

    assert _Source.served == ["/lines.geojson"] * 2


# A cached network is built again when its pipeline has another
# PIPELINE_VERSION. The module of the next version has the same name and the
# same source: only its version differs.
def test_build_geograph_builds_again_for_another_pipeline_version(
    tmp_path, source
):
    GeoGraph.build_geograph(_lines_pipeline(source), cache_dir=tmp_path)
    next_version = _lines_pipeline(source)
    next_version.PIPELINE_VERSION = 2

    GeoGraph.build_geograph(next_version, cache_dir=tmp_path)
    GeoGraph.build_geograph(next_version, cache_dir=tmp_path)

    assert _Source.served == ["/lines.geojson"] * 2  # once for each version


def test_local_files_only_loads_a_network_of_another_pipeline_version(
    tmp_path, source
):
    GeoGraph.build_geograph(_lines_pipeline(source), cache_dir=tmp_path)
    next_version = _lines_pipeline(source)
    next_version.PIPELINE_VERSION = 2

    # The warning names the two versions.
    with pytest.warns(UserWarning, match="pipeline version 1, now 2;"):
        geo = GeoGraph.build_geograph(
            next_version, cache_dir=tmp_path, local_files_only=True
        )

    assert len(geo.nodes) == 4
    assert _Source.served == ["/lines.geojson"]  # the first build only


def test_a_new_build_replaces_the_network_file_of_the_earlier_build(
    tmp_path, source, monkeypatch
):
    network = _lines_pipeline(source)
    earlier_file = Path(build.build_file(network, cache_dir=tmp_path))
    # The source has changed since. The new network has another content,
    # so its file has another name.
    moved_end = _GEOJSON.replace(b"0.02", b"0.03")
    monkeypatch.setitem(_FILES, "/lines.geojson", moved_end)

    new_file = Path(build.build_file(network, cache_dir=tmp_path, refresh=True))

    folder = tmp_path / "networks" / "lines"
    assert new_file != earlier_file
    assert {p.name for p in folder.iterdir()} == {"cache.json", new_file.name}


def test_a_pipeline_module_gives_the_last_part_of_its_name_to_its_network(
    tmp_path, source
):
    network = _lines_pipeline(source)  # the module my_pipelines.lines

    geo = GeoGraph.build_geograph(network, cache_dir=tmp_path)

    assert geo.metadata["pipeline"]["name"] == "lines"


def test_a_pipeline_module_named_like_a_built_in_network_is_refused(tmp_path):
    # Its network would take the place of the built-in marnet in the cache.
    namesake = types.ModuleType("my_pipelines.marnet")

    with pytest.raises(ValueError, match="Invalid pipeline module name"):
        GeoGraph.build_geograph(namesake, cache_dir=tmp_path)


def test_the_steps_that_a_pipeline_returns_are_stored_in_the_network_file(
    tmp_path, source
):
    def build_with_steps(files):
        return marnet.build(files), [{"step": "copy", "arcs": 1}]

    network = _lines_pipeline(source, build=build_with_steps)

    geo = GeoGraph.build_geograph(network, cache_dir=tmp_path)

    assert geo.metadata["steps"] == [{"step": "copy", "arcs": 1}]


# The ArcGIS layer of the local server holds the two lines of /lines.geojson
# and gives one line per page.
def test_build_geograph_reads_every_page_of_an_arcgis_layer_and_its_version(
    tmp_path, source, monkeypatch
):
    monkeypatch.setitem(
        north_america_rail.SOURCES["rail_lines"], "url", f"{source}/layer"
    )

    geo = GeoGraph.build_geograph("north_america_rail", cache_dir=tmp_path)

    assert len(geo.nodes) == 4  # the first line alone has 3 nodes
    # The version of the data is the last edit of the layer, which the layer
    # gives as 1704164645000 ms after 1970.
    (layer,) = geo.metadata["sources"]
    assert layer["version"] == "2024-01-02T03:04:05Z"


# The same sources must give the same network file in every process, so
# that a file can be checked against another build. The tests below build in
# child processes, as separate users do. A child takes the URL of the local
# server, its cache folder, the name of the network, its region or "", and
# the backend: "pure python" hides the C++ extension from the child.
_BUILD_IN_A_CHILD_PROCESS = """
import sys
server, cache_dir, name, region, backend = sys.argv[1:]
if backend == "pure python":
    sys.modules["scgraph.cpp"] = None  # importing the extension now fails
from scgraph import GeoGraph
from scgraph.pipelines import marnet, osm_main_roads
marnet.SOURCES["sea_lanes"]["url"] = server + "/tangled_lines.geojson"
roads = {**osm_main_roads.SOURCES["roads"], "url": server + "/{region}.osm"}
osm_main_roads.SOURCES["roads"] = roads
GeoGraph.build_geograph(name, region=region or None, cache_dir=cache_dir)
"""


def _build_in_a_child_process(
    source, cache_dir, name, region, hash_seed, backend="installed"
):
    """Build the network into `cache_dir` in a new Python process, and return
    the path of its network file. `hash_seed` sets the order in which the
    child iterates over its sets."""
    cache_dir.mkdir()
    subprocess.run(
        [
            sys.executable,
            "-c",
            _BUILD_IN_A_CHILD_PROCESS,
            source,
            str(cache_dir),
            name,
            region or "",
            backend,
        ],
        env={**os.environ, "PYTHONHASHSEED": hash_seed},
        check=True,
        timeout=120,
        cwd=cache_dir,  # so that the child imports the installed scgraph
    )
    folder = cache_dir / "networks" / name / (region or "")
    return folder / json.loads((folder / "cache.json").read_text())["file"]


# The two kinds of pipeline. marnet returns a GeoGraph, which scgraph then
# writes to a network file. osm_main_roads returns the arrays of the network
# file: its region "roads" is the file /roads.osm of the local server.
_NETWORKS_OF_BOTH_KINDS = [
    pytest.param("marnet", None, id="marnet"),
    pytest.param(
        "osm_main_roads",
        "roads",
        id="osm_main_roads",
        marks=pytest.mark.skipif(
            importlib.util.find_spec("osmium") is None,
            reason="osmium is not installed",
        ),
    ),
]


@pytest.mark.parametrize("name, region", _NETWORKS_OF_BOTH_KINDS)
def test_a_network_built_twice_from_the_same_sources_is_the_same_file(
    tmp_path, source, name, region
):
    first = _build_in_a_child_process(
        source, tmp_path / "first", name, region, hash_seed="1"
    )
    second = _build_in_a_child_process(
        source, tmp_path / "second", name, region, hash_seed="2"
    )

    assert first.read_bytes() == second.read_bytes()


# The pure-Python build and the C++ build give the same nodes, and the same
# arcs with the same lengths. The order of the arcs of a node may differ.
@pytest.mark.parametrize("name, region", _NETWORKS_OF_BOTH_KINDS)
def test_a_network_built_in_pure_python_is_the_same_graph(
    tmp_path, source, name, region
):
    installed_file = _build_in_a_child_process(
        source, tmp_path / "installed", name, region, hash_seed="1"
    )
    pure_python_file = _build_in_a_child_process(
        source,
        tmp_path / "pure_python",
        name,
        region,
        hash_seed="2",
        backend="pure python",
    )

    info = GeoGraph.get_scgraph_info(str(pure_python_file))
    assert info["software"]["backend"] == "python"
    installed = GeoGraph.load_from_scgraph(str(installed_file))
    pure_python = GeoGraph.load_from_scgraph(str(pure_python_file))
    assert pure_python.nodes == installed.nodes
    assert list(pure_python.node_ids) == list(installed.node_ids)
    assert pure_python.graph_object.graph == installed.graph_object.graph


def test_build_geograph_names_a_region_geofabrik_does_not_have(
    tmp_path, source, monkeypatch
):
    pytest.importorskip("osmium")  # checked before the download
    monkeypatch.setitem(
        osm_main_roads.SOURCES["roads"], "url", f"{source}/{{region}}.osm"
    )
    with pytest.raises(ValueError, match="No extract 'nowhere'"):
        GeoGraph.build_geograph(
            "osm_main_roads", region="nowhere", cache_dir=str(tmp_path)
        )
    assert GeoGraph.get_cache_info(cache_dir=str(tmp_path)) == []


# From the command line, a network is built into the cache without being loaded, and
# the path of its file is printed; build_geograph then loads that file
def test_build_command_builds_the_file_build_geograph_loads(
    tmp_path, source, monkeypatch, capsys
):
    monkeypatch.setitem(
        marnet.SOURCES["sea_lanes"], "url", f"{source}/lines.geojson"
    )
    build.main(["marnet", "--cache-dir", str(tmp_path)])
    path = capsys.readouterr().out.strip()
    folder = tmp_path / "networks" / "marnet"
    assert path == str(
        folder / json.loads((folder / "cache.json").read_text())["file"]
    )
    geo = GeoGraph.build_geograph("marnet", cache_dir=str(tmp_path))
    assert _Source.served == ["/lines.geojson"]  # loaded, not built again
    assert len(geo.nodes) == 4


# A source's own download hook is called for that source only, and its record says
# what identifies the source, in place of the downloaded file's sha256 and size
def test_build_geograph_calls_the_download_hook_of_a_source(tmp_path):
    calls = []

    def stream(url, filename):
        calls.append(url)
        with open(filename, "wb") as file:
            file.write(_GEOJSON)
        return {"bytes": 10**11, "md5": "0" * 32}

    module = types.ModuleType("my_pipelines.streamed")
    url = "https://planet.example/lines.geojson"
    module.SOURCES = {
        "sea_lanes": {
            **marnet.SOURCES["sea_lanes"],
            "url": url,
            "download": stream,
        }
    }
    module.PIPELINE_VERSION, module.build = 1, marnet.build
    module.download = lambda url, filename: pytest.fail("module's hook called")
    geo = GeoGraph.build_geograph(module, cache_dir=str(tmp_path))
    (record,) = geo.metadata["sources"]
    assert calls == [url] and "sha256" not in record
    assert (record["bytes"], record["md5"]) == (10**11, "0" * 32)


def test_list_buildable_geographs_matches_the_names_build_geograph_takes(
    tmp_path,
):
    listing = GeoGraph.list_buildable_geographs(str(tmp_path))
    names = [n["name"] for n in listing]
    annotation = typing.get_type_hints(GeoGraph.build_geograph)["name"]
    literal = typing.get_args(annotation)[0]  # Literal[...] | ModuleType
    assert names == list(pipelines.NAMES) == list(typing.get_args(literal))


# Two roads on the two sides of a strait, and five ferries. Each node is
# (latitude, longitude). Road 1 joins nodes 1 and 2 on the west side. Road 2
# runs 3, 5, 4 on the east side.
# - Ferry 3 runs 10, 11, 3. Node 10 is 0.6 km from node 2, and node 3 is on
#   road 2. Its route is 6.7 km long.
# - Ferry 4 runs from 0.1 km off node 2 to 0.1 km off node 3 in 5.3 km. It is
#   closed to cars.
# - Ferry 5 ends 0.2 km from node 3 and starts at node 30, 3.6 km from the
#   nearest road node. Its route is 4.2 km long.
# - Ferry 6 runs from 0.1 km off node 1 to 0.1 km off node 2 in 2.3 km. Road 1
#   joins the same nodes in 1.1 km.
# - Ferry 7 runs from node 5, in the middle of road 2, to node 50. Node 50 is
#   0.6 km from node 1.
_STRAIT_NODES = {
    1: (0, 0), 2: (0, 0.01), 3: (0, 0.06), 4: (0, 0.07), 5: (0, 0.065),
    10: (0, 0.015), 11: (0.02, 0.035), 50: (0.005, 0),
    20: (0, 0.011), 21: (0, 0.059),
    30: (0.025, 0.03), 31: (0, 0.058),
    40: (0.001, 0), 41: (0.01, 0.005), 42: (0.001, 0.01),
}  # fmt: skip
_STRAIT_WAYS = {
    1: ([1, 2], 'k="highway" v="primary"'),
    2: ([3, 5, 4], 'k="highway" v="trunk"'),
    3: ([10, 11, 3], 'k="route" v="ferry"'),
    4: ([20, 21], 'k="route" v="ferry"/><tag k="motor_vehicle" v="no"'),
    5: ([30, 31], 'k="route" v="ferry"'),
    6: ([40, 41, 42], 'k="route" v="ferry"'),
    7: ([5, 50], 'k="route" v="ferry"'),
}


def _write_strait_osm():
    """The strait as the bytes of an OSM file, its nodes sorted by id."""
    lines = [
        f'<node id="{node}" version="1" lat="{latitude}" lon="{longitude}"/>'
        for node, (latitude, longitude) in sorted(_STRAIT_NODES.items())
    ]
    for way, (nodes, tags) in _STRAIT_WAYS.items():
        refs = "".join(f'<nd ref="{node}"/>' for node in nodes)
        lines.append(f'<way id="{way}" version="1">{refs}<tag {tags}/></way>')
    return ('<osm version="0.6">' + "\n".join(lines) + "</osm>").encode()


_FILES["/strait.osm"] = _write_strait_osm()


def _strait_km(*nodes):
    """The length of the line through these nodes of the strait."""
    places = [_STRAIT_NODES[node] for node in nodes]
    return sum(great_circle_km(a, b) for a, b in zip(places, places[1:]))


@pytest.fixture(scope="module")
def strait_network(tmp_path_factory):
    """The network that `osm_main_roads` builds from the strait. The local
    server stands for Geofabrik: the region "strait" is its file /strait.osm.

    The build keeps the nodes 1, 3, 4 and 5. It contracts node 2, which only
    joins road 1 to ferry 3.
    """
    pytest.importorskip("osmium")
    with _local_server() as server, pytest.MonkeyPatch.context() as patch:
        patch.setitem(
            osm_main_roads.SOURCES["roads"], "url", f"{server}/{{region}}.osm"
        )
        return GeoGraph.build_geograph(
            "osm_main_roads",
            region="strait",
            cache_dir=tmp_path_factory.mktemp("strait"),
        )


def _by_osm_ids(geograph, rows):
    """The values of `rows`, a list of one dict per node, as one dict. Its
    keys are the pairs (OSM id of the origin, OSM id of the destination)."""
    osm_ids = list(geograph.node_ids)
    return {
        (osm_ids[u], osm_ids[v]): value
        for u, row in enumerate(rows)
        for v, value in row.items()
    }


def test_a_car_ferry_joins_the_road_nodes_nearest_its_two_ends(strait_network):
    arcs = _by_osm_ids(strait_network, strait_network.graph_object.graph)
    shapes = _by_osm_ids(strait_network, strait_network.intermediate_nodes)

    # From node 1: road 1 to node 2, then ferry 3. The ferry counts for the
    # length of its own route, from node 10 to node 3. Each ferry that must be
    # left out would give another length. Ferry 4 is closed to cars, and ferry
    # 5 starts far from any road: both are shorter than ferry 3. Ferry 6 is
    # longer than road 1, which joins the same nodes.
    assert arcs[(1, 3)] == pytest.approx(
        _strait_km(1, 2) + _strait_km(10, 11, 3)
    )
    # After node 2, the drawing goes to the start of ferry 3, then along it.
    assert shapes[(1, 3)] == [list(_STRAIT_NODES[node]) for node in (2, 10, 11)]


def test_a_ferry_that_starts_inside_a_road_cuts_the_road_at_that_node(
    strait_network,
):
    arcs = _by_osm_ids(strait_network, strait_network.graph_object.graph)

    # Node 5 is a middle point of road 2 and the start of ferry 7. The ferry
    # joins it to node 1, the road node nearest its other end.
    assert arcs[(5, 1)] == pytest.approx(_strait_km(5, 50))
    assert arcs[(3, 5)] == pytest.approx(_strait_km(3, 5))


def test_the_network_file_tells_how_many_ferry_arcs_the_build_added(
    strait_network,
):
    # Road 1 is one piece, and road 2 is cut at node 5 into two pieces.
    # Ferries 3, 6 and 7 each give one arc in each direction.
    assert strait_network.metadata["steps"][:2] == [
        {"step": "read", "pieces": 3},
        {"step": "ferries", "arcs": 6},
    ]


# With a work folder, the build keeps the pieces of the ways in files and
# not in memory.
def test_osm_main_roads_builds_the_same_network_with_a_work_folder(tmp_path):
    pytest.importorskip("osmium")
    strait_file = tmp_path / "strait.osm"
    strait_file.write_bytes(_FILES["/strait.osm"])

    built_in_memory = osm_main_roads.build({"roads": str(strait_file)})
    built_in_files = osm_main_roads.build(
        {"roads": str(strait_file)}, work_dir=str(tmp_path / "work")
    )

    assert built_in_files == built_in_memory


@pytest.fixture(scope="module")
def coast_network(tmp_path_factory):
    """The network that `osm_main_roads_and_marnet` builds from the coast that
    the comment above `_FILES` describes: a road, a sea lane and five ports.

    The local server stands for every source. The roads are served as a
    Geofabrik extract: a PBF whose header gives the time of its data. The
    region "roads" is the file /roads.osm.pbf.
    """
    osmium = pytest.importorskip("osmium")
    tmp_path = tmp_path_factory.mktemp("coast")
    xml, pbf = tmp_path / "roads.osm", tmp_path / "roads.osm.pbf"
    xml.write_bytes(_FILES["/roads.osm"])
    header = osmium.io.Header()
    header.set("osmosis_replication_timestamp", "2026-11-06T20:21:43Z")
    with osmium.SimpleWriter(str(pbf), header=header) as writer:
        for entity in osmium.FileProcessor(str(xml)):
            writer.add(entity)
    paths = {
        "roads": "/{region}.osm.pbf",
        "land": "/land.geojson",
        "lakes": "/lakes.geojson",
        "rivers": "/rivers.geojson",
        "sea": "/sea.gpkg",
        "ports": "/ports.csv",
    }
    with _local_server() as server, pytest.MonkeyPatch.context() as patch:
        patch.setitem(_FILES, "/roads.osm.pbf", pbf.read_bytes())
        for name, path in paths.items():
            patch.setitem(
                osm_main_roads_and_marnet.SOURCES,
                name,
                {
                    **osm_main_roads_and_marnet.SOURCES[name],
                    "url": server + path,
                },
            )
        return GeoGraph.build_geograph(
            "osm_main_roads_and_marnet", region="roads", cache_dir=tmp_path
        )


def test_nodes_are_stored_by_mode_and_each_mode_names_its_source(coast_network):
    assert coast_network.modes == [
        {"name": "road", "source": "roads"},
        {"name": "port"},
        {"name": "sea", "source": "sea"},
    ]
    # 3 road nodes, then 2 ports, then the 2 ends of the sea lane
    assert list(coast_network.node_modes) == [0, 0, 0, 1, 1, 2, 2]


def test_a_road_fragment_apart_from_the_main_road_is_left_out(coast_network):
    road_nodes = sorted(list(coast_network.nodes)[:3])

    # The fragment at (0.005, 0.024) is not among them.
    assert road_nodes == [[-0.01, 0], [0, 0], [0.01, 0]]


def test_only_a_port_near_a_road_and_near_water_becomes_a_node(coast_network):
    port_nodes = sorted(list(coast_network.nodes)[3:5])
    ids_of_port_nodes = sorted(list(coast_network.node_ids)[3:5])

    # "Near" and "Anchorage". "Island" and "Far" are too far from the road,
    # and "Inland" is too far from water.
    assert port_nodes == [[0, 0.02], [0.01, 0.06]]
    # A road node keeps its OSM id, which is positive. A port is not an OSM
    # node: scgraph numbers the ports -1, -2...
    assert ids_of_port_nodes == [-2, -1]


def test_a_route_from_the_road_to_the_sea_lane_passes_through_a_port(
    coast_network,
):
    route = coast_network.get_shortest_path(
        origin_node={"latitude": -0.01, "longitude": 0},
        destination_node={"latitude": 0, "longitude": 0.3},
        output_coordinate_path="list_of_lists",
    )

    assert [-0.004, 0.001] in route["coordinate_path"]  # the bend of the road
    assert [0, 0.02] in route["coordinate_path"]  # the port "Near"


def test_a_port_is_joined_to_the_road_by_1_2_times_the_straight_line(
    coast_network,
):
    nodes = list(coast_network.nodes)
    port, road_node = nodes.index([0, 0.02]), nodes.index([0, 0])

    connector_km = coast_network.graph_object.graph[port][road_node]

    assert connector_km == pytest.approx(
        1.2 * great_circle_km([0, 0.02], [0, 0])
    )


def test_a_port_is_joined_to_the_sea_by_the_length_of_its_path_on_water(
    coast_network,
):
    nodes = list(coast_network.nodes)
    port, lane_end = nodes.index([0, 0.02]), nodes.index([0, 0.2])
    shapes = coast_network.intermediate_nodes

    connector_km = coast_network.graph_object.graph[port][lane_end]

    path_on_water = [[0, 0.02], *shapes[port][lane_end], [0, 0.2]]
    drawn_km = sum(
        great_circle_km(a, b) for a, b in zip(path_on_water, path_on_water[1:])
    )
    assert connector_km == pytest.approx(drawn_km, rel=1e-4)
    # The way back from the sea to the port has the reversed shape.
    assert shapes[lane_end][port] == shapes[port][lane_end][::-1]


def test_the_network_file_lists_what_each_step_of_the_build_did(coast_network):
    assert coast_network.metadata["steps"] == [
        # The main road in 2 pieces and the fragment
        {"step": "read", "pieces": 3},
        {"step": "ferries", "arcs": 0},
        # The 2 ends of the sea lane, joined in both directions
        {"step": "sea", "nodes": 2, "arcs": 2},
        {"step": "ports", "joined": 2},
        # Without the fragment: 3 road nodes, 2 ports and 2 sea nodes
        {"step": "components", "nodes": 7, "arcs": 14},
        {"step": "contract", "nodes": 7, "arcs": 14},
    ]


def test_each_source_is_recorded_with_the_version_of_its_data(coast_network):
    versions = {
        source["name"]: source.get("version")
        for source in coast_network.metadata["sources"]
    }

    assert versions == {
        "roads": "2026-11-06T20:21:43Z",  # the time in the header of the PBF
        "land": "5.1.2",  # the release of Natural Earth that the pipeline names
        "lakes": "5.1.2",
        "rivers": "5.1.2",
        "sea": None,
        "ports": None,
    }


# Eurostat stores a lane that crosses the antimeridian as two lines. One
# ends at longitude 180 and the other starts at longitude -180.
def test_eurostat_marnet_joins_a_lane_cut_at_the_antimeridian(tmp_path):
    lanes = tmp_path / "lanes.gpkg"
    lanes.write_bytes(
        _sea_gpkg([([179, 0, 180, 0], None), ([-180, 0, -179, 0], None)])
    )

    geo = eurostat_marnet.build({"sea_lanes": str(lanes)})

    route = geo.get_shortest_path(
        origin_node={"latitude": 0, "longitude": 179},
        destination_node={"latitude": 0, "longitude": -179},
    )
    # Two degrees of the equator
    assert route["length"] == pytest.approx(
        great_circle_km([0, 179], [0, -179]), abs=0.01
    )


# Two points of the Arctic are joined by a direct lane of each Arctic
# passage, and by an open-sea lane that goes round by the south.
def test_eurostat_marnet_leaves_out_the_lanes_of_the_arctic_passages(tmp_path):
    lanes = tmp_path / "lanes.gpkg"
    lanes.write_bytes(
        _sea_gpkg(
            [
                ([100, 75, 110, 75], "northeast"),
                ([100, 75, 110, 75], "northwest"),
                ([100, 75, 105, 70, 110, 75], None),
            ]
        )
    )

    geo = eurostat_marnet.build({"sea_lanes": str(lanes)})

    route = geo.get_shortest_path(
        origin_node={"latitude": 75, "longitude": 100},
        destination_node={"latitude": 75, "longitude": 110},
    )
    assert route["length"] == pytest.approx(
        great_circle_km([75, 100], [70, 105])
        + great_circle_km([70, 105], [75, 110]),
        abs=0.01,
    )


@pytest.mark.parametrize(
    "name, region, message",
    [
        ("nowhere", None, "Unknown network"),
        ("marnett", None, "Did you mean 'marnet'"),
        ("osm_main_roads", None, "needs a region"),
        ("marnet", "europe/luxembourg", "has no region"),
        ("osm_main_roads", "../europe", "Invalid region"),
    ],
)
def test_build_geograph_checks_its_arguments_before_downloading(
    tmp_path, monkeypatch, name, region, message
):
    monkeypatch.setattr("requests.get", None)  # any download fails at once
    with pytest.raises(ValueError, match=message):
        GeoGraph.build_geograph(name, region=region, cache_dir=str(tmp_path))
    assert list(tmp_path.iterdir()) == []


# A cached network must stay the file that its cache.json names: nothing
# else is saved under `networks/` of the cache.
@pytest.mark.parametrize(
    "save, file_name",
    [
        (GeoGraph.save_as_scgraph, "edited.scgraph"),
        (GeoGraph.save_as_graphjson, "edited.graphjson"),
    ],
    ids=["save_as_scgraph", "save_as_graphjson"],
)
def test_saving_a_file_among_the_built_networks_of_the_cache_is_refused(
    tmp_path, monkeypatch, save, file_name
):
    monkeypatch.setenv("SCGRAPH_CACHE_DIR", str(tmp_path))
    geo = GeoGraph(graph=[{1: 1.0}, {0: 1.0}], nodes=[[0, 0], [0, 0.01]])
    target = tmp_path / "networks" / "marnet" / file_name
    target.parent.mkdir(parents=True)

    with pytest.raises(ValueError, match=re.escape(str(target))):
        save(geo, str(target))

    assert not target.exists()


def test_saving_into_the_cache_directory_itself_is_allowed(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SCGRAPH_CACHE_DIR", str(tmp_path))
    geo = GeoGraph(graph=[{1: 1.0}, {0: 1.0}], nodes=[[0, 0], [0, 0.01]])

    geo.save_as_scgraph(str(tmp_path / "edited.scgraph"))
    geo.save_as_graphjson(str(tmp_path / "edited.graphjson"))

    assert (tmp_path / "edited.scgraph").is_file()
    assert (tmp_path / "edited.graphjson").is_file()
