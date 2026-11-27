"""Tests of `scgraph.pipelines.derived_networks`: a network file derived from a parent file."""

import json
import shutil
import subprocess
import sys
from array import array
from pathlib import Path

import pytest

from scgraph import GeoGraph, network_file, pipelines
from scgraph.pipelines import derived_networks

# The parent network of these tests. A node is `id: [latitude, longitude]`.
# A road joins the nodes 1, 2 and 3 along the equator. A second road goes
# from node 2 to node 4, two degrees north. Node 10 is a port. It joins node
# 3 to the sea lane from node 20 to node 21, which is at 50 degrees east.
# A flight joins the airports 30 and 31.
ROAD_NODES = {1: [0, 0], 2: [0, 0.03], 3: [0, 0.06], 4: [2, 0.03]}
PORT_NODES = {10: [0, 0.07]}
SEA_NODES = {20: [-0.1, 0.07], 21: [-0.1, 50]}
AIRPORT_NODES = {30: [0.5, 0.5], 31: [0.5, 40]}
NODES = ROAD_NODES | PORT_NODES | SEA_NODES | AIRPORT_NODES
# Each link is (node, node, km), and gives one edge each way.
ROAD_LINKS = [(1, 2, 3.0), (2, 3, 3.0), (2, 4, 222.0)]
PORT_AND_SEA_LINKS = [(3, 10, 1.0), (10, 20, 11.0), (20, 21, 5550.0)]
FLIGHT_LINKS = [(30, 31, 4392.0)]
# The road from node 1 to node 2 bends at these two points: the only edge
# shape. The road from node 2 to node 1 passes them in the reverse order.
BEND = [[0.01, 0.01], [0.01, 0.02]]
MODES = [
    {"name": "road", "source": "osm"},
    {"name": "port", "source": "ports"},
    {"name": "sea", "source": "sea"},
    {"name": "airport", "source": "airports"},
]
# No mode names the sources `flights` and `land`, as in a multimodal pipeline.
SOURCES = [
    {"name": name}
    for name in ("osm", "ports", "sea", "airports", "flights", "land")
]
# The bbox (south, west, north, east) holds the nodes 1, 2, 3 and 30. The
# nodes 4, 21 and 31 are outside it.
BBOX = (-1, -1, 1, 1)


@pytest.fixture(scope="module")
def parent_file(tmp_path_factory):
    """The network file of the parent network, with the header that a
    pipeline writes."""
    position = {node: u for u, node in enumerate(NODES)}
    graph, shapes = [{} for _ in NODES], [{} for _ in NODES]
    for a, b, km in ROAD_LINKS + PORT_AND_SEA_LINKS + FLIGHT_LINKS:
        graph[position[a]][position[b]] = graph[position[b]][position[a]] = km
    shapes[position[1]][position[2]] = BEND
    shapes[position[2]][position[1]] = BEND[::-1]
    path = str(tmp_path_factory.mktemp("parent") / "parent.scgraph")
    GeoGraph(
        graph=graph,
        nodes=list(NODES.values()),
        intermediate_nodes=shapes,
        external_node_ids=list(NODES),
        node_mode_ids=[0] * 4 + [1] + [2] * 2 + [3] * 2,  # rows of MODES
        node_modes=MODES,
        coordinate_dtype="int32",
    ).save_as_scgraph(
        path,
        metadata=pipelines.build_metadata(
            "osm_world_multimodal", None, 1, SOURCES
        ),
    )
    return path


# The networks of these tests have fewer than 10 nodes, the default smallest
# component. So each derivation that keeps nodes gives `min_component_nodes=1`.
@pytest.fixture(scope="module")
def sea_file(parent_file, tmp_path_factory):
    """The file derived from the parent file with the modes of the sea."""
    path = str(tmp_path_factory.mktemp("sea") / "sea.scgraph")
    derived_networks.derive_network_file(
        parent_file, path, node_modes=["sea", "port"], min_component_nodes=1
    )
    return path


