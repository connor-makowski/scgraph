import math
import random
from array import array
from itertools import groupby

import pytest
from helpers import great_circle_km

from scgraph.pipelines.steps import assembly
from scgraph.utils import has_cpp

BACKENDS = {"python": assembly.python}
if has_cpp():
    from scgraph import cpp

    BACKENDS["cpp"] = cpp
needs_the_cpp_extension = pytest.mark.skipif(
    not has_cpp(), reason="The C++ extension is not built"
)
both_backends = pytest.mark.parametrize(
    "backend", list(BACKENDS.values()), ids=list(BACKENDS)
)

# These tests call the steps that assemble a network during a build. No public
# call runs one step alone: a build needs the download of its sources.

BIG = 2**40  # an id beyond 32 bits


# Arcs between source ids, as (origin, destination, weight). The id 5 is on a
# self-loop only, and -7 is a destination only.
ARCS_WITH_PARALLELS_AND_LOOPS = [
    (BIG, 10, 2.0),
    (10, BIG, 1.0),
    (BIG, 10, 1.5),  # shorter than arc 0
    (5, 5, 1.0),
    (BIG, 10, 1.5),  # as short as arc 2
    (BIG, -7, 4.0),
    (20, BIG, 3.0),
    (BIG, 20, 0.5),
    (20, BIG, 3.5),  # longer than arc 6
    (10, 10, 0.5),  # a self-loop on a node that has other arcs
]


def _columns(arcs):
    """The origins, the destinations and the weights of `arcs`, as the three
    arrays that `build_csr_from_arcs` takes."""
    origins, destinations, weights = (
        [arc[k] for arc in arcs] for k in range(3)
    )
    return array("q", origins), array("q", destinations), array("d", weights)


# The result of `build_csr_from_arcs` is (node ids, offsets, heads, weights,
# kept). The ids are sorted: 5 is not among them. The rows are those of -7 (no
# arc), 10 (to BIG), 20 (to BIG) and BIG (to -7, 10 and 20), each sorted by
# destination. `kept` gives the input index of each stored arc. From BIG to
# 10, arc 2 is kept: arc 0 is longer, and arc 4 is as short but comes later.
# From 20 to BIG, arc 6 is kept.
CSR_OF_THE_SHORTEST_ARCS = (
    [-7, 10, 20, BIG],
    [0, 0, 1, 2, 5],
    [3, 3, 0, 1, 2],
    [1.0, 3.0, 4.0, 1.5, 0.5],
    [1, 6, 5, 2, 7],
)


@both_backends
@pytest.mark.parametrize(
    "arcs, csr",
    [
        pytest.param(
            ARCS_WITH_PARALLELS_AND_LOOPS,
            CSR_OF_THE_SHORTEST_ARCS,
            id="parallel arcs and self-loops",
        ),
        pytest.param([], ([], [0], [], [], []), id="no arcs"),
    ],
)
def test_csr_from_arcs_stores_the_shortest_arcs_by_origin(backend, arcs, csr):
    result = backend.build_csr_from_arcs(*_columns(arcs))

    assert tuple(map(list, result)) == csr


def _random_arcs(seed):
    # Few ids, so many self-loops and parallel arcs; integer weights, so ties
    rng = random.Random(seed)
    ids = [rng.randrange(-(2**62), 2**62) for _ in range(300)]
    return [
        (rng.choice(ids), rng.choice(ids), float(rng.randint(1, 5)))
        for _ in range(5000)
    ]


# The expected arcs are found another way: the arcs that are not self-loops
# are sorted by origin, destination, weight and input index. The first arc of
# each pair (origin, destination) is then its shortest arc, and the first in
# the input among equals.
@both_backends
@pytest.mark.parametrize("seed", range(3))
def test_csr_from_random_arcs_keeps_the_first_shortest_arc_of_each_pair(
    backend, seed
):
    arcs = _random_arcs(seed)
    sorted_arcs = sorted(
        (origin, destination, weight, i)
        for i, (origin, destination, weight) in enumerate(arcs)
        if origin != destination
    )
    expected = [
        next(arcs_of_pair)
        for _pair, arcs_of_pair in groupby(sorted_arcs, lambda arc: arc[:2])
    ]

    node_ids, offsets, heads, weights, kept = backend.build_csr_from_arcs(
        *_columns(arcs)
    )

    assert list(kept) == [i for _, _, _, i in expected]
    assert list(weights) == [weight for _, _, weight, _ in expected]
    stored_pairs = [
        (node_ids[u], node_ids[heads[a]])
        for u in range(len(node_ids))
        for a in range(offsets[u], offsets[u + 1])
    ]
    assert stored_pairs == [
        (origin, destination) for origin, destination, _, _ in expected
    ]


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


