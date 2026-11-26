"""Turn restrictions: the nodes that they add to a junction, and how a route uses them.

WHAT IT ANSWERS

A "forbidden turn" is a list of nodes that no route may follow in this order, one
right after the other. `[W, J, S]` says that a route that arrives at the junction J
from the node W may not go on to the node S. A route may still go from W to S by
another way, and it may take every other turn at J.

A search of scgraph remembers the node where it is, and not the node that it comes
from. So the build writes the forbidden turns into the graph itself:
`add_junction_nodes` adds one node or more to some junctions. After that, every
search follows the turn restrictions without a change. Only the two ends of a route need a
rule (*Where a route starts and ends*).

WHAT THE BUILD CHANGES AT A JUNCTION

Four two-way streets meet at the junction J. The forbidden turn is `[W, J, S]`.

    BEFORE: one node for the junction     AFTER: two nodes at the same point

              N                                     N
              |                                     |
      W ----- J ----- E                     W       J ----- E
              |                              \\      |
              S                               `--> J'       S

      W -> J                                W -> J'           replaces W -> J
      J -> N, E, S, W                       J  -> N, E, S, W
                                            J' -> N, E, W     no edge to S

    J  is the junction for a route that arrives from N, E or S.
    J' is the junction for a route that arrives from W.

The "nodes of a junction" are J and the nodes that the build adds to it. J is the
"first node" of the junction, and J' is an "added node". They have the same point.
An edge of J' has the length, the class and the shape of the edge of J along the
same street. With streets of 1 km, the shortest route from W to S
was 2 km long. It is now 4 km long: W, J', N, J, S goes to N, turns back there and
passes the junction a second time.

WHERE A ROUTE STARTS AND ENDS

    A route that starts at the junction       A route that ends at the junction
    takes the edges of J: it arrives          may end at J or at J':
    from no street, so every turn is open.    both are the junction.

            J  -> N, E, S, W                      N, E, S -> J
            J' -> N, E, W                         W       -> J'

So a query point that is connected to one node of a junction is connected to each
of them, at the same distance (`connect_to_nodes_of_junctions`). This is also right
for a route that starts at the junction. Each edge of J' follows the same street as
an edge of J. So a route that starts at J' is never shorter than the shortest route
that starts at J.

A FORBIDDEN TURN THROUGH A STREET

OpenStreetMap also forbids a turn "from the street of A to the street of B, through
the street from J to K". This is how it forbids a U-turn between the two roadways of
a boulevard. The forbidden turn is `[A, J, K, B]`, and it adds two nodes:

    A --> J' --> K'' --> every exit of K, except B
          |
          `--> every other exit of J

    J'  is J for a route that arrives from A.
    K'' is K for a route that arrives from A through J.

A route that arrives at K from J, and did not come from A, is at the node K itself.
It may go on to B.

HOW THE NODES ARE ADDED

An "arrival" is a list of nodes that a route has just visited, one right after the
other. `[W, J]` is the arrival "at J, from W". An arrival "of a forbidden turn" is
the turn without its last node, or without several of its last nodes, with two nodes
at least. `[A, J, K, B]` has the arrivals `[A, J]` and `[A, J, K]`.

1. Each arrival of a forbidden turn gets one added node, at the last node of the
   arrival. Two forbidden turns with the same arrival share its node.
2. Take a route that follows an edge to a node Y. When the last nodes of the route
   are an arrival of a forbidden turn, the edge goes to the added node of this
   arrival. When several arrivals fit, the longest one is taken. When none fits, the
   edge goes to Y itself.
3. An edge that completes a forbidden turn is left out.

Aho and Corasick (1975) find words in a text this way. Villeneuve and Desaulniers
(2005) apply their method to the paths that a route may not follow.

WHY THE RESULT IS RIGHT

- Each edge of the new graph has the two ends and the length of one edge of the
  given graph. So a route of the new graph is a route of the given graph, with the
  same length.
- A route of the given graph that follows no forbidden turn has one route in the
  new graph, from the node where it starts. At each node, rule 2 gives its next
  edge, and rule 3 never removes this edge.
- A route that follows a forbidden turn has none. The turn without its last node is
  an arrival. After the nodes of this arrival, the route is at its added node, or
  at the added node of a longer arrival with the same last nodes. Rule 3 leaves the
  last edge of the turn out of both nodes.

HOW A NETWORK SAYS THAT IT FOLLOWS TURN RESTRICTIONS

The nodes of a junction come one right after the other: the first node of the
junction, then its added nodes. They have the same external id and the same node
mode. The row of this node mode in `GeoGraph.node_modes` has
`"has_turn_restrictions": True`. Without this key, two nodes with the same external
id are not one junction.

A build keeps these facts true (`scgraph.network_assembly`). It keeps all the nodes
of a junction, or removes them all. It never contracts a chain through a junction
with several nodes.
"""

