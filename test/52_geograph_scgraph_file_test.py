import copy
import hashlib
import json
import os
import pickle
from array import array

import pytest

from scgraph import GeoGraph, Graph, network_file
from scgraph.graph import Graph as PythonGraph
from scgraph.utils import has_cpp
from scgraph.helpers.hilbert import hilbert_order

# A one-way arc (0 -> 2), a shape on one arc only, integer weights and an isolated node
_GRAPH = [{2: 1.25, 1: 5}, {0: 5}, {}, {}]
_NODES = [[0.0, 0.0], [0.0, 0.01], [0.01, 0.0], [1.0, 1.0]]
# (0.0029 * 1e7 is just below 29000: shape points are rounded to 1e-7 degree, not cut)
_SHAPES = [{1: [[0.0029, 0.0058]]}, {}, {}, {}]
# Like those build_geograph records: a network built from many extracts keeps them all
_SOURCES = [
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
        graph=[dict(row) for row in _GRAPH],
        nodes=[list(node) for node in _NODES],
        intermediate_nodes=_SHAPES,
        default_off_graph_circuity=2,
        geograph_units="mi",
        node_ids=node_ids,
    )


@pytest.mark.parametrize("save_intermediate_nodes", [True, False])
def test_save_load_scgraph(tmp_path, save_intermediate_nodes):
    path = str(tmp_path / "small.scgraph")
    _small().save_as_scgraph(
        path, save_intermediate_nodes, metadata={"sources": _SOURCES}
    )
    arrays, metadata = network_file.read(path)
    assert metadata["symmetric"] is False
    assert metadata["sources"] == _SOURCES
    loaded = GeoGraph.load_from_scgraph(path)
    # What the file says of how the network was built is kept, and saved again
    assert loaded.metadata == {"sources": _SOURCES}
    loaded.save_as_scgraph(str(tmp_path / "again.scgraph"))
    again = network_file.read(str(tmp_path / "again.scgraph"))[1]
    assert again["sources"] == _SOURCES
    assert loaded.graph_object.graph == _GRAPH
    assert loaded.nodes == _NODES
    assert loaded.intermediate_nodes == (
        _SHAPES if save_intermediate_nodes else None
    )
    assert (loaded.default_off_graph_circuity, loaded.geograph_units) == (
        2,
        "mi",
    )
    if save_intermediate_nodes:
        # Read like the list of dicts it was saved from (negative indices and slices
        # included), and copied as one
        shapes = loaded.intermediate_nodes
        assert (
            shapes[-len(_SHAPES)] == _SHAPES[0] and shapes[1:3] == _SHAPES[1:3]
        )
        assert (
            type(copy.copy(shapes)) is list and copy.deepcopy(shapes) == _SHAPES
        )
        assert _route_0_to_1(loaded) == _route_0_to_1(_small())


# A network keeps its node ids, and a node added since gets a negative id; a network
# without ids (each id is its position) stores none
# (as int32 when every id fits, int64 otherwise, e.g. OSM ids)
@pytest.mark.parametrize(
    "node_ids, expected, size",
    [
        (None, [0, 1, 2, 3, -1], None),
        ([7, 5, 3, 1], [7, 5, 3, 1, -1], 4),
        ([2**40, 5, 3, 1], [2**40, 5, 3, 1, -1], 8),
    ],
)
def test_save_load_scgraph_keeps_node_ids(tmp_path, node_ids, expected, size):
    path = str(tmp_path / "small.scgraph")
    _small(node_ids).save_as_scgraph(path)
    stored = network_file.read(path)[0].get("node_ids")
    assert (None if stored is None else memoryview(stored).itemsize) == size
    loaded = GeoGraph.load_from_scgraph(path)
    loaded.add_coord_node({"latitude": 2.0, "longitude": 2.0}, auto_edge=False)
    # Saved to another file: Windows does not replace a mapped file
    again = str(tmp_path / "again.scgraph")
    loaded.save_as_scgraph(again)
    assert GeoGraph.load_from_scgraph(again).node_ids == expected