@pytest.fixture(scope="module")
def bbox_file(parent_file, tmp_path_factory):
    """The file derived from the parent file with the bbox."""
    path = str(tmp_path_factory.mktemp("bbox") / "bbox.scgraph")
    derived_networks.derive_network_file(
        parent_file, path, bbox=BBOX, min_component_nodes=1
    )
    return path


def _nodes_by_mode(file):
    """The nodes of a network file: for each mode, the sorted ids of its nodes."""
    network = GeoGraph.load_from_scgraph(file)
    nodes = {mode["name"]: [] for mode in network.node_modes}
    for row, node in zip(network.node_mode_ids, network.external_node_ids):
        nodes[network.node_modes[row]["name"]].append(node)
    return {mode: sorted(ids) for mode, ids in nodes.items()}


def _km_from_node_1_to_node_21(file):
    """The length of the shortest route of a network file from the west end
    of the road to the east end of the sea lane."""
    return GeoGraph.load_from_scgraph(file).get_shortest_path(
        {"latitude": 0, "longitude": 0},
        {"latitude": -0.1, "longitude": 50},
        snap_to_node_modes=["road", "sea"],
    )["length"]


def test_a_derived_file_holds_only_the_nodes_of_the_modes_asked(sea_file):
    assert _nodes_by_mode(sea_file) == {"port": [10], "sea": [20, 21]}


def test_a_derived_file_cites_only_the_sources_that_serve_it(sea_file):
    sources = GeoGraph.get_scgraph_info(sea_file)["sources"]

    # Only the modes `road` and `airport`, which are removed, use `osm`,
    # `airports` and `flights`: a flight joins two airports.
    assert sources == [{"name": "ports"}, {"name": "sea"}, {"name": "land"}]


def test_a_derived_file_with_airports_cites_the_source_of_the_flights(
    bbox_file,
):
    sources = GeoGraph.get_scgraph_info(bbox_file)["sources"]

    # The bbox removes no mode, so every source serves the file.
    assert sources == SOURCES


def test_a_bbox_cuts_the_roads_and_keeps_every_sea_node(bbox_file):
    # Node 4 is a road node north of the bbox. Node 21 is a sea node east of
    # the bbox, and node 31 an airport east of it. Node 2 lost its road to
    # node 4, and it stays.
    assert _nodes_by_mode(bbox_file) == {
        "road": [1, 2, 3],
        "port": [10],
        "sea": [20, 21],
        "airport": [30, 31],
    }


def test_a_route_of_a_derived_file_has_its_length_in_the_parent_file(bbox_file):
    # The links of the parent network on this route: 3 + 3 km of road, 1 + 11
    # km at the port, 5550 km of sea
    assert _km_from_node_1_to_node_21(bbox_file) == pytest.approx(5568.0)


# A network file stores the bend once, for one direction of the road. The
# derived file and a load of its roads must keep the bend in both directions.
def test_the_roads_of_a_derived_file_keep_their_bend_both_ways(bbox_file):
    roads = GeoGraph.load_from_scgraph(bbox_file, node_modes=["road"])

    node_1, node_2 = map(list(roads.external_node_ids).index, (1, 2))
    assert roads.intermediate_nodes[node_1][node_2] == BEND
    assert roads.intermediate_nodes[node_2][node_1] == BEND[::-1]


def _name_each_edge(arrays):
    """A name for each edge of the arrays of a network, in the order of the
    edges: "1-2" for the edge from node 1 to node 2."""
    ids, node_first_edge_ids, edge_destination_node_ids = (
        arrays[name]
        for name in (
            "external_node_ids",
            "node_first_edge_ids",
            "edge_destination_node_ids",
        )
    )
    return [
        f"{ids[u]}-{ids[edge_destination_node_ids[edge]]}"
        for u in range(len(ids))
        for edge in range(node_first_edge_ids[u], node_first_edge_ids[u + 1])
    ]