from array import array
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from scgraph.errors import PathNotFoundError

if TYPE_CHECKING:  # annotations only
    from scgraph.geograph import GeoGraph
    from scgraph.graph import Graph
    from scgraph.helpers.osm import TurnRestriction


def add_junction_nodes(
    node_first_edge_ids: Sequence[int],
    edge_destination_node_ids: Sequence[int],
    forbidden_turns: Iterable[Sequence[int]],
) -> tuple[array, array, array, array]:
    """Add the nodes that make a graph follow forbidden turns (module docstring,
    *How the nodes are added*).

    Args:
        node_first_edge_ids: For each node, the id of its first edge, and one more
            value at the end: the count of the edges.
        edge_destination_node_ids: The destination id of each edge.
        forbidden_turns: The forbidden turns. Each one is a list of three node ids
            or more. A forbidden turn with an edge that the graph does not have is
            ignored: no route can follow it.

    Returns:
        `(node_first_edge_ids, edge_destination_node_ids, given_node_ids,
        given_edge_ids)` for the new graph, as int32 arrays. The first two store
        its edges by origin, and the edges of a node are sorted by destination id.
        `given_node_ids[i]` is the id that the node `i` has in the given graph. An
        added node comes right after the first node of its junction, so `given_node_ids`
        never decreases. `given_edge_ids[e]` is the id of the edge of the given
        graph with the same ends as the edge `e`. The caller reads the length, the
        class and the shape of an edge with it.

    Raises:
        ValueError: A forbidden turn has fewer than three nodes, or a node id that
            the graph does not have.
    """
    node_count = len(node_first_edge_ids) - 1

    def has_edge(origin_id, destination_id):
        return (
            destination_id
            in edge_destination_node_ids[
                node_first_edge_ids[origin_id] : node_first_edge_ids[
                    origin_id + 1
                ]
            ]
        )

    turns = set()
    for turn in forbidden_turns:
        turn = tuple(turn)
        if len(turn) < 3:
            raise ValueError(
                f"A forbidden turn has three nodes or more: got {list(turn)}"
            )
        if not all(0 <= node_id < node_count for node_id in turn):
            raise ValueError(
                f"The graph has the node ids 0 to {node_count - 1}: got the "
                f"forbidden turn {list(turn)}"
            )
        if all(map(has_edge, turn, turn[1:])):
            turns.add(turn)

    # 1. One added node for each arrival. `arrival_of_new_node` lists the new
    # nodes in order: each node as `(node,)`, then the arrivals that end at it.
    arrivals_of_node = {}
    for arrival in sorted(
        {turn[:size] for turn in turns for size in range(2, len(turn))}
    ):
        arrivals_of_node.setdefault(arrival[-1], []).append(arrival)
    arrival_of_new_node = []
    # The new id of each node of the given graph, and of each arrival
    new_node_ids, new_id_of_arrival = array("i"), {}
    for node_id in range(node_count):
        new_node_ids.append(len(arrival_of_new_node))
        arrival_of_new_node.append((node_id,))
        for arrival in arrivals_of_node.get(node_id, ()):
            new_id_of_arrival[arrival] = len(arrival_of_new_node)
            arrival_of_new_node.append(arrival)
    # Most nodes are the first node of no arrival. An edge of such a node makes
    # no arrival, so it goes to its destination itself, without a call of `follow`.
    first_nodes_of_arrivals = {arrival[0] for arrival in new_id_of_arrival}

    def follow(route):
        # The new id of the node that `route` reaches, or None when its last edge
        # completes a forbidden turn. `route` is an arrival and one more node.
        for first in range(len(route) - 2):
            if route[first:] in turns:
                return None  # 3. This edge is left out
        # 2. The longest arrival that the route has made, or the node itself
        for first in range(len(route) - 1):
            if route[first:] in new_id_of_arrival:
                return new_id_of_arrival[route[first:]]
        return new_node_ids[route[-1]]

    new_first_edge_ids, new_destination_node_ids = array("i", [0]), array("i")
    given_edge_ids = array("i")
    for arrival in arrival_of_new_node:
        node_id = arrival[-1]
        makes_no_arrival = (
            len(arrival) == 1 and node_id not in first_nodes_of_arrivals
        )
        edges = []  # (new destination id, id of the edge of the given graph)
        for edge_id in range(
            node_first_edge_ids[node_id], node_first_edge_ids[node_id + 1]
        ):
            destination_id = edge_destination_node_ids[edge_id]
            new_destination_id = (
                new_node_ids[destination_id]
                if makes_no_arrival
                else follow(arrival + (destination_id,))
            )
            if new_destination_id is not None:
                edges.append((new_destination_id, edge_id))
        for new_destination_id, edge_id in sorted(edges):
            new_destination_node_ids.append(new_destination_id)
            given_edge_ids.append(edge_id)
        new_first_edge_ids.append(len(new_destination_node_ids))
    return (
        new_first_edge_ids,
        new_destination_node_ids,
        array("i", (arrival[-1] for arrival in arrival_of_new_node)),
        given_edge_ids,
    )


