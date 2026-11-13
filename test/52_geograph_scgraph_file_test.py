import copy
import hashlib
import json
import os
import pickle
from array import array

import pytest

from scgraph import GeoGraph, Graph, network_file
from scgraph.helpers.hilbert import hilbert_order

# The small network has four nodes, listed in Hilbert order. Node 0 has a
# one-way arc to node 2 and a two-way arc with node 1, with an integer weight.
# Node 3 has no arc. Only the arc from 0 to 1 has a shape.
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


def _small(node_ids=None):
    return GeoGraph(
        graph=[dict(row) for row in SMALL_GRAPH],
        nodes=[list(node) for node in SMALL_NODES],
        intermediate_nodes=SMALL_SHAPES,
        geograph_units="mi",
        node_ids=node_ids,
    )


def _route_0_to_1(geograph):
    # Through the arc 0 -> 1, which has a shape
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


def test_a_saved_network_is_read_back_with_its_graph_nodes_and_units(
    small_file,
):
    loaded = GeoGraph.load_from_scgraph(small_file)

    assert loaded.graph_object.graph == SMALL_GRAPH
    assert loaded.nodes == SMALL_NODES
    assert loaded.geograph_units == "mi"


def test_a_saved_network_is_read_back_with_the_shapes_of_its_arcs(small_file):
    loaded = GeoGraph.load_from_scgraph(small_file)

    assert loaded.intermediate_nodes == SMALL_SHAPES


def test_a_network_saved_without_its_shapes_is_read_back_without_shapes(
    tmp_path,
):
    path = str(tmp_path / "small.scgraph")
    _small().save_as_scgraph(path, save_intermediate_nodes=False)

    loaded = GeoGraph.load_from_scgraph(path)

    assert loaded.intermediate_nodes is None
    assert loaded.graph_object.graph == SMALL_GRAPH


def test_a_loaded_network_has_the_sources_that_its_file_names(small_file):
    loaded = GeoGraph.load_from_scgraph(small_file)

    assert loaded.metadata == {"sources": SOURCES}


def test_a_loaded_network_is_saved_again_with_its_sources(small_file, tmp_path):
    again = str(tmp_path / "again.scgraph")

    GeoGraph.load_from_scgraph(small_file).save_as_scgraph(again)

    assert GeoGraph.get_scgraph_info(again)["sources"] == SOURCES


def test_shapes_read_from_a_file_are_indexed_like_the_list_that_was_saved(
    small_file,
):
    shapes = GeoGraph.load_from_scgraph(small_file).intermediate_nodes

    assert shapes[-4] == SMALL_SHAPES[0]
    assert shapes[1:3] == SMALL_SHAPES[1:3]


def test_shapes_read_from_a_file_are_copied_as_a_list(small_file):
    shapes = GeoGraph.load_from_scgraph(small_file).intermediate_nodes

    assert type(copy.copy(shapes)) is list
    assert copy.deepcopy(shapes) == SMALL_SHAPES


def test_a_route_on_a_loaded_network_passes_the_points_of_the_shapes(
    small_file,
):
    loaded = GeoGraph.load_from_scgraph(small_file)

    route = _route_0_to_1(loaded)

    assert [0.0029, 0.0058] in route
    assert route == _route_0_to_1(_small())


# A node keeps the id that the geograph was given for it. A node added since
# gets a negative id, and a save keeps both.
@pytest.mark.parametrize(
    "node_ids",
    [[7, 5, 3, 1], [2**40, 5, 3, 1]],
    ids=["ids within 32 bits", "an id beyond 32 bits"],
)
def test_node_ids_and_the_id_of_an_added_node_are_kept_through_saves(
    tmp_path, node_ids
):
    path, again = str(tmp_path / "small.scgraph"), str(
        tmp_path / "again.scgraph"
    )
    _small(node_ids).save_as_scgraph(path)
    loaded = GeoGraph.load_from_scgraph(path)
    loaded.add_coord_node({"latitude": 2.0, "longitude": 2.0}, auto_edge=False)
    # Saved to another file: Windows does not replace a mapped file
    loaded.save_as_scgraph(again)

    assert GeoGraph.load_from_scgraph(again).node_ids == [*node_ids, -1]


def test_without_node_ids_the_id_of_a_node_is_its_position(tmp_path):
    path, again = str(tmp_path / "small.scgraph"), str(
        tmp_path / "again.scgraph"
    )
    _small().save_as_scgraph(path)
    loaded = GeoGraph.load_from_scgraph(path)
    loaded.add_coord_node({"latitude": 2.0, "longitude": 2.0}, auto_edge=False)
    loaded.save_as_scgraph(again)

    assert GeoGraph.load_from_scgraph(again).node_ids == [0, 1, 2, 3, -1]


def test_a_network_whose_ids_are_the_positions_stores_no_node_ids(small_file):
    assert GeoGraph.get_scgraph_info(small_file)["node_ids"] is False


def test_node_ids_are_stored_in_32_bits_when_they_all_fit(tmp_path):
    path = str(tmp_path / "small.scgraph")
    _small([7, 5, 3, 1]).save_as_scgraph(path)

    arrays, _ = network_file.read(path)

    assert arrays["node_ids"].itemsize == 4


def test_node_ids_are_stored_in_64_bits_when_one_does_not_fit_in_32(tmp_path):
    # OpenStreetMap has node ids beyond 32 bits
    path = str(tmp_path / "small.scgraph")
    _small([2**40, 5, 3, 1]).save_as_scgraph(path)

    arrays, _ = network_file.read(path)

    assert arrays["node_ids"].itemsize == 8


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


