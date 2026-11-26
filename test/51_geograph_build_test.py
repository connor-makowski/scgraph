import contextlib
import hashlib
import importlib.metadata
import importlib.util
import json
import logging
import os
import platform
import random
import re
import sqlite3
import struct
import subprocess
import sys
import sysconfig
import tempfile
import threading
import types
import typing
from array import array
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests
from helpers import build_main_roads, great_circle_km

from scgraph import GeoGraph, network_assembly, network_file, pipelines
from scgraph.helpers import osm
from scgraph.helpers.hilbert import get_hilbert_order
from scgraph.pipelines import eurostat_sea_lanes, osm_region_multimodal
from scgraph.pipelines import network_builder
from scgraph.pipelines.steps import step1_osm_sources
from scgraph.utils import has_cpp


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


# Two lines meeting at (0.01, 0) (lon, lat): 4 nodes, not read in Hilbert order
_LINES = [([0.02, 0, 0.01, 0, 0, 0], None), ([0.01, 0, 0.01, 0.01], None)]
_LINES_GPKG = _sea_gpkg(_LINES)
# The same lines, with the end of the first one moved from 0.02 to 0.03
_LINES_GPKG_WITH_A_MOVED_END = _sea_gpkg(
    [([0.03, 0, 0.01, 0, 0, 0], None), _LINES[1]]
)


def _polygons(*rings):
    return json.dumps(
        {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}}
            for ring in rings
        ]}
    ).encode()  # fmt: skip


# Railways (read by the multimodal pipeline only): a line along longitude 0.012, tagged
# `oneway=yes`; a branch that crosses the road at its node at (0, 0); a siding, left out;
# a second track along longitude 0.011, joined to the line by a crossover only. The two
# nodes of the second track have ids of the size of the planet's, 32,768 apart.
# Hubs of the multimodal pipeline: the ports below, "Near" served by rail; two airfields
# near the road, with a flight each way; "Far field", 28 km from the road, with a flight to
# "North field"; "Lone field", near the road, without a flight; a rail terminal between
# the road and the railway.
# Roads: from (-0.01, 0) to (0.01, 0) through (-0.004, 0.001), its nodes not read in
# Hilbert order, and a 2-node fragment at (0.005, 0.024) (lat, lon). Land west of
# longitude 0.03, an island at longitude 0.08 to 0.12, a sea lane from (0, 0.2) to
# (0, 0.3). Ports: "Near" (2.2 km from the road, 0.7 km from the fragment) and the open
# roadstead "Anchorage" (3.3 km of water to the road) are joined to the road; "Island"
# (5.5 km of water to any road), "Inland" (14 km from water) and "Far" (on the coast,
# 27 km from the road) are not
_FILES = {
    "/lines.gpkg": _LINES_GPKG,
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
<node id="11" version="1" lat="-0.008" lon="0.012"/>
<node id="12" version="1" lat="0" lon="0.012"/>
<node id="13" version="1" lat="0.008" lon="0.012"/>
<node id="14" version="1" lat="0.01" lon="0.015"/>
<way id="11" version="1"><nd ref="11"/><nd ref="12"/><nd ref="13"/><tag k="railway" v="rail"/><tag k="oneway" v="yes"/></way>
<way id="12" version="1"><nd ref="1"/><nd ref="12"/><tag k="railway" v="rail"/></way>
<way id="13" version="1"><nd ref="13"/><nd ref="14"/><tag k="railway" v="rail"/><tag k="service" v="siding"/></way>
<node id="12000000000" version="1" lat="-0.008" lon="0.011"/>
<node id="12000032768" version="1" lat="-0.004" lon="0.011"/>
<way id="14" version="1"><nd ref="12000000000"/><nd ref="12000032768"/><tag k="railway" v="rail"/></way>
<way id="15" version="1"><nd ref="11"/><nd ref="12000000000"/><tag k="railway" v="rail"/><tag k="service" v="crossover"/></way>
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
    "/ports.csv": b"""id,name,latitude,longitude,harbor_type,rail
1,Near,0,0.02,Coastal (Natural),1
2,Anchorage,0.01,0.06,Open Roadstead,0
3,Island,0,0.1,Coastal (Natural),0
4,Inland,0,-0.1,River (Natural),0
5,Far,0.25,0.02,Coastal (Natural),0
""",
    "/airports.csv": b"""id,code,name,type,latitude,longitude,country
100,XXNF,North field,medium_airport,0.012,-0.004,XX
101,XXSF,South field,medium_airport,-0.012,0.004,XX
102,XXFF,Far field,medium_airport,0.25,-0.004,XX
103,XXLF,Lone field,medium_airport,0.012,0.004,XX
""",
    "/flights.csv": b"""airport_a,airport_b,flights
100,101,120
100,102,150
""",
    "/rail_terminals.csv": b"""id,name,kind,latitude,longitude
200,Yard,freight terminal,0.008,0.006
""",
}


def _build_tangled_lines_gpkg():
    """80 lines through 60 points, drawn at random with a fixed seed, as the
    bytes of a GeoPackage of sea lanes. The lines share points, so a node has
    several edges: the order in which a build writes them shows in the file."""
    rng = random.Random(3)
    points = [[rng.uniform(0, 0.3), rng.uniform(0, 0.3)] for _ in range(60)]
    lines = [rng.sample(points, rng.randint(2, 6)) for _ in range(80)]
    return _sea_gpkg(
        [([x for point in line for x in point], None) for line in lines]
    )


_FILES["/tangled_lines.gpkg"] = _build_tangled_lines_gpkg()

# Where the local server has each source of `osm_region_multimodal`
_LOCAL_SOURCES = {
    "osm": "/{region}.osm",
    "land": "/land.geojson",
    "lakes": "/lakes.geojson",
    "rivers": "/rivers.geojson",
    "sea": "/sea.gpkg",
    "ports": "/ports.csv",
    "airports": "/airports.csv",
    "flights": "/flights.csv",
    "rail_terminals": "/rail_terminals.csv",
}


class _Source(BaseHTTPRequestHandler):
    """The files of _FILES at their paths, and 404 for any other path."""

    served = []

    def do_GET(self):
        self.served.append(self.path)
        if self.path not in _FILES:
            self.send_error(404)
            return
        data = _FILES[self.path]
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
def sea_lanes_are_the_local_lines(source, monkeypatch):
    """The `eurostat_sea_lanes` pipeline downloads /lines.gpkg of the local server
    in place of its online source. The fixture gives the URL of that file. The
    network of these two lines has 4 nodes."""
    url = f"{source}/lines.gpkg"
    monkeypatch.setitem(eurostat_sea_lanes.SOURCES["sea_lanes"], "url", url)
    return url


def test_build_geograph_downloads_and_builds_a_network_once(
    tmp_path, sea_lanes_are_the_local_lines
):
    first = GeoGraph.build_geograph("eurostat_sea_lanes", cache_dir=tmp_path)
    second = GeoGraph.build_geograph("eurostat_sea_lanes", cache_dir=tmp_path)

    assert len(first.nodes) == 4
    assert second.graph_object.graph == first.graph_object.graph
    assert _Source.served == ["/lines.gpkg"]  # the second call is local


