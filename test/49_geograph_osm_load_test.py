import subprocess
import sys

import pytest
from helpers import great_circle_km

from scgraph import GeoGraph
from scgraph.pipelines import osm_main_roads, world_main_roads
from scgraph.pipelines.steps.stage1_extract import osm
from scgraph.helpers.hilbert import hilbert_order

osmium = pytest.importorskip("osmium")

# OSM ids -> (latitude, longitude)
_NODES = {
    1: (0.0, 0.0),
    2: (0.0, 0.01),
    3: (0.0, 0.02),
    4: (0.01, 0.01),
    5: (-0.005, 0.015),  # bridge over way 1, no shared node
    6: (0.005, 0.015),
    7: (0.01, 0.02),
    10: (1.0, 0.0),  # a long way without junctions
    11: (1.005, 0.01),
    12: (1.0, 0.02),
    13: (1.0, 0.03),
    20: (2.0, 0.0),  # way 7 runs through node 99, missing from the file
    21: (2.0, 0.02),
    30: (3.0, 0.0),  # one way, drawn against the traffic
    31: (3.0, 0.01),
    40: (4.0, 0.0),  # roundabout piece, one way without a oneway tag
    41: (4.0, 0.01),
    50: (5.0, 0.0),  # motorway, one way without a oneway tag
    51: (5.0, 0.01),
    60: (6.0, 0.0),  # ferry route, without a highway tag
    61: (6.0, 0.01),
}
_WAYS = [
    (1, [1, 2, 3], {"highway": "primary"}),
    (2, [2, 4], {"highway": "primary"}),
    (3, [5, 6], {"highway": "primary", "bridge": "yes"}),
    (4, [3, 7], {"highway": "residential"}),
    (5, [4, 7], {"highway": "primary", "oneway": "yes"}),
    (6, [10, 11, 12, 13], {"highway": "trunk"}),
    (7, [20, 99, 21], {"highway": "primary"}),
    (8, [30, 31], {"highway": "primary", "oneway": "-1"}),
    (9, [40, 41], {"highway": "primary", "junction": "roundabout"}),
    (10, [50, 51], {"highway": "motorway"}),
    (11, [60, 61], {"route": "ferry"}),
]


def _write_osm(path):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<osm version="0.6">']
    for ref, (lat, lon) in _NODES.items():
        lines.append(f'<node id="{ref}" version="1" lat="{lat}" lon="{lon}"/>')
    for ref, refs, tags in _WAYS:
        lines.append(f'<way id="{ref}" version="1">')
        lines += [f'<nd ref="{r}"/>' for r in refs]
        lines += [f'<tag k="{k}" v="{v}"/>' for k, v in tags.items()]
        lines.append("</way>")
    lines.append("</osm>")
    path.write_text("\n".join(lines))


def _km(a, b):
    return great_circle_km(_NODES[a], _NODES[b])


def _arcs(geo):
    """Arcs as {(osm id, osm id): length}, through the node coordinates."""

    def key(c):
        return (round(c[0], 7), round(c[1], 7))  # OSM stores 1e-7 degrees

    osm_id = {key(c): ref for ref, c in _NODES.items()}
    return {
        (osm_id[key(geo.nodes[u])], osm_id[key(geo.nodes[v])]): w
        for u, row in enumerate(geo.graph_object.graph)
        for v, w in row.items()
    }


@pytest.fixture(scope="module")
def osm_file(tmp_path_factory):
    path = tmp_path_factory.mktemp("osm") / "small.osm"
    _write_osm(path)
    return str(path)


@pytest.fixture(scope="module")
def arcs(osm_file):
    # Every part of the small file, not only its largest connected part
    return _arcs(GeoGraph.load_from_osm(osm_file, largest_component=False))


def test_load_from_osm_joins_ways_only_at_shared_nodes(arcs):
    # Ways 1 and 2 share node 2; the bridge (5-6) crosses way 1 without a shared node
    assert {(1, 2), (2, 3), (2, 4), (5, 6)} <= set(arcs)
    assert {arc for arc in arcs if 5 in arc} == {(5, 6), (6, 5)}