def test_a_node_moved_by_a_save_keeps_its_former_position_as_its_id(tmp_path):
    path = str(tmp_path / "small.scgraph")
    _small_listed_backwards().save_as_scgraph(path)

    loaded = GeoGraph.load_from_scgraph(path)

    assert list(loaded.node_ids) == [3, 2, 1, 0]


def test_a_save_does_not_change_the_order_of_the_nodes_of_the_geograph(
    tmp_path,
):
    backwards = _small_listed_backwards()

    backwards.save_as_scgraph(str(tmp_path / "small.scgraph"))

    assert backwards.nodes == [[1.0, 1.0], [0.01, 0.0], [0.0, 0.01], [0.0, 0.0]]
    assert backwards.graph_object.graph == [{}, {}, {3: 5}, {1: 1.25, 2: 5}]


def test_a_loaded_file_is_saved_again_as_the_same_file(tmp_path):
    path, again = str(tmp_path / "small.scgraph"), str(
        tmp_path / "again.scgraph"
    )
    digest = _small_listed_backwards().save_as_scgraph(path)

    digest_again = GeoGraph.load_from_scgraph(path).save_as_scgraph(again)

    assert digest_again == digest


# A sea network of two nodes, and a road network of two nodes that then gets
# a node without a mode, a road node, and the sea network. The merge joins the
# two networks through a new node, of the mode "port".
@pytest.fixture(scope="module")
def sea():
    sea = GeoGraph(
        graph=[{1: 1.0}, {0: 1.0}],
        nodes=[[1, 0], [1, 1]],
        modes=[{"name": "sea", "source": "lanes"}],
    )
    sea.metadata = {"sources": [{"name": "lanes"}]}
    return sea


@pytest.fixture(scope="module")
def road_merged_with_sea(sea):
    road = GeoGraph(
        graph=[{1: 1.0}, {0: 1.0}],
        nodes=[[0, 1], [0, 0]],
        modes=[{"name": "road", "source": "osm"}],
    )
    road.metadata = {"sources": [{"name": "osm"}]}
    road.add_coord_node({"latitude": 0, "longitude": 3})
    road.add_coord_node({"latitude": 0, "longitude": 2}, mode="road")
    road.merge_with_other_geograph(
        sea, connection_nodes=[[0.5, 0.5]], mode="port"
    )
    return road


@pytest.fixture(scope="module")
def road_and_sea_file(road_merged_with_sea, tmp_path_factory):
    path = str(tmp_path_factory.mktemp("modes") / "modes.scgraph")
    road_merged_with_sea.save_as_scgraph(path)
    return path


def test_additions_and_a_merge_add_their_modes_after_those_of_the_geograph(
    road_merged_with_sea,
):
    assert road_merged_with_sea.modes == [
        {"name": "road", "source": "osm"},
        {"name": None},
        {"name": "port"},
        {"name": "sea", "source": "lanes"},
    ]


def test_each_node_has_the_mode_that_it_was_added_with(road_merged_with_sea):
    # Two road nodes, the node without a mode, the road node added after it,
    # the port node of the merge, then the two sea nodes
    assert list(road_merged_with_sea.node_modes) == [0, 0, 1, 0, 2, 3, 3]


def test_a_merge_leaves_the_modes_of_the_other_geograph(
    sea, road_merged_with_sea
):
    assert list(sea.node_modes) == [0, 0]


def test_a_merged_geograph_cites_the_sources_of_both(road_merged_with_sea):
    # Each mode names its source, so the merged geograph needs both sources
    assert road_merged_with_sea.metadata["sources"] == [
        {"name": "osm"},
        {"name": "lanes"},
    ]


def test_a_file_lists_the_nodes_mode_by_mode(
    road_merged_with_sea, road_and_sea_file
):
    loaded = GeoGraph.load_from_scgraph(road_and_sea_file)

    assert loaded.modes == road_merged_with_sea.modes
    assert list(loaded.node_modes) == [0, 0, 0, 1, 2, 3, 3]


def test_each_node_keeps_its_mode_and_its_id_through_a_save(
    road_merged_with_sea, road_and_sea_file
):
    road = road_merged_with_sea

    loaded = GeoGraph.load_from_scgraph(road_and_sea_file)

    assert sorted(
        zip(loaded.node_modes, loaded.node_ids, loaded.nodes)
    ) == sorted(zip(road.node_modes, road.node_ids, road.nodes))


def test_a_file_loaded_on_one_mode_has_the_nodes_of_that_mode_only(
    road_and_sea_file,
):
    # Loaded lazily: the file is read when the nodes are first asked for
    roads = GeoGraph.load_from_scgraph(
        road_and_sea_file, lazy=True, modes="road"
    )

    assert sorted(roads.nodes) == [[0, 0], [0, 1], [0, 2]]


def test_a_file_loaded_on_one_mode_routes_on_that_mode(road_and_sea_file):
    # The destination is a sea node of the file. On roads only, the route
    # ends at the road node nearest to it, (0, 1).
    roads = GeoGraph.load_from_scgraph(
        road_and_sea_file, lazy=True, modes="road"
    )

    route = roads.get_shortest_path(
        origin_node={"latitude": 0, "longitude": 0},
        destination_node={"latitude": 1, "longitude": 1},
        node_addition_type="closest",
        destination_node_addition_type="closest",
    )

    assert route["coordinate_path"] == [[0, 0], [0, 0], [0, 1], [1, 1]]


