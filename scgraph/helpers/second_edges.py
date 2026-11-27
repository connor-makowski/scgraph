"""
Pure-Python version of the C++ `remove_second_edge_shapes` and `find_pair_shape`, with
the same results and the same errors. This module is internal.
`scgraph/cpp/src/second_edges.hpp` explains the second edges of a network file and the
two functions. Read it first.

Same as in C++: the steps, the order of the edges and the messages of the errors.
Different: a shape is compared to the shape of its pair edge with two slices, in C, not
point by point.
"""

from array import array

# The message of the error of a damaged second edge, the same in both versions
SECOND_EDGE_ERROR = (
    "invalid edge_has_reversed_shape: a second edge has shape points, or no pair "
    "edge with shape points"
)


def find_pair_shape(
    node_first_edge_ids: array | memoryview,
    edge_destination_node_ids: array | memoryview,
    edge_first_shape_point_ids: array | memoryview,
    origin_id: int,
    edge_id: int,
) -> tuple[int, int]:
    """
    Return the range (first, last) of the shape points of the pair edge of a second
    edge. The second edge reads the points first to last - 1 backwards.

    Args:
        node_first_edge_ids: The edges of node u are the edges node_first_edge_ids[u]
            to node_first_edge_ids[u + 1] - 1.
        edge_destination_node_ids: The destination id of each edge.
        edge_first_shape_point_ids: The shape of edge e is the shape points
            edge_first_shape_point_ids[e] to edge_first_shape_point_ids[e + 1] - 1.
            The caller has checked its length.
        origin_id: The origin id of the second edge.
        edge_id: The id of the second edge, an edge of `origin_id`.

    Raises:
        ValueError: The second edge has shape points of its own, or no pair edge with
            shape points.
    """
    starts, destination_id = (
        edge_first_shape_point_ids,
        edge_destination_node_ids[edge_id],
    )
    node_count = len(node_first_edge_ids) - 1
    if (
        starts[edge_id] != starts[edge_id + 1]
        or not 0 <= destination_id < node_count
    ):
        raise ValueError(SECOND_EDGE_ERROR)
    first_edge, last_edge = node_first_edge_ids[
        destination_id : destination_id + 2
    ]
    if not 0 <= first_edge <= last_edge <= len(edge_destination_node_ids):
        raise ValueError("invalid node_first_edge_ids")
    for pair_edge_id in range(first_edge, last_edge):
        if edge_destination_node_ids[pair_edge_id] != origin_id:
            continue
        first, last = starts[pair_edge_id], starts[pair_edge_id + 1]
        if first >= last:
            break
        return first, last
    raise ValueError(SECOND_EDGE_ERROR)


def remove_second_edge_shapes(
    node_first_edge_ids: array | memoryview,
    edge_destination_node_ids: array | memoryview,
    edge_first_shape_point_ids: array | memoryview,
    shape_points: array | memoryview,
) -> tuple[array, array, array]:
    """
    Return the arrays of the shapes as a network file stores them: without the shape
    points of the second edges.

    Args:
        node_first_edge_ids: The edges of node u are the edges node_first_edge_ids[u]
            to node_first_edge_ids[u + 1] - 1.
        edge_destination_node_ids: The destination id of each edge.
        edge_first_shape_point_ids: The shape of edge e is the shape points
            edge_first_shape_point_ids[e] to edge_first_shape_point_ids[e + 1] - 1.
        shape_points: The latitude, then the longitude, of each shape point: float64
            degrees, or int32 units of 1e-7 degree. Each edge holds its own shape.
            `network_file.write` checks these arrays first, as a read checks a file.

    Returns:
        `(edge_first_shape_point_ids, edge_has_reversed_shape, shape_points)`.
        `edge_has_reversed_shape` holds 1 for a second edge and 0 for any other edge.
        The new `shape_points` has the dtype of `shape_points`.
    """
    starts, points = edge_first_shape_point_ids, memoryview(shape_points)
    has_reversed_shape = array("B", bytes(len(edge_destination_node_ids)))
    kept_starts, kept_points = array("i", [0]), array(points.format)

    # Step 1: whether the edge `edge_id` from `origin_id` is a second edge
    def is_second_edge(origin_id, edge_id):
        destination_id = edge_destination_node_ids[edge_id]
        first, last = starts[edge_id], starts[edge_id + 1]
        if destination_id >= origin_id or first == last:
            return False
        first_edge, last_edge = node_first_edge_ids[
            destination_id : destination_id + 2
        ]
        pair_edge_ids = [
            e
            for e in range(first_edge, last_edge)
            if edge_destination_node_ids[e] == origin_id
        ]
        if len(pair_edge_ids) != 1:
            return False
        pair_first, pair_last = starts[pair_edge_ids[0] : pair_edge_ids[0] + 2]
        shape = points[2 * first : 2 * last]
        pair_shape = points[2 * pair_first : 2 * pair_last]
        # The latitudes, then the longitudes, of the pair shape read backwards
        return (
            pair_last - pair_first == last - first
            and shape[0::2] == pair_shape[-2::-2]
            and shape[1::2] == pair_shape[-1::-2]
        )

    # Step 2: the flag, the kept shape points and the first shape point ids
    for origin_id in range(len(node_first_edge_ids) - 1):
        for edge_id in range(*node_first_edge_ids[origin_id : origin_id + 2]):
            if is_second_edge(origin_id, edge_id):
                has_reversed_shape[edge_id] = 1
            else:
                first, last = starts[edge_id], starts[edge_id + 1]
                kept_points.frombytes(points[2 * first : 2 * last].cast("B"))
            kept_starts.append(len(kept_points) // 2)
    return kept_starts, has_reversed_shape, kept_points
