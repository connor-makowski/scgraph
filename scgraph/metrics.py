"""The arrays that a GeoGraph keeps lined up with its edges.

This module is internal.

THE EDGES AND THEIR INDEX

A graph stores its edges by origin, in three arrays (`Graph._csr()`). The edges of
node `u` go to `heads[offsets[u]:offsets[u + 1]]`. The "index" of an edge is its
position in `heads`. An array is "lined up with the edges" when its value number `i`
belongs to the edge of index `i`. The classes of the edges are such an array.

Example, a graph of three nodes with the edges 0 -> 1, 0 -> 2 and 2 -> 0:

    offsets = [0, 2, 2, 3]    heads = [1, 2, 0]    edge_classes = [4, 4, 7]

The edge 2 -> 0 has the index 2, and its class is the row 7.

AFTER AN EDIT

An edit of the graph moves the edges: a new edge of node 0 takes the index 2, and
the edge 2 -> 0 gets the index 3. An edge is known by its two nodes, because a graph
holds one edge at most from a node to another. `match_edges` gives, for each edge of
the edited graph, its index before the edit, or -1 for a new edge.
`take_edge_values` then lines up an array with the edited graph.

Example, after the edge 0 -> 2 is removed and the edge 1 -> 2 is added:

    offsets = [0, 1, 2, 3]    heads = [1, 2, 0]    match_edges gives [0, -1, 2]
    take_edge_values([4, 4, 7], [0, -1, 2], 9) gives [4, 9, 7]
"""

from array import array


def find_edge_index(
    offsets: array | memoryview,
    heads: array | memoryview,
    origin_id: int,
    destination_id: int,
) -> int | None:
    """Return the index of the edge from one node to another.

    Args:
        offsets: The offsets of the edges, one for each node plus one.
        heads: The destination of each edge.
        origin_id: The node that the edge leaves.
        destination_id: The node that the edge goes to.

    Returns:
        The index of the edge, or None when the graph has no such edge or no node
        `origin_id`.
    """
    if not 0 <= origin_id < len(offsets) - 1:
        return None
    for edge_index in range(offsets[origin_id], offsets[origin_id + 1]):
        if heads[edge_index] == destination_id:
            return edge_index
    return None


def match_edges(
    old_offsets: array | memoryview,
    old_heads: array | memoryview,
    offsets: array | memoryview,
    heads: array | memoryview,
) -> array:
    """Return the index that each edge of a graph had before the graph was edited.

    Args:
        old_offsets: The offsets of the edges before the edit.
        old_heads: The destination of each edge before the edit.
        offsets: The offsets of the edges now.
        heads: The destination of each edge now.

    Returns:
        One int64 value for each edge of `heads`: the index in `old_heads` of the
        edge with the same two nodes, or -1 for an edge that was not there.
    """
    old_edge_indexes = array("q")
    old_node_count = len(old_offsets) - 1
    for origin_id in range(len(offsets) - 1):
        first, last = offsets[origin_id], offsets[origin_id + 1]
        if origin_id >= old_node_count:
            old_edge_indexes.extend([-1] * (last - first))
            continue
        old_first, old_last = old_offsets[origin_id], old_offsets[origin_id + 1]
        # Most rows are as they were. Two slices are compared in C, so that an edit
        # of a few rows of a large graph does not read each edge in Python.
        if heads[first:last] == old_heads[old_first:old_last]:
            old_edge_indexes.extend(range(old_first, old_last))
            continue
        old_row = {old_heads[i]: i for i in range(old_first, old_last)}
        old_edge_indexes.extend(
            old_row.get(heads[i], -1) for i in range(first, last)
        )
    return old_edge_indexes


def take_edge_values(
    old_values: array | memoryview,
    old_edge_indexes: array,
    new_edge_value: float,
) -> array:
    """Return an array lined up with the edges of an edited graph.

    Args:
        old_values: An array lined up with the edges before the edit.
        old_edge_indexes: The result of `match_edges`.
        new_edge_value: The value of an edge that was not there.

    Returns:
        A new array of the dtype of `old_values`, with one value for each edge.
    """
    old_values = memoryview(old_values)
    values = array(old_values.format)
    values.frombytes(old_values.cast("B"))
    # The index -1 of a new edge reads this last value
    values.append(new_edge_value)
    return array(values.typecode, map(values.__getitem__, old_edge_indexes))


def reorder_edge_values(
    values: array | memoryview,
    offsets: array | memoryview,
    order: list[int],
) -> array:
    """Return an array lined up with the edges of a graph whose nodes are reordered.

    Args:
        values: An array lined up with the edges.
        offsets: The offsets of the edges, one for each node plus one.
        order: The nodes in their new order: `order[new id] = id`. A node keeps the
            order of its edges, as `Graph._csr(order)` does.

    Returns:
        A new array of the dtype of `values`, with one value for each edge.
    """
    values = memoryview(values)
    ordered = array(values.format)
    for origin_id in order:
        first, last = offsets[origin_id], offsets[origin_id + 1]
        ordered.frombytes(values[first:last].cast("B"))
    return ordered
