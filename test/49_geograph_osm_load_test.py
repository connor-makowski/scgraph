import os
import subprocess
import sys

import pytest
from helpers import build_main_roads, great_circle_km

from scgraph import GeoGraph
from scgraph.pipelines import geofabrik_multimodal
from scgraph.pipelines.steps import step1_osm_ways
from scgraph.helpers.hilbert import hilbert_order
from scgraph.utils import has_cpp

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
    70: (7.0, 0.0),  # a trunk road through node 72, and a shorter primary road
    71: (7.0, 0.01),
    72: (7.005, 0.005),
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
    (12, [70, 72, 71], {"highway": "trunk"}),
    (13, [70, 71], {"highway": "primary"}),
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


def _edges(geo):
    """Edges as {(osm id, osm id): length}, through the node coordinates."""

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
def whole_network(osm_file):
    """The network of every part of the small file, not only of its largest
    connected part."""
    return GeoGraph.load_from_osm(osm_file, largest_component=False)


@pytest.fixture(scope="module")
def edges(whole_network):
    return _edges(whole_network)


def test_load_from_osm_joins_ways_only_at_shared_nodes(edges):
    # Ways 1 and 2 share node 2; the bridge (5-6) crosses way 1 without a shared node
    assert {(1, 2), (2, 3), (2, 4), (5, 6)} <= set(edges)
    assert {edge for edge in edges if 5 in edge} == {(5, 6), (6, 5)}


def test_load_from_osm_keeps_main_roads_by_default(edges):
    # The residential way 4 (3-7) is left out; only the one-way primary way 5 reaches 7
    assert {edge for edge in edges if 7 in edge} == {(4, 7)}


def test_load_from_osm_does_not_join_across_a_missing_node(edges):
    # Way 7 runs 20 -> 99 -> 21, node 99 is missing from the file
    assert not any(20 in edge or 21 in edge for edge in edges)


def test_an_edge_has_the_length_of_its_drawing(edges):
    # The edge from node 10 to node 12 passes node 11, which lies north of
    # the straight line between them.
    assert edges[(10, 12)] == pytest.approx(_km(10, 11) + _km(11, 12))


def test_a_long_way_is_cut_at_the_first_point_2_km_from_its_start(edges):
    # Way 6 runs 10, 11, 12, 13. Along the way, node 11 is 1.2 km from node
    # 10 and node 12 is 2.5 km from it: the way is cut at node 12.
    assert {edge for edge in edges if 12 in edge} == {
        (10, 12),
        (12, 10),
        (12, 13),
        (13, 12),
    }


def test_default_select_follows_one_way_streets_in_their_legal_direction(edges):
    # Way 5 (4-7) has oneway=yes. Way 8 (30-31) has oneway=-1: traffic runs
    # against its drawing. Way 9 (40-41) is a piece of a roundabout and way
    # 10 (50-51) is a motorway: both are one way without a oneway tag.
    ends_of_one_way_streets = {4, 7, 30, 31, 40, 41, 50, 51}

    assert {edge for edge in edges if set(edge) <= ends_of_one_way_streets} == {
        (4, 7),
        (31, 30),
        (40, 41),
        (50, 51),
    }


def test_select_decides_which_ways_are_kept_and_in_which_directions(osm_file):
    # For a way, `select` returns 0 for both directions, or None to leave
    # the way out.
    def select_primary_roads_as_two_way(tags):
        return 0 if tags.get("highway") == "primary" else None

    network = GeoGraph.load_from_osm(
        osm_file,
        select=select_primary_roads_as_two_way,
        largest_component=False,
    )

    edges = _edges(network)
    # Way 8 joins nodes 30 and 31. It is a primary road with oneway=-1.
    assert {edge for edge in edges if 30 in edge} == {(30, 31), (31, 30)}
    # Way 10, from node 50 to node 51, is the only motorway of the file.
    assert not any(50 in edge or 51 in edge for edge in edges)


