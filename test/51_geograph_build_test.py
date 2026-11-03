import hashlib
import json
import threading
import typing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from scgraph import GeoGraph, network_file, networks
from scgraph.networks import (
    marnet,
    north_america_rail,
    osm_main_roads,
    osm_main_roads_and_marnet,
)

# Two lines meeting at (0.01, 0): 4 nodes
_FEATURES = [
    {"type": "Feature", "properties": {}, "geometry": g}
    for g in (
        {"type": "LineString", "coordinates": [[0, 0], [0.01, 0], [0.02, 0]]},
        {"type": "LineString", "coordinates": [[0.01, 0], [0.01, 0.01]]},
    )
]
_GEOJSON = json.dumps(
    {"type": "FeatureCollection", "features": _FEATURES}
).encode()
# A road from (0, 0) to (0, 0.01) and a sea lane from (0, 2.2) to (0, 3). Ports:
# "Near" is 1 km from the road and 242 km from the sea (joined); "Inland" is 256 km
# from the sea and "Far" 277 km from the road (not joined)
_FILES = {
    "/lines.geojson": _GEOJSON,
    "/roads.osm": b"""<osm version="0.6">
<node id="1" version="1" lat="0" lon="0"/>
<node id="2" version="1" lat="0" lon="0.01"/>
<way id="1" version="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="primary"/></way>
</osm>""",
    "/sea.geojson": json.dumps(
        {
            "type": "GeometryCollection",
            "geometries": [
                {"type": "LineString", "coordinates": [[2.2, 0], [3, 0]]}
            ],
        }
    ).encode(),
    "/ports.csv": b"Main Port Name,Latitude,Longitude\nNear,0,0.02\nInland,0,-0.1\nFar,0,2.5\n",
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


# A new version of the build script or of the file format builds the network again
@pytest.mark.parametrize("versioned", [marnet, network_file])
def test_build_geograph_builds_once_per_version_and_records_the_source(
    tmp_path, source, monkeypatch, versioned
):
    monkeypatch.setitem(
        marnet.SOURCES["lines"], "url", f"{source}/lines.geojson"
    )
    geo = GeoGraph.build_geograph("marnet", cache_dir=str(tmp_path))
    again = GeoGraph.build_geograph("marnet", cache_dir=str(tmp_path))
    assert _Source.served == ["/lines.geojson"]  # the second call is local
    monkeypatch.setattr(versioned, "VERSION", versioned.VERSION + 1)
    GeoGraph.build_geograph("marnet", cache_dir=str(tmp_path))
    GeoGraph.build_geograph("marnet", cache_dir=str(tmp_path))
    assert _Source.served == ["/lines.geojson"] * 2  # built again once
    assert len(geo.nodes) == 4
    assert again.graph_object.graph == geo.graph_object.graph
    manifest = json.loads(
        (tmp_path / "downloads" / "marnet" / "marnet.manifest.json").read_text()
    )
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
    cached = tmp_path / "downloads" / "marnet" / "marnet.scgraph"
    assert network_file.read(str(cached))[1]["sources"] == manifest["sources"]
    # What a killed build leaves behind is not a cached network
    leftover = tmp_path / "downloads" / "us_freeway" / ".building-x"
    leftover.mkdir(parents=True)
    (leftover / "us_freeway.scgraph").write_text("{}")
    listing = {
        n["name"]: n
        for n in GeoGraph.list_downloadable_geographs(str(tmp_path))
    }
    assert listing["marnet"]["cached"] and not listing["us_freeway"]["cached"]


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
    assert not any((tmp_path / "downloads" / "marnet").iterdir())
    GeoGraph.build_geograph("marnet", cache_dir=str(tmp_path))  # built now
    assert _Source.served == ["/lines.geojson"] * 2


def test_list_downloadable_geographs_matches_the_names_build_geograph_takes(
    tmp_path,
):
    listing = GeoGraph.list_downloadable_geographs(str(tmp_path))
    names = [n["name"] for n in listing]
    annotation = typing.get_type_hints(GeoGraph.build_geograph)["name"]
    assert names == list(networks.NAMES) == list(typing.get_args(annotation))


def test_build_geograph_joins_roads_and_sea_at_ports(
    tmp_path, source, monkeypatch
):
    pytest.importorskip("osmium")
    # The roads URL keeps a {region} placeholder, as for Geofabrik: region "roads"
    # makes it the local file /roads.osm
    sources = {
        "roads": f"{source}/{{region}}.osm",
        "sea": f"{source}/sea.geojson",
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
    folder = tmp_path / "downloads" / "osm_main_roads_and_marnet" / "roads"
    manifest = json.loads(
        (folder / "osm_main_roads_and_marnet.manifest.json").read_text()
    )
    # Nodes by mode: 2 road nodes, the near port, 2 sea nodes
    assert manifest["node_modes"] == {
        "road": [0, 2],
        "port": [2, 3],
        "sea": [3, 5],
    }
    route = geo.get_shortest_path(
        origin_node={"latitude": 0, "longitude": 0},
        destination_node={"latitude": 0, "longitude": 3},
        output_coordinate_path="list_of_lists",
    )
    assert [0, 0.02] in route["coordinate_path"]  # through the port


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
    assert not (tmp_path / "downloads").exists()
