import hashlib
import json
import os
import re
import sqlite3
import struct
import threading
import typing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from helpers import great_circle_km

from scgraph import GeoGraph, network_file, networks
from scgraph.helpers.hilbert import hilbert_order
from scgraph.networks import (
    eurostat_marnet,
    marnet,
    north_america_rail,
    osm_main_roads,
    osm_main_roads_and_marnet,
)
from scgraph.utils import haversine

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
            body = {"objectIdField": "OBJECTID", "maxRecordCount": 1}
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


# A new version of the build script or of the file format, or a missing network file
# (None), builds the network again
@pytest.mark.parametrize("versioned", [marnet, network_file, None])
def test_build_geograph_builds_once_per_version_and_records_the_source(
    tmp_path, source, monkeypatch, versioned
):
    monkeypatch.setitem(
        marnet.SOURCES["lines"], "url", f"{source}/lines.geojson"
    )
    geo = GeoGraph.build_geograph("marnet", cache_dir=str(tmp_path))
    again = GeoGraph.build_geograph("marnet", cache_dir=str(tmp_path))
    assert _Source.served == ["/lines.geojson"]  # the second call is local
    assert len(geo.nodes) == 4
    assert again.graph_object.graph == geo.graph_object.graph
    folder = tmp_path / "networks" / "marnet"
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["build_version"] == marnet.VERSION
    assert manifest["sources"] == [
        {
            "name": "lines",
            "url": f"{source}/lines.geojson",
            "sha256": hashlib.sha256(_GEOJSON).hexdigest(),
            "bytes": len(_GEOJSON),
            "credit": marnet.SOURCES["lines"]["credit"],
            "license": "EUPL-1.2",
            "license_url": marnet.SOURCES["lines"]["license_url"],
        }
    ]
    cached = folder / manifest["file"]
    assert network_file.read(str(cached))[1]["sources"] == manifest["sources"]
    # Nodes numbered along the Hilbert curve, as the manifest says
    assert manifest["node_order"]["name"] == "hilbert"
    assert hilbert_order(geo.nodes) == list(range(len(geo.nodes)))
    # The source has changed since: the new build replaces the cached network
    monkeypatch.setitem(
        _FILES, "/lines.geojson", _GEOJSON.replace(b"0.02", b"0.03")
    )
    if versioned is None:
        cached.unlink()
        listing = GeoGraph.list_downloadable_geographs(str(tmp_path))
        assert not next(n for n in listing if n["name"] == "marnet")["cached"]
    else:
        monkeypatch.setattr(versioned, "VERSION", versioned.VERSION + 1)
    rebuilt = GeoGraph.build_geograph("marnet", cache_dir=str(tmp_path))
    GeoGraph.build_geograph("marnet", cache_dir=str(tmp_path))
    assert _Source.served == ["/lines.geojson"] * 2  # built again once
    assert rebuilt.nodes != geo.nodes
    # One network file is left, named by its content, and the manifest names it
    name = json.loads((folder / "manifest.json").read_text())["file"]
    content = (folder / name).read_bytes()[40:]
    assert name == hashlib.sha256(content).hexdigest() + ".scgraph"
    assert {p.name for p in folder.iterdir()} == {"manifest.json", name}
    # Backup tools skip the cache
    assert (
        (tmp_path / "networks" / "CACHEDIR.TAG")
        .read_text()
        .startswith("Signature: 8a477f597d28d172789f06886806bc55")
    )
    listing = {
        n["name"]: n
        for n in GeoGraph.list_downloadable_geographs(str(tmp_path))
    }
    assert listing["marnet"]["cached"] and not listing["us_freeway"]["cached"]


# What the cache holds: nothing, a current build, or a build by another version of the
# build script ("stale") or of the file format; SCGRAPH_OFFLINE sets the default of
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
        marnet.SOURCES["lines"], "url", f"{source}/lines.geojson"
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
    versioned = {"stale": marnet, "format": network_file}.get(cached)
    if versioned:
        monkeypatch.setattr(versioned, "VERSION", versioned.VERSION + 1)
    if offline:
        monkeypatch.setenv("SCGRAPH_OFFLINE", offline)

    def build():
        return GeoGraph.build_geograph(
            "marnet", cache_dir=str(tmp_path), **options
        )

    if outcome == "loaded":  # with a warning that names what differs
        old, new = marnet.VERSION - 1, marnet.VERSION
        differs = f"build script version {old}, now {new};"
        with pytest.warns(UserWarning, match=differs):
            assert len(build().nodes) == 4
    elif outcome == "built":
        assert len(build().nodes) == 4
    elif outcome == "down":
        monkeypatch.delitem(_FILES, "/lines.geojson")
        with pytest.raises(requests.HTTPError, match="local_files_only=True"):
            build()
        # The cached network is kept
        manifest = json.loads(
            (tmp_path / "networks/marnet/manifest.json").read_text()
        )
        assert (tmp_path / "networks/marnet" / manifest["file"]).is_file()
    else:  # scgraph's own error, which names the cause
        with pytest.raises(outcome, match="local_files_only"):
            build()
    downloaded = outcome in ("built", "down")
    assert _Source.served == (["/lines.geojson"] if downloaded else [])


