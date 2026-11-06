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
    _small().save_as_scgraph(path, save_intermediate_nodes, sources=_SOURCES)
    arrays, metadata = network_file.read(path)
    assert metadata["symmetric"] is False
    assert metadata["sources"] == _SOURCES
    loaded = GeoGraph.load_from_scgraph(path)
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


@pytest.mark.skipif(
    Graph.__module__ == "scgraph.cpp", reason="a C++ graph is not picklable"
)
def test_a_pickled_geograph_keeps_its_node_ids(tmp_path):
    geo = pickle.loads(pickle.dumps(_small([7, 5, 3, 1])))
    geo.add_coord_node({"latitude": 2.0, "longitude": 2.0}, auto_edge=False)
    geo.save_as_scgraph(str(tmp_path / "small.scgraph"))
    loaded = GeoGraph.load_from_scgraph(str(tmp_path / "small.scgraph"))
    assert loaded.node_ids == [7, 5, 3, 1, -1]


def test_node_ids_give_one_id_per_node():
    with pytest.raises(ValueError, match="one id per node"):
        _small(node_ids=[7, 5, 3])


# Shape points are stored as int32 in 1e-7 degree
@pytest.mark.parametrize("longitude", [214.75, float("nan")])
def test_save_as_scgraph_rejects_shape_points_it_cannot_store(
    tmp_path, longitude
):
    geo = _small()
    geo.intermediate_nodes = [{1: [[0.0, longitude]]}, {}, {}, {}]
    with pytest.raises(ValueError, match="arc 0 -> 1"):
        geo.save_as_scgraph(str(tmp_path / "small.scgraph"))


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
    assert _small().save_as_scgraph(str(path), sources=_SOURCES) == (
        _small().save_as_scgraph(
            str(tmp_path / "again.scgraph"), sources=reordered
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
