import copy
import hashlib
import json
import os
import pickle
from array import array

import pytest

from scgraph import GeoGraph, network_file
from scgraph.helpers.hilbert import get_hilbert_order
from scgraph.utils import has_cpp

# The small network has four nodes, listed in Hilbert order. Node 0 has a
# one-way edge to node 2 and a two-way edge with node 1, with an integer weight.
# Node 3 has no edge. Only the edge from 0 to 1 has a shape.
SMALL_GRAPH = [{2: 1.25, 1: 5}, {0: 5}, {}, {}]
SMALL_NODES = [[0.0, 0.0], [0.0, 0.01], [0.01, 0.0], [1.0, 1.0]]
# In floating point, 0.0029 * 1e7 is just below 29000. A file that stores
# 1e-7 degree must round this latitude, not cut it.
SMALL_SHAPES = [{1: [[0.0029, 0.0058]]}, {}, {}, {}]
# The sources that `build_geograph` records look like these. A network built
# from many extracts keeps them all.
SOURCES = [
    {
        "name": f"region-{i}",
        "url": f"https://download.geofabrik.de/region-{i}-latest.osm.pbf",
        "sha256": f"{i:064x}",
        "credit": "© OpenStreetMap contributors",
        "license": "ODbL-1.0",
    }
    for i in range(100)
]


def _small(external_node_ids=None):
    return GeoGraph(
        graph=[dict(row) for row in SMALL_GRAPH],
        nodes=[list(node) for node in SMALL_NODES],
        intermediate_nodes=SMALL_SHAPES,
        geograph_units="mi",
        external_node_ids=external_node_ids,
    )


def _route_0_to_1(geograph):
    # Through the edge 0 -> 1, which has a shape
    return geograph.get_shortest_path(
        origin_node={"latitude": 0, "longitude": 0},
        destination_node={"latitude": 0, "longitude": 0.01},
        node_addition_type="closest",
        destination_node_addition_type="closest",
    )["coordinate_path"]


@pytest.fixture(scope="module")
def small_file(tmp_path_factory):
    """The path of a file of the small network, saved with its sources. The
    tests read this file and do not change it."""
    path = str(tmp_path_factory.mktemp("small") / "small.scgraph")
    _small().save_as_scgraph(path, metadata={"sources": SOURCES})
    return path


def test_a_saved_network_is_read_back_as_it_was_saved(small_file):
    loaded = GeoGraph.load_from_scgraph(small_file)

    assert loaded.graph_object.graph == SMALL_GRAPH
    assert loaded.nodes == SMALL_NODES
    assert loaded.geograph_units == "mi"
    assert loaded.intermediate_nodes == SMALL_SHAPES
    assert loaded.metadata == {"sources": SOURCES}


def test_a_network_saved_without_its_shapes_is_read_back_without_shapes(
    tmp_path,
):
    path = str(tmp_path / "small.scgraph")
    _small().save_as_scgraph(path, save_intermediate_nodes=False)

    loaded = GeoGraph.load_from_scgraph(path)

    assert loaded.intermediate_nodes is None
    assert loaded.graph_object.graph == SMALL_GRAPH


def test_a_loaded_network_is_saved_again_with_its_sources(small_file, tmp_path):
    again = str(tmp_path / "again.scgraph")

    GeoGraph.load_from_scgraph(small_file).save_as_scgraph(again)

    assert GeoGraph.get_scgraph_info(again)["sources"] == SOURCES


def test_shapes_read_from_a_file_behave_as_the_list_that_was_saved(small_file):
    shapes = GeoGraph.load_from_scgraph(small_file).intermediate_nodes

    assert shapes[-4] == SMALL_SHAPES[0]
    assert shapes[1:3] == SMALL_SHAPES[1:3]
    assert type(copy.copy(shapes)) is list
    assert copy.deepcopy(shapes) == SMALL_SHAPES


# A node keeps the id that the geograph was given for it. Without ids, the id
# of a node is its position. A node added since gets a negative id, and a save
# keeps them all.
@pytest.mark.parametrize(
    "external_node_ids, ids_before_the_addition",
    [
        pytest.param([7, 5, 3, 1], [7, 5, 3, 1], id="ids within 32 bits"),
        pytest.param(
            [2**40, 5, 3, 1], [2**40, 5, 3, 1], id="an id beyond 32 bits"
        ),
        pytest.param(None, [0, 1, 2, 3], id="no ids: the positions"),
    ],
)
def test_external_node_ids_and_the_id_of_an_added_node_are_kept_through_saves(
    tmp_path, external_node_ids, ids_before_the_addition
):
    path, again = str(tmp_path / "small.scgraph"), str(
        tmp_path / "again.scgraph"
    )
    _small(external_node_ids).save_as_scgraph(path)
    loaded = GeoGraph.load_from_scgraph(path)
    loaded.add_coord_node({"latitude": 2.0, "longitude": 2.0}, auto_edge=False)
    # Saved to another file: Windows does not replace a mapped file
    loaded.save_as_scgraph(again)

    assert GeoGraph.load_from_scgraph(again).external_node_ids == [
        *ids_before_the_addition,
        -1,
    ]


# OpenStreetMap has node ids beyond 32 bits. No call of GeoGraph shows the
# size of the ids in the file: the test reads the arrays of the file.
@pytest.mark.parametrize(
    "external_node_ids, bytes_per_id",
    [
        pytest.param([7, 5, 3, 1], 4, id="ids within 32 bits"),
        pytest.param([2**40, 5, 3, 1], 8, id="an id beyond 32 bits"),
    ],
)
def test_external_node_ids_are_stored_in_32_bits_when_they_all_fit_and_else_in_64(
    tmp_path, external_node_ids, bytes_per_id
):
    path = str(tmp_path / "small.scgraph")
    _small(external_node_ids).save_as_scgraph(path)

    arrays, _ = network_file.read(path)

    assert arrays["external_node_ids"].itemsize == bytes_per_id


def _small_listed_backwards():
    """The small network with its nodes listed from the last to the first:
    node i of the small network is node 3 - i here."""
    return GeoGraph(
        graph=[{}, {}, {3: 5}, {1: 1.25, 2: 5}],
        nodes=[[1.0, 1.0], [0.01, 0.0], [0.0, 0.01], [0.0, 0.0]],
        intermediate_nodes=[{}, {}, {}, {2: [[0.0029, 0.0058]]}],
    )


def test_a_file_lists_the_nodes_in_hilbert_order(tmp_path):
    # The small network lists its nodes in Hilbert order: the file of the
    # same network listed backwards holds the small network.
    path = str(tmp_path / "small.scgraph")
    _small_listed_backwards().save_as_scgraph(path)

    loaded = GeoGraph.load_from_scgraph(path)

    assert loaded.nodes == SMALL_NODES
    assert loaded.graph_object.graph == SMALL_GRAPH
    assert loaded.intermediate_nodes == SMALL_SHAPES
    # A node moved by the save keeps its former position as its id.
    assert list(loaded.external_node_ids) == [3, 2, 1, 0]


def test_a_save_does_not_change_the_order_of_the_nodes_of_the_geograph(
    tmp_path,
):
    backwards = _small_listed_backwards()

    backwards.save_as_scgraph(str(tmp_path / "small.scgraph"))

    assert backwards.nodes == [[1.0, 1.0], [0.01, 0.0], [0.0, 0.01], [0.0, 0.0]]
    assert backwards.graph_object.graph == [{}, {}, {3: 5}, {1: 1.25, 2: 5}]