def test_a_node_of_a_257th_mode_is_refused_and_changes_nothing():
    modes = [{"name": str(i)} for i in range(256)]
    geograph = GeoGraph(graph=[{}], nodes=[[0, 0]], modes=modes)

    with pytest.raises(ValueError, match="at most 256 modes"):
        geograph.add_coord_node({"latitude": 0, "longitude": 1}, mode="new")

    assert (len(geograph.nodes), len(geograph.modes)) == (1, 256)


def test_a_merge_that_needs_a_257th_mode_is_refused_and_changes_nothing():
    # 200 modes, 60 other modes and the mode of the connection node: 261
    road_modes = [{"name": f"road {i}"} for i in range(200)]
    sea_modes = [{"name": f"sea {i}"} for i in range(60)]
    road = GeoGraph(graph=[{}], nodes=[[0, 0]], modes=road_modes)
    sea = GeoGraph(graph=[{}], nodes=[[1, 1]], modes=sea_modes)

    with pytest.raises(ValueError, match="at most 256 modes"):
        road.merge_with_other_geograph(sea, connection_nodes=[[0.5, 0.5]])

    assert (len(road.nodes), len(road.modes)) == (1, 200)


def test_nodes_appended_directly_are_saved_in_the_first_mode(tmp_path):
    geo = GeoGraph(
        graph=[{}, {}],
        nodes=[[0, 0], [1, 1]],
        node_modes=[1, 0],
        modes=[{"name": "road"}, {"name": "sea"}],
    )
    geo.graph_object.add_node({})
    geo.nodes.append([2, 2])
    geo.save_as_scgraph(str(tmp_path / "modes.scgraph"))
    loaded = GeoGraph.load_from_scgraph(str(tmp_path / "modes.scgraph"))
    assert dict(zip(map(tuple, loaded.nodes), loaded.node_modes)) == {
        (0, 0): 1,
        (1, 1): 0,
        (2, 2): 0,
    }


@pytest.mark.skipif(
    Graph.__module__ == "scgraph.cpp", reason="a C++ graph is not picklable"
)
def test_a_pickled_geograph_keeps_its_node_ids(tmp_path):
    geo = pickle.loads(pickle.dumps(_small([7, 5, 3, 1])))
    geo.add_coord_node({"latitude": 2.0, "longitude": 2.0}, auto_edge=False)
    geo.save_as_scgraph(str(tmp_path / "small.scgraph"))
    loaded = GeoGraph.load_from_scgraph(str(tmp_path / "small.scgraph"))
    assert loaded.node_ids == [7, 5, 3, 1, -1]


def test_a_geograph_is_refused_with_fewer_node_ids_than_nodes():
    with pytest.raises(ValueError, match="one id per node"):
        GeoGraph(graph=[{}, {}, {}, {}], nodes=SMALL_NODES, node_ids=[7, 5, 3])


def test_a_geograph_is_refused_with_fewer_node_modes_than_nodes():
    with pytest.raises(ValueError, match="a row of modes"):
        GeoGraph(
            graph=[{}, {}, {}, {}], nodes=SMALL_NODES, node_modes=[0, 0, 0]
        )


def test_a_geograph_is_refused_with_a_node_mode_that_is_not_in_its_modes():
    # Without `modes`, a geograph has one mode: the row 1 does not exist
    with pytest.raises(ValueError, match="a row of modes"):
        GeoGraph(
            graph=[{}, {}, {}, {}], nodes=SMALL_NODES, node_modes=[0, 0, 0, 1]
        )


def _small_with_fine_coordinates(coordinate_dtype):
    """The small network with two coordinates that are not multiples of 1e-7
    degree: the longitude of node 3 and the latitude of the shape point.
    `coordinate_dtype` is how the geograph says its coordinates are stored."""
    geograph = _small()
    geograph.coordinate_dtype = coordinate_dtype
    geograph.nodes[3] = [1.0, 1.000000001]
    geograph.intermediate_nodes = [{1: [[0.0029000001, 0.0058]]}, {}, {}, {}]
    return geograph


def test_a_float64_geograph_is_saved_with_its_exact_coordinates(tmp_path):
    path = str(tmp_path / "small.scgraph")
    _small_with_fine_coordinates("float64").save_as_scgraph(path)

    loaded = GeoGraph.load_from_scgraph(path)

    assert GeoGraph.get_scgraph_info(path)["coordinate_dtype"] == "float64"
    assert loaded.nodes[3] == [1.0, 1.000000001]
    assert loaded.intermediate_nodes[0][1] == [[0.0029000001, 0.0058]]


def test_an_int32_geograph_is_saved_with_coordinates_rounded_to_1e_7_degree(
    tmp_path,
):
    path = str(tmp_path / "small.scgraph")
    _small_with_fine_coordinates("int32").save_as_scgraph(path)

    loaded = GeoGraph.load_from_scgraph(path)

    assert GeoGraph.get_scgraph_info(path)["coordinate_dtype"] == "int32"
    assert loaded.nodes[3] == [1.0, 1.0]
    assert loaded.intermediate_nodes[0][1] == [[0.0029, 0.0058]]


def test_coordinate_dtype_int32_rounds_the_coordinates_of_a_float64_geograph(
    tmp_path,
):
    path = str(tmp_path / "small.scgraph")
    _small_with_fine_coordinates("float64").save_as_scgraph(
        path, coordinate_dtype="int32"
    )

    loaded = GeoGraph.load_from_scgraph(path)

    assert GeoGraph.get_scgraph_info(path)["coordinate_dtype"] == "int32"
    assert loaded.nodes[3] == [1.0, 1.0]
    assert loaded.intermediate_nodes[0][1] == [[0.0029, 0.0058]]