def test_build_geograph_numbers_the_nodes_along_the_hilbert_curve(
    tmp_path, sea_lanes_are_the_local_lines
):
    # The lines of /lines.gpkg list their points in another order.
    geo = GeoGraph.build_geograph("eurostat_sea_lanes", cache_dir=tmp_path)

    assert get_hilbert_order(geo.nodes) == list(range(len(geo.nodes)))


# The header of a network file says what built the network. The tests below
# read the header of the network built from the local lines.
@pytest.fixture
def network_file_info(tmp_path, sea_lanes_are_the_local_lines):
    built_file = network_builder.build_network_file(
        "eurostat_sea_lanes", cache_dir=tmp_path
    )
    return GeoGraph.get_scgraph_info(built_file)


def test_a_network_file_records_what_built_it_and_from_which_sources(
    network_file_info, sea_lanes_are_the_local_lines
):
    source = eurostat_sea_lanes.SOURCES["sea_lanes"]
    first_line_of_pipeline_docstring = eurostat_sea_lanes.__doc__.split("\n")[0]

    assert network_file_info["pipeline"] == {
        "name": "eurostat_sea_lanes",
        "region": None,
        "version": eurostat_sea_lanes.PIPELINE_VERSION,
    }
    assert first_line_of_pipeline_docstring in network_file_info["description"]
    assert network_file_info["node_order"] == "hilbert"
    software = network_file_info["software"]
    assert software["backend"] == ("cpp" if has_cpp() else "python")
    assert software["platform"].startswith(sysconfig.get_platform())
    assert software["scgraph"] == importlib.metadata.version("scgraph")
    # The record has no version: this file does not date its data.
    assert network_file_info["sources"] == [
        {
            "name": "sea_lanes",
            "url": sea_lanes_are_the_local_lines,
            "sha256": hashlib.sha256(_LINES_GPKG).hexdigest(),
            "bytes": len(_LINES_GPKG),
            "credit": source["credit"],
            "license": "EUPL-1.2",
            "license_url": source["license_url"],
        }
    ]
    assert network_file_info["data_up_to"] is None  # no source has a version
    # The credit line to cite
    assert network_file_info["attribution"] == f"{source['credit']} (EUPL-1.2)"


# The math functions of the C library decide the last bit of a length. Two
# builds give the same file only with the same C library.
@pytest.mark.skipif(
    not platform.libc_ver()[0],
    reason="Python does not know the C library of this platform",
)
def test_network_file_names_the_c_library_of_the_platform(network_file_info):
    library, version = platform.libc_ver()

    assert network_file_info["software"]["platform"].endswith(
        f" {library} {version}"
    )


# The time of the download is the only clock time of a build. It stays out of
# the network file, so that the same sources give the same file.
def test_download_time_is_in_cache_json_and_not_in_the_network_file(
    tmp_path, network_file_info
):
    cache_json = tmp_path / "networks" / "eurostat_sea_lanes" / "cache.json"
    download_time = json.loads(cache_json.read_text())["downloaded"]

    assert download_time not in json.dumps(network_file_info)


def test_a_built_network_is_a_folder_with_cache_json_and_the_file_it_names(
    tmp_path, sea_lanes_are_the_local_lines
):
    built_file = Path(
        network_builder.build_network_file(
            "eurostat_sea_lanes", cache_dir=tmp_path
        )
    )

    folder = tmp_path / "networks" / "eurostat_sea_lanes"
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
    tmp_path, sea_lanes_are_the_local_lines
):
    GeoGraph.build_geograph("eurostat_sea_lanes", cache_dir=tmp_path)

    listing = {
        n["name"]: n for n in GeoGraph.list_buildable_geographs(tmp_path)
    }
    assert listing["eurostat_sea_lanes"]["cached"]
    assert not listing["osm_world_multimodal"]["cached"]


def test_list_buildable_geographs_does_not_count_a_network_without_its_file(
    tmp_path, sea_lanes_are_the_local_lines
):
    built_file = Path(
        network_builder.build_network_file(
            "eurostat_sea_lanes", cache_dir=tmp_path
        )
    )
    built_file.unlink()

    listing = {
        n["name"]: n for n in GeoGraph.list_buildable_geographs(tmp_path)
    }
    assert not listing["eurostat_sea_lanes"]["cached"]


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
    tmp_path, sea_lanes_are_the_local_lines, damage
):
    built_file = Path(
        network_builder.build_network_file(
            "eurostat_sea_lanes", cache_dir=tmp_path
        )
    )
    damage(built_file)

    geo = GeoGraph.build_geograph("eurostat_sea_lanes", cache_dir=tmp_path)

    assert len(geo.nodes) == 4
    assert _Source.served == ["/lines.gpkg"] * 2


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
    sea_lanes_are_the_local_lines,
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
            "eurostat_sea_lanes",
            cache_dir=tmp_path,
            local_files_only=local_files_only,
        )

    assert _Source.served == []


def test_scgraph_offline_loads_a_cached_network_without_a_request(
    tmp_path, sea_lanes_are_the_local_lines, monkeypatch
):
    GeoGraph.build_geograph("eurostat_sea_lanes", cache_dir=tmp_path)
    monkeypatch.setenv("SCGRAPH_OFFLINE", "1")

    geo = GeoGraph.build_geograph("eurostat_sea_lanes", cache_dir=tmp_path)

    assert len(geo.nodes) == 4
    assert _Source.served == ["/lines.gpkg"]  # the first build only


def test_local_files_only_false_builds_despite_scgraph_offline(
    tmp_path, sea_lanes_are_the_local_lines, monkeypatch
):
    monkeypatch.setenv("SCGRAPH_OFFLINE", "1")

    geo = GeoGraph.build_geograph(
        "eurostat_sea_lanes", cache_dir=tmp_path, local_files_only=False
    )

    assert len(geo.nodes) == 4
    assert _Source.served == ["/lines.gpkg"]


def test_refresh_is_refused_when_scgraph_offline_forbids_the_download(
    tmp_path, sea_lanes_are_the_local_lines, monkeypatch
):
    GeoGraph.build_geograph("eurostat_sea_lanes", cache_dir=tmp_path)
    monkeypatch.setenv("SCGRAPH_OFFLINE", "1")

    with pytest.raises(ValueError, match="SCGRAPH_OFFLINE"):
        GeoGraph.build_geograph(
            "eurostat_sea_lanes", cache_dir=tmp_path, refresh=True
        )

    assert _Source.served == ["/lines.gpkg"]  # the first build only


def test_local_files_only_refuses_a_cached_network_that_cannot_be_read(
    tmp_path, sea_lanes_are_the_local_lines
):
    built_file = Path(
        network_builder.build_network_file(
            "eurostat_sea_lanes", cache_dir=tmp_path
        )
    )
    _cut_short(built_file)

    with pytest.raises(ValueError, match="can't be read"):
        GeoGraph.build_geograph(
            "eurostat_sea_lanes", cache_dir=tmp_path, local_files_only=True
        )

    assert _Source.served == ["/lines.gpkg"]  # the first build only