def test_a_derived_file_keeps_the_class_of_each_edge_and_the_list_of_classes(
    parent_file, tmp_path
):
    # The parent file again, where each of the 14 edges has a class of its own.
    # The name of the class is the name of the edge, and its mode is "road".
    arrays, metadata = network_file.read(parent_file)
    class_names = _name_each_edge(arrays)
    classes = [{"name": name, "edge_mode": "road"} for name in class_names]
    arrays["edge_class_ids"] = array("B", range(len(class_names)))
    classed_file = str(tmp_path / "classed.scgraph")
    network_file.write(classed_file, arrays, metadata | {"classes": classes})
    bbox_file = str(tmp_path / "bbox.scgraph")

    derived_networks.derive_network_file(
        classed_file, bbox_file, bbox=BBOX, min_component_nodes=1
    )

    # The bbox removes node 4 and its two edges, so the other edges move up.
    arrays, metadata = network_file.read(bbox_file)
    assert metadata["classes"] == classes
    assert [
        class_names[row] for row in arrays["edge_class_ids"]
    ] == _name_each_edge(arrays)


def test_a_query_point_snaps_to_its_closest_node_in_a_derived_file_without_roads(
    sea_file,
):
    sea_lanes = GeoGraph.load_from_scgraph(sea_file)

    # The origin is 0.001 degree east of the port, node 10. In the parent file,
    # which has roads, it snaps to the road node 3.
    route = sea_lanes.get_shortest_path(
        {"latitude": 0, "longitude": 0.071},
        {"latitude": -0.1, "longitude": 50},
        output_path=True,
    )

    assert sea_lanes.nodes[route["path"][0]] == PORT_NODES[10]


def test_a_file_without_shapes_holds_the_network_of_the_file_with_shapes(
    parent_file, bbox_file, tmp_path
):
    no_shapes_file = str(tmp_path / "bbox.no_shapes.scgraph")

    derived_networks.derive_network_file(
        parent_file,
        no_shapes_file,
        bbox=BBOX,
        save_intermediate_nodes=False,
        min_component_nodes=1,
    )

    assert (
        GeoGraph.get_scgraph_info(no_shapes_file)["has_intermediate_nodes"]
        is False
    )
    assert _km_from_node_1_to_node_21(
        no_shapes_file
    ) == _km_from_node_1_to_node_21(bbox_file)


def test_the_header_of_a_derived_file_records_its_derivation(
    parent_file, bbox_file
):
    derivation = GeoGraph.get_scgraph_info(bbox_file)["derivation"]

    assert derivation == {
        "parent_content_sha256": GeoGraph.get_scgraph_info(parent_file)[
            "content_sha256"
        ],
        "node_modes": None,
        "bbox": list(BBOX),
        "min_component_nodes": 1,
    }


# A one-way fork with a turn restriction, as a build stores it
# (`scgraph/turn_restrictions.py`). The street from W enters the junction J, and
# two streets leave J: to A and to B. The streets from A to B and from B to W
# let a route come back to W. Each street is 1 km long. The turn from W to B is
# forbidden, so J has two nodes, with the external id 20. The street from W
# enters the second one, which has no edge to B. No edge enters the first one.
# A parent file has several node modes and edge shapes: the network also has
# one sea node, and no edge has a shape point.
def test_a_derived_file_keeps_every_node_of_a_junction(tmp_path):
    w, first_node_of_j, added_node_of_j, a, b = range(5)
    fork = GeoGraph(
        graph=[
            {added_node_of_j: 1.0},
            {a: 1.0, b: 1.0},
            {a: 1.0},
            {b: 1.0},
            {w: 1.0},
            {},
        ],
        nodes=[
            [0, 0],
            [0, 0.01],
            [0, 0.01],
            [0.01, 0.02],
            [-0.01, 0.02],
            [-1, 0],
        ],
        intermediate_nodes=[{} for _ in range(6)],
        external_node_ids=[10, 20, 20, 30, 40, 50],
        node_mode_ids=[0] * 5 + [1],
        node_modes=[
            {"name": "road", "source": "osm", "has_turn_restrictions": True},
            {"name": "sea", "source": "sea"},
        ],
        coordinate_dtype="int32",
    )
    parent_file = str(tmp_path / "fork.scgraph")
    fork.save_as_scgraph(
        parent_file,
        metadata=pipelines.build_metadata(
            "osm_world_multimodal", None, 1, SOURCES
        ),
    )
    derived_file = str(tmp_path / "derived.scgraph")

    # `node_modes` takes one name, as `GeoGraph.load_from_scgraph` does
    derived_networks.derive_network_file(
        parent_file, derived_file, node_modes="road", min_component_nodes=2
    )

    # A route that starts at J takes the street to B
    route = GeoGraph.load_from_scgraph(derived_file).get_shortest_path(
        {"latitude": 0, "longitude": 0.01},
        {"latitude": -0.01, "longitude": 0.02},
    )
    assert route["length"] == pytest.approx(1.0)