def test_coordinate_dtype_float64_keeps_the_coordinates_of_an_int32_geograph(
    tmp_path,
):
    path = str(tmp_path / "small.scgraph")
    _small_with_fine_coordinates("int32").save_as_scgraph(
        path, coordinate_dtype="float64"
    )

    loaded = GeoGraph.load_from_scgraph(path)

    assert GeoGraph.get_scgraph_info(path)["coordinate_dtype"] == "float64"
    assert loaded.nodes[3] == [1.0, 1.000000001]
    assert loaded.intermediate_nodes[0][1] == [[0.0029000001, 0.0058]]


both_coordinate_dtypes = pytest.mark.parametrize(
    "coordinate_dtype", ["float64", "int32"]
)


@both_coordinate_dtypes
def test_a_route_passes_the_shape_points_of_a_file_of_either_dtype(
    tmp_path, coordinate_dtype
):
    path = str(tmp_path / "small.scgraph")
    _small().save_as_scgraph(path, coordinate_dtype=coordinate_dtype)

    route = _route_0_to_1(GeoGraph.load_from_scgraph(path))

    assert [0.0029, 0.0058] in route


@both_coordinate_dtypes
def test_a_loaded_file_is_saved_again_with_the_dtype_of_its_coordinates(
    tmp_path, coordinate_dtype
):
    # The second file has the digest of the first: the same bytes
    path, again = str(tmp_path / "small.scgraph"), str(
        tmp_path / "again.scgraph"
    )
    digest = _small_with_fine_coordinates("float64").save_as_scgraph(
        path, coordinate_dtype=coordinate_dtype
    )

    digest_again = GeoGraph.load_from_scgraph(path).save_as_scgraph(again)

    assert digest_again == digest


def test_a_node_that_is_not_a_finite_number_is_refused_by_its_position(
    tmp_path,
):
    geograph = _small()
    geograph.nodes[3] = [1.0, float("nan")]

    with pytest.raises(ValueError, match="Node 3"):
        geograph.save_as_scgraph(str(tmp_path / "small.scgraph"))


def test_a_shape_point_that_is_not_a_finite_number_is_refused_by_its_arc(
    tmp_path,
):
    geograph = _small()
    geograph.intermediate_nodes = [{1: [[0.0029, float("inf")]]}, {}, {}, {}]

    with pytest.raises(ValueError, match="arc 0 -> 1"):
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


def test_scgraph_info_counts_the_nodes_and_the_arcs(dated_file):
    path, _ = dated_file

    info = GeoGraph.get_scgraph_info(path)

    assert (info["nodes"], info["arcs"]) == (4, 3)


def test_scgraph_info_says_what_the_file_stores_and_how(dated_file):
    path, _ = dated_file

    info = GeoGraph.get_scgraph_info(path)

    assert info["coordinate_dtype"] == "int32"
    assert info["shapes"] is True
    assert info["node_ids"] is False
    assert info["units"] == "mi"


def test_scgraph_info_gives_the_sources_and_the_digest_of_the_file(dated_file):
    path, digest = dated_file

    info = GeoGraph.get_scgraph_info(path)

    assert info["sources"] == DATED_SOURCES
    assert info["content_sha256"] == digest


def test_scgraph_info_gives_the_credit_line_with_each_credit_once(dated_file):
    path, _ = dated_file

    info = GeoGraph.get_scgraph_info(path)

    assert info["attribution"] == (
        "© OpenStreetMap contributors (ODbL-1.0); NGA (NOASSERTION)"
    )


def test_scgraph_info_gives_the_latest_time_of_the_data_of_its_sources(
    dated_file,
):
    path, _ = dated_file

    info = GeoGraph.get_scgraph_info(path)

    assert info["data_up_to"] == "2026-11-06T20:21:43Z"


def test_metadata_may_not_set_a_key_that_scgraph_writes(tmp_path):
    # scgraph writes the units of the geograph itself
    with pytest.raises(ValueError, match="may not set"):
        _small().save_as_scgraph(
            str(tmp_path / "small.scgraph"), metadata={"units": "km"}
        )


def test_a_mode_must_name_a_source_of_the_metadata(tmp_path):
    geograph = _small()
    geograph.modes = [{"name": None, "source": "region-0"}]

    with pytest.raises(ValueError, match="names no source"):
        geograph.save_as_scgraph(
            str(tmp_path / "small.scgraph"),
            metadata={"sources": [{"name": "elsewhere"}]},
        )


# Four nodes: west, north, south and east. Two routes of the same length go
# from west to east, through north or through south. The two graphs differ
# only by the order in which the arcs of west and east are listed. A search
# visits the arcs in that order, and a network file keeps it.
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


def _save_and_read_symmetric(graph, tmp_path):
    """Save `graph` with its nodes in a row, and give what the file says in
    its `symmetric` field."""
    path = str(tmp_path / "graph.scgraph")
    nodes = [[0.0, 0.01 * i] for i in range(len(graph))]
    GeoGraph(graph=graph, nodes=nodes).save_as_scgraph(path)
    return GeoGraph.get_scgraph_info(path)["symmetric"]


def test_a_file_says_symmetric_when_each_arc_has_a_reverse_arc_of_its_weight(
    tmp_path,
):
    two_way_arcs = [{1: 1.0, 2: 1.0}, {0: 1.0}, {0: 1.0}]

    assert _save_and_read_symmetric(two_way_arcs, tmp_path) is True