def test_a_failed_download_leaves_the_cached_network_and_says_how_to_load_it(
    tmp_path, sea_lanes_are_the_local_lines, monkeypatch
):
    GeoGraph.build_geograph("eurostat_sea_lanes", cache_dir=tmp_path)
    # The server now answers 404 for the source.
    monkeypatch.delitem(_FILES, "/lines.gpkg")

    with pytest.raises(requests.HTTPError, match="local_files_only=True"):
        GeoGraph.build_geograph(
            "eurostat_sea_lanes", cache_dir=tmp_path, refresh=True
        )

    cached = GeoGraph.build_geograph(
        "eurostat_sea_lanes", cache_dir=tmp_path, local_files_only=True
    )
    assert len(cached.nodes) == 4


def _lines_pipeline(source, build=eurostat_sea_lanes.build, expected_km=2.22):
    """A pipeline module of one's own, cached as "lines". It builds the network of
    /lines.gpkg. Its validation case is the route between the ends of the first
    line, (0, 0) and (0, 0.02) (lat, lon): 0.02 degree of the equator, 2.22 km. The
    validation fails for another `expected_km`."""
    module = types.ModuleType("my_pipelines.lines")
    module.SOURCES = {
        "sea_lanes": {
            **eurostat_sea_lanes.SOURCES["sea_lanes"],
            "url": f"{source}/lines.gpkg",
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
    pipeline = _lines_pipeline(source)

    built_file = network_builder.build_network_file(
        pipeline=pipeline, cache_dir=tmp_path, run_validation_cases=True
    )

    cached = GeoGraph.build_geograph(
        pipeline=pipeline, cache_dir=tmp_path, local_files_only=True
    )
    assert len(cached.nodes) == 4
    assert built_file.startswith(str(tmp_path / "networks" / "lines"))


def test_build_file_does_not_cache_a_network_that_fails_its_validation(
    tmp_path, source
):
    # No route of this network is 100 km long
    pipeline = _lines_pipeline(source, expected_km=100)

    with pytest.raises(RuntimeError, match="validation failed for lines"):
        network_builder.build_network_file(
            pipeline=pipeline, cache_dir=tmp_path, run_validation_cases=True
        )

    assert not (tmp_path / "networks" / "lines").exists()


def test_a_failed_validation_leaves_the_network_of_an_earlier_build_cached(
    tmp_path, source, monkeypatch
):
    earlier_file = network_builder.build_network_file(
        pipeline=_lines_pipeline(source), cache_dir=tmp_path
    )
    earlier_bytes = Path(earlier_file).read_bytes()
    # The source has changed since, and the network it gives fails its validation
    monkeypatch.setitem(_FILES, "/lines.gpkg", _LINES_GPKG_WITH_A_MOVED_END)
    failing = _lines_pipeline(source, expected_km=100)

    with pytest.raises(RuntimeError, match="validation failed for lines"):
        network_builder.build_network_file(
            pipeline=failing,
            cache_dir=tmp_path,
            refresh=True,
            run_validation_cases=True,
        )

    cached_file = network_builder.build_network_file(
        pipeline=failing, cache_dir=tmp_path, local_files_only=True
    )
    assert cached_file == earlier_file
    assert Path(cached_file).read_bytes() == earlier_bytes


def test_build_geograph_refuses_a_network_that_fails_its_validation(
    tmp_path, source
):
    # No route of this network is 100 km long
    pipeline = _lines_pipeline(source, expected_km=100)

    with pytest.raises(RuntimeError, match="validation failed for lines"):
        GeoGraph.build_geograph(
            pipeline=pipeline, cache_dir=tmp_path, run_validation_cases=True
        )


def test_validate_checks_a_cached_network_without_building_it_again(
    tmp_path, source
):
    network_builder.build_network_file(
        pipeline=_lines_pipeline(source), cache_dir=tmp_path
    )
    # The same pipeline, with a case that its network fails
    failing = _lines_pipeline(source, expected_km=100)

    with pytest.raises(RuntimeError, match="validation failed for lines"):
        network_builder.build_network_file(
            pipeline=failing,
            cache_dir=tmp_path,
            run_validation_cases=True,
            local_files_only=True,
        )

    assert _Source.served == ["/lines.gpkg"]  # the first build only


def _fail_to_build(files):
    raise RuntimeError("build failed")


def test_a_failed_build_keeps_its_sources_for_the_next_build(tmp_path, source):
    broken = _lines_pipeline(source, build=_fail_to_build)
    with pytest.raises(RuntimeError, match="build failed"):
        GeoGraph.build_geograph(pipeline=broken, cache_dir=tmp_path)

    repaired = _lines_pipeline(source)
    geo = GeoGraph.build_geograph(pipeline=repaired, cache_dir=tmp_path)

    assert len(geo.nodes) == 4
    assert _Source.served == ["/lines.gpkg"]  # downloaded once


def test_refresh_downloads_the_sources_again_after_a_failed_build(
    tmp_path, source
):
    broken = _lines_pipeline(source, build=_fail_to_build)
    with pytest.raises(RuntimeError, match="build failed"):
        GeoGraph.build_geograph(pipeline=broken, cache_dir=tmp_path)

    repaired = _lines_pipeline(source)
    GeoGraph.build_geograph(pipeline=repaired, cache_dir=tmp_path, refresh=True)

    assert _Source.served == ["/lines.gpkg"] * 2


# After an upgrade, the files of a failed build may follow the old rules. The
# next build starts from an empty work folder and downloads the sources again.
def test_a_build_of_the_next_pipeline_version_does_not_resume_a_failed_build(
    tmp_path, source
):
    broken = _lines_pipeline(source, build=_fail_to_build)
    with pytest.raises(RuntimeError, match="build failed"):
        GeoGraph.build_geograph(pipeline=broken, cache_dir=tmp_path)

    next_version = _lines_pipeline(source)
    next_version.PIPELINE_VERSION = 2
    GeoGraph.build_geograph(pipeline=next_version, cache_dir=tmp_path)

    assert _Source.served == ["/lines.gpkg"] * 2


def test_a_build_refuses_a_work_folder_of_the_caller_that_another_version_left(
    tmp_path, source
):
    broken = _lines_pipeline(source, build=_fail_to_build)
    work_dir = tmp_path / "work"
    with pytest.raises(RuntimeError, match="build failed"):
        network_builder.build_network_file(
            pipeline=broken, cache_dir=tmp_path / "cache", work_dir=work_dir
        )

    next_version = _lines_pipeline(source)
    next_version.PIPELINE_VERSION = 2
    with pytest.raises(RuntimeError, match="refresh=True"):
        network_builder.build_network_file(
            pipeline=next_version,
            cache_dir=tmp_path / "cache",
            work_dir=work_dir,
        )


def test_a_build_keeps_its_files_in_the_work_folder_that_the_caller_gives(
    tmp_path, source
):
    def build_with_a_step_file(files, *, work_dir=None):
        Path(work_dir, "step_file").touch()
        return eurostat_sea_lanes.build(files)

    pipeline = _lines_pipeline(source, build=build_with_a_step_file)
    work_dir = tmp_path / "work"

    network_builder.build_network_file(
        pipeline=pipeline, cache_dir=tmp_path / "cache", work_dir=work_dir
    )

    # The runner removes its own work folder after a build, not the caller's
    assert (work_dir / "step_file").is_file()


# /dev/shm is a disk in memory on Linux. A file cannot be renamed from one disk
# to another: it must be copied.
@pytest.mark.skipif(
    not Path("/dev/shm").is_dir()
    or Path("/dev/shm").stat().st_dev
    == Path(tempfile.gettempdir()).stat().st_dev,
    reason="needs a second disk at /dev/shm",
)
def test_a_build_works_in_a_folder_on_another_disk_than_the_cache(
    tmp_path, source
):
    with tempfile.TemporaryDirectory(dir="/dev/shm") as work_dir:
        network_builder.build_network_file(
            pipeline=_lines_pipeline(source),
            cache_dir=tmp_path,
            work_dir=work_dir,
        )

    cached = GeoGraph.build_geograph(
        pipeline=_lines_pipeline(source),
        cache_dir=tmp_path,
        local_files_only=True,
    )
    assert len(cached.nodes) == 4


# A cached network is built again when its pipeline has another
# PIPELINE_VERSION. The module of the next version has the same name and the
# same source: only its version differs.
def test_build_geograph_builds_again_for_another_pipeline_version(
    tmp_path, source
):
    GeoGraph.build_geograph(
        pipeline=_lines_pipeline(source), cache_dir=tmp_path
    )
    next_version = _lines_pipeline(source)
    next_version.PIPELINE_VERSION = 2

    GeoGraph.build_geograph(pipeline=next_version, cache_dir=tmp_path)
    GeoGraph.build_geograph(pipeline=next_version, cache_dir=tmp_path)

    assert _Source.served == ["/lines.gpkg"] * 2  # once for each version


def test_local_files_only_loads_a_network_of_another_pipeline_version(
    tmp_path, source
):
    GeoGraph.build_geograph(
        pipeline=_lines_pipeline(source), cache_dir=tmp_path
    )
    next_version = _lines_pipeline(source)
    next_version.PIPELINE_VERSION = 2

    # The warning names the two versions, and points at the line of the caller.
    with pytest.warns(
        UserWarning, match="pipeline version 1, now 2;"
    ) as caught:
        geo = GeoGraph.build_geograph(
            pipeline=next_version, cache_dir=tmp_path, local_files_only=True
        )

    (warning,) = [w for w in caught if "pipeline version" in str(w.message)]
    assert warning.filename == __file__
    assert len(geo.nodes) == 4
    assert _Source.served == ["/lines.gpkg"]  # the first build only


def test_a_new_build_replaces_the_network_file_of_the_earlier_build(
    tmp_path, source, monkeypatch
):
    pipeline = _lines_pipeline(source)
    earlier_file = Path(
        network_builder.build_network_file(
            pipeline=pipeline, cache_dir=tmp_path
        )
    )
    # The source has changed since. The new network has another content,
    # so its file has another name.
    monkeypatch.setitem(_FILES, "/lines.gpkg", _LINES_GPKG_WITH_A_MOVED_END)

    new_file = Path(
        network_builder.build_network_file(
            pipeline=pipeline, cache_dir=tmp_path, refresh=True
        )
    )

    folder = tmp_path / "networks" / "lines"
    assert new_file != earlier_file
    assert {p.name for p in folder.iterdir()} == {"cache.json", new_file.name}


def test_a_pipeline_module_gives_the_last_part_of_its_name_to_its_network(
    tmp_path, source
):
    pipeline = _lines_pipeline(source)  # the module my_pipelines.lines

    geo = GeoGraph.build_geograph(pipeline=pipeline, cache_dir=tmp_path)

    assert geo.metadata["pipeline"]["name"] == "lines"


# A pipeline of one's own may have classes that scgraph does not know. Here the
# two lines of /lines.gpkg are canals: every edge has row 0 of the table of the
# pipeline.
def test_the_file_of_a_pipeline_with_its_own_classes_table_names_those_classes(
    tmp_path, source
):
    def build_canals(files):
        arrays = eurostat_sea_lanes.build_sea_lane_arrays(files)
        arrays["edge_class_ids"] = array(
            "B", bytes(len(arrays["edge_destination_node_ids"]))
        )
        return arrays, [{"name": None}]

    pipeline = _lines_pipeline(source, build=build_canals)
    pipeline.CLASSES = {"canal": "inland_water"}

    file = network_builder.build_network_file(
        pipeline=pipeline, cache_dir=tmp_path
    )

    canal = {"name": "canal", "edge_mode": "inland_water"}
    assert GeoGraph.get_scgraph_info(file)["classes"] == [canal]


def test_a_pipeline_module_named_like_a_built_in_network_is_refused(tmp_path):
    # Its network would take the place of the network of scgraph in the cache.
    namesake = types.ModuleType("my_pipelines.eurostat_sea_lanes")

    with pytest.raises(ValueError, match="Invalid pipeline module name"):
        GeoGraph.build_geograph(pipeline=namesake, cache_dir=tmp_path)


# The same sources must give the same network file in every process, so
# that a file can be checked against another build. The tests below build in
# child processes, as separate users do. A child takes the URL of the local
# server, its cache folder, the name of the network, its region or "", the
# backend ("pure python" hides the C++ extension from the child), and where
# the local server has each source of `osm_region_multimodal`.
_BUILD_IN_A_CHILD_PROCESS = """
import sys
import json
server, cache_dir, name, region, backend, local_sources = sys.argv[1:]
if backend == "pure python":
    sys.modules["scgraph.cpp"] = None  # importing the extension now fails
from scgraph import GeoGraph
from scgraph.pipelines import eurostat_sea_lanes, osm_region_multimodal
eurostat_sea_lanes.SOURCES["sea_lanes"]["url"] = server + "/tangled_lines.gpkg"
for source, path in json.loads(local_sources).items():
    osm_region_multimodal.SOURCES[source] = {
        **osm_region_multimodal.SOURCES[source], "url": server + path
    }
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
            json.dumps(_LOCAL_SOURCES),
        ],
        env={**os.environ, "PYTHONHASHSEED": hash_seed},
        check=True,
        timeout=120,
        cwd=cache_dir,  # so that the child imports the installed scgraph
    )
    folder = cache_dir / "networks" / name / (region or "")
    return folder / json.loads((folder / "cache.json").read_text())["file"]


# The two kinds of pipeline. eurostat_sea_lanes returns a GeoGraph, which scgraph
# then writes to a network file. osm_region_multimodal returns the arrays of the
# network file: its region "roads" is the file /roads.osm of the local server.
_NETWORKS_OF_BOTH_KINDS = [
    pytest.param("eurostat_sea_lanes", None, id="eurostat_sea_lanes"),
    pytest.param(
        "osm_region_multimodal",
        "roads",
        id="osm_region_multimodal",
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
# edges with the same lengths. The order of the edges of a node may differ.
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
    assert list(pure_python.external_node_ids) == list(
        installed.external_node_ids
    )
    assert pure_python.graph_object.graph == installed.graph_object.graph


def test_build_geograph_names_a_region_geofabrik_does_not_have(
    tmp_path, source, monkeypatch
):
    pytest.importorskip("osmium")  # checked before the download
    for name, path in _LOCAL_SOURCES.items():
        monkeypatch.setitem(
            osm_region_multimodal.SOURCES,
            name,
            {**osm_region_multimodal.SOURCES[name], "url": source + path},
        )
    # The local server has no file /nowhere.osm
    with pytest.raises(ValueError, match="The region 'nowhere' has no source"):
        GeoGraph.build_geograph(
            "osm_region_multimodal", region="nowhere", cache_dir=str(tmp_path)
        )
    # The small sources were downloaded before the extract. No network is built.
    kinds = {
        entry["kind"] for entry in GeoGraph.list_geograph_cache(str(tmp_path))
    }
    assert "built" not in kinds


# The strait has roads and ferries, and no railway.
def test_a_region_without_a_railway_builds_without_rail_nodes(
    tmp_path, source, monkeypatch
):
    pytest.importorskip("osmium")
    for name, path in _LOCAL_SOURCES.items():
        monkeypatch.setitem(
            osm_region_multimodal.SOURCES,
            name,
            {**osm_region_multimodal.SOURCES[name], "url": source + path},
        )

    strait = GeoGraph.build_geograph(
        "osm_region_multimodal", region="strait", cache_dir=tmp_path
    )

    assert _points_of(strait, "rail") == []
    # The road nodes 1, 2, 3, 5 and 4 of the strait. Node 2 stays a node: it
    # joins a road to a ferry, which are two classes. Ferry 6 joins the nodes 1
    # and 2, as road 1 does. Each of its two directions is split at node 41.
    assert _points_of(strait, "road") == [
        [0, 0],
        [0, 0.01],
        [0, 0.06],
        [0, 0.065],
        [0, 0.07],
        [0.01, 0.005],
        [0.01, 0.005],
    ]


# From the command line, a network is built into the cache without being loaded, and
# the path of its file is printed; build_geograph then loads that file
def test_build_command_builds_the_file_build_geograph_loads(
    tmp_path, source, monkeypatch, capsys
):
    monkeypatch.setitem(
        eurostat_sea_lanes.SOURCES["sea_lanes"], "url", f"{source}/lines.gpkg"
    )
    network_builder.main(["eurostat_sea_lanes", "--cache-dir", str(tmp_path)])
    path = capsys.readouterr().out.strip()
    folder = tmp_path / "networks" / "eurostat_sea_lanes"
    assert path == str(
        folder / json.loads((folder / "cache.json").read_text())["file"]
    )
    geo = GeoGraph.build_geograph("eurostat_sea_lanes", cache_dir=str(tmp_path))
    assert _Source.served == ["/lines.gpkg"]  # loaded, not built again
    assert len(geo.nodes) == 4


# A source's own download hook is called for that source only, and its record says
# what identifies the source, in place of the downloaded file's sha256 and size
def test_build_geograph_calls_the_download_hook_of_a_source(tmp_path):
    calls = []

    def stream(url, filename):
        calls.append(url)
        with open(filename, "wb") as file:
            file.write(_LINES_GPKG)
        return {"bytes": 10**11, "md5": "0" * 32}

    module = types.ModuleType("my_pipelines.streamed")
    url = "https://planet.example/lines.gpkg"
    module.SOURCES = {
        "sea_lanes": {
            **eurostat_sea_lanes.SOURCES["sea_lanes"],
            "url": url,
            "download": stream,
        }
    }
    module.PIPELINE_VERSION, module.build = 1, eurostat_sea_lanes.build
    module.download = lambda url, filename: pytest.fail("module's hook called")
    geo = GeoGraph.build_geograph(pipeline=module, cache_dir=str(tmp_path))
    (record,) = geo.metadata["sources"]
    assert calls == [url] and "sha256" not in record
    assert (record["bytes"], record["md5"]) == (10**11, "0" * 32)


def test_list_buildable_geographs_matches_the_names_build_geograph_takes(
    tmp_path,
):
    listing = GeoGraph.list_buildable_geographs(str(tmp_path))
    names = [n["name"] for n in listing]
    annotation = typing.get_type_hints(GeoGraph.build_geograph)["name"]
    literal = typing.get_args(annotation)[0]  # Literal[...] | None
    assert (
        names
        == list(pipelines.BUILDABLE_NETWORKS)
        == list(typing.get_args(literal))
    )


# Two roads on the two sides of a strait, and five ferries. Each node is
# (latitude, longitude). Road 1 joins nodes 1 and 2 on the west side. Road 2
# runs 3, 5, 4 on the east side.
# - Ferry 3 runs 10, 11, 3. Node 10 is 0.6 km from node 2, and node 3 is on
#   road 2. Its route is 6.7 km long.
# - Ferry 4 runs from 0.1 km off node 2 to 0.1 km off node 3 in 5.3 km. It is
#   closed to cars.
# - Ferry 5 ends 0.2 km from node 3 and starts at node 30, 3.6 km from the
#   closest road node. Its route is 4.2 km long.
# - Ferry 6 runs from 0.1 km off node 1 to 0.1 km off node 2 in 2.3 km. Road 1
#   joins the same nodes in 1.1 km.
# - Ferry 7 is a shuttle train for cars (`route=shuttle_train`, as in the
#   Channel Tunnel), read as a ferry. It runs from node 5, in the middle of
#   road 2, to node 50. Node 50 is 0.6 km from node 1.
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
    7: ([5, 50], 'k="route" v="shuttle_train"'),
}


def _build_strait_osm():
    """The strait as the bytes of an OSM file, its nodes sorted by id."""
    lines = [
        f'<node id="{node}" version="1" lat="{latitude}" lon="{longitude}"/>'
        for node, (latitude, longitude) in sorted(_STRAIT_NODES.items())
    ]
    for way, (nodes, tags) in _STRAIT_WAYS.items():
        refs = "".join(f'<nd ref="{node}"/>' for node in nodes)
        lines.append(f'<way id="{way}" version="1">{refs}<tag {tags}/></way>')
    return ('<osm version="0.6">' + "\n".join(lines) + "</osm>").encode()


_FILES["/strait.osm"] = _build_strait_osm()


def _main_roads_pipeline(server):
    """A pipeline module of one's own, cached as "main_roads". It builds the main
    roads and the vehicle ferries of the file /{region}.osm of the local server,
    with the steps of `osm_region_multimodal` (`helpers.build_main_roads`). Its
    select functions give no class."""
    module = types.ModuleType("my_pipelines.main_roads")
    module.SOURCES = {
        "roads": {
            **step1_osm_sources.GEOFABRIK,
            "url": f"{server}/{{region}}.osm",
        }
    }
    module.PIPELINE_VERSION, module.build = 1, build_main_roads
    module.download = step1_osm_sources.download
    return module


def _strait_km(*nodes):
    """The length of the line through these nodes of the strait."""
    places = [_STRAIT_NODES[node] for node in nodes]
    return sum(great_circle_km(a, b) for a, b in zip(places, places[1:]))


@pytest.fixture(scope="module")
def strait_network(tmp_path_factory):
    """The network that the pipeline of main roads builds from the strait. The
    local server stands for Geofabrik: the region "strait" is its file
    /strait.osm.

    The build keeps the nodes 1, 3, 4 and 5. It contracts node 2, which only
    joins road 1 to ferry 3.
    """
    pytest.importorskip("osmium")
    with _local_server() as server:
        return GeoGraph.build_geograph(
            pipeline=_main_roads_pipeline(server),
            region="strait",
            cache_dir=tmp_path_factory.mktemp("strait"),
        )


def _by_osm_ids(geograph, rows):
    """The values of `rows`, a list of one dict per node, as one dict. Its
    keys are the pairs (OSM id of the origin, OSM id of the destination)."""
    osm_ids = list(geograph.external_node_ids)
    return {
        (osm_ids[u], osm_ids[v]): value
        for u, row in enumerate(rows)
        for v, value in row.items()
    }


def test_a_car_ferry_joins_the_road_nodes_closest_its_two_ends(strait_network):
    edges = _by_osm_ids(strait_network, strait_network.graph_object.graph)
    shapes = _by_osm_ids(strait_network, strait_network.intermediate_nodes)

    # From node 1: road 1 to node 2, then ferry 3. The ferry counts for the
    # length of its own route, from node 10 to node 3. A build that kept
    # ferry 4, 5 or 6 by mistake would give another length. Ferry 4 is closed
    # to cars, and ferry 5 starts far from any road: both are shorter than
    # ferry 3. Ferry 6 is longer than road 1, which joins the same nodes.
    assert edges[(1, 3)] == pytest.approx(
        _strait_km(1, 2) + _strait_km(10, 11, 3)
    )
    # After node 2, the drawing goes to the start of ferry 3, then along it.
    assert shapes[(1, 3)] == [list(_STRAIT_NODES[node]) for node in (2, 10, 11)]


def test_a_ferry_that_starts_inside_a_road_cuts_the_road_at_that_node(
    strait_network,
):
    edges = _by_osm_ids(strait_network, strait_network.graph_object.graph)

    # Node 5 is a middle point of road 2 and the start of ferry 7. The ferry
    # joins it to node 1, the road node closest its other end.
    assert edges[(5, 1)] == pytest.approx(_strait_km(5, 50))
    assert edges[(3, 5)] == pytest.approx(_strait_km(3, 5))


# With a work folder, the build keeps the pieces of the ways in files and
# not in memory.
def test_ferries_are_attached_the_same_way_with_a_work_folder(tmp_path):
    pytest.importorskip("osmium")
    strait_file = tmp_path / "strait.osm"
    strait_file.write_bytes(_FILES["/strait.osm"])

    built_in_memory = build_main_roads({"roads": str(strait_file)})
    built_in_files = build_main_roads(
        {"roads": str(strait_file)}, work_dir=str(tmp_path / "work")
    )

    assert built_in_files == built_in_memory


# The select functions of `osm_region_multimodal` give the class of each way.
# The fixture of that pipeline has no ferry. So this test runs the two steps
# of a build that cut the ways of the strait and store them.
def test_a_ferry_edge_and_a_shuttle_train_edge_have_their_own_classes(tmp_path):
    pytest.importorskip("osmium")
    strait_file = tmp_path / "strait.osm"
    strait_file.write_bytes(_FILES["/strait.osm"])
    selects = {
        "road": {
            "ways": osm_region_multimodal.select_main_roads_with_class,
            "ferries": osm_region_multimodal.select_vehicle_ferries_with_class,
        }
    }

    pieces = osm.build_way_pieces(
        str(strait_file), selects, ("highway", "route"), max_km_between_nodes=2
    )
    graph = network_assembly.build_graph_from_pieces(pieces["road"])

    ids, node_first_edge_ids = (
        graph["external_node_ids"],
        graph["node_first_edge_ids"],
    )
    class_names = {
        (ids[u], ids[graph["edge_destination_node_ids"][edge]]): list(
            pipelines.CLASSES
        )[graph["edge_class_ids"][edge]]
        for u in range(len(ids))
        for edge in range(node_first_edge_ids[u], node_first_edge_ids[u + 1])
    }
    # Road 1 joins the nodes 1 and 2. Ferry 3 joins the nodes 2 and 3. The
    # shuttle train 7 joins the nodes 5 and 1.
    assert class_names[1, 2] == "primary"
    assert class_names[2, 3] == "ferry"
    assert class_names[5, 1] == "shuttle_train"


def _build_coast_network(tmp_path, region="roads"):
    """The network that `osm_region_multimodal` builds from the coast that the
    comment above `_FILES` describes: the road, the railways, the sea lane and
    the hubs. The local server stands for every source. The OSM file is served
    as a Geofabrik extract: a PBF whose header gives the time of its data. The
    region "roads" is the file /roads.osm.pbf. Another region has the roads and
    the railways of its own file.
    """
    pipeline = osm_region_multimodal
    paths = {**_LOCAL_SOURCES, "osm": "/{region}.osm.pbf"}
    osmium = pytest.importorskip("osmium")
    xml, pbf = tmp_path / f"{region}.osm", tmp_path / f"{region}.osm.pbf"
    xml.write_bytes(_FILES[f"/{region}.osm"])
    header = osmium.io.Header()
    header.set("osmosis_replication_timestamp", "2026-11-06T20:21:43Z")
    with osmium.SimpleWriter(str(pbf), header=header) as writer:
        for entity in osmium.FileProcessor(str(xml)):
            writer.add(entity)
    with _local_server() as server, pytest.MonkeyPatch.context() as patch:
        patch.setitem(_FILES, f"/{region}.osm.pbf", pbf.read_bytes())
        for name, path in paths.items():
            patch.setitem(
                pipeline.SOURCES,
                name,
                {**pipeline.SOURCES[name], "url": server + path},
            )
        return GeoGraph.build_geograph(
            "osm_region_multimodal", region=region, cache_dir=tmp_path
        )


@pytest.fixture(scope="module")
def coast_cache(tmp_path_factory):
    """The cache folder that holds the network of the coast, for the region
    "roads"."""
    cache_dir = tmp_path_factory.mktemp("coast")
    _build_coast_network(cache_dir)
    return cache_dir


@pytest.fixture(scope="module")
def coast_network(coast_cache):
    return GeoGraph.build_geograph(
        "osm_region_multimodal",
        region="roads",
        cache_dir=coast_cache,
        local_files_only=True,
    )


# The select functions of the pipeline of main roads give no class.
def test_a_pipeline_whose_selects_give_no_class_builds_no_edge_classes(
    tmp_path, source
):
    pytest.importorskip("osmium")
    path = network_builder.build_network_file(
        pipeline=_main_roads_pipeline(source),
        region="strait",
        cache_dir=tmp_path,
    )

    arrays, metadata = network_file.read(path)

    assert "edge_class_ids" not in arrays
    assert "classes" not in metadata


def test_nodes_are_stored_by_node_mode_and_each_node_mode_names_its_source(
    coast_network,
):
    # The roads follow turn restrictions: a road junction may have several nodes
    assert coast_network.node_modes == [
        {"name": "road", "source": "osm", "has_turn_restrictions": True},
        {"name": "rail", "source": "osm"},
        {"name": "sea", "source": "sea"},
        {"name": "port", "source": "ports"},
        {"name": "airport", "source": "airports"},
        {"name": "rail_terminal", "source": "rail_terminals"},
    ]
    # 3 road nodes, 4 rail nodes, the 2 ends of the sea lane, 2 ports, 2 airports
    # and 1 rail terminal
    assert list(coast_network.node_mode_ids) == [0] * 3 + [1] * 4 + [
        2,
        2,
        3,
        3,
        4,
        4,
        5,
    ]


def test_build_geograph_loads_only_the_modes_asked(coast_cache):
    roads = GeoGraph.build_geograph(
        "osm_region_multimodal",
        region="roads",
        cache_dir=coast_cache,
        local_files_only=True,
        node_modes=["road"],
        lazy=True,  # the modes also reach a network that is loaded at its first use
    )

    # The 3 road nodes of the coast, and no hub
    assert _get_node_mode_names(roads) == ["road", "road", "road"]


def test_a_road_fragment_apart_from_the_main_road_is_left_out(coast_network):
    # The fragment at (0.005, 0.024) is not among them.
    assert _points_of(coast_network, "road") == [[-0.01, 0], [0, 0], [0.01, 0]]


def test_a_route_from_the_road_to_the_sea_lane_passes_through_a_port(
    coast_network,
):
    # The destination is at sea. Without the modes, a point of a query snaps to
    # a road node, because the network has roads.
    route = coast_network.get_shortest_path(
        origin_node={"latitude": -0.01, "longitude": 0},
        destination_node={"latitude": 0, "longitude": 0.3},
        output_coordinate_path="list_of_lists",
        snap_to_node_modes=["road", "sea"],
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


def test_a_build_logs_the_counts_of_each_step(tmp_path, caplog):
    # The logger scgraph.pipelines leaves out the load that follows the build
    with caplog.at_level(logging.DEBUG, logger="scgraph.pipelines"):
        _build_coast_network(tmp_path)

    counts = {
        record.scgraph["step"]: {
            key: value
            for key, value in record.scgraph.items()
            if key not in ("step", "duration_ms")
        }
        for record in caplog.records
        if hasattr(record, "scgraph")
    }
    assert counts == {
        # Roads: the main road in 2 pieces and the fragment. Railways: the line
        # in 2 pieces, the branch, the second track and the crossover.
        "read and cut the ways": {"pieces": 8},
        "attach the ferries": {"edges": 0},
        # The coast has no turn restriction
        "read the turn restrictions": {
            "turn_restrictions": 0,
            "forbidden_turns": 0,
        },
        # The 2 ends of the sea lane
        "read the sea lanes": {"nodes": 2},
        # 5 ports, 4 airports and 1 rail terminal. 5 of them reach two networks.
        "join at the hubs": {
            "hubs": 10,
            "port": 2,
            "airport": 2,
            "rail_terminal": 1,
        },
        # 5 road nodes, 6 rail nodes, 2 sea nodes and 5 hubs. The road fragment
        # of 2 nodes and 2 edges is left out.
        "keep the strongly connected components": {
            "nodes": 18,
            "edges": 38,
            "kept_nodes": 16,
            "kept_edges": 36,
        },
        # Two rail nodes only join two tracks: the south end of the line and
        # the south end of the second track. Their chains are contracted.
        "contract the chains": {
            "nodes": 16,
            "edges": 36,
            "kept_nodes": 14,
            "kept_edges": 32,
        },
    }


# Three roads of 1.1 km meet at node 1: way 1 comes from node 2 in the south,
# way 2 goes to node 4 in the north, and way 3 goes to node 7 in the west. A
# turn restriction forbids the left turn at node 1, from way 1 into way 3. The
# hubs of the coast are around these roads, and the port "Near" has the id 1 in
# its own table.
_FILES["/t-junction.osm"] = b"""<osm version="0.6">
<node id="1" version="1" lat="0" lon="0"/>
<node id="2" version="1" lat="-0.01" lon="0"/>
<node id="4" version="1" lat="0.01" lon="0"/>
<node id="7" version="1" lat="0" lon="-0.01"/>
<way id="1" version="1"><nd ref="2"/><nd ref="1"/><tag k="highway" v="primary"/></way>
<way id="2" version="1"><nd ref="1"/><nd ref="4"/><tag k="highway" v="primary"/></way>
<way id="3" version="1"><nd ref="1"/><nd ref="7"/><tag k="highway" v="primary"/></way>
<relation id="1" version="1"><member type="way" ref="1" role="from"/><member type="node" ref="1" role="via"/><member type="way" ref="3" role="to"/><tag k="type" v="restriction"/><tag k="restriction" v="no_left_turn"/></relation>
</osm>"""


def test_a_route_makes_no_turn_that_a_turn_restriction_forbids(tmp_path):
    network = _build_coast_network(tmp_path, "t-junction")

    route = network.get_shortest_path(
        origin_node={"latitude": -0.01, "longitude": 0},  # node 2
        destination_node={"latitude": 0, "longitude": -0.01},  # node 7
    )

    # The route goes on to node 4, turns back there and passes node 1 again:
    # 4 roads of 1.1 km. With the forbidden turn, it would be 2 roads long.
    assert route["length"] == pytest.approx(
        4 * great_circle_km([0, 0], [0.01, 0])
    )


def test_each_source_is_recorded_with_the_version_of_its_data(coast_network):
    versions = {
        source["name"]: source.get("version")
        for source in coast_network.metadata["sources"]
    }

    assert versions == {
        "osm": "2026-11-06T20:21:43Z",  # the time in the header of the PBF
        "land": "5.1.2",  # the release of Natural Earth that the pipeline names
        "lakes": "5.1.2",
        "rivers": "5.1.2",
        "sea": None,
        # A table kept with scgraph says which copy of its source made it
        "ports": "UpdatedPub150.csv, SHA-256 315644f1e7796629",
        "airports": "airports.csv at commit 1cdbf9cbed1e47bed8f115ec173b91aeb999e44f",
        "flights": "flights of 2021: OpenSky v21.12; T-100 and Eurostat read on 2026-11-17",
        "rail_terminals": "query of 2026-11-16",
    }


def _get_node_mode_names(network):
    names = [mode["name"] for mode in network.node_modes]
    return [names[row] for row in network.node_mode_ids]


def _points_of(network, mode):
    return sorted(
        list(point)
        for point, name in zip(network.nodes, _get_node_mode_names(network))
        if name == mode
    )


# (0, 0) is a node of the road and of the railway branch in the OSM file. The two
# networks must stay apart there: a route changes mode only at a hub. So each
# network has its own node at (0, 0), and no edge joins a road node to a rail
# node.
def test_roads_and_railways_stay_apart_at_a_level_crossing(coast_network):
    node_modes = _get_node_mode_names(coast_network)

    assert [0, 0] in _points_of(coast_network, "road")
    assert [0, 0] in _points_of(coast_network, "rail")
    assert not any(
        {node_modes[u], node_modes[v]} == {"road", "rail"}
        for u, edges in enumerate(coast_network.graph_object.graph)
        for v in edges
    )


def test_a_railway_is_read_both_ways_and_without_its_sidings(
    coast_network,
):
    # The line's south end leads, through the crossover, to the end of the
    # second track at (-0.004, 0.011). Without the crossover, the second track
    # would be an island, left out. Read one way, the line tagged `oneway=yes`
    # would lose its two ends and the second track. The siding would add
    # (0.01, 0.015).
    assert _points_of(coast_network, "rail") == [
        [-0.004, 0.011],
        [0, 0],
        [0, 0.012],
        [0.008, 0.012],
    ]


def test_each_hub_joins_the_modes_it_serves(coast_network):
    node_modes = _get_node_mode_names(coast_network)
    ids = list(coast_network.external_node_ids)

    reached = {
        (node_modes[u], ids[u]): sorted({node_modes[v] for v in edges})
        for u, edges in enumerate(coast_network.graph_object.graph)
        if node_modes[u] in ("port", "airport", "rail_terminal")
    }

    # Each hub keeps the id of its table; an airport reaches the other by its
    # flight. The ports Island and Far are too far from the road, and Inland is
    # too far from water: the three stay out. The port Anchorage has no rail
    # flag, so no rail connector. Far field has no road, so its flight is
    # dropped. Lone field has no flight, so it reaches one mode only. Both stay
    # out.
    assert reached == {
        ("port", 1): ["rail", "road", "sea"],
        ("port", 2): ["road", "sea"],
        ("airport", 100): ["airport", "road"],
        ("airport", 101): ["airport", "road"],
        ("rail_terminal", 200): ["rail", "road"],
    }


# The test reads the classes from the network file. The roads of the coast
# are primary roads. Its railways have no `usage` tag, and its sea lane is
# outside a passage.
def test_each_edge_has_the_class_of_its_way_its_connector_or_its_flight(
    coast_cache,
):
    path = network_builder.build_network_file(
        "osm_region_multimodal",
        region="roads",
        cache_dir=coast_cache,
        local_files_only=True,
    )

    arrays, metadata = network_file.read(path)

    node_modes = [
        metadata["node_modes"][row]["name"]
        for row in network_file.build_node_mode_ids(metadata["node_modes"])
    ]
    classes = {}  # the modes of the two ends of an edge -> the classes found
    for u, mode in enumerate(node_modes):
        for edge in range(
            arrays["node_first_edge_ids"][u],
            arrays["node_first_edge_ids"][u + 1],
        ):
            ends = tuple(
                sorted(
                    (
                        mode,
                        node_modes[arrays["edge_destination_node_ids"][edge]],
                    )
                )
            )
            class_row = metadata["classes"][arrays["edge_class_ids"][edge]]
            classes.setdefault(ends, set()).add(class_row["name"])
    assert classes == {
        ("road", "road"): {"primary"},
        ("rail", "rail"): {"rail_other"},
        ("sea", "sea"): {"open_sea"},
        ("airport", "airport"): {"flight"},
        ("airport", "road"): {"road_connector"},
        ("port", "road"): {"road_connector"},
        ("rail_terminal", "road"): {"road_connector"},
        ("port", "rail"): {"rail_connector"},
        ("rail", "rail_terminal"): {"rail_connector"},
        ("port", "sea"): {"sea_connector"},
    }
    # A row of `classes` also gives the mode of the edges of its class.
    assert {"name": "flight", "edge_mode": "air"} in metadata["classes"]


def test_a_query_point_at_sea_snaps_to_a_road_node_of_a_multimodal_network(
    coast_network,
):
    # The destination is on the sea lane, 0.3 degree east of the road.
    route = coast_network.get_shortest_path(
        origin_node={"latitude": -0.01, "longitude": 0},
        destination_node={"latitude": 0, "longitude": 0.3},
        output_path=True,
    )

    assert _get_node_mode_names(coast_network)[route["path"][-1]] == "road"


# A high-speed line is also a main line (`usage=main`): `highspeed` comes
# first. A line without `usage` is `rail_other`.
@pytest.mark.parametrize(
    "tags, class_name",
    [
        ({"highspeed": "yes", "usage": "main"}, "rail_highspeed"),
        ({"usage": "main"}, "rail_main"),
        ({"usage": "branch"}, "rail_branch"),
        ({}, "rail_other"),
    ],
)
def test_a_railway_line_takes_its_class_from_highspeed_then_from_usage(
    tags, class_name
):
    tags = {"railway": "rail", **tags}

    assert osm_region_multimodal.select_rail_with_class(tags) == (0, class_name)


def test_the_edges_of_a_lane_of_a_passage_have_the_class_of_the_passage(
    tmp_path,
):
    # Along longitude 32: a lane of the Suez Canal from latitude 30 to 31,
    # then a lane outside a passage from latitude 31 to 32.
    lanes = tmp_path / "lanes.gpkg"
    lanes.write_bytes(
        _sea_gpkg([([32, 30, 32, 31], "suez"), ([32, 31, 32, 32], None)])
    )

    sea = eurostat_sea_lanes.build_sea_lane_arrays({"sea_lanes": str(lanes)})

    latitudes = [round(value * 1e-7) for value in sea["node_points"][0::2]]
    classes = {
        (latitudes[u], latitudes[sea["edge_destination_node_ids"][edge]]): list(
            pipelines.CLASSES
        )[sea["edge_class_ids"][edge]]
        for u in range(len(latitudes))
        for edge in range(
            sea["node_first_edge_ids"][u], sea["node_first_edge_ids"][u + 1]
        )
    }
    assert classes == {
        (30, 31): "suez",
        (31, 30): "suez",
        (31, 32): "open_sea",
        (32, 31): "open_sea",
    }


# Eurostat stores a lane that crosses the antimeridian as two lines. One
# ends at longitude 180 and the other starts at longitude -180.
def test_eurostat_sea_lanes_joins_a_lane_cut_at_the_antimeridian(tmp_path):
    lanes = tmp_path / "lanes.gpkg"
    lanes.write_bytes(
        _sea_gpkg([([179, 0, 180, 0], None), ([-180, 0, -179, 0], None)])
    )

    geo = eurostat_sea_lanes.build({"sea_lanes": str(lanes)})

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
def test_eurostat_sea_lanes_leaves_out_the_lanes_of_the_arctic_passages(
    tmp_path,
):
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

    geo = eurostat_sea_lanes.build({"sea_lanes": str(lanes)})

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
    "arguments, message",
    [
        ({"name": "nowhere"}, "Unknown network"),
        ({"name": "eurostat_marnett"}, "Did you mean 'eurostat_sea_lanes'"),
        ({"name": eurostat_sea_lanes}, "as pipeline=<module>"),
        ({}, "Give one of name"),
        (
            {"name": "eurostat_sea_lanes", "pipeline": eurostat_sea_lanes},
            "Give one of name",
        ),
        ({"name": "osm_region_multimodal"}, "'osm_region_multimodal' needs"),
        (
            {"name": "eurostat_sea_lanes", "region": "europe/luxembourg"},
            "'eurostat_sea_lanes' takes no region",
        ),
        (
            {"name": "osm_region_multimodal", "region": "../europe"},
            "Invalid region",
        ),
    ],
)
def test_build_geograph_checks_its_arguments_before_downloading(
    tmp_path, monkeypatch, arguments, message
):
    monkeypatch.setattr("requests.get", None)  # any download fails at once
    with pytest.raises(ValueError, match=message):
        GeoGraph.build_geograph(**arguments, cache_dir=str(tmp_path))
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
    target = tmp_path / "networks" / "eurostat_sea_lanes" / file_name
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