def test_save_as_scgraph_writes_the_nodes_in_hilbert_order(tmp_path):
    # The small network with its nodes listed backwards: written in Hilbert order (the
    # small network's own), each node keeping its former position as its id, the
    # geograph itself unchanged; a file already in that order is written as it is
    def back(i):
        return len(_NODES) - 1 - i

    backwards = GeoGraph(
        graph=[
            {back(v): w for v, w in _GRAPH[back(u)].items()} for u in range(4)
        ],
        nodes=_NODES[::-1],
        intermediate_nodes=[
            {back(v): s for v, s in _SHAPES[back(u)].items()} for u in range(4)
        ],
    )
    path, again = str(tmp_path / "small.scgraph"), str(
        tmp_path / "again.scgraph"
    )
    digest = backwards.save_as_scgraph(path)
    loaded = GeoGraph.load_from_scgraph(path)
    assert (loaded.nodes, list(loaded.node_ids)) == (_NODES, [3, 2, 1, 0])
    assert loaded.graph_object.graph == _GRAPH
    assert loaded.intermediate_nodes == _SHAPES
    assert backwards.nodes == _NODES[::-1]
    assert loaded.save_as_scgraph(again) == digest


def test_nodes_keep_their_modes_through_additions_merges_and_saves(tmp_path):
    road = GeoGraph(
        graph=[{1: 1.0}, {0: 1.0}],
        nodes=[[0, 1], [0, 0]],
        modes=[{"name": "road", "source": "osm"}],
    )
    road.metadata = {"sources": [{"name": "osm"}]}
    # A node of the mode without a name, then one of the road
    road.add_coord_node({"latitude": 0, "longitude": 3})
    road.add_coord_node({"latitude": 0, "longitude": 2}, mode="road")
    sea = GeoGraph(
        graph=[{1: 1.0}, {0: 1.0}],
        nodes=[[1, 0], [1, 1]],
        modes=[{"name": "sea", "source": "lanes"}],
    )
    sea.metadata = {"sources": [{"name": "lanes"}]}
    road.merge_with_other_geograph(
        sea, connection_nodes=[[0.5, 0.5]], mode="port"
    )
    assert road.modes == [
        {"name": "road", "source": "osm"},
        {"name": None},
        {"name": "port"},
        {"name": "sea", "source": "lanes"},
    ]
    assert list(road.node_modes) == [0, 0, 1, 0, 2, 3, 3]
    assert list(sea.node_modes) == [0, 0]
    # The merged graph cites both sources, so that each mode's source is named
    assert road.metadata["sources"] == [{"name": "osm"}, {"name": "lanes"}]
    # Saved by mode, then along the curve: each node keeps its mode and its id
    path = str(tmp_path / "modes.scgraph")
    road.save_as_scgraph(path)
    loaded = GeoGraph.load_from_scgraph(path)
    assert loaded.modes == road.modes
    assert list(loaded.node_modes) == sorted(road.node_modes)
    assert sorted(
        zip(loaded.node_modes, loaded.node_ids, loaded.nodes)
    ) == sorted(zip(road.node_modes, road.node_ids, road.nodes))


def test_a_geograph_has_at_most_256_modes():
    # Refused before any change, when a node or a merge would need a 257th mode
    many = [{"name": str(i)} for i in range(200)]
    geo = GeoGraph(graph=[{}], nodes=[[0, 0]], modes=many + many[:56])
    with pytest.raises(ValueError, match="at most 256 modes"):
        geo.add_coord_node({"latitude": 0, "longitude": 1}, mode="new")
    assert (len(geo.nodes), len(geo.modes)) == (1, 256)
    road = GeoGraph(graph=[{}], nodes=[[0, 0]], modes=many)
    sea = GeoGraph(graph=[{}], nodes=[[1, 1]], modes=many[:60])
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


@pytest.mark.parametrize(
    "data, message",
    [
        ({"node_ids": [7, 5, 3]}, "one id per node"),
        ({"node_modes": [0, 0, 0]}, "a row of modes"),
        ({"node_modes": [0, 0, 0, 1]}, "a row of modes"),
    ],
)
def test_geograph_needs_an_id_and_a_mode_per_node(data, message):
    with pytest.raises(ValueError, match=message):
        GeoGraph(
            graph=[{}, {}, {}, {}], nodes=[list(n) for n in _NODES], **data
        )