def list_junctions_with_several_nodes(
    external_node_ids: Sequence[int],
    node_mode_ids: Sequence[int] | None = None,
) -> list[range]:
    """List the junctions of a graph that have added nodes (module docstring, *How
    a network says that it follows turn restrictions*).

    Args:
        external_node_ids: The external id of each node of a graph that a build
            made with turn restrictions.
        node_mode_ids: The node mode id of each node, or None for a graph of one
            node mode.

    Returns:
        The node ids of each such junction, as a range: the first node of the junction,
        then its added nodes.
    """
    junctions, first = [], 0
    for node_id in range(1, len(external_node_ids) + 1):
        if node_id < len(external_node_ids) and _are_one_junction(
            external_node_ids, node_mode_ids, node_id - 1, node_id
        ):
            continue
        if node_id - first > 1:
            junctions.append(range(first, node_id))
        first = node_id
    return junctions


def _are_one_junction(external_node_ids, node_mode_ids, node_id, other_id):
    # Whether two nodes that follow each other are nodes of one junction
    return external_node_ids[node_id] == external_node_ids[other_id] and (
        node_mode_ids is None
        or node_mode_ids[node_id] == node_mode_ids[other_id]
    )


def has_turn_restrictions(geograph: "GeoGraph") -> bool:
    """Return whether a node mode of the geograph follows turn restrictions."""
    return any(row.get("has_turn_restrictions") for row in geograph.node_modes)