def test_a_derivation_that_keeps_no_node_is_refused(parent_file, tmp_path):
    # The network of the parent file has 8 nodes. The smallest component that a
    # derivation keeps has 10 nodes, unless the call gives another size.
    with pytest.raises(ValueError, match="no component of 10 nodes"):
        derived_networks.derive_network_file(
            parent_file, str(tmp_path / "empty.scgraph")
        )


# The pipeline of a parent file gives its land node modes. The pipeline
# eurostat_sea_lanes builds a network with one node mode, so it gives none.
# This version of scgraph has no pipeline atlantis_multimodal.
@pytest.mark.parametrize(
    "pipeline_name", ["eurostat_sea_lanes", "atlantis_multimodal"]
)
def test_a_parent_file_of_a_pipeline_without_land_modes_is_refused(
    parent_file, tmp_path, pipeline_name
):
    other_parent_file = str(tmp_path / "other_parent.scgraph")
    GeoGraph.load_from_scgraph(parent_file).save_as_scgraph(
        other_parent_file,
        metadata=pipelines.build_metadata(pipeline_name, None, 1, SOURCES),
    )

    with pytest.raises(ValueError, match=f"'{pipeline_name}'.*LAND_MODES"):
        derived_networks.derive_network_file(
            other_parent_file,
            str(tmp_path / "derived.scgraph"),
            bbox=BBOX,
            min_component_nodes=1,
        )


def test_a_bbox_with_its_south_above_its_north_is_refused(
    parent_file, tmp_path
):
    south, west, north, east = 1, -1, -1, 1

    with pytest.raises(ValueError, match="south above its north"):
        derived_networks.derive_network_file(
            parent_file,
            str(tmp_path / "bbox.scgraph"),
            bbox=(south, west, north, east),
        )


# The network of the validation test, at the ends of three cases that the
# pipeline `osm_region_multimodal` lists for `europe/denmark`. A road of 100 + 87 km
# joins Aarhus to Copenhagen. It passes through a road node north of Denmark.
# - `aarhus_to_copenhagen_intermodal` asks for a route of 186.9 km, within
#   10 %, between the two towns. This network passes the case.
# - `arhus_port` asks that the port of Aarhus is joined to a road, to a
#   railway and to a sea lane. `aalborg_airport` asks for an airport at
#   Aalborg. This network fails the two cases.
AARHUS, COPENHAGEN = [56.1629, 10.2039], [55.6761, 12.5683]
ARHUS_PORT, NORTH_OF_DENMARK = [56.15, 10.216667], [58, 11.4]
# This bbox holds the two towns and the port. The node north of Denmark and
# Aalborg are outside it.
DENMARK_BBOX = (55, 9, 57, 13)


@pytest.fixture(scope="module")
def denmark_file(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("denmark") / "denmark.scgraph")
    GeoGraph(
        graph=[{1: 1.6, 2: 100.0}, {0: 1.6}, {0: 100.0, 3: 87.0}, {2: 87.0}],
        nodes=[AARHUS, ARHUS_PORT, NORTH_OF_DENMARK, COPENHAGEN],
        intermediate_nodes=[{}, {}, {}, {}],
        node_mode_ids=[0, 1, 0, 0],
        node_modes=[{"name": "road"}, {"name": "port"}],
        coordinate_dtype="int32",
    ).save_as_scgraph(
        path,
        metadata=pipelines.build_metadata(
            "osm_region_multimodal", "europe/denmark", 1, []
        ),
    )
    return path