# A graph of 6 nodes in three components. Node 0 is alone: its one arc goes
# to node 1, and none comes back. Nodes 1, 2 and 3 are joined both ways (1-2
# and 2-3). Nodes 4 and 5 are joined both ways. The arcs are stored by origin:
# the arcs of node u are HEADS[OFFSETS[u]:OFFSETS[u + 1]].
OFFSETS = array("i", [0, 1, 2, 4, 5, 6, 7])
HEADS = array("i", [1, 2, 1, 3, 2, 5, 4])


@pytest.mark.parametrize(
    "options, kept_nodes",
    [
        pytest.param(
            {},
            [1, 2, 3],
            id="only the largest component without a minimum size",
        ),
        pytest.param(
            {"min_nodes": 2},
            [1, 2, 3, 4, 5],
            id="every component of the minimum size",
        ),
        pytest.param(
            {"min_nodes": 1},
            [0, 1, 2, 3, 4, 5],
            id="every node with a minimum size of one node",
        ),
    ],
)
def test_components_are_kept_by_their_size(options, kept_nodes):
    nodes, labels = assembly.keep_strongly_connected_components(
        OFFSETS, HEADS, **options
    )

    assert list(nodes) == kept_nodes
    # The label of a node is the number of its component, kept or not
    assert list(labels) == [0, 1, 1, 1, 2, 2]


def _scatter_nodes_around(centre):
    """The latitudes and the longitudes of 2,000 nodes drawn around `centre`,
    most of them within a few hundred kilometres. A longitude beyond 180
    degrees comes back on the other side of the antimeridian."""
    rng = random.Random(0)
    lats, lons = array("d"), array("d")
    for _ in range(2000):
        lats.append(max(-90, min(90, centre[0] + rng.gauss(0, 2))))
        lons.append((centre[1] + rng.gauss(0, 4) + 180) % 360 - 180)
    return lats, lons


# NearNodes sorts the nodes in rows of 0.2 degree of latitude. The centres are
# next to a limit between two rows in the south, on each side of the
# antimeridian, and next to a pole.
around_special_places = pytest.mark.parametrize(
    "centre", [(-30.1, 10), (0.1, 179.99), (-0.2, -180), (89.8, 0)]
)


@around_special_places
@pytest.mark.parametrize("km", [2, 20, 500])
def test_near_nodes_finds_every_node_within_a_distance(centre, km):
    lats, lons = _scatter_nodes_around(centre)
    nodes_within_km = [
        i
        for i in range(len(lats))
        if great_circle_km(centre, [lats[i], lons[i]]) <= km
    ]

    found = assembly.NearNodes(lats, lons).find_within(list(centre), km)

    assert sorted(i for _, i in found) == nodes_within_km


@around_special_places
def test_near_nodes_finds_the_nearest_node(centre):
    lats, lons = _scatter_nodes_around(centre)
    nearest_km, nearest_node = min(
        (great_circle_km(centre, [lats[i], lons[i]]), i)
        for i in range(len(lats))
    )

    node, km = assembly.NearNodes(lats, lons).find_nearest(list(centre), 500)

    assert node == nearest_node
    assert km == pytest.approx(nearest_km)


def test_near_nodes_finds_no_nearest_node_beyond_the_distance():
    # One node, one degree of latitude north of the point: 111 km away
    near_nodes = assembly.NearNodes(array("d", [1.0]), array("d", [0.0]))

    assert near_nodes.find_nearest([0.0, 0.0], 100) == (None, math.inf)