def test_a_file_says_not_symmetric_when_a_reverse_arc_has_another_weight(
    tmp_path,
):
    two_weights = [{1: 2.0}, {0: 3.0}]

    assert _save_and_read_symmetric(two_weights, tmp_path) is False


def test_a_file_says_not_symmetric_for_a_one_way_cycle(tmp_path):
    # Each node has one arc out and one arc in, and no arc has a reverse arc
    one_way_cycle = [{1: 1.0}, {2: 1.0}, {0: 1.0}]

    assert _save_and_read_symmetric(one_way_cycle, tmp_path) is False


def test_a_file_says_not_symmetric_when_one_arc_to_a_hub_has_no_reverse_arc(
    tmp_path,
):
    # Node 0 has arcs to 2 and 3 and arcs back from 1, 2 and 3: the arc from
    # 1 to 0 has no reverse arc
    hub = [{2: 1.0, 3: 1.0}, {0: 1.0}, {0: 1.0}, {0: 1.0}]

    assert _save_and_read_symmetric(hub, tmp_path) is False


# The tests below write a file from arrays with `network_file.write`, as a
# pipeline does, and read it with `network_file.read`. The arcs are stored by
# origin: the arcs of node u go to heads[offsets[u]:offsets[u + 1]].
ROAD_AND_PORT = [
    {"name": "road", "source": "roads"},
    {"name": "port", "source": "ports"},
]


def _two_road_nodes_and_a_port():
    """The arrays of a network of three nodes: two road nodes joined both
    ways, and a port without arcs. The first node id is beyond 32 bits."""
    return {
        "offsets": array("i", [0, 1, 2, 2]),
        "heads": array("i", [1, 0]),
        "weights": array("d", [1.0, 1.0]),
        "latitudes": array("d", [0.0, 0.0, 1.0]),
        "longitudes": array("d", [0.0, 1.0, 1.0]),
        "node_ids": array("q", [2**40, 7, -1]),
        "node_modes": array("B", [0, 0, 1]),
    }


# `mapped=True` gives views of the file in place of arrays read into memory.
@pytest.mark.parametrize("mapped", [False, True], ids=["copied", "mapped"])
def test_arrays_written_to_a_file_are_read_back_the_same(tmp_path, mapped):
    path = str(tmp_path / "arrays.scgraph")
    written = _two_road_nodes_and_a_port()
    network_file.write(path, written, {"modes": ROAD_AND_PORT})

    arrays, metadata = network_file.read(path, mapped=mapped)

    assert {name: list(values) for name, values in arrays.items()} == {
        name: list(values) for name, values in written.items()
    }
    assert metadata["modes"] == ROAD_AND_PORT


def test_a_file_with_fewer_node_ids_than_nodes_is_refused(tmp_path):
    path = str(tmp_path / "arrays.scgraph")
    arrays = _two_road_nodes_and_a_port()
    arrays["node_ids"] = array("q", [1, 2])
    network_file.write(path, arrays, {"modes": ROAD_AND_PORT})

    with pytest.raises(ValueError, match="one node id per node"):
        network_file.read(path)


def test_a_file_with_fewer_node_modes_than_nodes_is_refused(tmp_path):
    path = str(tmp_path / "arrays.scgraph")
    arrays = _two_road_nodes_and_a_port()
    arrays["node_modes"] = array("B", [0, 0])
    network_file.write(path, arrays, {"modes": ROAD_AND_PORT})

    with pytest.raises(ValueError, match="one node mode per node"):
        network_file.read(path)


def test_a_file_with_a_node_mode_beyond_its_list_of_modes_is_refused(tmp_path):
    path = str(tmp_path / "arrays.scgraph")
    arrays = _two_road_nodes_and_a_port()
    arrays["node_modes"] = array("B", [0, 0, 2])
    network_file.write(path, arrays, {"modes": ROAD_AND_PORT})

    with pytest.raises(ValueError, match="invalid node modes"):
        network_file.read(path)


def test_a_file_with_node_modes_and_no_list_of_modes_is_refused(tmp_path):
    path = str(tmp_path / "arrays.scgraph")
    network_file.write(path, _two_road_nodes_and_a_port(), {})

    with pytest.raises(ValueError, match="without a list of modes"):
        network_file.read(path)


def test_a_file_with_latitudes_and_longitudes_of_two_dtypes_is_refused(
    tmp_path,
):
    path = str(tmp_path / "arrays.scgraph")
    arrays = _two_road_nodes_and_a_port()
    arrays["latitudes"] = array("i", [0, 0, 10**7])
    network_file.write(path, arrays, {"modes": ROAD_AND_PORT})

    with pytest.raises(ValueError, match="coordinates of two dtypes"):
        network_file.read(path)


# `read(modes=...)` reads the nodes of some modes only. It finds them without
# reading the whole file, so the file must list its nodes mode by mode.
def test_reading_some_modes_refuses_node_modes_that_are_not_sorted(tmp_path):
    path = str(tmp_path / "arrays.scgraph")
    arrays = _two_road_nodes_and_a_port()
    arrays["node_modes"] = array("B", [1, 0, 0])
    network_file.write(path, arrays, {"modes": ROAD_AND_PORT})

    with pytest.raises(ValueError, match="unsorted"):
        network_file.read(path, modes=("road",))