# Coordinates are stored as save_as_scgraph's coordinate_dtype says, by default as
# the geograph's own: exactly in float64, rounded to 1e-7 degree in int32; read
# back (routes included) through either, and kept by the next save
@pytest.mark.parametrize(
    "own, chosen, size, node, point",
    [
        ("float64", "auto", 8, [1.0, 1.000000001], [0.0029000001, 0.0058]),
        ("int32", "auto", 4, [1.0, 1.0], [0.0029, 0.0058]),
        ("float64", "int32", 4, [1.0, 1.0], [0.0029, 0.0058]),
        ("int32", "float64", 8, [1.0, 1.000000001], [0.0029000001, 0.0058]),
    ],
)
def test_save_as_scgraph_stores_coordinates_as_chosen(
    tmp_path, own, chosen, size, node, point
):
    geo = _small()
    geo.coordinate_dtype = own
    geo.nodes[3] = [1.0, 1.000000001]
    geo.intermediate_nodes = [{1: [[0.0029000001, 0.0058]]}, {}, {}, {}]
    path, again = str(tmp_path / "small.scgraph"), str(
        tmp_path / "again.scgraph"
    )
    digest = geo.save_as_scgraph(path, coordinate_dtype=chosen)
    arrays = network_file.read(path)[0]
    assert {
        memoryview(arrays[n]).itemsize for n in network_file.COORDINATES
    } == {size}
    loaded = GeoGraph.load_from_scgraph(path)
    assert (loaded.nodes[3], loaded.intermediate_nodes[0][1]) == (node, [point])
    assert point in _route_0_to_1(loaded)
    assert loaded.save_as_scgraph(again) == digest


@pytest.mark.parametrize(
    "node, point, chosen, message",
    [
        ([1.0, float("nan")], [0.0029, 0.0058], "auto", "Node 3"),
        ([1.0, 1.0], [0.0029, float("inf")], "auto", "arc 0 -> 1"),
        ([1.0, 1.0], [0.0029, 214.75], "int32", "within ±214.7483647"),
        ([1.0, 1.0], [0.0029, 0.0058], "int16", "must be 'auto', 'float64' or"),
    ],
)
def test_save_as_scgraph_rejects_coordinates_it_cannot_store(
    tmp_path, node, point, chosen, message
):
    geo = _small()
    geo.nodes[3], geo.intermediate_nodes = node, [{1: [point]}, {}, {}, {}]
    with pytest.raises(ValueError, match=message):
        geo.save_as_scgraph(
            str(tmp_path / "small.scgraph"), coordinate_dtype=chosen
        )


def test_scgraph_info_reads_what_a_network_file_holds(tmp_path):
    path = str(tmp_path / "small.scgraph")
    dated = [
        {**_SOURCES[0], "version": "2026-11-06T20:21:43Z"},
        {**_SOURCES[1], "version": "2026-10-01T00:00:00Z"},
        {**_SOURCES[2], "credit": "NGA", "license": "NOASSERTION"},
    ]
    digest = _small().save_as_scgraph(
        path, metadata={"sources": dated}, coordinate_dtype="int32"
    )
    info = GeoGraph.scgraph_info(path)
    assert {
        key: info[key] for key in ("nodes", "arcs", "coordinate_dtype")
    } == {
        "nodes": 4,
        "arcs": 3,
        "coordinate_dtype": "int32",
    }
    assert (info["shapes"], info["node_ids"], info["units"]) == (
        True,
        False,
        "mi",
    )
    assert (info["sources"], info["content_sha256"]) == (dated, digest)
    # The credit line to cite, each credit once, and the newest time the data is up to
    assert info["attribution"] == (
        "© OpenStreetMap contributors (ODbL-1.0); NGA (NOASSERTION)"
    )
    assert info["data_up_to"] == "2026-11-06T20:21:43Z"


# Metadata cannot contradict what scgraph writes, and a mode cites a source by name
@pytest.mark.parametrize(
    "metadata, message",
    [
        ({"units": "km"}, "may not set"),
        ({"sources": [{"name": "elsewhere"}]}, "names no source"),
    ],
)
def test_save_as_scgraph_refuses_contradicting_metadata(
    tmp_path, metadata, message
):
    geo = _small()
    geo.modes = [{"name": None, "source": "region-0"}]
    with pytest.raises(ValueError, match=message):
        geo.save_as_scgraph(str(tmp_path / "x.scgraph"), metadata=metadata)


def _route_0_to_1(geograph):
    # Through the arc 0 -> 1, which has a shape
    return geograph.get_shortest_path(
        origin_node={"latitude": 0, "longitude": 0},
        destination_node={"latitude": 0, "longitude": 0.01},
        node_addition_type="closest",
        destination_node_addition_type="closest",
    )["coordinate_path"]


