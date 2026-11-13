import functools
import math
import random
from array import array

import pytest

from scgraph import GeoGraph
from scgraph.helpers.hilbert import hilbert_order
from scgraph.helpers.snap_index import SnapIndex as PythonSnapIndex

# The pure-Python index and, when the extension is built, the C++ index.
SNAP_INDEX_CLASSES = {"python": PythonSnapIndex}
try:
    from scgraph.cpp import SnapIndex as CppSnapIndex

    SNAP_INDEX_CLASSES["cpp"] = CppSnapIndex
except ImportError:
    pass
both_snap_index_classes = pytest.mark.parametrize(
    "implementation",
    list(SNAP_INDEX_CLASSES.values()),
    ids=list(SNAP_INDEX_CLASSES),
)


def _chord2(a, b):
    # Squared straight-line distance between two points of the unit sphere: it orders
    # points as the great-circle distance does
    def xyz(p):
        la, lo = math.radians(p[0]), math.radians(p[1])
        return (
            math.cos(la) * math.cos(lo),
            math.cos(la) * math.sin(lo),
            math.sin(la),
        )

    return sum((u - v) ** 2 for u, v in zip(xyz(a), xyz(b)))


def _is_nearest(nodes, point, ids, found):
    # found is a node of ids at the smallest distance, or None if ids is empty. The
    # same distance up to rounding, or up to 1e-24 (micrometres: the same place under
    # two names, as longitudes -180 and 180)
    if not ids:
        return found is None
    smallest = min(_chord2(point, nodes[i]) for i in ids)
    return (
        found in ids
        and _chord2(point, nodes[found]) <= smallest * (1 + 1e-12) + 1e-24
    )


def _quadrants(nodes, point):
    # GeoKDTree's quadrants: north if latitude >= the point's, east if within 180 degrees
    # of longitude eastwards (180 degrees exactly is both east and west)
    found = {"ne": [], "nw": [], "se": [], "sw": []}
    for i, (la, lo) in enumerate(nodes):
        d = (lo - point[1] + 180.0) % 360.0 - 180.0
        east, west = d >= 0 or d == -180.0, d <= 0 or d == -180.0
        for name, inside in (
            ("ne", la >= point[0] and east),
            ("nw", la >= point[0] and west),
            ("se", la <= point[0] and east),
            ("sw", la <= point[0] and west),
        ):
            if inside:
                found[name].append(i)
    return found


@functools.cache
def _networks():
    # Built once: the tests read these lists and do not change them
    rng = random.Random(53)

    def sphere(count):
        return [
            [
                math.degrees(math.asin(2 * rng.random() - 1)),
                rng.uniform(-180, 180),
            ]
            for _ in range(count)
        ]

    spread = sphere(1200)
    cluster = [
        [48.85 + rng.gauss(0, 0.05), 2.35 + rng.gauss(0, 0.05)]
        for _ in range(200)
    ]
    # Nodes at the same place (ties), on the antimeridian and at the poles
    special = [
        [10.0, 20.0],
        [10.0, 20.0],
        [0.0, 180.0],
        [0.0, -180.0],
        [90.0, 0.0],
    ]
    special += [[-90.0, 45.0], [45.0, 179.999], [45.0, -179.999]]
    # Twelve nodes one centimetre apart on a meridian: single-precision numbers
    # cannot tell them apart
    special += [[11.0 - i * 1e-7, 20.0] for i in range(12)]
    # Twelve nodes about 1 km around [11.0, 21.0], at the same distance within
    # centimetres
    degrees_east = 0.01 / math.cos(math.radians(11.0))
    special += [
        [11.0 + 0.01 * math.cos(k), 21.0 + degrees_east * math.sin(k)]
        for k in range(12)
    ]
    mixed = spread + cluster + special
    # Along a Hilbert curve, as network files are (a query scans about 4 leaves)
    ordered = [mixed[i] for i in hilbert_order(mixed)]
    shuffled = ordered[:]
    rng.shuffle(shuffled)  # a query would scan about 40 leaves
    return {
        "one node": [[12.0, 34.0]],
        "two nodes": [[12.0, 34.0], [-12.0, -34.0]],
        # Any order is accepted while a query can't scan many leaves
        "one leaf plus one": sphere(33),
        "ordered": ordered,
        "shuffled": shuffled,
        "ordered plus scattered": ordered + sphere(800),  # about 26 leaves
    }