def test_reading_some_modes_refuses_a_node_mode_beyond_the_list_of_modes(
    tmp_path,
):
    path = str(tmp_path / "arrays.scgraph")
    arrays = _two_road_nodes_and_a_port()
    arrays["node_modes"] = array("B", [0, 0, 2])
    network_file.write(path, arrays, {"modes": ROAD_AND_PORT})

    with pytest.raises(ValueError, match="unknown node"):
        network_file.read(path, modes=("road",))


def test_reading_some_modes_refuses_more_node_ids_than_nodes(tmp_path):
    path = str(tmp_path / "arrays.scgraph")
    arrays = _two_road_nodes_and_a_port()
    arrays["node_ids"] = array("q", [1, 2, 3, 4])
    network_file.write(path, arrays, {"modes": ROAD_AND_PORT})

    with pytest.raises(ValueError, match="per node"):
        network_file.read(path, modes=("road",))


def test_reading_a_mode_that_the_file_does_not_have_is_refused(tmp_path):
    path = str(tmp_path / "arrays.scgraph")
    network_file.write(
        path, _two_road_nodes_and_a_port(), {"modes": ROAD_AND_PORT}
    )

    with pytest.raises(ValueError, match=r"unknown modes \['rail'\]"):
        network_file.read(path, modes=("rail",))


def test_reading_some_modes_refuses_offsets_that_decrease(tmp_path):
    path = str(tmp_path / "arrays.scgraph")
    arrays = _two_road_nodes_and_a_port()
    arrays["offsets"] = array("i", [0, 2, 1, 2])
    network_file.write(path, arrays, {"modes": ROAD_AND_PORT})

    with pytest.raises(ValueError, match="invalid offsets"):
        network_file.read(path, modes=("road",))


def test_reading_some_modes_refuses_an_arc_to_a_node_that_does_not_exist(
    tmp_path,
):
    path = str(tmp_path / "arrays.scgraph")
    arrays = _two_road_nodes_and_a_port()
    arrays["heads"] = array("i", [-1, 0])
    network_file.write(path, arrays, {"modes": ROAD_AND_PORT})

    with pytest.raises(ValueError, match="arc to a missing node"):
        network_file.read(path, modes=("road",))


def test_reading_some_modes_refuses_shape_offsets_that_decrease(tmp_path):
    path = str(tmp_path / "arrays.scgraph")
    arrays = _two_road_nodes_and_a_port()
    arrays["shape_offsets"] = array("i", [0, 1, 0])
    arrays["shape_points"] = array("d")
    network_file.write(path, arrays, {"modes": ROAD_AND_PORT})

    with pytest.raises(ValueError, match="invalid shape offsets"):
        network_file.read(path, modes=("road",))


def _write_road_port_and_sea(path, coordinate_typecode, with_node_ids=True):
    """Write a file of five nodes, listed mode by mode: the road nodes 10 and
    11, the port 20, the sea nodes 30 and 31. A node has its id as latitude
    and minus its id as longitude, stored as they are in `coordinate_typecode`
    ("d" for float64, "i" for int32). The arcs, by origin:

        10 -> 11 (1 km)    11 -> 10 (1.5 km)    11 -> 20 (2 km)
        20 -> 30 (3 km)    30 -> 31 (4 km)      31 -> 20 (5 km)
        31 -> 30 (6 km)

    The shape of an arc repeats the point (origin id, destination id): once
    from 10 and 31, twice from 11 and 20, never from 30.
    """
    arrays = {
        "offsets": array("i", [0, 1, 3, 4, 5, 7]),
        "heads": array("i", [1, 0, 2, 3, 4, 2, 3]),
        "weights": array("d", [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0]),
        "latitudes": array(coordinate_typecode, [10, 11, 20, 30, 31]),
        "longitudes": array(coordinate_typecode, [-10, -11, -20, -30, -31]),
        "node_ids": array("i", [10, 11, 20, 30, 31]),
        "node_modes": array("B", [0, 0, 1, 2, 2]),
        "shape_offsets": array("i", [0, 1, 3, 5, 7, 7, 8, 9]),
        "shape_points": array(
            coordinate_typecode,
            [10, 11]
            + [11, 10, 11, 10]
            + [11, 20, 11, 20]
            + [20, 30, 20, 30]
            + [31, 20]
            + [31, 30],
        ),
    }
    if not with_node_ids:
        del arrays["node_ids"]
    names = [{"name": name} for name in ("road", "port", "sea")]
    network_file.write(path, arrays, {"modes": names})


def test_reading_one_mode_gives_the_nodes_of_that_mode(tmp_path):
    path = str(tmp_path / "modes.scgraph")
    _write_road_port_and_sea(path, "i")

    arrays, _ = network_file.read(path, modes="road")

    assert list(arrays["node_ids"]) == [10, 11]
    assert list(arrays["latitudes"]) == [10, 11]
    assert list(arrays["longitudes"]) == [-10, -11]
    assert list(arrays["node_modes"]) == [0, 0]


def test_reading_one_mode_gives_the_arcs_between_its_nodes_with_their_shapes(
    tmp_path,
):
    # The arc from 11 to the port is left out
    path = str(tmp_path / "modes.scgraph")
    _write_road_port_and_sea(path, "i")

    arrays, _ = network_file.read(path, modes="road")

    assert list(arrays["offsets"]) == [0, 1, 2]
    assert list(arrays["heads"]) == [1, 0]
    assert list(arrays["weights"]) == [1.0, 1.5]
    assert list(arrays["shape_offsets"]) == [0, 1, 3]
    assert list(arrays["shape_points"]) == [10, 11, 11, 10, 11, 10]