# Two routes of the same length from node 0 to node 3, through 1 or through 2, with the
# arcs in either order: a network file keeps the order searches visit them, so the file
# gives the route the graph gave
@pytest.mark.parametrize("first", [1, 2])
def test_a_network_file_gives_the_same_route_where_two_tie(tmp_path, first):
    second = 3 - first
    geo = GeoGraph(
        graph=[
            {first: 1.0, second: 1.0},
            {3: 1.0, 0: 1.0},
            {0: 1.0, 3: 1.0},
            {second: 1.0, first: 1.0},
        ],
        nodes=[[0.0, 0.0], [0.01, 0.01], [-0.01, 0.01], [0.0, 0.02]],
    )

    def route(geograph):
        return geograph.get_shortest_path(
            origin_node={"latitude": 0, "longitude": 0},
            destination_node={"latitude": 0, "longitude": 0.02},
            node_addition_type="closest",
            destination_node_addition_type="closest",
        )["coordinate_path"]

    geo.save_as_scgraph(str(tmp_path / "tie.scgraph"))
    saved = GeoGraph.load_from_scgraph(str(tmp_path / "tie.scgraph"))
    assert route(saved) == route(geo)


@pytest.mark.parametrize(
    "graph, symmetric",
    [
        ([{1: 1.0, 2: 1.0}, {0: 1.0}, {0: 1.0}], True),
        ([{1: 2.0}, {0: 3.0}], False),  # reverse arc of another weight
        ([{1: 1.0}, {2: 1.0}, {0: 1.0}], False),  # a one-way cycle
        # The arc 1 -> 0 has no reverse arc
        ([{2: 1.0, 3: 1.0}, {0: 1.0}, {0: 1.0}, {0: 1.0}], False),
    ],
)
def test_save_as_scgraph_flags_symmetric_graphs(tmp_path, graph, symmetric):
    path = str(tmp_path / "graph.scgraph")
    nodes = [[0.0, 0.01 * i] for i in range(len(graph))]
    GeoGraph(graph=graph, nodes=nodes).save_as_scgraph(path)
    assert network_file.read(path)[1]["symmetric"] is symmetric


# A file written from arrays (the graph's arcs, with its nodes in a given order or not)
# keeps its node ids and modes; modes index the header's list of modes
_MODES = [
    {"name": "road", "source": "roads"},
    {"name": "port", "source": "ports"},
]


def _write_from_arrays(path, graph, order=None, modes=_MODES, **columns):
    offsets, heads, weights = graph._csr(order)
    arrays = {
        "offsets": offsets,
        "heads": heads,
        "weights": weights,
        "latitudes": array("d", [0.0, 0.0, 1.0]),
        "longitudes": array("d", [0.0, 1.0, 1.0]),
        "node_ids": array("q", [2**40, 7, -1]),
        "node_modes": array("B", [0, 0, 1]),
        **columns,
    }
    network_file.write(path, arrays, {} if modes is None else {"modes": modes})


@pytest.mark.parametrize(
    "graph_class",
    [PythonGraph] + ([Graph] if has_cpp() else []),
    ids=lambda graph_class: graph_class.__module__,
)
@pytest.mark.parametrize(
    "order, mapped, rows",
    [
        (None, False, [{1: 1.5, 2: 3.0}, {0: 1.5, 2: 2.0}, {1: 2.0}]),
        # Old node 2 first: old 0 -> new 1, old 1 -> new 2, old 2 -> new 0
        ([2, 0, 1], True, [{2: 2.0}, {2: 1.5, 0: 3.0}, {1: 1.5, 0: 2.0}]),
    ],
)
def test_network_file_written_from_arrays(
    tmp_path, graph_class, order, mapped, rows
):
    path = str(tmp_path / "arrays.scgraph")
    graph = graph_class([{1: 1.5, 2: 3.0}, {0: 1.5, 2: 2.0}, {1: 2.0}])
    _write_from_arrays(path, graph, order)
    arrays, metadata = network_file.read(path, mapped=mapped)
    offsets, heads, weights = (
        arrays[k] for k in ("offsets", "heads", "weights")
    )
    assert [
        dict(zip(heads[a:b], weights[a:b]))
        for a, b in zip(offsets, offsets[1:])
    ] == rows
    assert list(arrays["node_ids"]) == [2**40, 7, -1]
    assert list(arrays["node_modes"]) == [0, 0, 1]
    assert metadata["modes"] == _MODES


