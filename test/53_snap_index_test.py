import math
import random

import pytest

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

    spread = sphere(600)
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
    rng.shuffle(mixed)
    # Along a Hilbert curve, as built networks are: the index keeps the order it is given
    ordered = [(spread + special)[i] for i in hilbert_order(spread + special)]
    return {
        "one node": [[12.0, 34.0]],
        "one leaf plus one": sphere(33),
        "mixed order": mixed,
        "ordered": ordered,
    }


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


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS)
@pytest.mark.parametrize("network", list(_networks()))
def test_snap_index_finds_the_nearest_node(implementation, network):
    nodes = _networks()[network]
    index = implementation(nodes)
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