both_coordinate_dtypes = pytest.mark.parametrize(
    "coordinate_dtype", ["float64", "int32"]
)


@both_coordinate_dtypes
def test_a_loaded_file_is_saved_again_as_the_same_file(
    tmp_path, coordinate_dtype
):
    # The second file has the digest of the first: the same bytes, so the
    # same order of nodes, the same ids and the same dtype of coordinates
    path, again = str(tmp_path / "small.scgraph"), str(
        tmp_path / "again.scgraph"
    )
    digest = _small_listed_backwards().save_as_scgraph(
        path, coordinate_dtype=coordinate_dtype
    )

    digest_again = GeoGraph.load_from_scgraph(path).save_as_scgraph(again)

    assert digest_again == digest


# The sea network has two nodes. The road network has two nodes, then gets a
# node without a mode, a road node, and the sea network. The merge joins the
# two networks through a new node, of the mode "port".
@pytest.fixture(scope="module")
def sea():
    sea = GeoGraph(
        graph=[{1: 1.0}, {0: 1.0}],
        nodes=[[1, 0], [1, 1]],
        node_modes=[{"name": "sea", "source": "lanes"}],
    )
    sea.metadata = {"sources": [{"name": "lanes"}]}
    return sea


@pytest.fixture(scope="module")
def road_merged_with_sea(sea):
    road = GeoGraph(
        graph=[{1: 1.0}, {0: 1.0}],
        nodes=[[0, 1], [0, 0]],
        node_modes=[{"name": "road", "source": "osm"}],
    )
    road.metadata = {"sources": [{"name": "osm"}]}
    road.add_coord_node({"latitude": 0, "longitude": 3})
    road.add_coord_node({"latitude": 0, "longitude": 2}, node_mode="road")
    road.merge_with_other_geograph(
        sea, connection_nodes=[[0.5, 0.5]], node_mode="port"
    )
    return road


@pytest.fixture(scope="module")
def road_and_sea_file(road_merged_with_sea, tmp_path_factory):
    path = str(tmp_path_factory.mktemp("modes") / "modes.scgraph")
    road_merged_with_sea.save_as_scgraph(path)
    return path


def test_additions_and_a_merge_give_each_node_its_node_mode_and_cite_both_sources(
    road_merged_with_sea,
):
    road = road_merged_with_sea

    # The modes of the additions and of the merge come after the road mode.
    assert road.node_modes == [
        {"name": "road", "source": "osm"},
        {"name": None},
        {"name": "port"},
        {"name": "sea", "source": "lanes"},
    ]
    # Two road nodes, the node without a mode, the road node added after it,
    # the port node of the merge, then the two sea nodes
    assert list(road.node_mode_ids) == [0, 0, 1, 0, 2, 3, 3]
    # Each mode names its source, so the merged geograph needs both sources
    assert road.metadata["sources"] == [{"name": "osm"}, {"name": "lanes"}]


def test_a_merge_leaves_the_modes_of_the_other_geograph(
    sea, road_merged_with_sea
):
    assert list(sea.node_mode_ids) == [0, 0]


def test_a_file_lists_the_nodes_node_mode_by_node_mode_with_their_node_modes_and_ids(
    road_merged_with_sea, road_and_sea_file
):
    road = road_merged_with_sea

    loaded = GeoGraph.load_from_scgraph(road_and_sea_file)

    assert loaded.node_modes == road.node_modes
    assert list(loaded.node_mode_ids) == [0, 0, 0, 1, 2, 3, 3]
    # Each node keeps its mode and its id, whatever its new position.
    assert sorted(
        zip(loaded.node_mode_ids, loaded.external_node_ids, loaded.nodes)
    ) == sorted(zip(road.node_mode_ids, road.external_node_ids, road.nodes))


def test_a_file_loaded_on_one_node_mode_has_the_nodes_of_that_node_mode_only(
    road_and_sea_file,
):
    # Loaded lazily: the file is read when the nodes are first asked for
    roads = GeoGraph.load_from_scgraph(
        road_and_sea_file, lazy=True, node_modes="road"
    )

    assert sorted(roads.nodes) == [[0, 0], [0, 1], [0, 2]]


def test_a_file_loaded_on_one_node_mode_routes_on_that_node_mode(
    road_and_sea_file,
):
    # The destination is a sea node of the file. On roads only, the route
    # ends at the road node closest to it, (0, 1).
    roads = GeoGraph.load_from_scgraph(
        road_and_sea_file, lazy=True, node_modes="road"
    )

    route = roads.get_shortest_path(
        origin_node={"latitude": 0, "longitude": 0},
        destination_node={"latitude": 1, "longitude": 1},
        node_addition_type="closest",
        destination_node_addition_type="closest",
    )

    assert route["coordinate_path"] == [[0, 0], [0, 0], [0, 1], [1, 1]]


def test_a_node_of_a_257th_node_mode_is_refused_and_changes_nothing():
    node_modes = [{"name": str(i)} for i in range(256)]
    geograph = GeoGraph(graph=[{}], nodes=[[0, 0]], node_modes=node_modes)

    with pytest.raises(ValueError, match="at most 256 node modes"):
        geograph.add_coord_node(
            {"latitude": 0, "longitude": 1}, node_mode="new"
        )

    assert (len(geograph.nodes), len(geograph.node_modes)) == (1, 256)


def test_a_merge_that_needs_a_257th_node_mode_is_refused_and_changes_nothing():
    # 200 modes, 60 other modes and the mode of the connection node: 261
    road_modes = [{"name": f"road {i}"} for i in range(200)]
    sea_modes = [{"name": f"sea {i}"} for i in range(60)]
    road = GeoGraph(graph=[{}], nodes=[[0, 0]], node_modes=road_modes)
    sea = GeoGraph(graph=[{}], nodes=[[1, 1]], node_modes=sea_modes)

    with pytest.raises(ValueError, match="at most 256 node modes"):
        road.merge_with_other_geograph(sea, connection_nodes=[[0.5, 0.5]])

    assert (len(road.nodes), len(road.node_modes)) == (1, 200)


def test_nodes_appended_directly_are_saved_in_the_first_node_mode(tmp_path):
    geo = GeoGraph(
        graph=[{}, {}],
        nodes=[[0, 0], [1, 1]],
        node_mode_ids=[1, 0],
        node_modes=[{"name": "road"}, {"name": "sea"}],
    )
    geo.graph_object.add_node({})
    geo.nodes.append([2, 2])
    geo.save_as_scgraph(str(tmp_path / "modes.scgraph"))
    loaded = GeoGraph.load_from_scgraph(str(tmp_path / "modes.scgraph"))
    assert dict(zip(map(tuple, loaded.nodes), loaded.node_mode_ids)) == {
        (0, 0): 1,
        (1, 1): 0,
        (2, 2): 0,
    }


@pytest.mark.skipif(has_cpp(), reason="a C++ graph is not picklable")
def test_a_pickled_geograph_keeps_its_external_node_ids(tmp_path):
    geo = pickle.loads(pickle.dumps(_small([7, 5, 3, 1])))
    geo.add_coord_node({"latitude": 2.0, "longitude": 2.0}, auto_edge=False)
    geo.save_as_scgraph(str(tmp_path / "small.scgraph"))
    loaded = GeoGraph.load_from_scgraph(str(tmp_path / "small.scgraph"))
    assert loaded.external_node_ids == [7, 5, 3, 1, -1]


