import math
import random
from array import array

import pytest

from scgraph import GeoGraph
from scgraph.helpers.hilbert import hilbert_order
from scgraph.helpers.snap_index import SnapIndex as PythonSnapIndex

IMPLEMENTATIONS = [PythonSnapIndex]
try:
    from scgraph.cpp import SnapIndex as CppSnapIndex

    IMPLEMENTATIONS.append(CppSnapIndex)
except ImportError:
    pass


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


def _networks():
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
    mixed = spread + cluster + special
    # Along a Hilbert curve, as network files are (a query scans about 4 leaves)
    ordered = [mixed[i] for i in hilbert_order(mixed)]
    shuffled = ordered[:]
    rng.shuffle(shuffled)  # a query would scan about 40 leaves
    return {
        "one node": [[12.0, 34.0]],
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
    return queries


def _from_points(implementation, nodes):
    return implementation(nodes), None


def _from_arrays(implementation, nodes):
    # As a network file is indexed: from two float64 arrays, which the caller then drops.
    # Same-size arrays allocated next are likely to take their memory, so an index that
    # read the dropped arrays in place without keeping them would read zeros
    latitudes = array("d", [p[0] for p in nodes])
    longitudes = array("d", [p[1] for p in nodes])
    index = implementation.from_arrays(latitudes, longitudes)
    del latitudes, longitudes
    return index, [array("d", [0.0]) * len(nodes) for _ in range(4)]


def _check_answers(nodes, index):
    everything = list(range(len(nodes)))
    for point in _queries(nodes):
        assert _is_nearest(nodes, point, everything, index.closest_idx(point))
        found = index.closest_idx_per_quadrant(point)
        for name, ids in _quadrants(nodes, point).items():
            assert _is_nearest(nodes, point, ids, found[name])
    # Nodes at the same coordinates: the lowest id
    same = [i for i, p in enumerate(nodes) if p == [10.0, 20.0]]
    if len(same) > 1:
        assert index.closest_idx([10.0, 20.0]) == min(same)
        assert index.closest_idx_per_quadrant([10.0, 20.0])["ne"] == min(same)
    # On each side of the antimeridian, the node of that side: the two are often not linked
    for point, name in (
        ([0.0, -179.99], [0.0, -180.0]),
        ([0.0, 179.99], [0.0, 180.0]),
    ):
        if name in nodes:
            assert nodes[index.closest_idx(point)] == name


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS)
@pytest.mark.parametrize(
    "network", [n for n in _networks() if n not in SCATTERED]
)
@pytest.mark.parametrize("build", [_from_points, _from_arrays])
def test_snap_index_finds_the_nearest_node(implementation, network, build):
    nodes = _networks()[network]
    index, _reused = build(implementation, nodes)
    _check_answers(nodes, index)


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS)
@pytest.mark.parametrize("network", SCATTERED)
def test_snap_index_refuses_scattered_nodes_and_says_how_to_sort(
    implementation, network
):
    with pytest.raises(ValueError, match="hilbert_order"):
        implementation(_networks()[network])


@pytest.mark.parametrize("saved", [False, True])
def test_geograph_snaps_nodes_in_any_order(tmp_path, saved):
    # GeoGraph keeps its node ids: it indexes scattered nodes in Hilbert order itself, also
    # when they come from a file (the answers are checked against the graph's own nodes)
    nodes = _networks()["shuffled"]
    geograph = GeoGraph(
        graph=[{} for _ in nodes], nodes=[list(p) for p in nodes]
    )
    if saved:
        path = str(tmp_path / "nodes.scgraph")
        geograph.save_as_scgraph(path)
        geograph = GeoGraph.load_from_scgraph(path)
    _check_answers([list(p) for p in geograph.nodes], geograph.snap_index)


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


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS)
@pytest.mark.parametrize("bad", [[float("nan"), 0.0], [0.0, float("inf")]])
def test_snap_index_rejects_non_finite_coordinates(implementation, bad):
    with pytest.raises(ValueError, match="finite"):
        implementation([[0.0, 0.0], bad])