@pytest.mark.parametrize(
    "columns, message",
    [
        ({"node_ids": array("q", [1, 2])}, "one node id per node"),
        ({"node_modes": array("B", [0, 0])}, "one node mode per node"),
        ({"node_modes": array("B", [0, 0, 2])}, "invalid node modes"),
        ({"modes": None}, "without a list of modes"),
        ({"latitudes": array("i", [0, 0, 10**7])}, "coordinates of two dtypes"),
    ],
)
def test_network_file_rejects_invalid_node_columns(tmp_path, columns, message):
    path = str(tmp_path / "arrays.scgraph")
    _write_from_arrays(path, Graph([{1: 1.0}, {0: 1.0}, {}]), **columns)
    with pytest.raises(ValueError, match=message):
        network_file.read(path)


def test_load_from_scgraph_reads_an_empty_network(tmp_path):
    path = str(tmp_path / "empty.scgraph")
    GeoGraph(graph=[], nodes=[]).save_as_scgraph(path)
    assert GeoGraph.load_from_scgraph(path).nodes == []


def test_save_as_scgraph_records_the_sha256_of_the_file(tmp_path):
    # The identity of the file, in its bytes 8 to 39: the digest of every byte after them
    path = tmp_path / "small.scgraph"
    digest = _small().save_as_scgraph(str(path))
    data = path.read_bytes()
    assert (
        digest
        == network_file.read(str(path))[1]["content_sha256"]
        == data[8:40].hex()
        == hashlib.sha256(data[40:]).hexdigest()
    )
    # The same network and metadata, whatever the order of their keys, give the same file
    reordered = [dict(reversed(source.items())) for source in _SOURCES]
    assert _small().save_as_scgraph(
        str(path), metadata={"sources": _SOURCES}
    ) == (
        _small().save_as_scgraph(
            str(tmp_path / "again.scgraph"), metadata={"sources": reordered}
        )
    )


def test_save_as_scgraph_leaves_the_previous_file_whole_when_it_fails(
    tmp_path, monkeypatch
):
    path = tmp_path / "small.scgraph"
    _small().save_as_scgraph(str(path))
    before = path.read_bytes()

    def fail(values):
        raise OSError("disk full")

    monkeypatch.setattr(network_file, "_little_endian", fail)
    with pytest.raises(OSError):
        _small().save_as_scgraph(str(path))
    assert path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["small.scgraph"]


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


def test_nodes_read_from_a_network_file_behave_as_a_list(tmp_path):
    # nodes reads the file's coordinate arrays: each edit, done on a list too, gives the
    # same nodes, and snapping sees the added nodes
    path = str(tmp_path / "small.scgraph")
    _small().save_as_scgraph(path)
    for edit in (
        lambda n: n.__setitem__(-1, [4.0, 4.0]),
        lambda n: n.pop(),
        lambda n: n.extend([[5.0, 5.0], [6.0, 6.0]]),
        lambda n: n.__setitem__(1, [7.0, 7.0]),
        lambda n: n.insert(0, [8.0, 8.0]),
        lambda n: n.__delitem__(slice(2, 4)),
    ):
        nodes = GeoGraph.load_from_scgraph(path).nodes
        expected = [list(node) for node in _NODES]
        for n in (nodes, expected):
            n.append([3.0, 3.0])
            edit(n)
        assert (nodes, nodes[-1], nodes[1:3]) == (
            expected,
            expected[-1],
            expected[1:3],
        )
        assert nodes.take(range(-1, len(nodes))) == [expected[-1], *expected]
    loaded = GeoGraph.load_from_scgraph(path)
    loaded.add_coord_node({"latitude": 9.0, "longitude": 9.0}, auto_edge=False)
    assert loaded.snap_index.closest_idx([8.9, 8.9]) == len(_NODES)
    graphjson = str(tmp_path / "small.graphjson")
    loaded.save_as_graphjson(graphjson)
    assert GeoGraph.load_from_graphjson(graphjson).nodes == [
        *_NODES,
        [9.0, 9.0],
    ]


