import math
import random
from array import array

import pytest
from helpers import great_circle_km

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
        expected = tuple(map(list, assembly.python.build_csr_from_arcs(*args)))
    assert tuple(map(list, backend.build_csr_from_arcs(*args))) == expected


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
def test_strongly_connected_components_groups_nodes_that_reach_each_other(
    backend, rows
):
    offsets, heads = array("i", [0]), array("i")
    for row in rows:
        heads.extend(row)
        offsets.append(len(heads))
    labels, sizes = map(
        list, backend.strongly_connected_components(offsets, heads)
    )
    reach = [_reachable(rows, u) for u in range(len(rows))]
    assert all(
        (labels[u] == labels[v]) == (v in reach[u] and u in reach[v])
        for u in range(len(rows))
        for v in range(len(rows))
    )
    # Numbered in the order of their smallest node
    assert list(dict.fromkeys(labels)) == list(range(len(sizes)))
    assert sizes == [labels.count(label) for label in range(len(sizes))]


@pytest.mark.parametrize(
    "min_nodes, kept",
    [(None, [1, 2, 3]), (2, [1, 2, 3, 4, 5]), (1, [0, 1, 2, 3, 4, 5])],
)
def test_keep_strongly_connected_components_keeps_components_by_size(
    min_nodes, kept
):
    # Components {0} (one way to 1), {1, 2, 3} and {4, 5} (both ways)
    arcs = [(0, 1), (1, 2), (2, 1), (2, 3), (3, 2), (4, 5), (5, 4)]
    offsets, heads = array("i", [0]), array("i")
    for u in range(6):
        heads.extend(v for origin, v in arcs if origin == u)
        offsets.append(len(heads))
    nodes, labels = assembly.keep_strongly_connected_components(
        offsets, heads, min_nodes
    )
    assert list(nodes) == kept
    assert labels[1] == labels[2] == labels[3] != labels[0]
    assert labels[4] == labels[5] not in (labels[0], labels[1])


# Around a row boundary in the south, the antimeridian on both sides and a pole
@pytest.mark.parametrize(
    "centre", [(-30.1, 10), (0.1, 179.99), (-0.2, -180), (89.8, 0)]
)
@pytest.mark.parametrize("km", [2, 20, 500])
def test_near_nodes_finds_every_node_within_a_distance(centre, km):
    rng = random.Random(0)
    lats, lons = array("d"), array("d")
    for _ in range(2000):
        lats.append(max(-90, min(90, centre[0] + rng.gauss(0, 2))))
        lons.append((centre[1] + rng.gauss(0, 4) + 180) % 360 - 180)
    near = assembly.NearNodes(lats, lons)
    point = [centre[0], centre[1]]
    expected = sorted(
        (great_circle_km(point, [lats[i], lons[i]]), i)
        for i in range(len(lats))
    )
    within = [i for d, i in expected if d <= km]
    assert sorted(i for _, i in near.within(point, km)) == sorted(within)
    assert near.nearest(point, km)[0] == (within[0] if within else None)


def test_assemble_keeps_closed_components_and_contracts_their_chains(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        assembly.PieceArrays, "BATCH", 1
    )  # drawings stored by batch
    pieces = assembly.PieceArrays(work_dir=tmp_path)  # columns in files
    where = {1: [0, 0], 2: [0, 0.01], 3: [0, 0.02], 4: [1, 0], 5: [1, 0.01]}
    # Of pieces 1-2 and 2-3, each point off its piece's line
    shape = {
        1: [[0.003, 0.003], [0.004, 0.006]],
        2: [[0.003, 0.013], [0.004, 0.016]],
    }
    for u, v, direction in [(1, 2, 0), (2, 3, 0), (3, 4, 1), (4, 5, 0)]:
        ends = [where[u], where[v]]
        pieces.append(u, v, float(u), direction, ends, shape.get(u, []))
    arrays, _ = assembly.assemble(
        assembly.build_graph_from_pieces(pieces),
        max_km_between_nodes=100,
        min_nodes_per_strongly_connected_component=1,
    )
    ids, offsets = arrays["node_ids"], arrays["offsets"]
    arcs = {
        (ids[u], ids[arrays["heads"][a]]): arrays["weights"][a]
        for u in range(len(ids))
        for a in range(offsets[u], offsets[u + 1])
    }
    # 3 -> 4 joins two components: left out; node 2 is contracted
    assert arcs == {(1, 3): 3.0, (3, 1): 3.0, (4, 5): 4.0, (5, 4): 4.0}
    # The shape of 1 -> 3 runs through node 2, that of 3 -> 1 back (1e-7 degree)
    line, starts = arrays["shape_points"], arrays["shape_offsets"]
    drawn = {
        (ids[u], ids[arrays["heads"][a]]): list(
            line[2 * starts[a] : 2 * starts[a + 1]]
        )
        for u in range(len(ids))
        for a in range(offsets[u], offsets[u + 1])
    }
    along = [
        30000,
        30000,
        40000,
        60000,
        0,
        100000,
        30000,
        130000,
        40000,
        160000,
    ]
    assert drawn[1, 3] == along
    assert drawn[3, 1] == [x for k in (8, 6, 4, 2, 0) for x in along[k : k + 2]]