# Without `node_modes`, a geograph has one node mode: the node mode id 1 does
# not exist.
@pytest.mark.parametrize(
    "columns, message",
    [
        pytest.param(
            {"external_node_ids": [7, 5, 3]},
            "one id per node",
            id="fewer node ids than nodes",
        ),
        pytest.param(
            {"node_mode_ids": [0, 0, 0]},
            "a row of node_modes",
            id="fewer node modes than nodes",
        ),
        pytest.param(
            {"node_mode_ids": [0, 0, 0, 1]},
            "a row of node_modes",
            id="a node mode id beyond the node modes",
        ),
    ],
)
def test_a_geograph_whose_external_node_ids_or_node_mode_ids_do_not_fit_is_refused(
    columns, message
):
    with pytest.raises(ValueError, match=message):
        GeoGraph(graph=[{}, {}, {}, {}], nodes=SMALL_NODES, **columns)


def _small_with_fine_coordinates(coordinate_dtype):
    """The small network with two coordinates that are not multiples of 1e-7
    degree: the longitude of node 3 and the latitude of the shape point.
    `coordinate_dtype` is how the geograph says its coordinates are stored."""
    geograph = _small()
    geograph.coordinate_dtype = coordinate_dtype
    geograph.nodes[3] = [1.0, 1.000000001]
    geograph.intermediate_nodes = [{1: [[0.0029000001, 0.0058]]}, {}, {}, {}]
    return geograph


# A file stores its coordinates as the geograph does, unless `save_as_scgraph`
# gets a `coordinate_dtype`. The two cases of each test below give the dtype
# in these two ways.
@pytest.mark.parametrize(
    "dtype_of_the_geograph, save_options",
    [
        pytest.param("float64", {}, id="a float64 geograph"),
        pytest.param(
            "int32", {"coordinate_dtype": "float64"}, id="saved as float64"
        ),
    ],
)
def test_a_file_stored_as_float64_keeps_the_exact_coordinates(
    tmp_path, dtype_of_the_geograph, save_options
):
    path = str(tmp_path / "small.scgraph")
    _small_with_fine_coordinates(dtype_of_the_geograph).save_as_scgraph(
        path, **save_options
    )

    loaded = GeoGraph.load_from_scgraph(path)

    assert GeoGraph.get_scgraph_info(path)["coordinate_dtype"] == "float64"
    assert loaded.nodes[3] == [1.0, 1.000000001]
    assert loaded.intermediate_nodes[0][1] == [[0.0029000001, 0.0058]]


@pytest.mark.parametrize(
    "dtype_of_the_geograph, save_options",
    [
        pytest.param("int32", {}, id="an int32 geograph"),
        pytest.param(
            "float64", {"coordinate_dtype": "int32"}, id="saved as int32"
        ),
    ],
)
def test_a_file_stored_as_int32_rounds_the_coordinates_to_1e_7_degree(
    tmp_path, dtype_of_the_geograph, save_options
):
    path = str(tmp_path / "small.scgraph")
    _small_with_fine_coordinates(dtype_of_the_geograph).save_as_scgraph(
        path, **save_options
    )

    loaded = GeoGraph.load_from_scgraph(path)

    assert GeoGraph.get_scgraph_info(path)["coordinate_dtype"] == "int32"
    assert loaded.nodes[3] == [1.0, 1.0]
    assert loaded.intermediate_nodes[0][1] == [[0.0029, 0.0058]]


@both_coordinate_dtypes
def test_a_route_on_a_loaded_network_passes_the_points_of_the_shapes(
    tmp_path, coordinate_dtype
):
    path = str(tmp_path / "small.scgraph")
    _small().save_as_scgraph(path, coordinate_dtype=coordinate_dtype)

    route = _route_0_to_1(GeoGraph.load_from_scgraph(path))

    assert [0.0029, 0.0058] in route
    assert route == _route_0_to_1(_small())


@pytest.mark.parametrize(
    "coordinates, message",
    [
        pytest.param(
            {"nodes": [*SMALL_NODES[:3], [1.0, float("nan")]]},
            "Node 3",
            id="a node",
        ),
        pytest.param(
            {
                "intermediate_nodes": [
                    {1: [[0.0029, float("inf")]]},
                    {},
                    {},
                    {},
                ]
            },
            "edge 0 -> 1",
            id="a shape point",
        ),
    ],
)
def test_a_coordinate_that_is_not_a_finite_number_is_refused_and_located(
    tmp_path, coordinates, message
):
    geograph = _small()
    for name, value in coordinates.items():
        setattr(geograph, name, value)

    with pytest.raises(ValueError, match=message):
        geograph.save_as_scgraph(str(tmp_path / "small.scgraph"))


def test_a_coordinate_beyond_the_range_of_int32_is_refused_as_int32(tmp_path):
    # An int32 holds up to 214.7483647 degrees, in units of 1e-7 degree
    geograph = _small()
    geograph.intermediate_nodes = [{1: [[0.0029, 214.75]]}, {}, {}, {}]

    with pytest.raises(ValueError, match="within ±214.7483647"):
        geograph.save_as_scgraph(
            str(tmp_path / "small.scgraph"), coordinate_dtype="int32"
        )


def test_an_unknown_coordinate_dtype_is_refused(tmp_path):
    with pytest.raises(ValueError, match="must be 'auto', 'float64' or"):
        _small().save_as_scgraph(
            str(tmp_path / "small.scgraph"), coordinate_dtype="int16"
        )


def test_metadata_may_not_set_a_key_that_scgraph_writes(tmp_path):
    # scgraph writes the metrics of the geograph itself
    with pytest.raises(ValueError, match="may not set"):
        _small().save_as_scgraph(
            str(tmp_path / "small.scgraph"), metadata={"metrics": []}
        )


# Three sources. The first two give the time up to which their data goes. The
# first two also share a credit and a license.
DATED_SOURCES = [
    {**SOURCES[0], "version": "2026-11-06T20:21:43Z"},
    {**SOURCES[1], "version": "2026-10-01T00:00:00Z"},
    {**SOURCES[2], "credit": "NGA", "license": "NOASSERTION"},
]


@pytest.fixture(scope="module")
def dated_file(tmp_path_factory):
    """The path of a file of the small network with the dated sources, its
    coordinates stored as int32. The fixture also gives the digest that
    `save_as_scgraph` returned."""
    path = str(tmp_path_factory.mktemp("dated") / "small.scgraph")
    digest = _small().save_as_scgraph(
        path, metadata={"sources": DATED_SOURCES}, coordinate_dtype="int32"
    )
    return path, digest


def test_scgraph_info_describes_a_file_and_its_sources(dated_file):
    path, digest = dated_file

    info = GeoGraph.get_scgraph_info(path)

    assert (info["nodes"], info["edges"]) == (4, 3)
    assert info["metrics"] == [{"name": "length", "unit": "mi"}]
    assert info["coordinate_dtype"] == "int32"
    assert info["has_intermediate_nodes"] is True
    # The ids of the small network are the positions: the file stores none.
    assert info["has_external_node_ids"] is False
    assert info["content_sha256"] == digest
    assert info["sources"] == DATED_SOURCES
    # The credit line gives each credit once, with its license.
    assert info["attribution"] == (
        "© OpenStreetMap contributors (ODbL-1.0); NGA (NOASSERTION)"
    )
    # The data goes up to the latest of the times that the sources give.
    assert info["data_up_to"] == "2026-11-06T20:21:43Z"
    # The function of `network_file` gives the same dict.
    assert network_file.get_scgraph_info(path) == info