def test_an_edge_has_the_class_that_the_default_select_gives_to_its_way(
    whole_network, edges
):
    osm_id = list(whole_network.node_ids)
    classes = {
        (osm_id[edge["origin_id"]], osm_id[edge["destination_id"]]): (
            edge["class"]
        )
        for edge in whole_network.get_edges()
    }

    # The class of a main road is its `highway` value. Way 6 is a trunk road,
    # cut at node 12. Way 10 is the motorway. Every other edge is a primary
    # road: between nodes 70 and 71, the primary road is kept, because it is
    # shorter than the trunk road.
    trunk_road = [(10, 12), (12, 10), (12, 13), (13, 12)]
    assert classes == {
        **dict.fromkeys(edges, "primary"),
        **dict.fromkeys(trunk_road, "trunk"),
        (50, 51): "motorway",
    }


def test_rates_may_name_a_class_that_the_loaded_roads_lack(
    osm_file,
):
    network = GeoGraph.load_from_osm(osm_file)
    # Minutes for 1 km. `per_km` may name any class of
    # `scgraph.pipelines.CLASSES`: these roads have no motorway.
    network.create_metric(
        "minutes", per_km={"road": 2.0, "motorway": 0.5, "off_graph": 4.0}
    )

    # From the point of node 1 to the point of node 4, without an access leg
    route = network.get_shortest_path(
        dict(zip(("latitude", "longitude"), _NODES[1])),
        dict(zip(("latitude", "longitude"), _NODES[4])),
        metric="minutes",
    )

    # The route goes through node 2.
    assert route["metrics"] == {
        "minutes": pytest.approx(2.0 * (_km(1, 2) + _km(2, 4)))
    }


def test_a_select_that_gives_no_class_gives_a_network_without_classes(osm_file):
    def select_primary_roads(tags):
        return 0 if tags.get("highway") == "primary" else None

    network = GeoGraph.load_from_osm(osm_file, select=select_primary_roads)

    assert network.classes == []


def test_tag_keys_name_the_keys_of_the_ways_that_reach_select(osm_file):
    def select_primary_roads_and_ferries(tags):
        is_kept = (
            tags.get("highway") == "primary" or tags.get("route") == "ferry"
        )
        return 0 if is_kept else None

    network = GeoGraph.load_from_osm(
        osm_file,
        select=select_primary_roads_and_ferries,
        tag_keys=("highway", "route"),
        largest_component=False,
    )

    # Way 1 (1-2-3) has the key highway only. The ferry way 11 (60-61) has
    # the key route only: the default tag_keys would leave it out.
    edges = _edges(network)
    assert (1, 2) in edges
    assert (60, 61) in edges


# A pipeline gives its selects to `locate_ways` by mode, then by kind of way:
# the kinds "ways" and "ferries" of the mode "road", for example.
# `load_from_osm` takes one select, so the tests below call `locate_ways`.
def test_a_way_goes_to_the_first_select_that_keeps_it(osm_file):
    def select_primary_roads(tags):
        return 0 if tags.get("highway") == "primary" else None

    # Both selects keep the primary roads, and "ways" comes first.
    selects = {
        "road": {
            "ways": step1_osm_ways.select_main_roads,
            "ferries": select_primary_roads,
        }
    }

    _, polylines = step1_osm_ways.locate_ways(osm_file, selects, ("highway",))

    assert {kind for _, kind, _, _, _ in polylines} == {"ways"}


def test_a_way_that_two_modes_keep_goes_to_each_of_them(osm_file):
    def select_primary_roads(tags):
        return 0 if tags.get("highway") == "primary" else None

    selects = {
        "road": {"ways": step1_osm_ways.select_main_roads},
        "primary_road": {"ways": select_primary_roads},
    }

    _, polylines = step1_osm_ways.locate_ways(osm_file, selects, ("highway",))

    # Way 3 is the primary road from node 5 to node 6. Both modes keep it.
    modes_of_way_3 = {
        mode for mode, _, _, _, vertices in polylines if vertices[0][0] == 5
    }
    assert modes_of_way_3 == {"road", "primary_road"}


def test_ways_of_two_kinds_meet_at_a_node_that_both_have(osm_file):
    def select_side_roads(tags):
        return 0 if tags.get("highway") == "residential" else None

    # The side roads stand for ferries here: a kind beside the kind "ways".
    selects = {
        "road": {
            "ferries": select_side_roads,
            "ways": step1_osm_ways.select_main_roads,
        }
    }

    junctions, _ = step1_osm_ways.locate_ways(osm_file, selects, ("highway",))

    # Node 3 is the end of the main road 1 and of the side road 4.
    # Node 1 is the end of the main road 1 only.
    assert 3 in junctions["road"]
    assert 1 not in junctions["road"]


