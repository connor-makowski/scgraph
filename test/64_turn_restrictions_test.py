import heapq
import random

import pytest
from helpers import great_circle_km

from scgraph import GeoGraph, network_file
from scgraph.helpers.osm import (
    list_forbidden_turns,
    read_turn_restrictions,
    select_main_roads,
)
from scgraph.turn_restrictions import add_junction_nodes
from scgraph import network_assembly
from scgraph.helpers import osm

osmium = pytest.importorskip("osmium")

# Six places, 0.01 degree apart on the equator or on a meridian:
#
#                     NORTH
#                       |
#     WEST --- A ------ B --- EAST
#              |
#            SOUTH
#
# OSM ids -> (latitude, longitude)
WEST, A, B, EAST, NORTH, SOUTH = 104, 100, 105, 102, 101, 103
# A point off the straight line from A to B, for a street that bends. No way of
# `_WAYS` passes there.
BEND = 106
_POINTS = {
    BEND: (0.003, 0.005),
    WEST: (0.0, -0.01),
    A: (0.0, 0.0),
    B: (0.0, 0.01),
    EAST: (0.0, 0.02),
    NORTH: (0.01, 0.01),
    SOUTH: (-0.01, 0.0),
}
# Each street is one two-way way, between two places
WEST_STREET, MIDDLE_STREET, EAST_STREET, NORTH_STREET, SOUTH_STREET = range(
    1, 6
)
_WAYS = {
    WEST_STREET: [WEST, A],
    MIDDLE_STREET: [A, B],
    EAST_STREET: [B, EAST],
    NORTH_STREET: [B, NORTH],
    SOUTH_STREET: [A, SOUTH],
}
# The length of each street, in km
STREET_KM = great_circle_km(_POINTS[A], _POINTS[B])

# The length of a street from A to B that passes at BEND, in km
BENT_STREET_KM = great_circle_km(_POINTS[A], _POINTS[BEND]) + great_circle_km(
    _POINTS[BEND], _POINTS[B]
)

# A driver who comes from A may not turn left at B, into the north street
NO_LEFT_TURN_AT_B = {
    "restriction": "no_left_turn",
    "from": MIDDLE_STREET,
    "via": [("node", B)],
    "to": NORTH_STREET,
}