def test_a_node_mode_must_name_a_source_of_the_metadata(tmp_path):
    geograph = _small()
    geograph.node_modes = [{"name": None, "source": "region-0"}]

    with pytest.raises(ValueError, match="names no source"):
        geograph.save_as_scgraph(
            str(tmp_path / "small.scgraph"),
            metadata={"sources": [{"name": "elsewhere"}]},
        )


# Four nodes: west, north, south and east. Two routes of the same length go
# from west to east, through north or through south. The two graphs differ
# only by the order in which the edges of west and east are listed. A search
# visits the edges in that order, and a network file keeps it.
WEST_NORTH_SOUTH_EAST = [[0.0, 0.0], [0.01, 0.01], [-0.01, 0.01], [0.0, 0.02]]
NORTH_LISTED_FIRST = [
    {1: 1.0, 2: 1.0},
    {3: 1.0, 0: 1.0},
    {0: 1.0, 3: 1.0},
    {2: 1.0, 1: 1.0},
]
SOUTH_LISTED_FIRST = [
    {2: 1.0, 1: 1.0},
    {3: 1.0, 0: 1.0},
    {0: 1.0, 3: 1.0},
    {1: 1.0, 2: 1.0},
]


def _route_west_to_east(geograph):
    return geograph.get_shortest_path(
        origin_node={"latitude": 0, "longitude": 0},
        destination_node={"latitude": 0, "longitude": 0.02},
        node_addition_type="closest",
        destination_node_addition_type="closest",
    )["coordinate_path"]


@pytest.mark.parametrize(
    "graph",
    [NORTH_LISTED_FIRST, SOUTH_LISTED_FIRST],
    ids=["north listed first", "south listed first"],
)
def test_a_network_file_gives_the_route_of_the_graph_where_two_tie(
    tmp_path, graph
):
    path = str(tmp_path / "tie.scgraph")
    geograph = GeoGraph(
        graph=[dict(row) for row in graph], nodes=WEST_NORTH_SOUTH_EAST
    )
    geograph.save_as_scgraph(path)

    loaded = GeoGraph.load_from_scgraph(path)

    assert _route_west_to_east(loaded) == _route_west_to_east(geograph)


# The tests below write a file from arrays with `network_file.write`, as a
# pipeline does. This is the way to write a file that `save_as_scgraph` would
# never write. The edges are stored by origin: the edges of node u go to
# edge_destination_node_ids[node_first_edge_ids[u]:node_first_edge_ids[u + 1]].
# The header names the metrics of the file: the length first. Another metric
# gives its weight for 1 km between a query point and its node: here, no toll.
LENGTH_IN_KM = {"name": "length", "unit": "km"}
TOLL = {"name": "toll", "unit": "EUR", "off_graph_weight_per_km": 0.0}
ROAD_AND_PORT = [
    {"name": "road", "source": "roads"},
    {"name": "port", "source": "ports"},
]
# In a file, the row of a node mode also gives the count of its nodes. The
# nodes 0 and 1 are road nodes, and the node 2 is a port.
ROAD_AND_PORT_IN_A_FILE = [
    {"name": "road", "source": "roads", "node_count": 2},
    {"name": "port", "source": "ports", "node_count": 1},
]
ROAD_AND_PORT_HEADER = {
    "metrics": [LENGTH_IN_KM],
    "node_modes": ROAD_AND_PORT_IN_A_FILE,
}


def _two_road_nodes_and_a_port():
    """The arrays of a network of three nodes: two road nodes joined both
    ways, and a port without edges. The first node id is beyond 32 bits."""
    return {
        "node_first_edge_ids": array("i", [0, 1, 2, 2]),
        "edge_destination_node_ids": array("i", [1, 0]),
        "metric_length": array("d", [1.0, 1.0]),
        "node_points": array("d", [0.0, 0.0, 0.0, 1.0, 1.0, 1.0]),
        "external_node_ids": array("q", [2**40, 7, -1]),
    }


