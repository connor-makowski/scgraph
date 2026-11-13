from scgraph import Graph

# A square lattice of 12 x 12 nodes; each node is linked to its neighbors in
# its row and in its column by arcs of length 1. The node at (row, column) has
# the id `row * 12 + column`.
SIDE = 12
lattice = Graph(
    [
        {
            neighbor_row * SIDE + neighbor_column: 1.0
            for neighbor_row, neighbor_column in (
                (row - 1, column),
                (row + 1, column),
                (row, column - 1),
                (row, column + 1),
            )
            if 0 <= neighbor_row < SIDE and 0 <= neighbor_column < SIDE
        }
        for row in range(SIDE)
        for column in range(SIDE)
    ]
)
corner = 0
center = 6 * SIDE + 6


def _count_heuristic_calls(destination_id):
    """Number of calls of the heuristic by one A* search from the corner."""
    calls = []

    def straight_line(node, destination):
        calls.append(node)
        rows = node // SIDE - destination // SIDE
        columns = node % SIDE - destination % SIDE
        return (rows**2 + columns**2) ** 0.5

    lattice.a_star(corner, destination_id, heuristic_fn=straight_line)
    return len(calls)


def test_a_star_searches_no_wider_when_the_destination_is_off_the_graph():
    # An exit distance joins the destination node to a point off the graph
    on_the_graph = _count_heuristic_calls({center: 0.0})
    off_the_graph = _count_heuristic_calls({center: 5.0})
    assert off_the_graph == on_the_graph


def test_a_star_with_more_than_four_destinations_does_not_call_the_heuristic():
    five_nodes_around_the_center = {
        center: 0.0,
        center - 1: 0.0,
        center + 1: 0.0,
        center - SIDE: 0.0,
        center + SIDE: 0.0,
    }
    assert _count_heuristic_calls(five_nodes_around_the_center) == 0


def test_a_star_returns_the_shortest_path_when_the_heuristic_is_not_consistent():
    # Two routes from node 0 to node 3, then one way to node 5:
    # 0 -> 1 -> 3 has length 2, and 0 -> 2 -> 3 has length 3.
    two_routes = Graph(
        [{1: 1.0, 2: 1.5}, {3: 1.0}, {3: 1.5}, {4: 1.0}, {5: 1.0}, {}]
    )

    # The distance left from node 1 to node 5 is 3.0: a heuristic of 2.9 never
    # exceeds the distance left. The heuristic drops by 2.9 along the arc
    # 1 -> 3, which is 1 long: it is not consistent, and the search first
    # reaches node 3 by the long route.
    def high_at_node_1(node, destination):
        return 2.9 if node == 1 else 0.0

    assert two_routes.a_star(0, 5, heuristic_fn=high_at_node_1) == {
        "path": [0, 1, 3, 4, 5],
        "length": 4.0,
    }