def test_a_derived_file_fails_only_for_a_case_that_its_parent_file_passes(
    denmark_file, tmp_path
):
    whole_file = str(tmp_path / "whole.scgraph")
    cut_file = str(tmp_path / "cut.scgraph")
    derived_networks.derive_network_file(
        denmark_file, whole_file, min_component_nodes=1
    )
    derived_networks.derive_network_file(
        denmark_file, cut_file, bbox=DENMARK_BBOX, min_component_nodes=1
    )

    # The whole network passes one case and fails two, as its parent file.
    derived_networks.validate_derived_network_file(whole_file, denmark_file)
    # The bbox cuts the road between the two towns. The message names this
    # case, and not the case of the port, which the parent file fails too.
    with pytest.raises(
        RuntimeError, match="passes: aarhus_to_copenhagen_intermodal$"
    ):
        derived_networks.validate_derived_network_file(cut_file, denmark_file)


# A small world for the files of a network release, with the six modes of
# `osm_world_multimodal`. Each of the eight regions of `DERIVED_NETWORKS` has a
# road of 10 nodes. Europe also has a railway of 10 nodes. A port at the end of
# the road of Europe starts a sea lane of 10 nodes. Two neighbours are 1 km
# apart. Each derived network then has components of at least 10 nodes, the
# smallest that a derivation keeps by default.
WORLD_MODES = [
    {"name": name}
    for name in ("road", "rail", "sea", "port", "airport", "rail_terminal")
]
# One point inside the bbox of each region, where its road starts
REGION_POINTS = {
    "europe": [50, 10],
    "north_america": [40, -100],
    "south_america": [-20, -60],
    "africa": [0, 20],
    "west_south_asia": [25, 60],
    "east_southeast_asia": [20, 110],
    "north_asia": [60, 100],
    "oceania": [-25, 135],
}


# What a pipeline records in the header of the file that it builds: its docstring,
# and each source with its credit and its license
WORLD_DESCRIPTION = (
    "The roads, the railways and the sea lanes of a small world."
)
WORLD_SOURCE = {"name": "osm", "credit": "The mappers", "license": "ODbL-1.0"}


def _write_small_world(path, pipeline_name):
    """Write the small world to `path`, as a file that the pipeline
    `pipeline_name` built."""
    nodes, node_mode_ids, links = [], [], []

    def add_chain(start, mode, count=10):
        first = len(nodes)
        latitude, longitude = start
        nodes.extend([latitude, longitude + 0.01 * i] for i in range(count))
        node_mode_ids.extend([mode] * count)
        links.extend((u, u + 1) for u in range(first, first + count - 1))
        return first + count - 1  # the last node of the chain

    for name, point in REGION_POINTS.items():
        end_of_road = add_chain(point, mode=0)
        if name == "europe":
            add_chain([51, 10], mode=1)  # the railway
            port = add_chain([50, 10.1], mode=3, count=1)
            links.append((end_of_road, port))
            links.append((port, len(nodes)))  # to the first node of the lane
            add_chain([50, 10.11], mode=2)
    graph = [{} for _ in nodes]
    for u, v in links:
        graph[u][v] = graph[v][u] = 1.0
    shapes = [{} for _ in nodes]
    shapes[0][1] = shapes[1][0] = [[50.001, 10.005]]  # one edge has a shape
    GeoGraph(
        graph=graph,
        nodes=nodes,
        intermediate_nodes=shapes,
        node_mode_ids=node_mode_ids,
        node_modes=WORLD_MODES,
        coordinate_dtype="int32",
    ).save_as_scgraph(
        path,
        metadata=pipelines.build_metadata(
            pipeline_name, None, 1, [WORLD_SOURCE], WORLD_DESCRIPTION
        ),
    )
    return path


