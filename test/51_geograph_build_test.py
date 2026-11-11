import hashlib
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

from scgraph import GeoGraph, network_file, pipelines
from scgraph.helpers.hilbert import hilbert_order
from scgraph.pipelines import (
    eurostat_marnet,
    marnet,
    north_america_rail,
    osm_main_roads,
    osm_main_roads_and_marnet,
)
from scgraph.pipelines import build
from scgraph.pipelines.steps import assembly, osm
from scgraph.utils import has_cpp, haversine

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


def _sea_gpkg(lines):
    """A GeoPackage of lines as Eurostat stores them, as bytes."""
    database = sqlite3.connect(":memory:")
    database.execute('create table "type" (geometry blob, pass text)')
    for xy in lines:
        # GeoPackage header with an envelope (left empty), then big-endian WKB
        wkb = struct.pack(f">BII{len(xy)}d", 0, 2, len(xy) // 2, *xy)
        database.execute('insert into "type" values (?, null)', (b"GP\x00\x02" + bytes(36) + wkb,))  # fmt: skip
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
    "/sea.gpkg": _sea_gpkg([[0.2, 0, 0.3, 0]]),
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


@pytest.fixture
def source(monkeypatch):
    """The base URL of a local server for the sources."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Source)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(_Source, "served", [])
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


# A new version of the pipeline or of the file format, a missing network file (None) or
# a damaged one builds the network again
@pytest.mark.parametrize(
    "versioned",
    [(marnet, "PIPELINE_VERSION"), (network_file, "VERSION"), None, "damaged"],
)
def test_build_geograph_builds_once_per_version_and_records_the_source(
    tmp_path, source, monkeypatch, versioned
):
    monkeypatch.setitem(
        marnet.SOURCES["sea_lanes"], "url", f"{source}/lines.geojson"
    )
    geo = GeoGraph.build_geograph("marnet", cache_dir=str(tmp_path))
    again = GeoGraph.build_geograph("marnet", cache_dir=str(tmp_path))
    assert _Source.served == ["/lines.geojson"]  # the second call is local
    assert len(geo.nodes) == 4
    assert again.graph_object.graph == geo.graph_object.graph
    folder = tmp_path / "networks" / "marnet"
    pointer = json.loads((folder / "cache.json").read_text())
    cached = folder / pointer["file"]
    # The file says what built it; the download time, a clock time, is only in the cache
    info = GeoGraph.get_scgraph_info(str(cached))
    assert info["pipeline"] == {
        "name": "marnet",
        "region": None,
        "version": marnet.PIPELINE_VERSION,
    }
    credit = marnet.SOURCES["sea_lanes"]["credit"]
    assert info["sources"] == [  # no version: the GeoJSON gives no data time
        {
            "name": "sea_lanes",
            "url": f"{source}/lines.geojson",
            "sha256": hashlib.sha256(_GEOJSON).hexdigest(),
            "bytes": len(_GEOJSON),
            "credit": credit,
            "license": "EUPL-1.2",
            "license_url": marnet.SOURCES["sea_lanes"]["license_url"],
        }
    ]
    assert info["software"]["backend"] == ("cpp" if has_cpp() else "python")
    assert info["software"]["platform"].startswith(sysconfig.get_platform())
    assert marnet.__doc__.split("\n")[0] in info["description"]
    assert (info["attribution"], info["data_up_to"]) == (
        f"{credit} (EUPL-1.2)",
        None,
    )
    assert pointer["downloaded"] not in json.dumps(info)
    # Nodes numbered along the Hilbert curve, as the file says
    assert info["node_order"]["name"] == "hilbert"
    assert hilbert_order(geo.nodes) == list(range(len(geo.nodes)))
    # The source has changed since (except for the damaged file, rebuilt under the same
    # name): the new build replaces the cached network
    nodes = list(geo.nodes)
    if versioned == "damaged":  # a new file: geo may still read the old one
        damaged = cached.with_suffix(".damaged")
        damaged.write_bytes(cached.read_bytes()[:100])
        damaged.replace(cached)
    else:
        monkeypatch.setitem(
            _FILES, "/lines.geojson", _GEOJSON.replace(b"0.02", b"0.03")
        )
    if versioned in (None, "damaged"):
        if versioned is None:
            cached.unlink()
            listing = GeoGraph.list_buildable_geographs(str(tmp_path))
            entry = next(n for n in listing if n["name"] == "marnet")
            assert not entry["cached"]
    else:
        module, constant = versioned
        monkeypatch.setattr(module, constant, getattr(module, constant) + 1)
    rebuilt = GeoGraph.build_geograph("marnet", cache_dir=str(tmp_path))
    GeoGraph.build_geograph("marnet", cache_dir=str(tmp_path))
    assert _Source.served == ["/lines.geojson"] * 2  # built again once
    assert (rebuilt.nodes == nodes) == (versioned == "damaged")
    # One network file is left, named by its content, and cache.json names it
    name = json.loads((folder / "cache.json").read_text())["file"]
    content = (folder / name).read_bytes()[40:]
    assert name == hashlib.sha256(content).hexdigest() + ".scgraph"
    assert {p.name for p in folder.iterdir()} == {"cache.json", name}
    # Backup tools skip the cache
    assert (
        (tmp_path / "networks" / "CACHEDIR.TAG")
        .read_text()
        .startswith("Signature: 8a477f597d28d172789f06886806bc55")
    )
    listing = {
        n["name"]: n for n in GeoGraph.list_buildable_geographs(str(tmp_path))
    }
    assert listing["marnet"]["cached"] and not listing["us_freeway"]["cached"]


# What the cache holds: nothing, a current build, or a build by another version of the
# pipeline ("stale") or of the file format; SCGRAPH_OFFLINE sets the default of
# local_files_only. "loaded" without a download, "built" with one, "down": the source fails.
# As on Windows, a network file can't be replaced while it is open (here: any existing one)
@pytest.mark.parametrize(
    "cached, offline, options, outcome",
    [
        (None, None, {"local_files_only": True}, FileNotFoundError),
        (None, "1", {}, FileNotFoundError),
        ("current", None, {"refresh": True}, "built"),
        ("current", "1", {"refresh": True}, ValueError),
        ("stale", None, {"local_files_only": True}, "loaded"),
        ("stale", "1", {"local_files_only": False}, "built"),
        ("stale", None, {}, "down"),
        ("format", None, {"local_files_only": True}, ValueError),
    ],
)
def test_build_geograph_downloads_only_if_allowed(
    tmp_path, source, monkeypatch, cached, offline, options, outcome
):
    monkeypatch.setitem(
        marnet.SOURCES["sea_lanes"], "url", f"{source}/lines.geojson"
    )
    monkeypatch.delenv("SCGRAPH_OFFLINE", raising=False)
    replace = os.replace

    def in_use(source, target, **kwargs):
        if str(target).endswith(".scgraph") and os.path.exists(target):
            raise PermissionError(f"{target} is open in another process")
        replace(source, target, **kwargs)

    monkeypatch.setattr(os, "replace", in_use)
    if cached:
        GeoGraph.build_geograph("marnet", cache_dir=str(tmp_path))
        _Source.served.clear()
    if cached == "stale":
        monkeypatch.setattr(
            marnet, "PIPELINE_VERSION", marnet.PIPELINE_VERSION + 1
        )
    if cached == "format":
        monkeypatch.setattr(network_file, "VERSION", network_file.VERSION + 1)
    if offline:
        monkeypatch.setenv("SCGRAPH_OFFLINE", offline)

    def build():
        return GeoGraph.build_geograph(
            "marnet", cache_dir=str(tmp_path), **options
        )

    if outcome == "loaded":  # with a warning that names what differs
        old, new = marnet.PIPELINE_VERSION - 1, marnet.PIPELINE_VERSION
        differs = f"pipeline version {old}, now {new};"
        with pytest.warns(UserWarning, match=differs):
            assert len(build().nodes) == 4
    elif outcome == "built":
        assert len(build().nodes) == 4
    elif outcome == "down":
        monkeypatch.delitem(_FILES, "/lines.geojson")
        with pytest.raises(requests.HTTPError, match="local_files_only=True"):
            build()
        # The cached network is kept
        pointer = json.loads(
            (tmp_path / "networks/marnet/cache.json").read_text()
        )
        assert (tmp_path / "networks/marnet" / pointer["file"]).is_file()
    else:  # scgraph's own error, which names the cause
        with pytest.raises(outcome, match="local_files_only"):
            build()
    downloaded = outcome in ("built", "down")
    assert _Source.served == (["/lines.geojson"] if downloaded else [])


# Built in separate subprocesses with different PYTHONHASHSEED values: the same backend
# gives byte-identical files, and the pure-Python backend (scgraph.cpp hidden) the same
# graph: the same nodes, and the same arcs and lengths (==), in any order (meaningful in
# the C++ build; the GeoJSON input gives arcs without shapes). Two paths: a GeoGraph
# (marnet) and the network file's arrays (an OSM pipeline)
@pytest.mark.parametrize(
    "name, region", [("marnet", ""), ("osm_main_roads", "roads")]
)
def test_build_geograph_gives_the_same_file_for_the_same_inputs(
    tmp_path, source, monkeypatch, name, region
):
    if region:
        pytest.importorskip("osmium")
    # Lines meeting at shared points, so that rows hold several arcs
    rng = random.Random(3)
    points = [[rng.uniform(0, 0.3), rng.uniform(0, 0.3)] for _ in range(60)]
    lines = [rng.sample(points, rng.randint(2, 6)) for _ in range(80)]
    geometries = [{"type": "LineString", "coordinates": line} for line in lines]
    monkeypatch.setitem(
        _FILES,
        "/lines.geojson",
        json.dumps(
            {"type": "GeometryCollection", "geometries": geometries}
        ).encode(),
    )
    script = (
        "import sys\n"
        "if sys.argv[3] == 'python':\n"
        "    sys.modules['scgraph.cpp'] = None\n"
        "from scgraph import GeoGraph\n"
        "from scgraph.pipelines import marnet, osm_main_roads as roads\n"
        "marnet.SOURCES['sea_lanes']['url'] = sys.argv[1] + '/lines.geojson'\n"
        "url = sys.argv[1] + '/{region}.osm'\n"
        "roads.SOURCES['roads'] = {**roads.SOURCES['roads'], 'url': url}\n"
        "region = sys.argv[5] or None\n"
        "GeoGraph.build_geograph(sys.argv[4], region=region, cache_dir=sys.argv[2])\n"
    )
    files = []
    for seed, backend in (("1", "this"), ("2", "this"), ("3", "python")):
        cache = tmp_path / seed
        subprocess.run(
            [
                sys.executable,
                "-c",
                script,
                source,
                cache,
                backend,
                name,
                region,
            ],
            env={**os.environ, "PYTHONHASHSEED": seed},
            check=True,
            timeout=120,
            cwd=tmp_path,  # the installed scgraph, not the sources
        )
        folder = cache / "networks" / name / region
        files.append(
            folder / json.loads((folder / "cache.json").read_text())["file"]
        )
    assert files[0].read_bytes() == files[1].read_bytes()
    # The builds ran in this backend, then in pure Python
    backends = [
        GeoGraph.get_scgraph_info(str(f))["software"]["backend"] for f in files
    ]
    assert backends == ["cpp" if has_cpp() else "python"] * 2 + ["python"]

    def graph(file):
        arrays = network_file.read(str(file))[0]
        offsets, heads, weights = (
            arrays[k] for k in ("offsets", "heads", "weights")
        )
        columns = ("latitudes", "longitudes", "node_ids", "node_modes")
        nodes = list(zip(*(arrays[k] for k in columns if k in arrays)))
        return nodes, {
            (tail, heads[arc], weights[arc])
            for tail in range(len(nodes))
            for arc in range(offsets[tail], offsets[tail + 1])
        }

    assert graph(files[0]) == graph(files[2])


# The platform names what holds the math functions: the C library on Linux, the system
# version on macOS, nothing more where neither is known
@pytest.mark.parametrize(
    "libc, macos, system",
    [
        (("glibc", "2.41"), "", " glibc 2.41"),
        (("", ""), "14.6", " macOS 14.6"),
        (("", ""), "", ""),
    ],
)
def test_build_metadata_names_the_platform(monkeypatch, libc, macos, system):
    monkeypatch.setattr(platform, "libc_ver", lambda: libc)
    monkeypatch.setattr(platform, "mac_ver", lambda: (macos, ("", "", ""), ""))
    metadata = pipelines.build_metadata("x", None, 1, [])
    assert metadata["software"]["platform"] == sysconfig.get_platform() + system


# Every page of an ArcGIS layer is read, by name or from a module of one's own (an
# adapted copy), cached under its last name, which may not be a built-in's
@pytest.mark.parametrize(
    "module_name, folder",
    [
        (None, "north_america_rail"),
        ("my_pipelines.rail", "rail"),
        ("my_pipelines.north_america_rail", None),  # refused
    ],
)
def test_build_geograph_reads_every_page_of_an_arcgis_layer(
    tmp_path, source, monkeypatch, module_name, folder
):
    monkeypatch.setitem(
        north_america_rail.SOURCES["rail_lines"], "url", f"{source}/layer"
    )
    network = "north_america_rail"
    if module_name:
        network = types.ModuleType(module_name)
        for name in ("SOURCES", "PIPELINE_VERSION", "download"):
            setattr(network, name, getattr(north_america_rail, name))
        # Its steps are stored in the file
        network.build = lambda files: (
            north_america_rail.build(files),
            [{"step": "copy", "arcs": 1}],
        )
    if folder is None:
        with pytest.raises(ValueError, match="Invalid pipeline module name"):
            GeoGraph.build_geograph(network, cache_dir=str(tmp_path))
        return
    geo = GeoGraph.build_geograph(network, cache_dir=str(tmp_path))
    assert len(geo.nodes) == 4
    assert geo.metadata["pipeline"]["name"] == folder
    assert geo.metadata.get("steps") == (
        [{"step": "copy", "arcs": 1}] if module_name else None
    )
    # The layer's last edit is the version of its data
    assert geo.metadata["sources"][0]["version"] == "2024-01-02T03:04:05Z"
    assert (tmp_path / "networks" / folder / "cache.json").is_file()


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


def test_build_geograph_leaves_nothing_after_a_failed_build(
    tmp_path, source, monkeypatch
):
    monkeypatch.setitem(
        marnet.SOURCES["sea_lanes"], "url", f"{source}/lines.geojson"
    )

    def broken(files):
        raise RuntimeError("build failed")

    with monkeypatch.context() as patch:
        patch.setattr(marnet, "build", broken)
        with pytest.raises(RuntimeError):
            GeoGraph.build_geograph("marnet", cache_dir=str(tmp_path))
    assert [p.name for p in tmp_path.rglob("*")] == ["networks", "CACHEDIR.TAG"]
    GeoGraph.build_geograph("marnet", cache_dir=str(tmp_path))  # built now
    assert _Source.served == ["/lines.geojson"] * 2


def test_list_buildable_geographs_matches_the_names_build_geograph_takes(
    tmp_path,
):
    listing = GeoGraph.list_buildable_geographs(str(tmp_path))
    names = [n["name"] for n in listing]
    annotation = typing.get_type_hints(GeoGraph.build_geograph)["name"]
    literal = typing.get_args(annotation)[0]  # Literal[...] | ModuleType
    assert names == list(pipelines.NAMES) == list(typing.get_args(literal))


# Two roads across a strait (ways 1, 2), a car ferry between them from 0.6 km off a road
# node to another (3), a ferry closed to cars (4) and one that ends 3.6 km from a road
# (5), both shorter than the car ferry, a car ferry longer than the road it doubles (6),
# and one from an interior node of road 2, which cuts the road there (7)
_FERRY_NODES = {
    1: (0, 0), 2: (0, 0.01), 3: (0, 0.06), 4: (0, 0.07), 5: (0, 0.065),
    10: (0, 0.015), 11: (0.02, 0.035), 50: (0.005, 0),
    20: (0, 0.011), 21: (0, 0.059),
    30: (0.025, 0.03), 31: (0, 0.058),
    40: (0.001, 0), 41: (0.01, 0.005), 42: (0.001, 0.01),
}  # fmt: skip
_FERRY_WAYS = [
    ([1, 2], 'k="highway" v="primary"'),
    ([3, 5, 4], 'k="highway" v="trunk"'),
    ([10, 11, 3], 'k="route" v="ferry"'),
    ([20, 21], 'k="route" v="ferry"/><tag k="motor_vehicle" v="no"'),
    ([30, 31], 'k="route" v="ferry"'),
    ([40, 41, 42], 'k="route" v="ferry"'),
    ([5, 50], 'k="route" v="ferry"'),
]


@pytest.mark.parametrize("in_files", [False, True])  # PieceArrays in a folder
def test_osm_main_roads_joins_roads_by_vehicle_ferries_ending_near_them(
    tmp_path, in_files
):
    pytest.importorskip("osmium")
    lines = [
        f'<node id="{i}" version="1" lat="{la}" lon="{lo}"/>'
        # By id, as in OSM files
        for i, (la, lo) in sorted(_FERRY_NODES.items())
    ]
    for w, (refs, tags) in enumerate(_FERRY_WAYS, start=1):
        nds = "".join(f'<nd ref="{i}"/>' for i in refs)
        lines.append(f'<way id="{w}" version="1">{nds}<tag {tags}/></way>')
    path = tmp_path / "roads.osm"
    path.write_text('<osm version="0.6">' + "\n".join(lines) + "</osm>")
    selects, folder = osm_main_roads.SELECTS, in_files and str(tmp_path) or None
    pieces, steps = osm.build_way_pieces(
        str(path), selects, ("highway", "route"), osm.MAX_KM, folder
    )
    # Ferries 3, 6 and 7, both ways
    assert steps[-1] == {"step": "ferries", "arcs": 6}
    full = _geograph(
        assembly.build_graph_from_pieces(pieces), tmp_path / "full.scgraph"
    )
    node = {tuple(c): i for i, c in _FERRY_NODES.items()}
    arcs = {
        (node[tuple(full.nodes[u])], node[tuple(full.nodes[v])]): w
        for u, row in enumerate(full.graph_object.graph)
        for v, w in row.items()
    }
    km = {
        (a, b): great_circle_km(_FERRY_NODES[a], _FERRY_NODES[b])
        for a, b in [(1, 2), (3, 5), (5, 4), (10, 11), (11, 3), (5, 50)]
    }
    ferry = km[10, 11] + km[11, 3]
    # Ferry 6, longer than the road it doubles, is not kept
    assert arcs == pytest.approx(
        {
            **{(a, b): km[a, b] for a, b in [(1, 2), (3, 5), (5, 4)]},
            **{(b, a): km[a, b] for a, b in [(1, 2), (3, 5), (5, 4)]},
            (2, 3): ferry,
            (3, 2): ferry,
            (5, 1): km[5, 50],
            (1, 5): km[5, 50],
        }
    )
    u, v = (full.nodes.index(list(_FERRY_NODES[i])) for i in (2, 3))
    assert full.intermediate_nodes[u][v] == [
        list(_FERRY_NODES[i]) for i in (10, 11)
    ]
    # The build contracts the chain 1-2-3-4; routes between the nodes it keeps have the
    # same length, drawn with some of the same points (shapes simplified at 50 m)
    (arrays, _), _ = osm_main_roads.build({"roads": str(path)})
    contracted = _geograph(arrays, tmp_path / "contracted.scgraph")
    assert len(contracted.nodes) < len(full.nodes)

    def route(geo, a, b):
        return geo.get_shortest_path(
            origin_node={"latitude": a[0], "longitude": a[1]},
            destination_node={"latitude": b[0], "longitude": b[1]},
            output_coordinate_path="list_of_lists",
        )

    pairs = [
        (a, b) for a in contracted.nodes for b in contracted.nodes if a != b
    ]
    for a, b in pairs:
        got, want = route(contracted, a, b), route(full, a, b)
        assert got["length"] == pytest.approx(want["length"])
        rest = iter(want["coordinate_path"])
        assert all(point in rest for point in got["coordinate_path"])


def _geograph(arrays, path):
    """The GeoGraph that a network file of `arrays` reads back."""
    units = {"units": "km", "modes": [{"name": None}]}
    circuities = {
        "default_off_graph_circuity": 1,
        "default_node_addition_circuity": 4,
    }
    metadata = network_file.header_metadata({}, **units, **circuities)
    network_file.write(str(path), arrays, metadata)
    return GeoGraph.load_from_scgraph(str(path))


def test_build_geograph_joins_roads_and_sea_at_ports(
    tmp_path, source, monkeypatch
):
    osmium = pytest.importorskip("osmium")
    # As a Geofabrik extract, a PBF whose header says when its data is up to
    xml, pbf = tmp_path / "roads.osm", tmp_path / "roads.osm.pbf"
    xml.write_bytes(_FILES["/roads.osm"])
    header = osmium.io.Header()
    header.set("osmosis_replication_timestamp", "2026-11-06T20:21:43Z")
    with osmium.SimpleWriter(str(pbf), header=header) as writer:
        for entity in osmium.FileProcessor(str(xml)):
            writer.add(entity)
    monkeypatch.setitem(_FILES, "/roads.osm.pbf", pbf.read_bytes())
    # The roads URL keeps a {region} placeholder, as for Geofabrik: region "roads"
    # makes it the local file /roads.osm.pbf
    sources = {
        "roads": f"{source}/{{region}}.osm.pbf",
        **{
            name: f"{source}/{name}.geojson"
            for name in ("land", "lakes", "rivers")
        },
        "sea": f"{source}/sea.gpkg",
        "ports": f"{source}/ports.csv",
    }
    for name, url in sources.items():
        monkeypatch.setitem(
            osm_main_roads_and_marnet.SOURCES,
            name,
            {**osm_main_roads_and_marnet.SOURCES[name], "url": url},
        )
    geo = GeoGraph.build_geograph(
        "osm_main_roads_and_marnet",
        region="roads",
        cache_dir=str(tmp_path),
    )
    # Each node has its mode, each mode the source of its node ids: 3 road nodes (not the
    # fragment), 2 ports, 2 sea nodes, stored by mode
    assert geo.modes == [
        {"name": "road", "source": "roads"},
        {"name": "port"},
        {"name": "sea", "source": "sea"},
    ]
    assert list(geo.node_modes) == [0, 0, 0, 1, 1, 2, 2]
    # Ports have scgraph's ids
    assert list(geo.node_ids)[3:5] in ([-1, -2], [-2, -1])
    # What each step did: 5 road nodes read, no ferry, 2 sea nodes, 2 ports joined,
    # then the fragment left out, and no chain to contract
    assert geo.metadata["steps"] == [
        {"step": "read", "pieces": 3},
        {"step": "ferries", "arcs": 0},
        {"step": "sea", "nodes": 2, "arcs": 2},
        {"step": "ports", "joined": 2},
        {"step": "components", "nodes": 7, "arcs": 14},
        {"step": "contract", "nodes": 7, "arcs": 14},
    ]
    assert [
        sorted(
            node for node, mode in zip(geo.nodes, geo.node_modes) if mode == row
        )
        for row in range(3)
    ] == [
        [[-0.01, 0], [0, 0], [0.01, 0]],
        [[0, 0.02], [0.01, 0.06]],
        [[0, 0.2], [0, 0.3]],
    ]
    route = geo.get_shortest_path(
        origin_node={"latitude": -0.01, "longitude": 0},
        destination_node={"latitude": 0, "longitude": 0.3},
        output_coordinate_path="list_of_lists",
    )
    assert [0, 0.02] in route["coordinate_path"]  # through the port
    versions = {s["name"]: s.get("version") for s in geo.metadata["sources"]}
    assert versions == {
        "sea": None,
        "ports": None,
        **dict.fromkeys(["land", "lakes", "rivers"], "5.1.2"),
        "roads": "2026-11-06T20:21:43Z",
    }
    assert [-0.004, 0.001] in route["coordinate_path"]  # along the road's shape
    # Connectors: 1.2 times the straight line to the road, the length of the water path
    port = list(geo.nodes).index([0, 0.02])
    (road, road_km), (sea, sea_km) = sorted(
        geo.graph_object.graph[port].items(), key=lambda a: geo.node_modes[a[0]]
    )
    assert road_km == pytest.approx(
        1.2 * great_circle_km([0, 0.02], geo.nodes[road])
    )
    path = [[0, 0.02], *geo.intermediate_nodes[port][sea], geo.nodes[sea]]
    drawn = sum(great_circle_km(a, b) for a, b in zip(path, path[1:]))
    assert sea_km == pytest.approx(drawn, rel=1e-4)
    assert geo.intermediate_nodes[sea][port] == path[-2:0:-1]  # and back


# Lines as Eurostat stores them: a lane cut at the antimeridian, at 180 and at -180, and
# Arctic passage lanes shorter than the open-sea lane beside them
def test_eurostat_marnet_joins_the_antimeridian_and_leaves_out_arctic_passages(
    tmp_path,
):
    lines = [
        ([179, 0, 180, 0], None),
        ([-180, 0, -179, 0], None),
        ([100, 75, 110, 75], "northeast"),
        ([100, 75, 110, 75], "northwest"),
        ([100, 75, 105, 70, 110, 75], None),
    ]
    gpkg = str(tmp_path / "lines.gpkg")
    database = sqlite3.connect(gpkg)
    database.execute('create table "type" (geometry blob, pass text)')
    for xy, passage in lines:
        # GeoPackage header with an envelope (left empty), then big-endian WKB
        geometry = (
            b"GP\x00\x02"
            + bytes(36)
            + struct.pack(f">BII{len(xy)}d", 0, 2, len(xy) // 2, *xy)
        )
        database.execute(
            'insert into "type" values (?, ?)', (geometry, passage)
        )
    database.commit()
    database.close()
    geo = eurostat_marnet.build({"sea_lanes": gpkg})

    def km(origin, destination):
        return geo.get_shortest_path(
            origin_node={"latitude": origin[0], "longitude": origin[1]},
            destination_node={
                "latitude": destination[0],
                "longitude": destination[1],
            },
        )["length"]

    assert km([0, 179], [0, -179]) == pytest.approx(
        haversine([0, 179], [0, -179]), abs=0.01
    )
    assert km([75, 100], [75, 110]) == pytest.approx(
        haversine([75, 100], [70, 105]) + haversine([70, 105], [75, 110]),
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


# Saving elsewhere, in the cache directory itself included, is allowed
@pytest.mark.parametrize("extension", ["scgraph", "graphjson"])
def test_saving_into_the_built_networks_of_the_cache_is_refused(
    tmp_path, monkeypatch, extension
):
    monkeypatch.setenv("SCGRAPH_CACHE_DIR", str(tmp_path))
    geo = GeoGraph(graph=[{1: 1.0}, {0: 1.0}], nodes=[[0, 0], [0, 0.01]])
    save = getattr(geo, f"save_as_{extension}")
    target = tmp_path / "networks" / "marnet" / f"edited.{extension}"
    target.parent.mkdir(parents=True)
    with pytest.raises(ValueError, match=re.escape(str(target))):
        save(str(target))
    save(str(tmp_path / f"edited.{extension}"))
    assert [p.name for p in tmp_path.rglob("edited.*")] == [
        f"edited.{extension}"
    ]


def test_piece_arrays_resume_mapping(tmp_path):
    folder = tmp_path / "stage1"
    pieces = assembly.PieceArrays(folder=str(folder))
    pieces.append(
        101, 102, 12.5, 0, [[48.8, 2.3], [48.9, 2.4]], [[48.85, 2.35]]
    )
    pieces.flush()
    reloaded = assembly.PieceArrays(folder=str(folder), truncate=False)
    assert len(reloaded.km) == 1 and reloaded.origins[0] == 101
    assert reloaded.destinations[0] == 102 and reloaded.km[0] == 12.5
    graph = assembly.build_graph_from_pieces(reloaded)
    assert len(graph["offsets"]) == 3
    reloaded.close()


def test_build_file_checkpoint_resume_and_invalidation(tmp_path):
    pipe = types.ModuleType("pipe")
    pipe.__doc__, pipe.PIPELINE_VERSION = "doc", 1
    pipe.SOURCES = {
        "src": {
            "url": "http://x/s.txt",
            "credit": "c",
            "license": "MIT",
            "license_url": "",
            "download": lambda url, target: Path(target).write_text("ok"),
        }
    }
    pipe.build = lambda files, *, folder=None: GeoGraph(
        graph=[{1: 1.0}, {}], nodes=[[0.0, 0.0], [1.0, 1.0]]
    )
    work = tmp_path / "work"
    build.build_file(
        pipe, cache_dir=str(tmp_path / "c"), keep_work=True, work_dir=str(work)
    )
    assert work.joinpath("sources", "src.txt").is_file()
    st1 = work / "stage1"
    st1.mkdir(parents=True, exist_ok=True)
    (st1 / "pass1.done").write_text("1")
    (st1 / "pass2.done").write_text("2")
    build.build_file(
        pipe,
        cache_dir=str(tmp_path / "c"),
        from_stage="pass2",
        keep_work=True,
        work_dir=str(work),
        refresh=True,
    )
    assert (st1 / "pass1.done").is_file() and not (st1 / "pass2.done").is_file()
    build.build_file(
        pipe,
        cache_dir=str(tmp_path / "c"),
        clean=True,
        keep_work=True,
        work_dir=str(work),
        refresh=True,
    )
    assert not (st1 / "pass1.done").is_file()


def test_build_cli_options(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        build,
        "build_file",
        lambda name, region=None, cache_dir=None, **kw: calls.append(kw)
        or "/file.scgraph",
    )
    build.main(
        [
            "marnet",
            "--cache-dir",
            str(tmp_path),
            "--clean",
            "--from",
            "stage2",
            "--keep-work",
            "--work-dir",
            str(tmp_path / "w"),
        ]
    )
    assert calls[0]["clean"] is True and calls[0]["from_stage"] == "stage2"
    assert calls[0]["keep_work"] is True and calls[0]["resume"] is True
    build.main(["marnet", "--no-resume"])
    assert calls[-1]["resume"] is False