def test_reading_two_modes_gives_their_nodes_in_the_order_of_the_file(
    tmp_path,
):
    # The sea is asked for first, and the file lists the road first
    path = str(tmp_path / "modes.scgraph")
    _write_road_port_and_sea(path, "d")

    arrays, _ = network_file.read(path, modes=("sea", "road"))

    assert list(arrays["node_ids"]) == [10, 11, 30, 31]
    assert list(arrays["latitudes"]) == [10, 11, 30, 31]
    assert list(arrays["longitudes"]) == [-10, -11, -30, -31]
    assert list(arrays["node_modes"]) == [0, 0, 2, 2]


def test_reading_two_modes_renumbers_the_arcs_of_each_mode(tmp_path):
    # Without the port, the sea nodes move from the positions 3 and 4 to the
    # positions 2 and 3. The arcs 11 -> 20 and 31 -> 20 are left out.
    path = str(tmp_path / "modes.scgraph")
    _write_road_port_and_sea(path, "d")

    arrays, _ = network_file.read(path, modes=("sea", "road"))

    assert list(arrays["offsets"]) == [0, 1, 2, 3, 4]
    assert list(arrays["heads"]) == [1, 0, 3, 2]
    assert list(arrays["weights"]) == [1.0, 1.5, 4.0, 6.0]
    assert list(arrays["shape_offsets"]) == [0, 1, 3, 3, 4]
    assert list(arrays["shape_points"]) == [10, 11, 11, 10, 11, 10, 31, 30]


@pytest.mark.parametrize("coordinate_typecode", ["i", "d"])
def test_reading_some_modes_keeps_the_dtype_of_the_coordinates(
    tmp_path, coordinate_typecode
):
    path = str(tmp_path / "modes.scgraph")
    _write_road_port_and_sea(path, coordinate_typecode)

    arrays, _ = network_file.read(path, modes="road")

    assert arrays["latitudes"].typecode == coordinate_typecode
    assert arrays["longitudes"].typecode == coordinate_typecode
    assert arrays["shape_points"].typecode == coordinate_typecode


def test_reading_some_modes_of_a_file_without_node_ids_gives_the_positions(
    tmp_path,
):
    # The id of a node is then its position in the whole file
    path = str(tmp_path / "modes.scgraph")
    _write_road_port_and_sea(path, "d", with_node_ids=False)

    arrays, _ = network_file.read(path, modes=("sea", "road"))

    assert list(arrays["node_ids"]) == [0, 1, 3, 4]


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
        "offsets": array("i", [0, 1, 2]),
        "heads": array("i", [1, 0]),
        "weights": every_second_value,
        "latitudes": array("d", [0.0, 0.0]),
        "longitudes": array("d", [0.0, 1.0]),
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
# Each test below edits the nodes of a new load of the small network, after a
# fifth node was appended.
@pytest.fixture
def nodes_of_a_file(tmp_path):
    path = str(tmp_path / "small.scgraph")
    _small().save_as_scgraph(path)
    nodes = GeoGraph.load_from_scgraph(path).nodes
    nodes.append([3.0, 3.0])
    return nodes


def test_nodes_read_from_a_file_take_a_new_node_at_their_end(nodes_of_a_file):
    assert nodes_of_a_file == [*SMALL_NODES, [3.0, 3.0]]


def test_nodes_read_from_a_file_are_read_from_the_end_and_by_slice(
    nodes_of_a_file,
):
    assert nodes_of_a_file[-1] == [3.0, 3.0]
    assert nodes_of_a_file[-2] == [1.0, 1.0]
    assert nodes_of_a_file[1:3] == [[0.0, 0.01], [0.01, 0.0]]


def test_an_added_node_is_replaced(nodes_of_a_file):
    nodes_of_a_file[-1] = [4.0, 4.0]

    assert nodes_of_a_file == [*SMALL_NODES, [4.0, 4.0]]


def test_an_added_node_is_popped(nodes_of_a_file):
    nodes_of_a_file.pop()

    assert nodes_of_a_file == SMALL_NODES


def test_nodes_read_from_a_file_are_extended(nodes_of_a_file):
    nodes_of_a_file.extend([[5.0, 5.0], [6.0, 6.0]])

    assert nodes_of_a_file == [
        *SMALL_NODES,
        [3.0, 3.0],
        [5.0, 5.0],
        [6.0, 6.0],
    ]


def test_a_node_of_the_file_is_replaced(nodes_of_a_file):
    nodes_of_a_file[1] = [7.0, 7.0]

    assert nodes_of_a_file == [
        [0.0, 0.0],
        [7.0, 7.0],
        [0.01, 0.0],
        [1.0, 1.0],
        [3.0, 3.0],
    ]


def test_a_node_is_inserted_before_the_nodes_of_the_file(nodes_of_a_file):
    nodes_of_a_file.insert(0, [8.0, 8.0])

    assert nodes_of_a_file == [[8.0, 8.0], *SMALL_NODES, [3.0, 3.0]]


def test_nodes_of_the_file_are_deleted_by_slice(nodes_of_a_file):
    del nodes_of_a_file[2:4]

    assert nodes_of_a_file == [[0.0, 0.0], [0.0, 0.01], [3.0, 3.0]]


def test_the_nodes_of_a_path_are_taken_from_the_file_and_from_added_nodes(
    nodes_of_a_file,
):
    # A route reads the coordinates of its path with `take`. The position -1
    # is the last node, as in a list.
    assert nodes_of_a_file.take([-1, 0, 4]) == [
        [3.0, 3.0],
        [0.0, 0.0],
        [3.0, 3.0],
    ]


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
WINDOWS_WITH_CPP = os.name == "nt" and Graph.__module__ == "scgraph.cpp"


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