# Four pieces of ways between five places, given by their source ids. A piece
# is (origin, destination, direction): 0 for both ways, 1 for one way. Places
# 1, 2 and 3 are on a road along the equator. Places 4 and 5 are on a road one
# degree north. The piece from 3 to 4 joins the two roads one way only. The
# length of a piece is the id of its origin, in km.
PLACES = {1: [0, 0], 2: [0, 0.01], 3: [0, 0.02], 4: [1, 0], 5: [1, 0.01]}
PIECES = [(1, 2, 0), (2, 3, 0), (3, 4, 1), (4, 5, 0)]
# The points between the ends of the pieces 1-2 and 2-3. Each point is more
# than 300 m off the straight line of its piece, so that the simplification of
# the shapes (within 50 m) keeps it.
POINTS_FROM_1_TO_2 = [[0.003, 0.003], [0.004, 0.006]]
POINTS_FROM_2_TO_3 = [[0.003, 0.013], [0.004, 0.016]]


def _by_node_ids(arrays, value_of_arc):
    """One value per arc of the network arrays, as a dict. Its keys are the
    pairs (id of the origin, id of the destination)."""
    ids, offsets, heads = (
        arrays[name] for name in ("node_ids", "offsets", "heads")
    )
    return {
        (ids[u], ids[heads[arc]]): value_of_arc(arc)
        for u in range(len(ids))
        for arc in range(offsets[u], offsets[u + 1])
    }


@pytest.fixture(scope="module")
def assembled(tmp_path_factory):
    """The arrays of the network built from the four pieces. The arguments
    keep every component, even of one node, and cut no arc: no chain reaches
    100 km."""
    pieces = assembly.PieceArrays(work_dir=tmp_path_factory.mktemp("pieces"))
    shapes = {1: POINTS_FROM_1_TO_2, 2: POINTS_FROM_2_TO_3}
    for origin, destination, direction in PIECES:
        pieces.append(
            origin,
            destination,
            float(origin),
            direction,
            [PLACES[origin], PLACES[destination]],
            shapes.get(origin, []),
        )
    arrays, _steps = assembly.assemble(
        assembly.build_graph_from_pieces(pieces),
        max_km_between_nodes=100,
        min_nodes_per_strongly_connected_component=1,
    )
    return arrays


def test_assemble_keeps_closed_components_and_contracts_their_chains(
    assembled,
):
    # The piece from 3 to 4 joins two components one way only: it is left
    # out. Place 2 is between 1 and 3 only: it is contracted. The arc from 1
    # to 3 has the length of the two pieces, 1 km + 2 km.
    arcs = _by_node_ids(assembled, lambda arc: assembled["weights"][arc])

    assert arcs == {(1, 3): 3.0, (3, 1): 3.0, (4, 5): 4.0, (5, 4): 4.0}


def _shape_points(arrays, arc):
    """The points of the shape of `arc`, as (latitude, longitude) pairs in
    units of 1e-7 degree, the units of the network arrays."""
    points, starts = arrays["shape_points"], arrays["shape_offsets"]
    flat = points[2 * starts[arc] : 2 * starts[arc + 1]]
    return list(zip(flat[0::2], flat[1::2]))


def test_the_shape_of_a_contracted_arc_passes_through_the_contracted_node(
    assembled,
):
    shapes = _by_node_ids(assembled, lambda arc: _shape_points(assembled, arc))

    # The points of piece 1-2, then place 2, then the points of piece 2-3
    points_from_1_to_3 = [
        (30000, 30000),
        (40000, 60000),
        (0, 100000),
        (30000, 130000),
        (40000, 160000),
    ]
    assert shapes[1, 3] == points_from_1_to_3
    # The reverse arc lists the same points from its own origin
    assert shapes[3, 1] == points_from_1_to_3[::-1]


def test_pieces_stored_in_two_batches_keep_their_own_points(tmp_path):
    # PieceArrays stores the pieces by batches of 10,000. Each of the 10,002
    # pieces has one point, at its own latitude: i units of 1e-7 degree.
    pieces = assembly.PieceArrays(tolerance_meters=None, work_dir=tmp_path)
    for i in range(10_002):
        pieces.append(i, i + 1, 1.0, 0, [[0, 0], [0, 0.01]], [[i * 1e-7, 0]])
    pieces.flush()

    last = 10_001
    first_point, end = pieces.offsets[last], pieces.offsets[last + 1]

    assert list(pieces.points[2 * first_point : 2 * end]) == [last, 0]
    assert list(pieces.origins[-2:]) == [10_000, 10_001]