def test_ways_of_two_modes_do_not_meet_at_a_node_that_both_have(osm_file):
    def select_side_roads(tags):
        return 0 if tags.get("highway") == "residential" else None

    selects = {
        "side_road": {"ways": select_side_roads},
        "road": {"ways": step1_osm_ways.select_main_roads},
    }

    junctions, _ = step1_osm_ways.locate_ways(osm_file, selects, ("highway",))

    # Node 3 is the end of the main road 1 and of the side road 4: one way of
    # each mode.
    assert 3 not in junctions["road"]
    assert 3 not in junctions["side_road"]


# A select function may give the class of a way with its direction. The class
# is a name of `scgraph.pipelines.CLASSES`.
def test_a_select_that_returns_an_unknown_class_name_is_refused(osm_file):
    def select_roads_as_canals(tags):
        return 0, "canal"

    selects = {"road": {"ways": select_roads_as_canals}}

    with pytest.raises(ValueError, match="canal"):
        step1_osm_ways.locate_ways(osm_file, selects, ("highway",))


def test_load_from_osm_keeps_the_largest_strongly_connected_part(osm_file):
    # Ways 1 and 2 (nodes 1 to 4, two-way) are the largest part where every node
    # reaches every other; node 7 is only reached by a one-way street
    geo = GeoGraph.load_from_osm(osm_file)
    assert {node for edge in _edges(geo) for node in edge} == {1, 2, 3, 4}
    assert dict(zip(geo.node_ids, map(tuple, geo.nodes))) == {
        ref: _NODES[ref] for ref in (1, 2, 3, 4)
    }


def test_load_from_osm_stores_its_nodes_in_hilbert_order_with_their_osm_ids(
    whole_network,
):
    nodes = whole_network.nodes
    places_of_node_ids = [_NODES[osm_id] for osm_id in whole_network.node_ids]

    assert hilbert_order(nodes) == list(range(len(nodes)))
    assert places_of_node_ids == [tuple(node) for node in nodes]
    # OSM stores a coordinate as an integer, in 1e-7 degree. A network file
    # stores it the same way, as an int32.
    assert whole_network.coordinate_dtype == "int32"


# A long build keeps files between its steps in a work folder. The next
# build in the same folder reads these files in place of the OSM file.
def test_a_build_resumed_in_its_work_folder_gives_the_same_network(
    osm_file, tmp_path
):
    work_dir = str(tmp_path / "work")
    built_without_folder = build_main_roads({"roads": osm_file})[0]

    first = build_main_roads({"roads": osm_file}, work_dir=work_dir)[0]
    resumed = build_main_roads({"roads": osm_file}, work_dir=work_dir)[0]

    assert first == built_without_folder
    assert resumed == built_without_folder


def test_a_work_folder_is_not_reused_for_another_selection_of_ways(
    osm_file, tmp_path
):
    work_dir = str(tmp_path / "work")
    build_main_roads({"roads": osm_file}, work_dir=work_dir)

    # The file has no railway. A build that took the roads kept in the
    # folder for railways would succeed.
    with pytest.raises(ValueError, match="No way"):
        step1_osm_ways.build_way_pieces(
            osm_file,
            {"rail": {"ways": geofabrik_multimodal.select_rail}},
            ("railway",),
            step1_osm_ways.MAX_KM_BETWEEN_NODES,
            os.path.join(work_dir, "ways"),  # the folder of `build_main_roads`
        )