def test_a_file_written_from_arrays_is_loaded_as_the_network_of_the_arrays(
    tmp_path,
):
    path = str(tmp_path / "arrays.scgraph")
    network_file.write(path, _two_road_nodes_and_a_port(), ROAD_AND_PORT_HEADER)

    loaded = GeoGraph.load_from_scgraph(path)

    assert loaded.graph_object.graph == [{1: 1.0}, {0: 1.0}, {}]
    assert loaded.nodes == [[0.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
    assert list(loaded.external_node_ids) == [2**40, 7, -1]
    assert list(loaded.node_mode_ids) == [0, 0, 1]
    assert loaded.node_modes == ROAD_AND_PORT


# A file may come from another tool, or be damaged. `load_from_scgraph` must
# refuse arrays that do not fit together, and name what is wrong. Each case
# below replaces or adds arrays of the valid network above.
@pytest.mark.parametrize(
    "invalid_arrays, message",
    [
        pytest.param(
            {"external_node_ids": array("q", [1, 2])},
            "one node id per node",
            id="fewer node ids than nodes",
        ),
        pytest.param(
            {
                "edge_first_shape_point_ids": array("i", [0, 0, 0]),
                "shape_points": array("i"),
            },
            "coordinates of two dtypes",
            id="node points and shape points of two dtypes",
        ),
        pytest.param(
            {"edge_class_ids": array("B", [0])},
            "one edge class per edge",
            id="fewer edge classes than edges",
        ),
    ],
)
def test_a_file_whose_arrays_do_not_fit_together_is_refused(
    tmp_path, invalid_arrays, message
):
    path = str(tmp_path / "arrays.scgraph")
    arrays = {**_two_road_nodes_and_a_port(), **invalid_arrays}
    network_file.write(path, arrays, ROAD_AND_PORT_HEADER)

    with pytest.raises(ValueError, match=message):
        GeoGraph.load_from_scgraph(path)


# A row of the list `classes` gives a class and the edge mode of its edges.
MOTORWAY = {"name": "motorway", "edge_mode": "road"}


# A value of `edge_class_ids` is the position of a row of the list `classes`
# of the metadata: a file has both, or neither. Each case gives the class ids
# of the edges, the header, and words of the error.
@pytest.mark.parametrize(
    "class_id_arrays, header, message",
    [
        pytest.param(
            {"edge_class_ids": array("B", [0, 0])},
            ROAD_AND_PORT_HEADER,
            "without a list of classes",
            id="class ids without a list of classes",
        ),
        pytest.param(
            {},
            ROAD_AND_PORT_HEADER | {"classes": [MOTORWAY]},
            "no array `edge_class_ids`",
            id="a list of classes without class ids",
        ),
    ],
)
def test_a_file_with_class_ids_or_classes_alone_is_refused(
    tmp_path, class_id_arrays, header, message
):
    path = str(tmp_path / "arrays.scgraph")
    arrays = _two_road_nodes_and_a_port() | class_id_arrays
    network_file.write(path, arrays, header)

    with pytest.raises(ValueError, match=message):
        GeoGraph.load_from_scgraph(path)


# The header must describe the arrays of the file, and `load_from_scgraph`
# must name what is wrong. Here the valid network above also has a class and a
# toll for each edge. Each case below replaces or adds a key of the valid
# header.
ROAD_AND_PORT_HEADER_WITH_A_TOLL = {
    "metrics": [LENGTH_IN_KM, TOLL],
    "node_modes": ROAD_AND_PORT_IN_A_FILE,
    "classes": [MOTORWAY],
}


@pytest.mark.parametrize(
    "invalid_header, message",
    [
        pytest.param(
            ROAD_AND_PORT_HEADER_WITH_A_TOLL
            | {"metrics": [TOLL, TOLL | {"name": "length"}]},
            "the first metric must be length",
            id="the toll before the length",
        ),
        pytest.param(
            ROAD_AND_PORT_HEADER_WITH_A_TOLL
            | {"metrics": [{"name": "length"}, TOLL]},
            "length, with its unit",
            id="a length without its unit",
        ),
        pytest.param(
            ROAD_AND_PORT_HEADER_WITH_A_TOLL | {"metrics": [LENGTH_IN_KM]},
            "one array of weights per metric",
            id="tolls without their row of metric",
        ),
        pytest.param(
            ROAD_AND_PORT_HEADER_WITH_A_TOLL
            | {"metrics": [LENGTH_IN_KM, {"name": "toll"}]},
            "must give off_graph_weight_per_km",
            id="a toll without off_graph_weight_per_km",
        ),
        pytest.param(
            ROAD_AND_PORT_HEADER_WITH_A_TOLL | {"classes": ["motorway"]},
            "a row with a name and an edge mode",
            id="a class without its edge mode",
        ),
        pytest.param(
            ROAD_AND_PORT_HEADER_WITH_A_TOLL
            | {
                "node_modes": [
                    {"name": "road", "node_count": 2},
                    {"name": "port", "node_count": 2},
                ]
            },
            "must add up to the count of the nodes",
            id="four nodes in the node modes of three nodes",
        ),
        pytest.param(
            ROAD_AND_PORT_HEADER_WITH_A_TOLL
            | {
                "classes": [
                    {"name": f"class_{class_id}", "edge_mode": "road"}
                    for class_id in range(256)
                ]
            },
            "255 classes at most",
            id="a 256th class",
        ),
    ],
)
def test_a_file_whose_header_does_not_describe_its_arrays_is_refused(
    tmp_path, invalid_header, message
):
    path = str(tmp_path / "arrays.scgraph")
    arrays = _two_road_nodes_and_a_port() | {
        "edge_class_ids": array("B", [0, 0]),
        "metric_toll": array("d", [2.0, 2.0]),
    }
    network_file.write(path, arrays, invalid_header)

    with pytest.raises(ValueError, match=message):
        GeoGraph.load_from_scgraph(path)


# `load_from_scgraph(node_modes=...)` loads the nodes of some modes only. It finds
# them without reading the whole file, so the file must list its nodes mode by
# mode. It checks the arrays that it reads on the way. The file names one
# class, so the only row of an edge class is 0. The case of an edge class beyond
# the list is here, because a mapped read of the whole file does not check the
# values of an array.
@pytest.mark.parametrize(
    "invalid_arrays, message",
    [
        pytest.param(
            {"external_node_ids": array("q", [1, 2, 3, 4])},
            "per node",
            id="more node ids than nodes",
        ),
        pytest.param(
            {"node_first_edge_ids": array("i", [0, 2, 1, 2])},
            "invalid node_first_edge_ids",
            id="node_first_edge_ids that decrease",
        ),
        pytest.param(
            {"edge_destination_node_ids": array("i", [-1, 0])},
            "edge to a missing node",
            id="an edge to a node that does not exist",
        ),
        pytest.param(
            {"edge_destination_node_ids": array("i", [1, 3])},
            "edge to a missing node",
            id="an edge to a node after the last node",
        ),
        pytest.param(
            {
                "edge_first_shape_point_ids": array("i", [0, 1, 0]),
                "shape_points": array("d"),
            },
            "invalid edge_first_shape_point_ids",
            id="edge_first_shape_point_ids that decrease",
        ),
        pytest.param(
            {
                # The second edge now goes to the port: a load of the road
                # reads `edge_first_shape_point_ids` for the first edge only.
                "edge_destination_node_ids": array("i", [1, 2]),
                "edge_first_shape_point_ids": array("i", [0, 2, 1]),
                "shape_points": array("d", [0.0, 0.0]),
            },
            "invalid edge_first_shape_point_ids",
            id="a shape that ends after the last shape point",
        ),
        pytest.param(
            {"edge_class_ids": array("B", [0, 1])},
            "invalid edge classes",
            id="an edge class beyond the list of classes",
        ),
    ],
)
def test_loading_some_modes_refuses_arrays_that_do_not_fit_together(
    tmp_path, invalid_arrays, message
):
    path = str(tmp_path / "arrays.scgraph")
    arrays = {
        **_two_road_nodes_and_a_port(),
        "edge_class_ids": array("B", [0, 0]),
        **invalid_arrays,
    }
    metadata = ROAD_AND_PORT_HEADER | {"classes": [MOTORWAY]}
    network_file.write(path, arrays, metadata)

    with pytest.raises(ValueError, match=message):
        GeoGraph.load_from_scgraph(path, node_modes=["road"])


def test_loading_a_node_mode_that_the_file_does_not_have_is_refused(tmp_path):
    path = str(tmp_path / "arrays.scgraph")
    network_file.write(path, _two_road_nodes_and_a_port(), ROAD_AND_PORT_HEADER)

    with pytest.raises(ValueError, match=r"unknown node modes \['rail'\]"):
        GeoGraph.load_from_scgraph(path, node_modes=["rail"])


EDGE_CLASSES = [
    {"name": "connector", "edge_mode": "sea"},
    {"name": "motorway", "edge_mode": "road"},
    {"name": "primary", "edge_mode": "road"},
    {"name": "lane", "edge_mode": "sea"},
    {"name": "strait", "edge_mode": "sea"},
]


def _write_road_port_and_sea(
    path, coordinate_typecode, with_external_node_ids=True
):
    """Write a file of five nodes, listed mode by mode: the road nodes 10 and
    11, the port 20, the sea nodes 30 and 31. A node has its id as latitude
    and minus its id as longitude, stored as they are in `coordinate_typecode`
    ("d" for float64, "i" for int32). The edges, by origin:

        10 -> 11 (1 km)    11 -> 10 (1.5 km)    11 -> 20 (2 km)
        20 -> 30 (3 km)    30 -> 31 (4 km)      31 -> 20 (5 km)
        31 -> 30 (6 km)

    The shape of an edge repeats the point (origin id, destination id): once
    from 10 and 31, twice from 11 and 20, never from 30.

    Each edge has a class, a row of EDGE_CLASSES. The four edges between two
    road nodes or two sea nodes have a class each. The three edges of the port
    are connectors.

    The file has a second metric, `toll`. The toll of an edge is ten times its
    km.
    """
    arrays = {
        "node_first_edge_ids": array("i", [0, 1, 3, 4, 5, 7]),
        "edge_destination_node_ids": array("i", [1, 0, 2, 3, 4, 2, 3]),
        "metric_length": array("d", [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0]),
        "metric_toll": array("d", [10.0, 15.0, 20.0, 30.0, 40.0, 50.0, 60.0]),
        "node_points": array(
            coordinate_typecode,
            [10, -10, 11, -11, 20, -20, 30, -30, 31, -31],
        ),
        "external_node_ids": array("i", [10, 11, 20, 30, 31]),
        "edge_first_shape_point_ids": array("i", [0, 1, 3, 5, 7, 7, 8, 9]),
        "shape_points": array(
            coordinate_typecode,
            [10, 11]
            + [11, 10, 11, 10]
            + [11, 20, 11, 20]
            + [20, 30, 20, 30]
            + [31, 20]
            + [31, 30],
        ),
        "edge_class_ids": array("B", [1, 2, 0, 0, 3, 0, 4]),
    }
    if not with_external_node_ids:
        del arrays["external_node_ids"]
    names = [
        {"name": "road", "node_count": 2},
        {"name": "port", "node_count": 1},
        {"name": "sea", "node_count": 2},
    ]
    metadata = {
        "metrics": [LENGTH_IN_KM, TOLL],
        "node_modes": names,
        "classes": EDGE_CLASSES,
    }
    network_file.write(path, arrays, metadata)


# `network_file.read` gives the class of each edge, with the rows of the
# classes.
def test_a_file_written_with_edge_classes_is_read_back_with_them(tmp_path):
    path = str(tmp_path / "modes.scgraph")
    _write_road_port_and_sea(path, "d")

    arrays, metadata = network_file.read(path)

    assert list(arrays["edge_class_ids"]) == [1, 2, 0, 0, 3, 0, 4]
    assert metadata["classes"] == EDGE_CLASSES


def test_reading_some_modes_keeps_the_class_and_the_weights_of_each_kept_edge(
    tmp_path,
):
    path = str(tmp_path / "modes.scgraph")
    _write_road_port_and_sea(path, "d")

    arrays, _ = network_file.read(path, node_modes=["road", "sea"])

    # The kept edges are 10 -> 11, 11 -> 10, 30 -> 31 and 31 -> 30. They are
    # 1, 1.5, 4 and 6 km long.
    assert list(arrays["edge_class_ids"]) == [1, 2, 3, 4]
    assert list(arrays["metric_length"]) == [1.0, 1.5, 4.0, 6.0]
    assert list(arrays["metric_toll"]) == [10.0, 15.0, 40.0, 60.0]


def test_a_geograph_loaded_from_a_file_is_saved_with_its_classes_and_metrics(
    tmp_path,
):
    path, saved_path = (
        str(tmp_path / name) for name in ("a.scgraph", "b.scgraph")
    )
    _write_road_port_and_sea(path, "d")

    GeoGraph.load_from_scgraph(path).save_as_scgraph(saved_path)

    # The save lists the sea node 31 before the sea node 30. The file ends
    # with the edges 31 -> 20, 31 -> 30 and 30 -> 31, of 5, 6 and 4 km.
    arrays, metadata = network_file.read(saved_path)
    assert list(arrays["edge_class_ids"]) == [1, 2, 0, 0, 0, 4, 3]
    assert metadata["classes"] == EDGE_CLASSES
    assert list(arrays["metric_toll"]) == [10, 15, 20, 30, 50, 60, 40]
    assert metadata["metrics"] == [LENGTH_IN_KM, TOLL]


def test_loading_one_node_mode_gives_its_nodes_and_the_edges_between_them(
    tmp_path,
):
    path = str(tmp_path / "modes.scgraph")
    _write_road_port_and_sea(path, "d")

    roads = GeoGraph.load_from_scgraph(path, node_modes="road")

    assert list(roads.external_node_ids) == [10, 11]
    assert roads.nodes == [[10, -10], [11, -11]]
    assert list(roads.node_mode_ids) == [0, 0]
    # The edge from 11 to the port is left out
    assert roads.graph_object.graph == [{1: 1.0}, {0: 1.5}]
    assert [dict(shapes) for shapes in roads.intermediate_nodes] == [
        {1: [[10, 11]]},
        {0: [[11, 10], [11, 10]]},
    ]


def test_loading_two_modes_gives_their_nodes_in_the_order_of_the_file(
    tmp_path,
):
    # The sea is asked for first, and the file lists the road first
    path = str(tmp_path / "modes.scgraph")
    _write_road_port_and_sea(path, "d")

    geograph = GeoGraph.load_from_scgraph(path, node_modes=("sea", "road"))

    assert list(geograph.external_node_ids) == [10, 11, 30, 31]
    assert geograph.nodes == [[10, -10], [11, -11], [30, -30], [31, -31]]
    assert list(geograph.node_mode_ids) == [0, 0, 2, 2]
    # Without the port, the sea nodes move from the positions 3 and 4 to the
    # positions 2 and 3. The edges 11 -> 20 and 31 -> 20 are left out.
    assert geograph.graph_object.graph == [
        {1: 1.0},
        {0: 1.5},
        {3: 4.0},
        {2: 6.0},
    ]
    assert [dict(shapes) for shapes in geograph.intermediate_nodes] == [
        {1: [[10, 11]]},
        {0: [[11, 10], [11, 10]]},
        {},
        {2: [[31, 30]]},
    ]
    classes = [edge["edge_class"] for edge in geograph.get_edges()]
    assert classes == ["motorway", "primary", "lane", "strait"]


# The typecode "i" stores a coordinate as an int32, in 1e-7 degree. The
# typecode "d" stores it as a float64, in degrees.
@pytest.mark.parametrize(
    "coordinate_typecode, coordinate_dtype", [("i", "int32"), ("d", "float64")]
)
def test_loading_some_modes_keeps_the_dtype_of_the_coordinates(
    tmp_path, coordinate_typecode, coordinate_dtype
):
    path = str(tmp_path / "modes.scgraph")
    _write_road_port_and_sea(path, coordinate_typecode)

    roads = GeoGraph.load_from_scgraph(path, node_modes="road")

    assert roads.coordinate_dtype == coordinate_dtype


def test_loading_some_node_modes_of_a_file_without_external_node_ids_gives_the_node_ids_of_the_file(
    tmp_path,
):
    # The id of a node is then its position in the whole file
    path = str(tmp_path / "modes.scgraph")
    _write_road_port_and_sea(path, "d", with_external_node_ids=False)

    geograph = GeoGraph.load_from_scgraph(path, node_modes=("sea", "road"))

    assert list(geograph.external_node_ids) == [0, 1, 3, 4]


def test_load_from_scgraph_reads_an_empty_network(tmp_path):
    path = str(tmp_path / "empty.scgraph")
    GeoGraph(graph=[], nodes=[]).save_as_scgraph(path)
    assert GeoGraph.load_from_scgraph(path).nodes == []


def test_a_file_holds_the_sha256_of_its_bytes_from_byte_40(tmp_path):
    # The digest is in the bytes 8 to 39. `save_as_scgraph` returns it.
    path = tmp_path / "small.scgraph"

    digest = _small().save_as_scgraph(str(path))

    data = path.read_bytes()
    assert digest == data[8:40].hex() == hashlib.sha256(data[40:]).hexdigest()
    assert GeoGraph.get_scgraph_info(str(path))["content_sha256"] == digest


def test_the_order_of_the_keys_of_the_metadata_does_not_change_the_file(
    tmp_path,
):
    keys_reversed = [dict(reversed(source.items())) for source in SOURCES]

    digest = _small().save_as_scgraph(
        str(tmp_path / "small.scgraph"), metadata={"sources": SOURCES}
    )
    digest_with_keys_reversed = _small().save_as_scgraph(
        str(tmp_path / "again.scgraph"), metadata={"sources": keys_reversed}
    )

    assert digest_with_keys_reversed == digest


def test_a_save_that_fails_leaves_the_previous_file_and_no_other_file(
    tmp_path,
):
    path = tmp_path / "small.scgraph"
    _small().save_as_scgraph(str(path))
    previous_bytes = path.read_bytes()
    # The weights are every second value of an array. Python cannot write
    # such a view as bytes: the save fails after it wrote the first arrays.
    every_second_value = memoryview(array("d", [1.0, 0.0, 1.0, 0.0]))[::2]
    arrays = {
        "node_first_edge_ids": array("i", [0, 1, 2]),
        "edge_destination_node_ids": array("i", [1, 0]),
        "metric_length": every_second_value,
        "node_points": array("d", [0.0, 0.0, 0.0, 1.0]),
    }

    with pytest.raises(TypeError):
        network_file.write(str(path), arrays, {})

    assert path.read_bytes() == previous_bytes
    assert [file.name for file in tmp_path.iterdir()] == ["small.scgraph"]


def test_load_from_scgraph_keeps_the_original_graph_after_reduction(tmp_path):
    # A chain 0-1-2-3-4: reduction removes 1, 2 and 3 from the searches only
    chain = [
        {1: 1.0},
        {0: 1.0, 2: 2.0},
        {1: 2.0, 3: 1.5},
        {2: 1.5, 4: 1.0},
        {3: 1.0},
    ]
    path = str(tmp_path / "chain.scgraph")
    GeoGraph(
        graph=[dict(row) for row in chain],
        nodes=[[0.0, 0.01 * i] for i in range(5)],
    ).save_as_scgraph(path)
    loaded = GeoGraph.load_from_scgraph(path, reduce_iterations=-1)
    assert loaded.graph == chain


# The nodes of a loaded network are read from the arrays of the file. They
# must still behave as the list of [latitude, longitude] that a geograph has.
# Each test below uses the nodes of a new load of the small network, after a
# fifth node was appended.
@pytest.fixture
def nodes_of_a_file(tmp_path):
    path = str(tmp_path / "small.scgraph")
    _small().save_as_scgraph(path)
    nodes = GeoGraph.load_from_scgraph(path).nodes
    nodes.append([3.0, 3.0])
    return nodes


def test_nodes_read_from_a_file_are_read_as_a_list_with_an_appended_node(
    nodes_of_a_file,
):
    assert nodes_of_a_file == [*SMALL_NODES, [3.0, 3.0]]
    assert nodes_of_a_file[-1] == [3.0, 3.0]
    assert nodes_of_a_file[-2] == [1.0, 1.0]
    assert nodes_of_a_file[1:3] == [[0.0, 0.01], [0.01, 0.0]]
    # A route reads the coordinates of its path with `take`. The position -1
    # is the last node, as in a list.
    assert nodes_of_a_file.take([-1, 0, 4]) == [
        [3.0, 3.0],
        [0.0, 0.0],
        [3.0, 3.0],
    ]


# Each function below edits a list of nodes in place.
def _replace_the_appended_node(nodes):
    nodes[-1] = [4.0, 4.0]


def _pop_the_appended_node(nodes):
    nodes.pop()


def _extend_with_two_nodes(nodes):
    nodes.extend([[5.0, 5.0], [6.0, 6.0]])


def _replace_a_node_of_the_file(nodes):
    nodes[1] = [7.0, 7.0]


def _insert_a_node_before_the_nodes_of_the_file(nodes):
    nodes.insert(0, [8.0, 8.0])


def _delete_two_nodes_of_the_file_by_slice(nodes):
    del nodes[2:4]


@pytest.mark.parametrize(
    "edit",
    [
        _replace_the_appended_node,
        _pop_the_appended_node,
        _extend_with_two_nodes,
        _replace_a_node_of_the_file,
        _insert_a_node_before_the_nodes_of_the_file,
        _delete_two_nodes_of_the_file_by_slice,
    ],
)
def test_nodes_read_from_a_file_are_edited_as_a_list(nodes_of_a_file, edit):
    edited_list = [*SMALL_NODES, [3.0, 3.0]]
    edit(edited_list)

    edit(nodes_of_a_file)

    assert nodes_of_a_file == edited_list


def test_snapping_finds_a_node_added_to_a_loaded_network(small_file):
    loaded = GeoGraph.load_from_scgraph(small_file)

    loaded.add_coord_node({"latitude": 9.0, "longitude": 9.0}, auto_edge=False)

    # The added node is the fifth node: its position is 4
    assert loaded.snap_index.closest_idx([8.9, 8.9]) == 4


def test_a_loaded_network_with_an_added_node_is_saved_as_graphjson(
    small_file, tmp_path
):
    graphjson = str(tmp_path / "small.graphjson")
    loaded = GeoGraph.load_from_scgraph(small_file)
    loaded.add_coord_node({"latitude": 9.0, "longitude": 9.0}, auto_edge=False)

    loaded.save_as_graphjson(graphjson)

    assert GeoGraph.load_from_graphjson(graphjson).nodes == [
        *SMALL_NODES,
        [9.0, 9.0],
    ]


# The C++ graph reads its file in place. Windows does not replace a file that
# a process reads in place; the other systems do.
WINDOWS_WITH_CPP = os.name == "nt" and has_cpp()


@pytest.mark.skipif(
    WINDOWS_WITH_CPP, reason="Windows does not replace a file read in place"
)
def test_a_graph_stays_whole_when_another_network_is_saved_over_its_file(
    tmp_path,
):
    path = str(tmp_path / "small.scgraph")
    _small().save_as_scgraph(path)
    opened = GeoGraph.load_from_scgraph(path)
    other = GeoGraph(graph=[{1: 7.0}, {0: 7.0}], nodes=[[0, 0], [0, 0.01]])

    other.save_as_scgraph(path)

    assert opened.graph_object.dijkstra(0, 1)["length"] == 5
    assert opened.graph_object.graph == SMALL_GRAPH
    assert GeoGraph.load_from_scgraph(path).graph_object.graph == other.graph


@pytest.mark.skipif(
    not WINDOWS_WITH_CPP,
    reason="the other systems replace a file read in place",
)
def test_a_save_over_a_file_read_in_place_is_refused_on_windows(tmp_path):
    path = str(tmp_path / "small.scgraph")
    _small().save_as_scgraph(path)
    opened = GeoGraph.load_from_scgraph(path)
    other = GeoGraph(graph=[{1: 7.0}, {0: 7.0}], nodes=[[0, 0], [0, 0.01]])

    with pytest.raises(PermissionError, match="open in a graph"):
        other.save_as_scgraph(path)

    assert opened.graph_object.graph == SMALL_GRAPH


# The tests below damage the bytes of a file of the small network. A file
# starts with 8 bytes that name the format and 32 bytes of digest. Then come
# the length of the header in 8 bytes, the header in JSON, zeros up to a
# multiple of 64 bytes, and the arrays. The header gives the position of each
# array, counted from the end of these zeros. Reading does not check the
# digest.
@pytest.fixture
def file_to_damage(tmp_path):
    path = tmp_path / "small.scgraph"
    _small().save_as_scgraph(str(path))
    return path


def _read_header(data):
    header_length = int.from_bytes(data[40:48], "little")
    return json.loads(data[48 : 48 + header_length])


def _find_start_of_arrays(data):
    header_length = int.from_bytes(data[40:48], "little")
    return -(-(48 + header_length) // 64) * 64


def _replace_header(data, header):
    """The bytes of the file with `header` in place of its header, and the
    arrays as they were."""
    text = json.dumps(header).encode()
    zeros = bytes(-(48 + len(text)) % 64)
    arrays = data[_find_start_of_arrays(data) :]
    return data[:40] + len(text).to_bytes(8, "little") + text + zeros + arrays


def _replace_int32(data, array_name, index, value):
    """The bytes of the file with `value` as the int32 at `index` of the
    array `array_name`."""
    array_offset = _read_header(data)["arrays"][array_name]["offset"]
    position = _find_start_of_arrays(data) + array_offset + 4 * index
    return data[:position] + value.to_bytes(4, "little") + data[position + 4 :]


# Each function below takes the bytes of a file and returns them damaged.
def _replace_with_a_file_of_another_format(data):
    return b'{"type": "GeoGraph"}'


def _set_a_later_format_version(data):
    header = _read_header(data)
    header["format_version"] = 2
    return _replace_header(data, header)


def _cut_before_the_end(data):
    return data[:-8]


def _give_an_array_a_wrong_dtype(data):
    header = _read_header(data)
    header["arrays"]["edge_destination_node_ids"]["dtype"] = "float64"
    return _replace_header(data, header)


def _declare_float32_lengths(data):
    header = _read_header(data)
    header["arrays"]["metric_length"]["dtype"] = "float32"
    return _replace_header(data, header)


def _say_the_header_as_long_as_the_file(data):
    return data[:40] + len(data).to_bytes(8, "little") + data[48:]


def _place_an_array_before_the_arrays(data):
    header = _read_header(data)
    header["arrays"]["node_first_edge_ids"]["offset"] = -_find_start_of_arrays(
        data
    )
    return _replace_header(data, header)


def _remove_the_list_of_arrays(data):
    header = _read_header(data)
    del header["arrays"]
    return _replace_header(data, header)


def _put_the_header_in_a_json_list(data):
    return _replace_header(data, [_read_header(data)])


def _point_an_edge_to_a_node_that_does_not_exist(data):
    return _replace_int32(data, "edge_destination_node_ids", 0, 99)


def _set_a_first_edge_id_past_the_edges(data):
    return _replace_int32(data, "node_first_edge_ids", 1, 2**30)


# A damaged file must be refused with a message that names the damage. It
# must not be read as a wrong network. The last two damages are in the arrays
# of the edges: the C++ graph, which reads the file in place, finds them with
# its own message.
@pytest.mark.parametrize(
    "damage, message",
    [
        (_replace_with_a_file_of_another_format, "not a scgraph network file"),
        (_set_a_later_format_version, "format version 2"),
        (_cut_before_the_end, "invalid array"),
        (_give_an_array_a_wrong_dtype, "invalid array"),
        (
            _declare_float32_lengths,
            "the metric 'length' has float32 weights; this version of scgraph"
            " reads float64 weights only",
        ),
        (_say_the_header_as_long_as_the_file, "invalid header length"),
        (_place_an_array_before_the_arrays, "invalid array"),
        (_remove_the_list_of_arrays, "invalid header"),
        (_put_the_header_in_a_json_list, "invalid header"),
        (
            _point_an_edge_to_a_node_that_does_not_exist,
            "edge to a missing node|is not in the graph",
        ),
        (
            _set_a_first_edge_id_past_the_edges,
            "invalid node_first_edge_ids|non-decreasing",
        ),
    ],
)
def test_a_damaged_file_is_refused(file_to_damage, damage, message):
    file_to_damage.write_bytes(damage(file_to_damage.read_bytes()))

    with pytest.raises(ValueError, match=message):
        GeoGraph.load_from_scgraph(str(file_to_damage))


# A later version of scgraph may add an array to the file. Here the header
# names the bytes of `edge_destination_node_ids` a second time, as `later_array`.
def test_a_file_with_an_array_that_scgraph_does_not_know_is_read_without_it(
    file_to_damage,
):
    known_arrays, _ = network_file.read(str(file_to_damage))
    data = file_to_damage.read_bytes()
    header = _read_header(data)
    header["arrays"]["later_array"] = header["arrays"][
        "edge_destination_node_ids"
    ]
    file_to_damage.write_bytes(_replace_header(data, header))

    arrays, _ = network_file.read(str(file_to_damage))

    assert arrays == known_arrays


# The C++ build reads the shapes in place and does not check them all at
# load. A value of `edge_first_shape_point_ids` past the shape points is refused at
# load, or when the shape is read.
def test_a_route_refuses_edge_first_shape_point_ids_that_go_past_the_shape_points(
    file_to_damage,
):
    data = file_to_damage.read_bytes()
    file_to_damage.write_bytes(
        _replace_int32(data, "edge_first_shape_point_ids", 1, 2**30)
    )

    with pytest.raises(ValueError, match="invalid edge_first_shape_point_ids"):
        _route_0_to_1(GeoGraph.load_from_scgraph(str(file_to_damage)))


def test_reading_a_shape_refuses_edge_first_shape_point_ids_that_go_past_the_shape_points(
    file_to_damage,
):
    data = file_to_damage.read_bytes()
    file_to_damage.write_bytes(
        _replace_int32(data, "edge_first_shape_point_ids", 1, 2**30)
    )

    with pytest.raises(ValueError, match="invalid edge_first_shape_point_ids"):
        dict(
            GeoGraph.load_from_scgraph(str(file_to_damage)).intermediate_nodes[
                0
            ]
        )


def test_hilbert_order_follows_the_curve():
    # One point per quadrant of the globe: north-east, south-west, north-west, south-east;
    # the curve visits them south-west, north-west, north-east, south-east
    nodes = [[45, 90], [-45, -90], [45, -90], [-45, 90]]
    assert get_hilbert_order(nodes) == [1, 2, 0, 3]


def test_a_network_file_is_saved_and_loaded_with_a_path_object(tmp_path):
    saved = GeoGraph(graph=[{1: 1.0}, {0: 1.0}], nodes=[[0, 0], [0, 0.01]])

    saved.save_as_scgraph(tmp_path / "two_nodes.scgraph")
    loaded = GeoGraph.load_from_scgraph(tmp_path / "two_nodes.scgraph")

    assert loaded.nodes == saved.nodes
    assert loaded.scgraph_file == str(tmp_path / "two_nodes.scgraph")


def test_a_graphjson_file_is_saved_and_loaded_with_a_path_object(tmp_path):
    saved = GeoGraph(graph=[{1: 1.0}, {0: 1.0}], nodes=[[0, 0], [0, 0.01]])

    saved.save_as_graphjson(tmp_path / "two_nodes.graphjson")
    loaded = GeoGraph.load_from_graphjson(tmp_path / "two_nodes.graphjson")

    assert loaded.nodes == saved.nodes