def find_nodes_of_junction(geograph: "GeoGraph", node_id: int) -> range:
    """Return the ids of the nodes of a junction, from the id of any of them.

    Returns:
        The range of the ids: the first node of the junction, then its added
        nodes. A node of a node mode without `has_turn_restrictions`, or of a
        junction without an added node, gives a range of one id.

    Example: the nodes 6, 7 and 8 have the external id 42, and the nodes 5 and 9
    have other ids. The ids 6, 7 and 8 each give `range(6, 9)`.
    """
    node_mode_ids = geograph._read_node_mode_ids()
    if not geograph.node_modes[node_mode_ids[node_id]].get(
        "has_turn_restrictions"
    ):
        return range(node_id, node_id + 1)
    external_node_ids = geograph.external_node_ids
    first, last = node_id, node_id
    while first > 0 and _are_one_junction(
        external_node_ids, node_mode_ids, first - 1, first
    ):
        first -= 1
    while last + 1 < len(node_mode_ids) and _are_one_junction(
        external_node_ids, node_mode_ids, last, last + 1
    ):
        last += 1
    return range(first, last + 1)


def connect_to_nodes_of_junctions(
    geograph: "GeoGraph", node_distances: dict[int, float]
) -> dict[int, float]:
    """Connect a query point to each node of the junctions that it is connected to
    (module docstring, *Where a route starts and ends*).

    Args:
        node_distances: The distance from the query point to each node that it is
            connected to, by node id.

    Returns:
        `node_distances` with the other nodes of each junction, at the distance of
        the junction.
    """
    if not has_turn_restrictions(geograph):
        return node_distances
    return {
        node_id: distance
        for connected_node_id, distance in node_distances.items()
        for node_id in find_nodes_of_junction(geograph, connected_node_id)
    }


def find_route_end_at_junction(
    geograph: "GeoGraph", graph_object: "Graph", origin_id: int, node_id: int
) -> int:
    """Return the node where the shortest route from a node to a junction ends.

    Args:
        graph_object: The graph that is searched, with `cached_shortest_path`.
        origin_id: The node where the route starts.
        node_id: A node of the junction where the route ends.

    Returns:
        The id of this node, which is one of the nodes of the junction. When no
        route reaches the junction, the first node of the junction.
    """
    node_ids = find_nodes_of_junction(geograph, node_id)
    closest_id, closest_length = node_ids[0], float("inf")
    if len(node_ids) == 1:
        return closest_id
    for candidate_id in node_ids:
        try:
            length = graph_object.cached_shortest_path(
                origin_id=origin_id,
                destination_id=candidate_id,
                length_only=True,
            )["length"]
        except PathNotFoundError:
            continue
        if length < closest_length:
            closest_id, closest_length = candidate_id, length
    return closest_id