def test_a_file_of_another_format_is_refused(file_to_damage):
    file_to_damage.write_bytes(b'{"type": "GeoGraph"}')

    with pytest.raises(ValueError, match="not a scgraph network file"):
        GeoGraph.load_from_scgraph(str(file_to_damage))


def test_a_file_of_a_later_format_version_is_refused(file_to_damage):
    data = file_to_damage.read_bytes()
    header = _read_header(data)
    header["format_version"] = 2
    file_to_damage.write_bytes(_replace_header(data, header))

    with pytest.raises(ValueError, match="format version 2"):
        GeoGraph.load_from_scgraph(str(file_to_damage))


def test_a_file_cut_before_its_end_is_refused(file_to_damage):
    data = file_to_damage.read_bytes()
    file_to_damage.write_bytes(data[:-8])

    with pytest.raises(ValueError, match="invalid array"):
        GeoGraph.load_from_scgraph(str(file_to_damage))


def test_a_file_whose_header_gives_an_array_a_wrong_dtype_is_refused(
    file_to_damage,
):
    data = file_to_damage.read_bytes()
    header = _read_header(data)
    header["arrays"]["heads"]["dtype"] = "float64"
    file_to_damage.write_bytes(_replace_header(data, header))

    with pytest.raises(ValueError, match="invalid array"):
        GeoGraph.load_from_scgraph(str(file_to_damage))


def test_a_file_whose_header_is_said_longer_than_the_file_is_refused(
    file_to_damage,
):
    data = file_to_damage.read_bytes()
    length_of_the_file = len(data).to_bytes(8, "little")
    file_to_damage.write_bytes(data[:40] + length_of_the_file + data[48:])

    with pytest.raises(ValueError, match="invalid header length"):
        GeoGraph.load_from_scgraph(str(file_to_damage))


def test_a_file_whose_header_places_an_array_before_the_arrays_is_refused(
    file_to_damage,
):
    data = file_to_damage.read_bytes()
    header = _read_header(data)
    header["arrays"]["offsets"]["offset"] = -_find_start_of_arrays(data)
    file_to_damage.write_bytes(_replace_header(data, header))

    with pytest.raises(ValueError, match="invalid array"):
        GeoGraph.load_from_scgraph(str(file_to_damage))


def test_a_file_whose_header_lists_no_arrays_is_refused(file_to_damage):
    data = file_to_damage.read_bytes()
    header = _read_header(data)
    del header["arrays"]
    file_to_damage.write_bytes(_replace_header(data, header))

    with pytest.raises(ValueError, match="invalid header"):
        GeoGraph.load_from_scgraph(str(file_to_damage))


def test_a_file_whose_header_is_not_a_json_object_is_refused(file_to_damage):
    data = file_to_damage.read_bytes()
    header_in_a_list = [_read_header(data)]
    file_to_damage.write_bytes(_replace_header(data, header_in_a_list))

    with pytest.raises(ValueError, match="invalid header"):
        GeoGraph.load_from_scgraph(str(file_to_damage))


# The next two damages are in the arrays of the arcs. `network_file.read`
# finds them in the pure-Python build. The C++ graph, which reads the file in
# place, finds them in the C++ build: each build has its message.
def test_a_file_with_an_arc_to_a_node_that_does_not_exist_is_refused(
    file_to_damage,
):
    data = file_to_damage.read_bytes()
    file_to_damage.write_bytes(_replace_int32(data, "heads", 0, 99))

    with pytest.raises(
        ValueError, match="arc to a missing node|is not in the graph"
    ):
        GeoGraph.load_from_scgraph(str(file_to_damage))


def test_a_file_whose_offsets_go_past_its_arcs_is_refused(file_to_damage):
    data = file_to_damage.read_bytes()
    file_to_damage.write_bytes(_replace_int32(data, "offsets", 1, 2**30))

    with pytest.raises(ValueError, match="invalid offsets|non-decreasing"):
        GeoGraph.load_from_scgraph(str(file_to_damage))


# Shape offsets that go past the shape points are refused when the file is
# loaded, or at the latest where a shape is read: the C++ build reads the
# shapes in place and does not check them all when it loads the file.
def test_a_route_refuses_shape_offsets_that_go_past_the_shape_points(
    file_to_damage,
):
    data = file_to_damage.read_bytes()
    file_to_damage.write_bytes(_replace_int32(data, "shape_offsets", 1, 2**30))

    with pytest.raises(ValueError, match="invalid shape offsets"):
        _route_0_to_1(GeoGraph.load_from_scgraph(str(file_to_damage)))


def test_reading_a_shape_refuses_shape_offsets_that_go_past_the_shape_points(
    file_to_damage,
):
    data = file_to_damage.read_bytes()
    file_to_damage.write_bytes(_replace_int32(data, "shape_offsets", 1, 2**30))

    with pytest.raises(ValueError, match="invalid shape offsets"):
        dict(
            GeoGraph.load_from_scgraph(str(file_to_damage)).intermediate_nodes[
                0
            ]
        )


def test_hilbert_order_follows_the_curve():
    # One point per quadrant of the globe: north-east, south-west, north-west, south-east;
    # the curve visits them south-west, north-west, north-east, south-east
    nodes = [[45, 90], [-45, -90], [45, -90], [-45, 90]]
    assert hilbert_order(nodes) == [1, 2, 0, 3]