# Networks whose order the index refuses, and GeoGraph indexes in Hilbert order
SCATTERED = ["shuffled", "ordered plus scattered"]


def _queries(nodes):
    rng = random.Random(len(nodes))
    queries = [
        [math.degrees(math.asin(2 * rng.random() - 1)), rng.uniform(-180, 180)]
        for _ in range(150)
    ]
    queries += [list(p) for p in nodes[:20]]  # exactly on a node
    queries += [
        [10.0, 20.0],
        [0.0, 180.0],
        [0.0, -180.0],
        [90.0, 0.0],
        [-90.0, 0.0],
    ]
    queries += [[45.0, 180.0], [48.85, 2.35], [-1e-9, 179.9999999]]
    # South and north of the nodes one centimetre apart, the centre of the ring, and
    # a point due south of the first node of the ring
    queries += [[10.5, 20.0], [11.5, 20.0], [11.0, 21.0], [11.005, 21.0]]
    # Each point is exactly 180 degrees of longitude from one node of "two nodes":
    # that node counts as east and as west of the point
    queries += [[0.0, -146.0], [0.0, 146.0]]
    return queries


# Each builder returns the index, the nodes as indexed, and arrays that reuse the memory of
# arrays it dropped
def _from_points(implementation, nodes):
    return implementation(nodes), nodes, None


def _from_arrays(implementation, nodes, typecode="d"):
    # As a network file is indexed: from two arrays, which the caller then drops. Same-size
    # arrays allocated next are likely to take their memory, so an index that read the
    # dropped arrays in place without keeping them would read zeros
    columns = [array(typecode, [p[c] for p in nodes]) for c in (0, 1)]
    index = implementation.from_arrays(*columns)
    del columns
    return index, nodes, [array(typecode, [0]) * len(nodes) for _ in range(4)]


def _from_units(implementation, nodes):
    # As a network file stores coordinates in int32 units of 1e-7 degree: the index finds
    # the nearest of the nodes those units stand for
    units = [[round(v * 1e7) for v in p] for p in nodes]
    index, _, reused = _from_arrays(implementation, units, "i")
    return index, [[v / 1e7 for v in p] for p in units], reused


def _check_answers(nodes, index):
    """Compare the answers of `index` with a search of every node, for each
    point of `_queries`: the nearest node, then the nearest node of each
    quadrant."""
    everything = list(range(len(nodes)))
    for point in _queries(nodes):
        assert _is_nearest(nodes, point, everything, index.closest_idx(point))
        found = index.closest_idx_per_quadrant(point)
        for name, ids in _quadrants(nodes, point).items():
            assert _is_nearest(nodes, point, ids, found[name])


@both_snap_index_classes
@pytest.mark.parametrize(
    "network", [n for n in _networks() if n not in SCATTERED]
)
@pytest.mark.parametrize("builder", [_from_points, _from_arrays, _from_units])
def test_snap_index_finds_the_nearest_node(implementation, network, builder):
    index, nodes, _reused = builder(implementation, _networks()[network])
    _check_answers(nodes, index)


# The ordered network has two nodes at (10, 20).
@both_snap_index_classes
@pytest.mark.parametrize("builder", [_from_points, _from_arrays, _from_units])
def test_snap_index_gives_the_lowest_id_of_nodes_at_the_same_place(
    implementation, builder
):
    index, nodes, _reused = builder(implementation, _networks()["ordered"])
    first_node_there = nodes.index([10.0, 20.0])

    assert index.closest_idx([10.0, 20.0]) == first_node_there
    assert index.closest_idx_per_quadrant([10.0, 20.0])["ne"] == (
        first_node_there
    )


