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

# The highest value of an int32, the type of the offsets of a network file
INT32_MAX = 2**31 - 1


def select_edges(
    offsets: array | memoryview,
    heads: array | memoryview,
    node_mode_ids: array | memoryview,
    is_node_mode_kept: list[bool],
    shape_offsets: array | memoryview | None = None,
) -> tuple:
    """
    Select the nodes of some node modes of a network file, and the edges between them.

    A "position" is the rank of a node, of an edge or of a shape point in the arrays of
    the file. A "run" (first, last) is the range of positions from first to last - 1.

    Args:
        offsets: The edges of node u are at the positions offsets[u] to
            offsets[u + 1] - 1 (int32).
        heads: The head of each edge, as the position of a node (int32).
        node_mode_ids: The node mode of each node (uint8). The values must not decrease.
        is_node_mode_kept: For each node mode of the file, True if the selection
            keeps it.
        shape_offsets: The shape of edge a is the shape points at the positions
            shape_offsets[a] to shape_offsets[a + 1] - 1 (int32). None for a file
            without edge shapes.

    Returns:
        A tuple (offsets, heads, shape_offsets, node_runs, edge_runs,
        shape_point_runs). The first three are the arrays of the selection, where a
        position counts only the kept nodes, edges and shape points. `shape_offsets`
        is None without edge shapes. The last three are lists of runs: the positions
        in the file of the kept nodes, of the kept edges and of their shape points.

    Raises:
        ValueError: If a value of the arrays cannot be used as a position.
    """
    node_count, edge_count = len(offsets) - 1, len(heads)
    mode_count = len(is_node_mode_kept)
    if node_count < 0 or len(node_mode_ids) != node_count:
        raise ValueError("one node mode per node expected")
    if shape_offsets is not None and len(shape_offsets) != edge_count + 1:
        raise ValueError("invalid shape offsets")

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
        # Step 3 uses the offsets of these nodes as positions in `heads`
        mode_offsets = offsets[first : last + 1]
        if (
            mode_offsets[0] < 0
            or mode_offsets[-1] > edge_count
            or not is_sorted(mode_offsets)
        ):
            raise ValueError("invalid offsets")
        _add_run(node_runs, first, last)
        shift[mode] = kept_nodes - first
        kept_nodes += last - first

    # 3. Visit the edges of each kept node
    new_offsets, new_heads = array("i", [0]), array("i")
    new_shape_offsets = None if shape_offsets is None else array("i", [0])
    edge_runs, shape_point_runs = [], []
    kept_shape_points = 0
    for first, last in node_runs:
        for node in range(first, last):
            for edge in range(offsets[node], offsets[node + 1]):
                head = heads[edge]
                if not 0 <= head < node_count:
                    raise ValueError("edge to a missing node")
                mode = node_mode_ids[head]
                if not is_node_mode_kept[mode]:
                    continue
                new_heads.append(head + shift[mode])
                _add_run(edge_runs, edge, edge + 1)
                if shape_offsets is None:
                    continue
                first_point, last_point = (
                    shape_offsets[edge],
                    shape_offsets[edge + 1],
                )
                if not 0 <= first_point <= last_point <= shape_offsets[-1]:
                    raise ValueError("invalid shape offsets")
                _add_run(shape_point_runs, first_point, last_point)
                kept_shape_points += last_point - first_point
                # The offsets of a damaged file can count a shape point twice
                if kept_shape_points > INT32_MAX:
                    raise ValueError("invalid shape offsets")
                new_shape_offsets.append(kept_shape_points)
            new_offsets.append(len(new_heads))
    return (
        new_offsets,
        new_heads,
        new_shape_offsets,
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