def _csr(one_way=(), two_way=()):
    # (origin, destination, km) arcs, two_way ones in both directions, by origin
    arcs = [*one_way, *two_way, *((v, u, km) for u, v, km in two_way)]
    columns = (array(t, c) for t, c in zip("qqd", zip(*arcs)))
    return assembly.python.build_csr_from_arcs(*columns)[1:4]


def _two_way(*pairs):
    return _csr(two_way=[(u, v, 1.0) for u, v in pairs])


# Each case below is the three arguments of `contract_chains`: a graph as
# (offsets, heads, km), the mode of each node or None, and the length at
# which a chain is cut. The arcs are 1 km long.

# Node 2 is between 1 and 3. Node 4 is a dead end off node 1.
ROAD_WITH_A_DEAD_END = (
    _two_way((0, 1), (1, 2), (2, 3), (1, 4)),
    None,
    math.inf,
)
# The chains 0-1-3 and 0-2-3 would give two arcs from 0 to 3. The first one
# contracts node 1. The second one keeps its middle node, 2.
TWO_CHAINS_BETWEEN_THE_SAME_NODES = (
    _two_way((0, 1), (1, 3), (0, 2), (2, 3)),
    None,
    math.inf,
)
# The loop 0 -> 1 -> 2 -> 3 -> 0 would give an arc from 0 to 0. It keeps its
# middle node, 2.
ONE_WAY_LOOP_OFF_A_ROAD = (
    _csr(
        one_way=[(0, 1, 1), (1, 2, 1), (2, 3, 1), (3, 0, 1)],
        two_way=[(0, 4, 1)],
    ),
    None,
    math.inf,
)
TWO_ONE_WAY_ROADS_THAT_MERGE = (
    _csr(one_way=[(0, 2, 1), (1, 2, 1), (2, 3, 1)]),
    None,
    math.inf,
)
ONE_WAY_CYCLE = (
    _csr(one_way=[(1, 2, 1), (2, 3, 1), (3, 0, 1), (0, 1, 1)]),
    None,
    math.inf,
)
# The mode of each node: a road (nodes 0 and 1), a port (2), the sea (3 and 4)
ROAD_PORT_SEA = (
    _two_way((0, 1), (1, 2), (2, 3), (3, 4)),
    array("B", [0, 0, 1, 2, 2]),
    math.inf,
)
# The road is 0-4-3-2-1-5. It is walked from its lower end, node 0, and cut
# every 2 km: at node 3, then at node 1.
LONG_ROAD_CUT_EVERY_2_KM = (
    _two_way((5, 1), (1, 2), (2, 3), (3, 4), (4, 0)),
    None,
    2.0,
)


# `contract_chains` gives first the nodes that it keeps.
@both_backends
@pytest.mark.parametrize(
    "graph, modes, max_km, kept_nodes",
    [
        pytest.param(
            *ROAD_WITH_A_DEAD_END,
            [0, 1, 3, 4],
            id="a node between two others is contracted and a dead end stays",
        ),
        pytest.param(
            *TWO_CHAINS_BETWEEN_THE_SAME_NODES,
            [0, 2, 3],
            id="the second of two parallel chains is cut at its middle",
        ),
        pytest.param(
            *ONE_WAY_LOOP_OFF_A_ROAD,
            [0, 2, 4],
            id="a chain that comes back to its start is cut at its middle",
        ),
        pytest.param(
            *TWO_ONE_WAY_ROADS_THAT_MERGE,
            [0, 1, 2, 3],
            id="a node where two one-way roads merge is kept",
        ),
        pytest.param(
            *ONE_WAY_CYCLE,
            [0, 2],
            id="a cycle joined to nothing keeps its lowest node and its middle",
        ),
        pytest.param(
            *ROAD_PORT_SEA,
            [0, 1, 2, 3, 4],
            id="a node between two nodes of other modes is kept",
        ),
        pytest.param(
            *LONG_ROAD_CUT_EVERY_2_KM,
            [0, 1, 3, 5],
            id="a long chain is cut each time it reaches max_km_between_nodes",
        ),
    ],
)
def test_contract_chains_keeps_the_nodes_where_a_chain_ends_or_is_cut(
    backend, graph, modes, max_km, kept_nodes
):
    kept, *_ = backend.contract_chains(*graph, modes, max_km)

    assert list(kept) == kept_nodes


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