def test_save_as_scgraph_over_a_file_in_use(tmp_path):
    # The C++ graph reads its file in place: replacing the file leaves the open graph
    # whole (Linux, macOS), or is refused (Windows does not replace a mapped file)
    path = str(tmp_path / "small.scgraph")
    _small().save_as_scgraph(path)
    opened = GeoGraph.load_from_scgraph(path)
    other = GeoGraph(graph=[{1: 7.0}, {0: 7.0}], nodes=[[0, 0], [0, 0.01]])
    if os.name == "nt" and Graph.__module__ == "scgraph.cpp":
        with pytest.raises(PermissionError, match="open in a graph"):
            other.save_as_scgraph(path)
        return
    other.save_as_scgraph(path)
    assert opened.graph_object.dijkstra(0, 1)["length"] == 5
    assert opened.graph_object.graph == _GRAPH
    assert GeoGraph.load_from_scgraph(path).graph_object.graph == other.graph


def _damage(data, how):
    header_length = int.from_bytes(data[40:48], "little")
    header = json.loads(data[48 : 48 + header_length])
    # Array offsets count from the end of the header, padded to 64 bytes
    base = -(-(48 + header_length) // 64) * 64
    if how == "not a network file":
        return b'{"type": "GeoGraph"}'
    if how == "later version":
        header["format_version"] = 2
    if how == "header without arrays":
        del header["arrays"]
    if how == "heads of another dtype":
        header["arrays"]["heads"]["dtype"] = "float64"
    if how == "header is not an object":
        header = [header]
    if how == "truncated":
        return data[:-8]
    if how == "header longer than the file":
        return data[:40] + (len(data)).to_bytes(8, "little") + data[48:]
    if how == "array in the header":
        header["arrays"]["offsets"]["offset"] = -base
    if how == "offsets past the arcs":
        offsets = base + header["arrays"]["offsets"]["offset"]
        big = (2**30).to_bytes(4, "little")
        return data[: offsets + 4] + big + data[offsets + 8 :]
    if how == "shape offsets past the points":
        shapes = base + header["arrays"]["shape_offsets"]["offset"]
        big = (2**30).to_bytes(4, "little")
        return data[: shapes + 4] + big + data[shapes + 8 :]
    if how == "arc to a missing node":
        heads = base + header["arrays"]["heads"]["offset"]
        return data[:heads] + (99).to_bytes(4, "little") + data[heads + 4 :]
    # The edited header, padded again, then the arrays as they were
    text = json.dumps(header).encode()
    length = len(text).to_bytes(8, "little")
    padding = bytes(-(48 + len(text)) % 64)
    return data[:40] + length + text + padding + data[base:]


@pytest.mark.parametrize(
    "how, message",
    [
        ("not a network file", "not a scgraph network file"),
        ("later version", "format version 2"),
        ("truncated", "invalid array"),
        ("heads of another dtype", "invalid array"),
        ("header longer than the file", "invalid header length"),
        ("array in the header", "invalid array"),
        # Checked by network_file.read, or by the C++ graph on a mapped file
        ("arc to a missing node", "arc to a missing node|is not in the graph"),
        ("offsets past the arcs", "invalid offsets|non-decreasing"),
        ("header without arrays", "invalid header"),
        ("header is not an object", "invalid header"),
    ],
)
def test_load_from_scgraph_rejects_damaged_files(tmp_path, how, message):
    path = tmp_path / "small.scgraph"
    _small().save_as_scgraph(str(path))
    path.write_bytes(_damage(path.read_bytes(), how))
    with pytest.raises(ValueError, match=message):
        GeoGraph.load_from_scgraph(str(path))


@pytest.mark.parametrize(
    "read",
    [_route_0_to_1, lambda geograph: dict(geograph.intermediate_nodes[0])],
    ids=["route", "shapes"],
)
def test_load_from_scgraph_rejects_damaged_shape_offsets(tmp_path, read):
    # Checked by network_file.read, or where a shape is read from a mapped file
    path = tmp_path / "small.scgraph"
    _small().save_as_scgraph(str(path))
    path.write_bytes(
        _damage(path.read_bytes(), "shape offsets past the points")
    )
    with pytest.raises(ValueError, match="invalid shape offsets"):
        read(GeoGraph.load_from_scgraph(str(path)))


def test_hilbert_order_follows_the_curve():
    # One point per quadrant of the globe: north-east, south-west, north-west, south-east;
    # the curve visits them south-west, north-west, north-east, south-east
    nodes = [[45, 90], [-45, -90], [45, -90], [-45, 90]]
    assert hilbert_order(nodes) == [1, 2, 0, 3]
