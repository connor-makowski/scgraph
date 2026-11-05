import hashlib
import json
import os

import pytest

from scgraph import GeoGraph, Graph, network_file
from scgraph.helpers.hilbert import hilbert_order

# A one-way arc (0 -> 2), a shape on one arc only, integer weights and an isolated node
_GRAPH = [{2: 1.25, 1: 5}, {0: 5}, {}, {}]
_NODES = [[0.0, 0.0], [0.0, 0.01], [0.01, 0.0], [1.0, 1.0]]
_SHAPES = [{1: [[0.0, 0.0], [0.002, 0.005], [0.0, 0.01]]}, {}, {}, {}]


def _small():
    return GeoGraph(
        graph=[dict(row) for row in _GRAPH],
        nodes=[list(node) for node in _NODES],
        intermediate_nodes=_SHAPES,
        default_off_graph_circuity=2,
        geograph_units="mi",
    )


@pytest.mark.parametrize("save_intermediate_nodes", [True, False])
def test_save_load_scgraph(tmp_path, save_intermediate_nodes):
    path = str(tmp_path / "small.scgraph")
    _small().save_as_scgraph(path, save_intermediate_nodes)
    arrays, metadata = network_file.read(path)
    assert metadata["symmetric"] is False
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


def test_save_as_scgraph_flags_symmetric_graphs(tmp_path):
    path = str(tmp_path / "two.scgraph")
    GeoGraph(
        graph=[{1: 2.0}, {0: 2.0}], nodes=[[0.0, 0.0], [0.0, 0.01]]
    ).save_as_scgraph(path)
    assert network_file.read(path)[1]["symmetric"] is True


def test_save_as_scgraph_records_the_sha256_of_the_arrays(tmp_path):
    # The identity of the network: every byte after the 4 KB header
    path = tmp_path / "small.scgraph"
    _small().save_as_scgraph(str(path))
    assert (
        network_file.read(str(path))[1]["content_sha256"]
        == hashlib.sha256(path.read_bytes()[4096:]).hexdigest()
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
    header_length = int.from_bytes(data[8:16], "little")
    header = json.loads(data[16 : 16 + header_length])
    if how == "not a network file":
        return b'{"type": "GeoGraph"}'
    if how == "later version":
        header["format_version"] = 2
    if how == "without content_sha256":
        del header["content_sha256"]
    if how == "header without arrays":
        del header["arrays"]
    if how == "header is not an object":
        header = [header]
    if how == "truncated":
        return data[:-8]
    if how == "offsets past the arcs":
        offsets = header["arrays"]["offsets"]["offset"]
        big = (2**30).to_bytes(4, "little")
        return data[: offsets + 4] + big + data[offsets + 8 :]
    if how == "arc to a missing node":
        heads = header["arrays"]["heads"]["offset"]
        return data[:heads] + (99).to_bytes(4, "little") + data[heads + 4 :]
    text = json.dumps(header).encode().ljust(header_length)
    return data[:16] + text + data[16 + header_length :]


@pytest.mark.parametrize(
    "how, message",
    [
        ("not a network file", "not a scgraph network file"),
        ("later version", "format version 2"),
        ("truncated", "invalid array"),
        # Checked by network_file.read, or by the C++ graph on a mapped file
        ("arc to a missing node", "arc to a missing node|is not in the graph"),
        ("offsets past the arcs", "invalid offsets|non-decreasing"),
        ("header without arrays", "invalid header"),
        ("header is not an object", "invalid header"),
        ("without content_sha256", "invalid header"),
    ],
)
def test_load_from_scgraph_rejects_damaged_files(tmp_path, how, message):
    path = tmp_path / "small.scgraph"
    _small().save_as_scgraph(str(path))
    path.write_bytes(_damage(path.read_bytes(), how))
    with pytest.raises(ValueError, match=message):
        GeoGraph.load_from_scgraph(str(path))


def test_hilbert_order_follows_the_curve():
    # One point per quadrant of the globe: north-east, south-west, north-west, south-east;
    # the curve visits them south-west, north-west, north-east, south-east
    nodes = [[45, 90], [-45, -90], [45, -90], [-45, 90]]
    assert hilbert_order(nodes) == [1, 2, 0, 3]