# The test below states what holds for any graph: it runs on the seven cases
# above and on six random graphs. A contracted arc is given by its `members`:
# the arcs of the graph that it replaces, in travel order.
on_every_graph = pytest.mark.parametrize(
    "graph, modes, max_km",
    [
        ROAD_WITH_A_DEAD_END,
        TWO_CHAINS_BETWEEN_THE_SAME_NODES,
        ONE_WAY_LOOP_OFF_A_ROAD,
        TWO_ONE_WAY_ROADS_THAT_MERGE,
        ONE_WAY_CYCLE,
        ROAD_PORT_SEA,
        LONG_ROAD_CUT_EVERY_2_KM,
        *(_random_chains(seed) for seed in range(6)),
    ],
)


def _origin_of_each_arc(offsets):
    return [
        u
        for u in range(len(offsets) - 1)
        for _ in range(offsets[u], offsets[u + 1])
    ]


def _members_of_each_arc(member_offsets, members):
    return [
        list(members[start:end])
        for start, end in zip(member_offsets, member_offsets[1:])
    ]


@both_backends
@on_every_graph
def test_contracted_arcs_replace_the_chains_of_the_graph(
    backend, graph, modes, max_km
):
    offsets, heads, weights = graph
    origin_of = _origin_of_each_arc(offsets)

    kept, origins, ends, km, member_offsets, members = backend.contract_chains(
        *graph, modes, max_km
    )

    # Every arc is a member of exactly one contracted arc
    assert sorted(members) == list(range(len(heads)))
    # The contracted arcs are sorted by origin then end, without twin or loop
    pairs = list(zip(origins, ends))
    assert pairs == sorted(set(pairs))
    assert all(origin != end for origin, end in pairs)
    # A contracted arc follows its members between two kept nodes
    members_of = _members_of_each_arc(member_offsets, members)
    for origin, end, arcs in zip(origins, ends, members_of):
        assert origin_of[arcs[0]] == kept[origin]
        assert heads[arcs[-1]] == kept[end]
        # Each member starts where the one before ends, at a contracted node
        for arc, next_arc in zip(arcs, arcs[1:]):
            assert heads[arc] == origin_of[next_arc]
            assert heads[arc] not in kept
    # A contracted arc has the length of its members
    assert list(km) == pytest.approx(
        [sum(weights[arc] for arc in arcs) for arcs in members_of]
    )
    # The two directions of a chain have the same length to the last bit.
    # `km_along` gives the length of each contracted arc by the nodes that it
    # passes. A chain that has no reverse arc is compared with itself.
    km_along = {
        (origin_of[arcs[0]], *(heads[arc] for arc in arcs)): length
        for arcs, length in zip(members_of, km)
    }
    for nodes, length in km_along.items():
        assert km_along.get(nodes[::-1], length) == length


# Both builds must give the same network file. Where a loop or a parallel
# chain is cut is a choice that the two kernels make the same way.
@needs_the_cpp_extension
def test_the_cpp_kernel_contracts_random_chains_as_the_python_kernel():
    for seed in range(6):
        graph, modes, max_km = _random_chains(seed)

        contracted = cpp.contract_chains(*graph, modes, max_km)

        assert list(map(list, contracted)) == list(
            map(list, assembly.python.contract_chains(*graph, modes, max_km))
        ), f"seed {seed}"


def _simplify(backend, ends, interior, tolerance_m):
    """The points of `interior` that the simplification keeps. A shape goes
    from (ends[0], ends[1]) to (ends[2], ends[3]) through the points of
    `interior`, all as (latitude, longitude) in units of 1e-7 degree: about
    1.1 cm at the equator. The kernel gets two shapes: an empty one, then
    this one. It must then find the points of this shape through the offsets."""
    points = array("i", [value for point in interior for value in point])
    kept, offsets = backend.simplify_shapes(
        points,
        array("i", [0, 0, len(interior)]),
        array("i", (0, 0, 0, 1000) + ends),
        tolerance_m,
    )
    flat = kept[2 * offsets[1] : 2 * offsets[2]]
    return list(zip(flat[0::2], flat[1::2]))