# The ordered network has a node at longitude 180 and a node at longitude
# -180, on the equator: the same place under two names. A network often has
# such a pair, with no arc between the two nodes. A point snaps to the node
# whose longitude has its sign.
@both_snap_index_classes
@pytest.mark.parametrize("builder", [_from_points, _from_arrays, _from_units])
def test_snap_index_gives_the_node_on_the_same_side_of_the_antimeridian(
    implementation, builder
):
    index, nodes, _reused = builder(implementation, _networks()["ordered"])

    assert nodes[index.closest_idx([0.0, -179.99])] == [0.0, -180.0]
    assert nodes[index.closest_idx([0.0, 179.99])] == [0.0, 180.0]


@both_snap_index_classes
def test_snap_index_reads_two_arrays_of_one_dtype(implementation):
    with pytest.raises(TypeError):
        implementation.from_arrays(array("i", [0]), array("d", [0.0]))


@both_snap_index_classes
@pytest.mark.parametrize("network", SCATTERED)
def test_snap_index_refuses_scattered_nodes_and_says_how_to_sort(
    implementation, network
):
    with pytest.raises(ValueError, match="hilbert_order"):
        implementation(_networks()[network])


# A GeoGraph may list its nodes in any order. A network file lists them in
# Hilbert order. The two geographs below hold the shuffled network in these
# two orders. The answers are checked against the nodes of each geograph.
@pytest.fixture(scope="module")
def geograph_with_shuffled_nodes():
    nodes = _networks()["shuffled"]
    return GeoGraph(graph=[{} for _ in nodes], nodes=[list(p) for p in nodes])


@pytest.fixture(scope="module")
def geograph_read_from_a_file(geograph_with_shuffled_nodes, tmp_path_factory):
    path = str(tmp_path_factory.mktemp("snap") / "nodes.scgraph")
    geograph_with_shuffled_nodes.save_as_scgraph(path)
    return GeoGraph.load_from_scgraph(path)


both_geographs = pytest.mark.parametrize(
    "name", ["geograph_with_shuffled_nodes", "geograph_read_from_a_file"]
)


@both_geographs
def test_geograph_snaps_to_the_nearest_node_whatever_the_order_of_its_nodes(
    name, request
):
    geograph = request.getfixturevalue(name)

    _check_answers([list(p) for p in geograph.nodes], geograph.snap_index)


@both_geographs
def test_geograph_snaps_to_the_lowest_id_of_nodes_at_the_same_place(
    name, request
):
    geograph = request.getfixturevalue(name)
    first_node_there = list(geograph.nodes).index([10.0, 20.0])

    assert geograph.snap_index.closest_idx([10.0, 20.0]) == first_node_there
    assert geograph.snap_index.closest_idx_per_quadrant([10.0, 20.0])["ne"] == (
        first_node_there
    )


@both_geographs
def test_geograph_snaps_to_the_node_on_the_same_side_of_the_antimeridian(
    name, request
):
    geograph = request.getfixturevalue(name)

    west_of_it = geograph.snap_index.closest_idx([0.0, 179.99])
    east_of_it = geograph.snap_index.closest_idx([0.0, -179.99])

    assert geograph.nodes[west_of_it] == [0.0, 180.0]
    assert geograph.nodes[east_of_it] == [0.0, -180.0]


def test_geograph_snaps_nodes_added_to_a_network_file(tmp_path):
    # A file in Hilbert order, then enough scattered nodes added to make the order refused
    network = _networks()["ordered plus scattered"]
    ordered = _networks()["ordered"]
    path = str(tmp_path / "ordered.scgraph")
    GeoGraph(
        graph=[{} for _ in ordered], nodes=[list(p) for p in ordered]
    ).save_as_scgraph(path)
    geograph = GeoGraph.load_from_scgraph(path)
    for latitude, longitude in network[len(ordered) :]:
        geograph.add_coord_node(
            {"latitude": latitude, "longitude": longitude}, auto_edge=False
        )
    _check_answers(network, geograph.snap_index)


@both_snap_index_classes
@pytest.mark.parametrize(
    "point_that_is_not_finite", [[float("nan"), 0.0], [0.0, float("inf")]]
)
def test_snap_index_refuses_a_coordinate_that_is_not_finite(
    implementation, point_that_is_not_finite
):
    with pytest.raises(ValueError, match="finite"):
        implementation([[0.0, 0.0], point_that_is_not_finite])