# The planet file is too large to download: scgraph reads it in place, by
# HTTP byte ranges (`step1_osm_ways.StreamedPbf`). It first finds where the nodes and
# the ways start in the file. In a file above 8 MB, it finds them by bisection.
@pytest.fixture(scope="module")
def planet_folder(osm_file, tmp_path_factory):
    """A folder with `planet.osm.pbf` and its md5 file, as a mirror has them.

    The PBF holds the nodes and the ways of the small file. Filler nodes and
    filler ways, each with a note of 1 kB, make it 9.7 MB: 3 MB of nodes, then
    6.6 MB of ways. The notes are all different and the file is not compressed,
    so that it keeps this size. A filler way has no highway tag: no road
    pipeline keeps it.
    """
    folder = tmp_path_factory.mktemp("planet")
    header = osmium.io.Header()
    header.set("osmosis_replication_timestamp", "2026-11-02T00:00:00Z")
    pbf = osmium.io.File(
        str(folder / "planet.osm.pbf"), "pbf,pbf_compression=none"
    )
    with osmium.SimpleWriter(pbf, header=header) as writer:
        for node in osmium.FileProcessor(osm_file, osmium.osm.NODE):
            writer.add(node)
        for filler in range(3000):
            writer.add_node(
                osmium.osm.mutable.Node(
                    id=1000 + filler,
                    location=(0, 0),
                    tags={"note": f"{filler:08d}" * 125},
                )
            )
        for way in osmium.FileProcessor(osm_file, osmium.osm.WAY):
            writer.add(way)
        for filler in range(6500):
            writer.add_way(
                osmium.osm.mutable.Way(
                    id=1000 + filler,
                    nodes=[1, 2],
                    tags={"note": f"{filler:08d}" * 125},
                )
            )
    (folder / "planet.osm.pbf.md5").write_text("9a8b  planet.osm.pbf\n")
    return folder


# The mirror serves the files of a folder by HTTP, with byte ranges. Every
# answer carries an ETag: the text of the file "tag" of the folder, read at
# each request. A test changes that file to make the PBF a new file for scgraph.
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


@pytest.fixture
def planet_url(planet_folder):
    """The URL of `planet.osm.pbf` on a mirror that serves `planet_folder`.

    The mirror runs in a child process. A thread of this process could not
    answer: osmium keeps the interpreter locked while it waits for the bytes.
    """
    (planet_folder / "tag").write_text('"first upload"')
    mirror = subprocess.Popen(
        [sys.executable, "-c", _MIRROR, str(planet_folder)],
        stdout=subprocess.PIPE,
    )
    try:
        port = int(mirror.stdout.readline())
        yield f"http://127.0.0.1:{port}/planet.osm.pbf"
    finally:
        mirror.kill()
        mirror.wait()


def test_streamed_pbf_download_records_the_version_size_and_md5_of_the_file(
    planet_url, planet_folder, tmp_path
):
    record = step1_osm_ways.StreamedPbf.download(
        planet_url, tmp_path / "layout.json"
    )

    # The version is the time in the header of the PBF. The md5 is the one
    # that the mirror publishes beside the file.
    assert record == {
        "version": "2026-11-02T00:00:00Z",
        "bytes": (planet_folder / "planet.osm.pbf").stat().st_size,
        "md5": "9a8b",
    }


def test_a_pbf_read_by_byte_ranges_gives_the_network_of_its_ways(
    planet_url, osm_file, tmp_path
):
    layout = str(tmp_path / "layout.json")
    step1_osm_ways.StreamedPbf.download(planet_url, layout)

    streamed = build_main_roads({"roads": layout})[0]

    # The PBF holds the ways of the small file, and filler that no select keeps.
    assert streamed == build_main_roads({"roads": osm_file})[0]


def test_a_pbf_that_changes_on_the_server_stops_the_build(
    planet_url, planet_folder, tmp_path
):
    layout = str(tmp_path / "layout.json")
    step1_osm_ways.StreamedPbf.download(planet_url, layout)
    (planet_folder / "tag").write_text('"second upload"')

    with pytest.raises(RuntimeError, match="Reading http"):
        build_main_roads({"roads": layout})


@pytest.mark.skipif(has_cpp(), reason="The C++ extension is built")
def test_the_planet_is_not_streamed_without_the_cpp_extension(tmp_path):
    download_planet = step1_osm_ways.PLANET["download"]

    # The refusal comes before any request: nothing listens at this address.
    with pytest.raises(RuntimeError, match="C\\+\\+ extension"):
        download_planet(
            "http://127.0.0.1:9/planet.osm.pbf", str(tmp_path / "layout.json")
        )