# A line along the equator, from longitude 0 to longitude 0.1: 11 km
ALONG_THE_EQUATOR = (0, 0, 0, 1000000)


# A line to the north at latitude 60, where a degree of longitude is half as
# long as at the equator
NORTH_AT_LATITUDE_60 = (600000000, 0, 601000000, 0)
# Lines of 0.002 degree across the antimeridian
EASTWARDS_ACROSS_THE_ANTIMERIDIAN = (0, 1799900000, 0, -1799900000)
WESTWARDS_ACROSS_THE_ANTIMERIDIAN = (0, -1799900000, 0, 1799900000)


@both_backends
@pytest.mark.parametrize(
    "ends, interior, tolerance_m, kept_points",
    [
        # 500 units of latitude are 5.6 m.
        pytest.param(
            ALONG_THE_EQUATOR,
            [(500, 300000), (-500, 600000)],
            10,
            [],
            id="points within the tolerance of the straight line are dropped",
        ),
        pytest.param(
            ALONG_THE_EQUATOR,
            [(0, 500000)],
            0,
            [],
            id="a point on the straight line is dropped with a tolerance of 0",
        ),
        # The point is on the equator too, 5.6 km east of the end of the line.
        pytest.param(
            ALONG_THE_EQUATOR,
            [(0, 1500000)],
            10,
            [(0, 1500000)],
            id="a point past the end of the line is kept",
        ),
        # The third point is 67 m off the equator: kept. The first point is
        # 55 m off the line from the start to the third point: kept. The
        # second point is 17 m off the line between these two points: dropped.
        pytest.param(
            ALONG_THE_EQUATOR,
            [(3000, 250000), (0, 500000), (-6000, 750000)],
            20,
            [(3000, 250000), (-6000, 750000)],
            id="a point near the line of the kept points is dropped",
        ),
        # The point is 4000 units of longitude east of the line: 22 m at
        # latitude 60. At the equator, it would be 44 m away.
        pytest.param(
            NORTH_AT_LATITUDE_60,
            [(600500000, 4000)],
            30,
            [],
            id="a degree of longitude is counted at the latitude of the line",
        ),
        # The two points are within 1 m of the line only if the line is taken
        # the short way.
        pytest.param(
            EASTWARDS_ACROSS_THE_ANTIMERIDIAN,
            [(0, 1800000000), (0, -1799950000)],
            1,
            [],
            id="a line eastwards across the antimeridian goes the short way",
        ),
        pytest.param(
            WESTWARDS_ACROSS_THE_ANTIMERIDIAN,
            [(0, -1800000000), (0, 1799950000)],
            1,
            [],
            id="a line westwards across the antimeridian goes the short way",
        ),
    ],
)
def test_simplify_keeps_the_points_beyond_the_tolerance_of_the_simplified_line(
    backend, ends, interior, tolerance_m, kept_points
):
    assert _simplify(backend, ends, interior, tolerance_m) == kept_points


@both_backends
def test_simplify_shapes_gives_where_the_points_of_each_shape_start(backend):
    # Three shapes along the equator: no interior point, then a point that is
    # kept (past the end of the line), then a point that is dropped.
    points = array("i", [0, 1500000, 0, 500000])
    offsets = array("i", [0, 0, 1, 2])
    ends = array("i", ALONG_THE_EQUATOR * 3)

    kept, kept_offsets = backend.simplify_shapes(points, offsets, ends, 10)

    assert list(kept_offsets) == [0, 0, 1, 1]
    assert list(kept) == [0, 1500000]


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


@needs_the_cpp_extension
def test_the_cpp_kernel_simplifies_random_walks_as_the_python_kernel():
    for seed in range(6):
        ends, interior = _random_shape(seed)

        assert _simplify(cpp, ends, interior, 20) == _simplify(
            assembly.python, ends, interior, 20
        ), f"seed {seed}"
