import random
from array import array

import pytest

from scgraph.pipelines.steps import assembly
from scgraph.utils import has_cpp

BACKENDS = {"python": assembly.python}
if has_cpp():
    from scgraph import cpp

    BACKENDS["cpp"] = cpp
both_backends = pytest.mark.parametrize(
    "backend", list(BACKENDS.values()), ids=list(BACKENDS)
)

BIG = 2**40  # an id beyond 32 bits


def _random_arcs(seed):
    # Few ids, so many self-loops and parallel arcs; integer weights, so ties
    rng = random.Random(seed)
    ids = [rng.randrange(-(2**62), 2**62) for _ in range(300)]
    return [
        (rng.choice(ids), rng.choice(ids), float(rng.randint(1, 5)))
        for _ in range(5000)
    ]


def _random_shape(seed):
    # A walk of 300 points, steps of up to 50 m, from near the antimeridian or anywhere
    rng = random.Random(seed)
    lat = rng.randint(-800000000, 800000000)
    lon = rng.choice([rng.randint(-1800000000, 1800000000), 1799990000])
    start, interior = (lat, lon), []
    for _ in range(300):
        lat += rng.randint(-4000, 4000)
        lon = (
            lon + rng.randint(-4000, 4000) + 1800000000
        ) % 3600000000 - 1800000000
        interior.append((lat, lon))
    return (*start, lat + 1000, lon), interior


@both_backends
@pytest.mark.parametrize(
    "arcs, expected",
    [
        (
            # (origin, destination, weight); id 5 is on a self-loop only, -7 is a
            # destination only
            [
                (BIG, 10, 2.0),
                (10, BIG, 1.0),
                (BIG, 10, 1.5),  # shorter: replaces arc 0
                (5, 5, 1.0),
                (BIG, 10, 1.5),  # as short: arc 2 stays
                (BIG, -7, 4.0),
                (20, BIG, 3.0),
                (BIG, 20, 0.5),
                (20, BIG, 3.5),  # longer: arc 6 stays
                (10, 10, 0.5),  # a self-loop on a node
            ],
            # node_ids, offsets, heads (rows sorted by head), weights, kept
            (
                [-7, 10, 20, BIG],
                [0, 0, 1, 2, 5],
                [3, 3, 0, 1, 2],
                [1.0, 3.0, 4.0, 1.5, 0.5],
                [1, 6, 5, 2, 7],
            ),
        ),
        ([], ([], [0], [], [], [])),
        # Random arcs: the same result as the pure-Python version
        *((_random_arcs(seed), None) for seed in range(3)),
    ],
)
def test_csr_from_arcs_stores_the_shortest_arcs_by_origin(
    backend, arcs, expected
):
    origins, destinations, weights = (
        [arc[k] for arc in arcs] for k in range(3)
    )
    args = array("q", origins), array("q", destinations), array("d", weights)
    if expected is None:
        expected = tuple(map(list, assembly.python.csr_from_arcs(*args)))
    assert tuple(map(list, backend.csr_from_arcs(*args))) == expected


def _random_graph(seed):
    rng = random.Random(seed)
    n = rng.randint(1, 40)
    return [
        sorted(rng.randrange(n) for _ in range(rng.choice([0, 1, 1, 2, 3])))
        for _ in range(n)
    ]


def _reachable(rows, start):
    seen, stack = {start}, [start]
    while stack:
        for v in rows[stack.pop()]:
            if v not in seen:
                seen.add(v)
                stack.append(v)
    return seen


@both_backends
@pytest.mark.parametrize(
    "rows",
    [
        [],
        # Components {0, 3}, {1, 2}, {4}: the search finds {4} first
        [[1, 3], [2], [1], [0], []],
        *(_random_graph(seed) for seed in range(20)),
    ],
)
def test_strong_components_groups_nodes_that_reach_each_other(backend, rows):
    offsets, heads = array("i", [0]), array("i")
    for row in rows:
        heads.extend(row)
        offsets.append(len(heads))
    labels, sizes = map(list, backend.strong_components(offsets, heads))
    reach = [_reachable(rows, u) for u in range(len(rows))]
    assert all(
        (labels[u] == labels[v]) == (v in reach[u] and u in reach[v])
        for u in range(len(rows))
        for v in range(len(rows))
    )
    # Numbered in the order of their smallest node
    assert list(dict.fromkeys(labels)) == list(range(len(sizes)))
    assert sizes == [labels.count(label) for label in range(len(sizes))]


# At the equator, 1e-7 degree is about 1.1 cm
@both_backends
@pytest.mark.parametrize(
    "ends, interior, tolerance_m, expected",
    [
        # Within 10 m of the chord: nothing kept
        ((0, 0, 0, 1000000), [(500, 300000), (-500, 600000)], 10, []),
        # On the chord's line but past its end (5.6 km): kept
        ((0, 0, 0, 1000000), [(0, 1500000)], 10, [(0, 1500000)]),
        # 66 m off, kept; then 55 m off the new chord, kept; then 17 m, dropped
        (
            (0, 0, 0, 1000000),
            [(3000, 250000), (0, 500000), (-6000, 750000)],
            20,
            [(3000, 250000), (-6000, 750000)],
        ),
        # On the chord, tolerance 0: dropped
        ((0, 0, 0, 1000000), [(0, 500000)], 0, []),
        # At 60 degrees north a degree of longitude is half as long: 22 m off, dropped
        ((600000000, 0, 601000000, 0), [(600500000, 4000)], 30, []),
        # Across the antimeridian, eastwards and westwards, on the chord
        (
            (0, 1799900000, 0, -1799900000),
            [(0, 1800000000), (0, -1799950000)],
            1,
            [],
        ),
        (
            (0, -1799900000, 0, 1799900000),
            [(0, -1800000000), (0, 1799950000)],
            1,
            [],
        ),
        # Random walks: the same points as the pure-Python version
        *((*_random_shape(seed), 20, None) for seed in range(6)),
    ],
)
def test_simplify_shapes_keeps_the_points_away_from_the_simplified_line(
    backend, ends, interior, tolerance_m, expected
):
    # A shape without interior points first: offsets carry over
    points = array("i", [value for point in interior for value in point])
    args = (
        points,
        array("i", [0, 0, len(interior)]),
        array("i", (0, 0, 0, 1000) + ends),
        tolerance_m,
    )
    if expected is None:
        kept = assembly.python.simplify_shapes(*args)[0]
        expected = list(zip(kept[::2], kept[1::2]))
    kept, offsets = backend.simplify_shapes(*args)
    assert list(offsets) == [0, 0, len(expected)]
    assert list(kept) == [value for point in expected for value in point]