def _csr(one_way=(), two_way=()):
    # (origin, destination, km) arcs, two_way ones in both directions, by origin
    arcs = [*one_way, *two_way, *((v, u, km) for u, v, km in two_way)]
    columns = (array(t, c) for t, c in zip("qqd", zip(*arcs)))
    return assembly.python.build_csr_from_arcs(*columns)[1:4]


def _random_chains(seed):
    # Junctions 0-19 joined by chains of new nodes, both ways or one way (loops and
    # parallel chains among them), numbered at random, the same length both ways; a few
    # nodes of another mode
    rng = random.Random(seed)
    ids, arcs, count = rng.sample(range(10**6), 400), ([], []), 20
    for _ in range(60):
        size = rng.randrange(6)
        path = [
            rng.randrange(20),
            *range(count, count + size),
            rng.randrange(20),
        ]
        count += size
        arcs[rng.random() < 0.7].extend(
            (ids[u], ids[v], (0.1, 0.2, 0.3)[(u + v) % 3])
            for u, v in zip(path, path[1:])
            if u != v
        )
    graph = _csr(*arcs)
    modes = array("B", (rng.random() < 0.05 for _ in range(len(graph[0]) - 1)))
    return graph, modes, rng.choice([math.inf, 0.5])


def _two_way(*pairs):
    return _csr(two_way=[(u, v, 1.0) for u, v in pairs])


@both_backends
@pytest.mark.parametrize(
    "graph, modes, max_km, kept",
    [
        # A dead-end spur (4) stays
        (
            _two_way((0, 1), (1, 2), (2, 3), (1, 4)),
            None,
            math.inf,
            [0, 1, 3, 4],
        ),
        # Of two parallel chains, the second (taken from the lower end, in row order, so
        # that both backends agree) is cut at its middle
        (_two_way((0, 1), (1, 3), (0, 2), (2, 3)), None, math.inf, [0, 2, 3]),
        # A one-way loop off node 0 is cut at its middle
        (
            _csr([(0, 1, 1), (1, 2, 1), (2, 3, 1), (3, 0, 1)], [(0, 4, 1)]),
            None,
            math.inf,
            [0, 2, 4],
        ),
        # A one-way merge into 2 is not a chain; an isolated cycle keeps its lowest node
        (_csr([(0, 2, 1), (1, 2, 1), (2, 3, 1)]), None, math.inf, [0, 1, 2, 3]),
        (
            _csr([(1, 2, 1), (2, 3, 1), (3, 0, 1), (0, 1, 1)]),
            None,
            math.inf,
            [0, 2],
        ),
        # A port (2) between road (0, 1) and sea (3, 4) is never contracted
        (
            _two_way((0, 1), (1, 2), (2, 3), (3, 4)),
            array("B", [0, 0, 1, 2, 2]),
            math.inf,
            [0, 1, 2, 3, 4],
        ),
        # Cut every 2 km from the lower end, 0, along 0-4-3-2-1-5
        (
            _two_way((5, 1), (1, 2), (2, 3), (3, 4), (4, 0)),
            None,
            2.0,
            [0, 1, 3, 5],
        ),
        # Random chains: the same result as the pure-Python version
        *((*_random_chains(seed), None) for seed in range(6)),
    ],
)
def test_contract_chains_keeps_every_arc_and_contracts_through_nodes(
    backend, graph, modes, max_km, kept
):
    offsets, heads, weights = graph
    result = backend.contract_chains(offsets, heads, weights, modes, max_km)
    nodes, origins, ends, km, member_offsets, members = map(list, result)
    if kept is None:
        expected = assembly.python.contract_chains(
            offsets, heads, weights, modes, max_km
        )
        assert [nodes, origins, ends, km, member_offsets, members] == list(
            map(list, expected)
        )
    else:
        assert nodes == kept
    # Each input arc on exactly one arc, which follows it between kept nodes
    tails = [
        u
        for u in range(len(offsets) - 1)
        for _ in range(offsets[u], offsets[u + 1])
    ]
    assert sorted(members) == list(range(len(heads)))
    walks = {}
    for i, (u, v) in enumerate(zip(origins, ends)):
        walk = members[member_offsets[i] : member_offsets[i + 1]]
        stops = [tails[walk[0]], *(heads[a] for a in walk)]
        assert stops[0] == nodes[u] and stops[-1] == nodes[v] and u != v
        assert all(
            tails[b] == heads[a] and heads[a] not in nodes
            for a, b in zip(walk, walk[1:])
        )
        assert math.isclose(km[i], sum(weights[a] for a in walk))
        walks[stops[0], stops[-1]] = (stops, km[i])
    assert len(walks) == len(origins)
    assert list(zip(origins, ends)) == sorted(zip(origins, ends))
    # Both directions of a chain have the same length to the last bit
    for (u, v), (stops, length) in walks.items():
        back = walks.get((v, u))
        assert back is None or back[0] != stops[::-1] or back[1] == length


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