def _write_streets(tmp_path, turn_restriction, ways=_WAYS, way_tags=None):
    """Write an OpenStreetMap file of the six places, with `ways` and one turn
    restriction. A way is a primary road, with the tags that `way_tags` gives
    for its id, if any. Return the path of the file."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<osm version="0.6">']
    # An OpenStreetMap file lists its nodes by rising id
    for ref, (lat, lon) in sorted(_POINTS.items()):
        lines.append(f'<node id="{ref}" version="1" lat="{lat}" lon="{lon}"/>')
    for ref, refs in ways.items():
        lines.append(f'<way id="{ref}" version="1">')
        lines += [f'<nd ref="{r}"/>' for r in refs]
        tags = {"highway": "primary"} | (way_tags or {}).get(ref, {})
        lines += [f'<tag k="{k}" v="{v}"/>' for k, v in tags.items()]
        lines.append("</way>")
    members = [
        ("way", turn_restriction["from"], "from"),
        *((kind, ref, "via") for kind, ref in turn_restriction["via"]),
        ("way", turn_restriction["to"], "to"),
    ]
    tags = {"type": "restriction"} | {
        key: value
        for key, value in turn_restriction.items()
        if key not in ("from", "via", "to")
    }
    lines.append('<relation id="1" version="1">')
    lines += [
        f'<member type="{kind}" ref="{ref}" role="{role}"/>'
        for kind, ref, role in members
    ]
    lines += [f'<tag k="{k}" v="{v}"/>' for k, v in tags.items()]
    lines.append("</relation></osm>")
    path = tmp_path / "streets.osm"
    path.write_text("\n".join(lines))
    return str(path)


def _load(
    tmp_path, turn_restriction, ways=_WAYS, way_tags=None, **load_arguments
):
    """Load the six places and their streets, with one turn restriction."""
    return GeoGraph.load_from_osm(
        _write_streets(tmp_path, turn_restriction, ways, way_tags),
        **load_arguments,
    )


def _km(geograph, origin, destination):
    """The length of the route between two of the six places."""
    return geograph.get_shortest_path(
        dict(zip(("latitude", "longitude"), _POINTS[origin])),
        dict(zip(("latitude", "longitude"), _POINTS[destination])),
    )["length"]


@pytest.mark.parametrize(
    "turn_restriction",
    [
        NO_LEFT_TURN_AT_B,
        # At B, a driver who comes from A may only go on to the east street
        {
            "restriction": "only_straight_on",
            "from": MIDDLE_STREET,
            "via": [("node", B)],
            "to": EAST_STREET,
        },
        # A driver who comes by the west street and the middle street may not
        # turn left at B
        {
            "restriction": "no_left_turn",
            "from": WEST_STREET,
            "via": [("way", MIDDLE_STREET)],
            "to": NORTH_STREET,
        },
    ],
    ids=["no_left_turn", "only_straight_on", "via_way"],
)
def test_a_route_makes_no_turn_that_a_turn_restriction_forbids(
    tmp_path, turn_restriction
):
    streets = _load(tmp_path, turn_restriction)
    # The route goes on to EAST, turns back there, and turns right at B: the
    # west, middle and north streets once, and the east street twice.
    assert _km(streets, WEST, NORTH) == pytest.approx(5 * STREET_KM)


def test_a_turn_restriction_through_a_via_way_holds_from_its_from_way_only(
    tmp_path,
):
    streets = _load(
        tmp_path,
        {
            "restriction": "no_left_turn",
            "from": WEST_STREET,
            "via": [("way", MIDDLE_STREET)],
            "to": NORTH_STREET,
        },
    )
    # A driver who comes by the south street may turn left at B
    assert _km(streets, SOUTH, NORTH) == pytest.approx(3 * STREET_KM)


def test_a_route_can_end_at_the_junction_of_a_turn_restriction(tmp_path):
    streets = _load(tmp_path, NO_LEFT_TURN_AT_B)
    # The west street and the middle street: the route ends where the turn
    # would start
    assert _km(streets, WEST, B) == pytest.approx(2 * STREET_KM)


def test_a_route_from_a_point_at_an_added_node_starts_at_its_junction():
    # A junction of two streets of 1 km, to the west and to the north. The
    # forbidden turn is from the west street to the north street. The node 1 is
    # the first node of the junction, and the node 2 is its added node, for a route
    # that arrives from the west: it has no edge to the north.
    # A build gives the two nodes the same point. Here the added node is 1 m to
    # the east, so that the query point snaps to it.
    added_node_point = [0, 0.00001]
    junction = GeoGraph(
        graph=[{2: 1.0}, {0: 1.0, 3: 1.0}, {0: 1.0}, {1: 1.0}],
        nodes=[[0, -0.01], [0, 0], added_node_point, [0.01, 0]],
        external_node_ids=[10, 11, 11, 12],
        node_modes=[{"name": None, "has_turn_restrictions": True}],
    )
    route = junction.get_shortest_path(
        dict(zip(("latitude", "longitude"), added_node_point)),
        {"latitude": 0.01, "longitude": 0},
    )
    # The route starts at the junction, so it arrives from no street: it takes
    # the north street
    assert route["length"] == pytest.approx(1.0)


def test_a_turn_restriction_holds_for_the_longer_of_two_roads_between_two_junctions(
    tmp_path,
):
    # Two roads join A and B. The middle street is a primary road, one way from
    # B to A. The trunk road bends, both ways. A driver who comes by the trunk
    # road may not turn left at B.
    trunk_road = 6
    streets = _load(
        tmp_path,
        NO_LEFT_TURN_AT_B | {"from": trunk_road},
        ways=_WAYS | {trunk_road: [A, BEND, B]},
        way_tags={
            MIDDLE_STREET: {"oneway": "-1"},
            trunk_road: {"highway": "trunk"},
        },
    )
    # The west street, the trunk road, the east street twice, the north street
    assert _km(streets, WEST, NORTH) == pytest.approx(
        4 * STREET_KM + BENT_STREET_KM
    )


def test_a_route_through_an_added_node_follows_the_drawing_of_its_street(
    tmp_path,
):
    streets = _load(
        tmp_path, NO_LEFT_TURN_AT_B, ways=_WAYS | {MIDDLE_STREET: [A, BEND, B]}
    )
    route = streets.get_shortest_path(
        dict(zip(("latitude", "longitude"), _POINTS[WEST])),
        dict(zip(("latitude", "longitude"), _POINTS[B])),
    )
    # The route arrives at B by the bent street: at the added node of B
    assert [tuple(point) for point in route["coordinate_path"]] == [
        _POINTS[place] for place in (WEST, WEST, A, BEND, B, B)
    ]


def test_nodes_with_one_external_id_are_one_junction_only_with_turn_restrictions():
    # Three nodes on a line, 1 km apart, with the same external id. Node 0 is a
    # road node, and the road nodes follow turn restrictions. The nodes 1 and 2
    # are sea nodes, and the sea nodes do not.
    line = GeoGraph(
        graph=[{1: 1.0}, {0: 1.0, 2: 1.0}, {1: 1.0}],
        nodes=[[0, 0], [0, 0.01], [0, 0.02]],
        external_node_ids=[7, 7, 7],
        node_modes=[
            {"name": "road", "has_turn_restrictions": True},
            {"name": "sea"},
        ],
        node_mode_ids=[0, 1, 1],
    )
    route = line.get_shortest_path(
        {"latitude": 0, "longitude": 0.02},
        {"latitude": 0, "longitude": 0},
        output_path=True,
        snap_to_node_modes=["road", "sea"],
    )
    # The route starts at node 2 and ends at node 0: no two of the three nodes
    # are one junction
    assert route["path"] == [2, 1, 0]


def test_a_conditional_turn_restriction_is_not_applied(tmp_path):
    left_turn_forbidden_in_the_morning = {
        "restriction:conditional": "no_left_turn @ (07:00-09:00)",
        "from": MIDDLE_STREET,
        "via": [("node", B)],
        "to": NORTH_STREET,
    }
    streets = _load(tmp_path, left_turn_forbidden_in_the_morning)
    assert _km(streets, WEST, NORTH) == pytest.approx(3 * STREET_KM)


@pytest.mark.parametrize("excepted_vehicles", ["motorcar", "psv; motorcar"])
def test_a_turn_restriction_that_excepts_cars_is_not_applied(
    tmp_path, excepted_vehicles
):
    streets = _load(tmp_path, NO_LEFT_TURN_AT_B | {"except": excepted_vehicles})
    assert _km(streets, WEST, NORTH) == pytest.approx(3 * STREET_KM)


# The long street is one way, from A to EAST through B. It replaces the middle
# street and the east street.
LONG_STREET = 6
_WAYS_WITH_LONG_STREET = {
    WEST_STREET: [WEST, A],
    LONG_STREET: [A, B, EAST],
    NORTH_STREET: [B, NORTH],
    SOUTH_STREET: [A, SOUTH],
}


def test_a_u_turn_restriction_lets_a_route_go_straight_on_a_one_way_street(
    tmp_path,
):
    # A driver who arrives at B along the long street may not go back along it
    streets = _load(
        tmp_path,
        {
            "restriction": "no_u_turn",
            "from": LONG_STREET,
            "via": [("node", B)],
            "to": LONG_STREET,
        },
        ways=_WAYS_WITH_LONG_STREET,
        way_tags={LONG_STREET: {"oneway": "yes"}},
        # No route comes back from EAST, so EAST is not in the largest component
        largest_component=False,
    )
    assert _km(streets, WEST, EAST) == pytest.approx(3 * STREET_KM)


# A turn restriction that does not give one turn of the network changes no route.
@pytest.mark.parametrize(
    "turn_restriction, ways",
    [
        # The file has no way 99
        (NO_LEFT_TURN_AT_B | {"to": 99}, _WAYS),
        # B is in the middle of the long street: a driver arrives there from A
        # or from EAST
        (NO_LEFT_TURN_AT_B | {"from": LONG_STREET}, _WAYS_WITH_LONG_STREET),
        # The south street does not leave B, where the middle street ends
        (
            {
                "restriction": "no_left_turn",
                "from": WEST_STREET,
                "via": [("way", MIDDLE_STREET), ("way", SOUTH_STREET)],
                "to": NORTH_STREET,
            },
            _WAYS,
        ),
    ],
    ids=["way_not_in_the_file", "via_node_inside_a_way", "via_ways_apart"],
)
def test_a_turn_restriction_that_names_no_single_turn_is_not_applied(
    tmp_path, turn_restriction, ways
):
    streets = _load(tmp_path, turn_restriction, ways=ways)
    assert _km(streets, WEST, NORTH) == pytest.approx(3 * STREET_KM)


def test_load_turn_restrictions_false_allows_every_turn(tmp_path):
    streets = _load(tmp_path, NO_LEFT_TURN_AT_B, load_turn_restrictions=False)
    assert _km(streets, WEST, NORTH) == pytest.approx(3 * STREET_KM)


def test_distance_matrix_follows_the_turn_restrictions(tmp_path):
    streets = _load(tmp_path, NO_LEFT_TURN_AT_B)
    places = [
        dict(zip(("latitude", "longitude"), _POINTS[place]))
        for place in (WEST, NORTH, B)
    ]
    # In streets: WEST to NORTH makes the detour by EAST. The other routes are
    # direct, and a route that starts or ends at B makes no turn there.
    assert streets.distance_matrix(places) == [
        pytest.approx([0, 5 * STREET_KM, 2 * STREET_KM]),
        pytest.approx([3 * STREET_KM, 0, STREET_KM]),
        pytest.approx([2 * STREET_KM, STREET_KM, 0]),
    ]


@pytest.mark.parametrize("file_format", ["scgraph", "graphjson"])
def test_a_saved_network_keeps_its_turn_restrictions(tmp_path, file_format):
    file = str(tmp_path / f"streets.{file_format}")
    saved = _load(tmp_path, NO_LEFT_TURN_AT_B)
    getattr(saved, f"save_as_{file_format}")(file)
    streets = getattr(GeoGraph, f"load_from_{file_format}")(file)
    assert {
        "to NORTH": _km(streets, WEST, NORTH),
        "to B": _km(streets, WEST, B),
    } == pytest.approx({"to NORTH": 5 * STREET_KM, "to B": 2 * STREET_KM})


def test_an_added_node_is_reached_from_each_street_of_a_junction(tmp_path):
    streets = _load(tmp_path, NO_LEFT_TURN_AT_B)
    # A depot 0.001 degree north of B, joined to the closest junction
    depot = {"latitude": 0.001, "longitude": 0.01}
    streets.add_coord_node(depot, node_addition_type="closest")
    depot_km = great_circle_km(_POINTS[B], (0.001, 0.01))
    lengths = {
        origin: streets.get_shortest_path(
            dict(zip(("latitude", "longitude"), _POINTS[origin])), depot
        )["length"]
        for origin in (WEST, EAST)
    }
    # From WEST, the route arrives at B by the street of the turn restriction
    assert lengths == pytest.approx(
        {WEST: 2 * STREET_KM + depot_km, EAST: STREET_KM + depot_km}
    )


# A pipeline removes each node that offers no choice to a route. This test calls
# the steps of a pipeline: no public call builds a network without a download.
def test_a_built_network_keeps_the_junction_of_a_turn_restriction(tmp_path):
    # The middle street is one way, from A to B. A back street, one way from
    # EAST to SOUTH, lets a route come back to A. With the turn restriction,
    # the route that arrives at B from A can only go on to EAST: B offers it no
    # choice. The middle street bends, so it is longer than the straight line
    # from A to B.
    back_street = 6
    streets = _write_streets(
        tmp_path,
        NO_LEFT_TURN_AT_B,
        ways=_WAYS | {MIDDLE_STREET: [A, BEND, B], back_street: [EAST, SOUTH]},
        way_tags={
            MIDDLE_STREET: {"oneway": "yes"},
            back_street: {"oneway": "yes"},
        },
    )
    pieces = osm.build_way_pieces(
        streets, {"road": {"ways": select_main_roads}}, ("highway",), 2
    )
    graph = network_assembly.build_graph_from_pieces(pieces["road"])
    graph = network_assembly.forbid_turns(
        graph,
        list_forbidden_turns(graph, read_turn_restrictions(streets)),
    )
    arrays = network_assembly.assemble_network(
        graph, max_km_between_nodes=2, min_component_nodes=None
    )
    file = str(tmp_path / "built.scgraph")
    node_modes = [{"name": None, "has_turn_restrictions": True}]
    network_file.write(
        file,
        arrays,
        network_file.build_header_metadata(
            {},
            node_modes=node_modes,
            node_mode_ids=bytes(len(arrays["node_points"]) // 2),
        ),
    )

    built = GeoGraph.load_from_scgraph(file)

    # The west street and the middle street: the route ends at B, not at a
    # node that is a straight line away from B.
    assert _km(built, WEST, B) == pytest.approx(STREET_KM + BENT_STREET_KM)


def _find_lengths_without_forbidden_turns(graph, forbidden_turns, origin_id):
    """The length of the shortest route from `origin_id` to each node, among the
    routes that follow no forbidden turn. A search state is the last nodes of the
    route: as many as the longest forbidden turn has, less one."""
    forbidden = {tuple(turn) for turn in forbidden_turns}
    kept = max(map(len, forbidden)) - 1
    lengths, settled, queue = {}, set(), [(0, (origin_id,))]
    while queue:
        length, route = heapq.heappop(queue)
        if route in settled:
            continue
        settled.add(route)
        lengths.setdefault(route[-1], length)
        for destination_id, weight in graph[route[-1]].items():
            new_route = route + (destination_id,)
            if not any(
                new_route[first:] in forbidden
                for first in range(len(new_route))
            ):
                heapq.heappush(queue, (length + weight, new_route[-kept:]))
    return lengths


def _random_graph_with_forbidden_turns(randomizer):
    """A graph of 8 nodes with 6 forbidden turns of 3 or 4 nodes."""
    graph = [
        {
            destination_id: randomizer.randint(1, 9)
            for destination_id in randomizer.sample(range(8), 3)
            if destination_id != origin_id
        }
        for origin_id in range(8)
    ]
    forbidden_turns = []
    while len(forbidden_turns) < 6:
        turn = [randomizer.randrange(8)]
        while len(turn) < randomizer.choice((3, 4)) and graph[turn[-1]]:
            turn.append(randomizer.choice(list(graph[turn[-1]])))
        if len(turn) >= 3:
            forbidden_turns.append(turn)
    return graph, forbidden_turns


def _add_junction_nodes(graph, forbidden_turns):
    """`add_junction_nodes` for a graph given as one dict of edges for each node.
    Return the new graph in the same form, and the id that each of its nodes has
    in `graph`."""
    node_first_edge_ids, edge_destination_node_ids, weights = [0], [], []
    for edges in graph:
        edge_destination_node_ids += edges
        weights += edges.values()
        node_first_edge_ids.append(len(weights))
    first_edge_ids, destination_node_ids, given_node_ids, given_edge_ids = (
        add_junction_nodes(
            node_first_edge_ids, edge_destination_node_ids, forbidden_turns
        )
    )
    new_graph = [
        {
            destination_node_ids[edge_id]: weights[given_edge_ids[edge_id]]
            for edge_id in range(first_edge_ids[node_id], last_edge_id)
        }
        for node_id, last_edge_id in enumerate(first_edge_ids[1:])
    ]
    return new_graph, list(given_node_ids)


def test_the_added_nodes_keep_the_shortest_routes_without_a_forbidden_turn(
    graph_class,
):
    randomizer = random.Random(64)
    cases = [
        # The route 0, 1, 2 is an arrival of the first forbidden turn, and its
        # end 1, 2 is an arrival of the second one: the edge to node 4 must be
        # left out.
        (
            [{1: 1}, {2: 1}, {3: 1, 4: 1}, {4: 5}, {}],
            [[0, 1, 2, 3], [1, 2, 4]],
        ),
        *(_random_graph_with_forbidden_turns(randomizer) for _ in range(30)),
    ]
    for graph, forbidden_turns in cases:
        new_graph, given_node_ids = _add_junction_nodes(graph, forbidden_turns)
        searched = graph_class(new_graph)
        for origin_id in range(len(graph)):
            # A route starts at the first node of a junction, and ends at any node
            # of a junction
            lengths = {}
            tree = searched.get_shortest_path_tree(
                given_node_ids.index(origin_id)
            )
            for node_id, length in enumerate(tree["distance_matrix"]):
                if length != float("inf"):
                    given_id = given_node_ids[node_id]
                    lengths[given_id] = min(
                        length, lengths.get(given_id, length)
                    )
            assert lengths == _find_lengths_without_forbidden_turns(
                graph, forbidden_turns, origin_id
            )