@pytest.fixture(scope="module")
def small_world_file(tmp_path_factory):
    folder = tmp_path_factory.mktemp("world")
    return _write_small_world(
        str(folder / "world_multimodal.scgraph"), "osm_world_multimodal"
    )


# The ten derived networks of a network release
DERIVED_NAMES = ["world_sea", "world_rail", *REGION_POINTS]


def test_a_network_release_gets_two_files_for_each_derived_network(
    small_world_file, tmp_path
):
    written = derived_networks.derive_network_release_files(
        small_world_file, tmp_path, run_validation_cases=False
    )

    assert [Path(path).name for path in written] == [
        f"{name}{suffix}.scgraph"
        for name in DERIVED_NAMES
        for suffix in ("", ".no_shapes")
    ] + ["world_multimodal.no_shapes.scgraph"]


# `utils/draft_network_release.py` writes the index of a network release from the
# files of a run of the workflow `build_networks.yml`. The world file without shapes
# is derived from the world file, and it is not a derived network.
def test_the_index_of_a_network_release_describes_every_file(
    small_world_file, tmp_path
):
    files, previous = tmp_path / "files", tmp_path / "previous"
    files.mkdir()
    previous.mkdir()
    shutil.copy(small_world_file, files)
    derived_networks.derive_network_release_files(
        small_world_file, files, run_validation_cases=False
    )

    subprocess.run(
        [
            sys.executable,
            Path(__file__).parent.parent / "utils" / "draft_network_release.py",
            files,
            previous,
            tmp_path / "release",
            "networks-2000.01.01",
            "the commit of the run",
        ],
        check=True,
    )

    index = json.loads((tmp_path / "release" / "networks.json").read_text())
    description = {
        network["file"]: network["description"] for network in index["networks"]
    }
    assert (
        description["world_multimodal.no_shapes.scgraph.gz"]
        == description["world_multimodal.scgraph.gz"]
        == WORLD_DESCRIPTION
    )
    assert description["europe.no_shapes.scgraph.gz"] == (
        derived_networks.describe_derived_network("europe")
    )


def test_a_derived_network_has_the_modes_or_the_bbox_of_its_name(
    small_world_file, tmp_path
):
    written = derived_networks.derive_network_release_files(
        small_world_file,
        tmp_path,
        ["europe", "world_sea"],
        run_validation_cases=False,
    )

    europe, europe_without_shapes, world_sea, _ = map(
        GeoGraph.get_scgraph_info, written
    )
    # The road and the railway of Europe, the port and the sea lane. The
    # roads of the seven other regions are outside the bbox.
    assert (europe["nodes"], europe["has_intermediate_nodes"]) == (31, True)
    assert (
        europe_without_shapes["nodes"],
        europe_without_shapes["has_intermediate_nodes"],
    ) == (
        31,
        False,
    )
    # `world_sea` keeps the port and the sea lane.
    assert world_sea["nodes"] == 11
    assert world_sea["derivation"]["node_modes"] == ["sea", "port"]


def test_a_name_that_is_not_a_derived_network_is_refused(
    small_world_file, tmp_path
):
    with pytest.raises(ValueError, match="Unknown derived network 'atlantis'"):
        derived_networks.derive_network_release_files(
            small_world_file, tmp_path, ["atlantis"]
        )


# The command writes the two files of each derived network that it names. With
# `--no-validate`, it does not check them against the cases of the pipeline.
def test_the_derive_command_writes_without_validation_when_asked(
    small_world_file, tmp_path, capsys
):
    derived_networks.main(
        [
            small_world_file,
            str(tmp_path),
            "world_sea",
            "--no-validate",
        ]
    )

    printed = capsys.readouterr().out.split()
    assert printed == [
        str(tmp_path / "world_sea.scgraph"),
        str(tmp_path / "world_sea.no_shapes.scgraph"),
    ]
    assert all(Path(path).is_file() for path in printed)