def test_load_from_osm_keeps_main_roads_by_default(arcs):
    # The residential way 4 (3-7) is left out; only the one-way primary way 5 reaches 7
    assert {arc for arc in arcs if 7 in arc} == {(4, 7)}


def test_load_from_osm_does_not_join_across_a_missing_node(arcs):
    # Way 7 runs 20 -> 99 -> 21, node 99 is missing from the file
    assert not any(20 in arc or 21 in arc for arc in arcs)


def test_load_from_osm_arc_lengths_follow_the_shape(arcs):
    assert arcs[(1, 2)] == pytest.approx(_km(1, 2))
    # Way 6 is cut at node 12, the first point 2 km or more from node 10
    assert arcs[(10, 12)] == pytest.approx(_km(10, 11) + _km(11, 12))
    assert arcs[(12, 13)] == pytest.approx(_km(12, 13))


_ONE_WAY = {(4, 7), (31, 30), (40, 41), (50, 51)}
_BRIDGE = {(5, 6), (6, 5)}  # way 3, two-way
_FERRY = {(60, 61), (61, 60)}  # way 11, two-way


@pytest.mark.parametrize(
    "source, select, tag_keys, expected",
    [
        # one-way streets kept one way (the default)
        (str, osm.main_roads, ("highway",), _ONE_WAY | _BRIDGE),
        # every kept way both ways
        (
            str,
            lambda tags: None if osm.main_roads(tags) is None else 0,
            ("highway",),
            _ONE_WAY | {(b, a) for a, b in _ONE_WAY} | _BRIDGE,
        ),
        # a way left out
        (
            str,
            lambda tags: None if "bridge" in tags else osm.main_roads(tags),
            ("highway",),
            _ONE_WAY,
        ),
        # ways with any one of the keys: main roads or ferry routes
        (
            str,
            lambda tags: (
                0 if tags.get("route") == "ferry" else osm.main_roads(tags)
            ),
            ("highway", "route"),
            _ONE_WAY | _BRIDGE | _FERRY,
        ),
    ],
)
def test_load_from_osm_selects_ways_and_their_direction(
    osm_file, source, select, tag_keys, expected
):
    arcs = _arcs(
        GeoGraph.load_from_osm(
            source(osm_file),
            select=select,
            tag_keys=tag_keys,
            largest_component=False,
        )
    )
    nodes = {5, 7, 30, 40, 50, 60}  # the bridge, one-way streets and the ferry
    assert {arc for arc in arcs if nodes & set(arc)} == expected


def test_locate_ways_reads_every_kind_of_way_in_one_set_of_passes(osm_file):
    # A way goes to the first select that keeps it (primary roads are main roads), and
    # ways of two kinds meet at junctions (residential way 4 meets road way 1 at node 3)
    selects = {
        "residential": lambda tags: (
            0 if tags.get("highway") == "residential" else None
        ),
        "roads": osm.main_roads,
        "primary": lambda tags: 0 if tags.get("highway") == "primary" else None,
    }
    junctions, polylines = osm.locate_ways(osm_file, selects, ("highway",))
    nodes = {}
    for kind, _, points in polylines:
        nodes.setdefault(kind, set()).update(ref for ref, _ in points)
    assert set(nodes) == {"residential", "roads"}
    assert (
        nodes["residential"] == {3, 7} and {1, 2, 3, 50, 51} <= nodes["roads"]
    )
    assert 3 in junctions and 1 not in junctions


def test_load_from_osm_keeps_the_largest_strongly_connected_part(osm_file):
    # Ways 1 and 2 (nodes 1 to 4, two-way) are the largest part where every node
    # reaches every other; node 7 is only reached by a one-way street
    geo = GeoGraph.load_from_osm(osm_file)
    assert {node for arc in _arcs(geo) for node in arc} == {1, 2, 3, 4}
    assert dict(zip(geo.node_ids, map(tuple, geo.nodes))) == {
        ref: _NODES[ref] for ref in (1, 2, 3, 4)
    }