def list_forbidden_turns(
    graph: dict, restrictions: Sequence["TurnRestriction"]
) -> list[list[int]]:
    """Give turn restrictions as the forbidden turns of a graph (the docstring of
    `scgraph.helpers.osm`, *How a turn restriction is read*).

    Args:
        graph: The graph, as a dict of arrays with `edge_way_ids` and
            `external_node_ids`. A graph without `edge_way_ids` gives no forbidden
            turn.
        restrictions: The turn restrictions, as `read_turn_restrictions` returns
            them.

    Returns:
        The forbidden turns, each as a list of node ids of the graph.
    """
    if "edge_way_ids" not in graph or not restrictions:
        return []
    node_first_edge_ids = graph["node_first_edge_ids"]
    edge_destination_node_ids = graph["edge_destination_node_ids"]
    named_way_ids, via_node_ids = set(), set()
    for restriction in restrictions:
        named_way_ids.update(
            (
                restriction.from_way_id,
                *restriction.via_way_ids,
                restriction.to_way_id,
            )
        )
        via_node_ids.add(restriction.via_node_id)
    # The edges of each named way, as (origin id, destination id)
    edges_of_way = {way_id: [] for way_id in named_way_ids}
    edge_way_ids = graph["edge_way_ids"]
    for origin_id in range(len(node_first_edge_ids) - 1):
        for edge_id in range(
            node_first_edge_ids[origin_id], node_first_edge_ids[origin_id + 1]
        ):
            if edge_way_ids[edge_id] in edges_of_way:
                edges_of_way[edge_way_ids[edge_id]].append(
                    (origin_id, edge_destination_node_ids[edge_id])
                )
    node_id_of_via = {
        external_id: node_id
        for node_id, external_id in enumerate(graph["external_node_ids"])
        if external_id in via_node_ids
    }

    forbidden_turns = []
    for restriction in restrictions:
        from_edges = edges_of_way[restriction.from_way_id]
        if (
            restriction.via_node_id is not None
            and restriction.from_way_id == restriction.to_way_id
        ):
            # A U-turn at the `via` node: the node after the turn is the node
            # before the turn. The steps below would take the next node of the
            # way as the node after the turn, and forbid to go straight on.
            via_id = node_id_of_via.get(restriction.via_node_id)
            if not restriction.is_only:
                forbidden_turns.extend(
                    [before_id, via_id, before_id]
                    for before_id, destination_id in from_edges
                    if destination_id == via_id
                )
            continue
        # 1. The turn nodes
        if restriction.via_node_id is not None:
            turn_node_ids = [node_id_of_via.get(restriction.via_node_id)]
        else:
            turn_node_ids = _follow_via_ways(
                from_edges,
                [edges_of_way[way_id] for way_id in restriction.via_way_ids],
            )
        if turn_node_ids is None or turn_node_ids[0] is None:
            continue
        # 2. The node before the turn. 3. The node after the turn. The driver
        # does not come back along the first `via` way, nor go on along the last
        # one.
        before_node_ids = [
            origin_id
            for origin_id, destination_id in from_edges
            if destination_id == turn_node_ids[0]
            and origin_id not in turn_node_ids[1:2]
        ]
        after_node_ids = [
            destination_id
            for origin_id, destination_id in edges_of_way[restriction.to_way_id]
            if origin_id == turn_node_ids[-1]
            and destination_id not in turn_node_ids[-2:-1]
        ]
        if len(before_node_ids) != 1 or len(after_node_ids) != 1:
            continue
        # 4. The forbidden turn, or one for each other edge of the last turn node
        first_node_ids = before_node_ids + turn_node_ids
        if not restriction.is_only:
            forbidden_turns.append(first_node_ids + after_node_ids)
            continue
        last = turn_node_ids[-1]
        forbidden_turns.extend(
            first_node_ids + [destination_id]
            for destination_id in edge_destination_node_ids[
                node_first_edge_ids[last] : node_first_edge_ids[last + 1]
            ]
            if destination_id != after_node_ids[0]
        )
    return forbidden_turns


def _follow_via_ways(from_edges, edges_of_via_ways):
    """Return the turn nodes of a restriction with `via` ways, or None when the ways
    do not follow each other in one way only.

    `from_edges` are the edges of the `from` way, and `edges_of_via_ways` are the
    edges of each `via` way, in the order of travel. An edge is
    `(origin id, destination id)`.
    """
    # The node where the `from` way meets the first `via` way
    meeting_node_ids = {destination_id for _, destination_id in from_edges} & {
        origin_id for origin_id, _ in edges_of_via_ways[0]
    }
    if len(meeting_node_ids) != 1:
        return None
    turn_node_ids = [meeting_node_ids.pop()]
    for via_edges in edges_of_via_ways:
        # Follow the way from the last turn node to its other end, edge after
        # edge, without turning back
        previous_id = None
        while True:
            next_ids = [
                destination_id
                for origin_id, destination_id in via_edges
                if origin_id == turn_node_ids[-1]
                and destination_id != previous_id
            ]
            if len(next_ids) != 1 or next_ids[0] in turn_node_ids:
                break
            previous_id = turn_node_ids[-1]
            turn_node_ids.append(next_ids[0])
        if previous_id is None:  # the way does not leave the last turn node
            return None
    return turn_node_ids
