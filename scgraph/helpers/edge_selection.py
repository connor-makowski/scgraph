"""
Pure-Python version of the C++ `select_edges`, with the same result. The algorithm is
described in `scgraph/cpp/src/edge_selection.hpp`. Read it first.

Same as in C++: the three steps, the checks and the messages of the errors.

Different: step 1 finds the first node of each node mode by bisection, because
`node_mode_ids` is sorted. The check of the order runs in C (`map`), not in a Python
loop.
"""

from array import array
from bisect import bisect_left

from scgraph.array_checks import is_sorted

# The highest value of an int32, the type of `node_first_edge_ids` in a network file
INT32_MAX = 2**31 - 1


def select_edges(
    node_first_edge_ids: array | memoryview,
    edge_destination_node_ids: array | memoryview,
    node_mode_ids: array | memoryview,
    is_node_mode_kept: list[bool],
    edge_first_shape_point_ids: array | memoryview | None = None,
) -> tuple:
    """
    Select the nodes of some node modes of a network file, and the edges between them.

    A "position" is the rank of a node, of an edge or of a shape point in the arrays of
    the file. A "run" (first, last) is the range of positions from first to last - 1.

    Args:
        node_first_edge_ids: The edges of node u are at the positions node_first_edge_ids[u] to
            node_first_edge_ids[u + 1] - 1 (int32).
        edge_destination_node_ids: The destination id of each edge, as the position of a node (int32).
        node_mode_ids: The node mode of each node (uint8). The values must not decrease.
        is_node_mode_kept: For each node mode of the file, True if the selection
            keeps it.
        edge_first_shape_point_ids: The shape of edge a is the shape points at the positions
            edge_first_shape_point_ids[a] to edge_first_shape_point_ids[a + 1] - 1 (int32). None for a file
            without edge shapes.

    Returns:
        A tuple (node_first_edge_ids, edge_destination_node_ids, edge_first_shape_point_ids, node_runs, edge_runs,
        shape_point_runs). The first three are the arrays of the selection, where a
        position counts only the kept nodes, edges and shape points. `edge_first_shape_point_ids`
        is None without edge shapes. The last three are lists of runs: the positions
        in the file of the kept nodes, of the kept edges and of their shape points.

    Raises:
        ValueError: If a value of the arrays cannot be used as a position.
    """
    node_count, edge_count = len(node_first_edge_ids) - 1, len(
        edge_destination_node_ids
    )
    mode_count = len(is_node_mode_kept)
    if node_count < 0 or len(node_mode_ids) != node_count:
        raise ValueError("one node mode per node expected")
    if (
        edge_first_shape_point_ids is not None
        and len(edge_first_shape_point_ids) != edge_count + 1
    ):
        raise ValueError("invalid edge_first_shape_point_ids")

    # 1. Find the nodes of each node mode
    if not is_sorted(node_mode_ids) or (
        node_count and node_mode_ids[-1] >= mode_count
    ):
        raise ValueError("unsorted or unknown node modes")
    first_node = [
        bisect_left(node_mode_ids, mode) for mode in range(mode_count + 1)
    ]

    # 2. Give their positions to the kept nodes
    node_runs = []
    shift = [0] * mode_count
    kept_nodes = 0
    for mode in range(mode_count):
        if not is_node_mode_kept[mode]:
            continue
        first, last = first_node[mode], first_node[mode + 1]
        # Step 3 uses the first edge ids of these nodes as positions in `edge_destination_node_ids`
        mode_node_first_edge_ids = node_first_edge_ids[first : last + 1]
        if (
            mode_node_first_edge_ids[0] < 0
            or mode_node_first_edge_ids[-1] > edge_count
            or not is_sorted(mode_node_first_edge_ids)
        ):
            raise ValueError("invalid node_first_edge_ids")
        _add_run(node_runs, first, last)
        shift[mode] = kept_nodes - first
        kept_nodes += last - first

    # 3. Visit the edges of each kept node
    new_node_first_edge_ids, new_edge_destination_node_ids = array(
        "i", [0]
    ), array("i")
    new_edge_first_shape_point_ids = (
        None if edge_first_shape_point_ids is None else array("i", [0])
    )
    edge_runs, shape_point_runs = [], []
    kept_shape_points = 0
    for first, last in node_runs:
        for node in range(first, last):
            for edge in range(
                node_first_edge_ids[node], node_first_edge_ids[node + 1]
            ):
                destination_id = edge_destination_node_ids[edge]
                if not 0 <= destination_id < node_count:
                    raise ValueError("edge to a missing node")
                mode = node_mode_ids[destination_id]
                if not is_node_mode_kept[mode]:
                    continue
                new_edge_destination_node_ids.append(
                    destination_id + shift[mode]
                )
                _add_run(edge_runs, edge, edge + 1)
                if edge_first_shape_point_ids is None:
                    continue
                first_point, last_point = (
                    edge_first_shape_point_ids[edge],
                    edge_first_shape_point_ids[edge + 1],
                )
                if (
                    not 0
                    <= first_point
                    <= last_point
                    <= edge_first_shape_point_ids[-1]
                ):
                    raise ValueError("invalid edge_first_shape_point_ids")
                _add_run(shape_point_runs, first_point, last_point)
                kept_shape_points += last_point - first_point
                # A damaged file can count a shape point twice in `edge_first_shape_point_ids`
                if kept_shape_points > INT32_MAX:
                    raise ValueError("invalid edge_first_shape_point_ids")
                new_edge_first_shape_point_ids.append(kept_shape_points)
            new_node_first_edge_ids.append(len(new_edge_destination_node_ids))
    return (
        new_node_first_edge_ids,
        new_edge_destination_node_ids,
        new_edge_first_shape_point_ids,
        node_runs,
        edge_runs,
        shape_point_runs,
    )


def _add_run(runs, first, last):
    # Adds the positions first to last - 1 to `runs`. They extend the last run when
    # they start where it ends.
    if first == last:
        return
    if runs and runs[-1][1] == first:
        runs[-1] = (runs[-1][0], last)
    else:
        runs.append((first, last))