def test_load_from_osm_numbers_nodes_along_a_hilbert_curve_with_their_osm_ids(
    osm_file,
):
    geo = GeoGraph.load_from_osm(osm_file, largest_component=False)
    assert hilbert_order(geo.nodes) == list(range(len(geo.nodes)))
    assert geo.coordinate_dtype == "int32"  # OSM's own encoding
    assert all(
        _NODES[ref] == tuple(node) for ref, node in zip(geo.node_ids, geo.nodes)
    )


# A planet mirror: the files of a folder by HTTP, with byte ranges; their ETag is the text
# of the folder's file "tag", read at each request. In a child process: osmium holds the
# GIL while it waits for the pipe, which a server thread would need to fill
_MIRROR = r"""
import http.server, pathlib, sys
folder = pathlib.Path(sys.argv[1])
class Mirror(http.server.BaseHTTPRequestHandler):
    def do_GET(self, body=True):
        data = (folder / self.path[1:]).read_bytes()
        ranged = self.headers.get("Range", "bytes=0-").removeprefix("bytes=")
        first, last = (int(x) if x else len(data) - 1 for x in ranged.split("-"))
        end = min(len(data), last + 1)
        self.send_response(206 if "Range" in self.headers else 200)
        self.send_header("Content-Range", f"bytes {first}-{end - 1}/{len(data)}")
        self.send_header("Content-Length", str(end - first))
        self.send_header("ETag", (folder / "tag").read_text())
        self.end_headers()
        self.wfile.write(data[first:end] if body else b"")
    def do_HEAD(self):
        self.do_GET(body=False)
    def log_message(self, *args):
        pass
server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Mirror)
print(server.server_port, flush=True)
server.serve_forever()
"""


# The ways of a PBF read by byte ranges are those of the file; a file that changes on the
# server stops the read
def test_streamed_pbf_reads_the_ways_of_the_file(
    osm_file, tmp_path, monkeypatch
):
    header, pbf = osmium.io.Header(), tmp_path / "small.osm.pbf"
    header.set("osmosis_replication_timestamp", "2026-11-02T00:00:00Z")
    with osmium.SimpleWriter(str(pbf), header=header) as writer:
        for entity in osmium.FileProcessor(osm_file):
            writer.add(entity)
    (tmp_path / "small.osm.pbf.md5").write_text("9a8b  small.osm.pbf\n")
    (tmp_path / "tag").write_text('"one"')
    mirror = subprocess.Popen(
        [sys.executable, "-c", _MIRROR, str(tmp_path)], stdout=subprocess.PIPE
    )
    try:
        url = f"http://127.0.0.1:{int(mirror.stdout.readline())}/small.osm.pbf"
        layout = str(tmp_path / "layout.json")
        monkeypatch.setattr(osm, "_SCAN", 0)  # bisection down to single bytes
        record = osm.StreamedPbf.download(url, layout)
        assert record == {
            "version": "2026-11-02T00:00:00Z",
            "bytes": pbf.stat().st_size,
            "md5": "9a8b",
        }

        def ways(source):
            junctions, lines = osm.locate_ways(source, {"r": osm.main_roads})
            return list(junctions.ids), list(lines)

        stream = osm.StreamedPbf(layout)
        assert ways(stream) == ways(str(pbf))
        # The world: C++ only, checked before any download; then the regional build
        # with the world's source (a stream) and folder (the runner's)
        with monkeypatch.context() as patch:
            patch.setattr(osm, "has_cpp", lambda: False)
            with pytest.raises(RuntimeError, match="C\\+\\+ backend"):
                osm.PLANET["download"](url, layout)
        monkeypatch.setattr(world_main_roads, "MAX_KM", osm.MAX_KM)
        monkeypatch.setattr(world_main_roads, "MIN_NODES", None)
        world, _ = world_main_roads.build({"roads": layout})
        assert world == osm_main_roads.build({"roads": str(pbf)})[0]
        world_from_local, _ = world_main_roads.build({"roads": str(pbf)})
        assert world_from_local == world
        (tmp_path / "tag").write_text('"two"')
        with pytest.raises(RuntimeError, match="Reading http"):
            ways(stream)
    finally:
        mirror.kill()
        mirror.wait()