def test_build_geograph_reads_every_page_of_an_arcgis_layer(
    tmp_path, source, monkeypatch
):
    monkeypatch.setitem(
        north_america_rail.SOURCES["lines"], "url", f"{source}/layer"
    )
    geo = GeoGraph.build_geograph("north_america_rail", cache_dir=str(tmp_path))
    assert len(geo.nodes) == 4


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


def test_build_geograph_leaves_nothing_after_a_failed_build(
    tmp_path, source, monkeypatch
):
    monkeypatch.setitem(
        marnet.SOURCES["lines"], "url", f"{source}/lines.geojson"
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


def test_list_downloadable_geographs_matches_the_names_build_geograph_takes(
    tmp_path,
):
    listing = GeoGraph.list_downloadable_geographs(str(tmp_path))
    names = [n["name"] for n in listing]
    annotation = typing.get_type_hints(GeoGraph.build_geograph)["name"]
    assert names == list(networks.NAMES) == list(typing.get_args(annotation))


# Two roads across a strait (ways 1, 2), a car ferry between them from 0.6 km off a road
# node to another (3), a ferry closed to cars (4) and one that ends 3.6 km from a road
# (5), both shorter than the car ferry, and a car ferry longer than the road it doubles (6)
_FERRY_NODES = {
    1: (0, 0), 2: (0, 0.01), 3: (0, 0.06), 4: (0, 0.07),
    10: (0, 0.015), 11: (0.02, 0.035),
    20: (0, 0.011), 21: (0, 0.059),
    30: (0.025, 0.03), 31: (0, 0.058),
    40: (0.001, 0), 41: (0.01, 0.005), 42: (0.001, 0.01),
}  # fmt: skip
_FERRY_WAYS = [
    ([1, 2], 'k="highway" v="primary"'),
    ([3, 4], 'k="highway" v="trunk"'),
    ([10, 11, 3], 'k="route" v="ferry"'),
    ([20, 21], 'k="route" v="ferry"/><tag k="motor_vehicle" v="no"'),
    ([30, 31], 'k="route" v="ferry"'),
    ([40, 41, 42], 'k="route" v="ferry"'),
]


def test_osm_main_roads_joins_roads_by_car_ferries_ending_near_them(tmp_path):
    pytest.importorskip("osmium")
    lines = [
        f'<node id="{i}" version="1" lat="{la}" lon="{lo}"/>'
        for i, (la, lo) in _FERRY_NODES.items()
    ]
    for w, (refs, tags) in enumerate(_FERRY_WAYS, start=1):
        nds = "".join(f'<nd ref="{i}"/>' for i in refs)
        lines.append(f'<way id="{w}" version="1">{nds}<tag {tags}/></way>')
    path = tmp_path / "roads.osm"
    path.write_text('<osm version="0.6">' + "\n".join(lines) + "</osm>")
    geo = osm_main_roads.build({"roads": str(path)})
    node = {tuple(c): i for i, c in _FERRY_NODES.items()}
    arcs = {
        (node[tuple(geo.nodes[u])], node[tuple(geo.nodes[v])]): w
        for u, row in enumerate(geo.graph_object.graph)
        for v, w in row.items()
    }
    ferry = sum(
        great_circle_km(_FERRY_NODES[a], _FERRY_NODES[b])
        for a, b in [(10, 11), (11, 3)]
    )
    assert arcs == pytest.approx(
        {
            (1, 2): great_circle_km(_FERRY_NODES[1], _FERRY_NODES[2]),
            (2, 1): great_circle_km(_FERRY_NODES[1], _FERRY_NODES[2]),
            (3, 4): great_circle_km(_FERRY_NODES[3], _FERRY_NODES[4]),
            (4, 3): great_circle_km(_FERRY_NODES[3], _FERRY_NODES[4]),
            (2, 3): ferry,
            (3, 2): ferry,
        }
    )
    u, v = (geo.nodes.index(list(_FERRY_NODES[i])) for i in (2, 3))
    assert geo.intermediate_nodes[u][v] == [
        list(_FERRY_NODES[i]) for i in (10, 11)
    ]


def test_build_geograph_joins_roads_and_sea_at_ports(
    tmp_path, source, monkeypatch
):
    pytest.importorskip("osmium")
    # The roads URL keeps a {region} placeholder, as for Geofabrik: region "roads"
    # makes it the local file /roads.osm
    sources = {
        "roads": f"{source}/{{region}}.osm",
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
    folder = tmp_path / "networks" / "osm_main_roads_and_marnet" / "roads"
    manifest = json.loads((folder / "manifest.json").read_text())
    # Each node has its mode, each mode the source of its node ids: 3 road nodes (not the
    # fragment), 2 ports, 2 sea nodes, stored by mode
    assert geo.modes == [
        {"name": "road", "source": "roads"},
        {"name": "port"},
        {"name": "sea", "source": "sea"},
    ]
    assert list(geo.node_modes) == [0, 0, 0, 1, 1, 2, 2]
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
    geo = eurostat_marnet.build({"lines": gpkg})

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
