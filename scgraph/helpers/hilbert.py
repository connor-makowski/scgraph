"""
Order nodes along a Hilbert curve over latitude and longitude, so that nodes close on the
globe get close ids. Searches then read memory in fewer places, and a range of ids covers a
compact area.

The curve has order 16: longitude is scaled to x in [0, 2^16) and latitude to y in [0, 2^16),
cells of about 600 m by 300 m at the equator. Nodes in the same cell keep their relative order.
"""

__all__ = ["get_hilbert_order"]

CURVE_ORDER = 16
# Recorded in network files' headers; changing it means raising PIPELINE_VERSION in each
# scgraph/pipelines/*.py, so that cached builds are built again
NODE_ORDER = "hilbert"


def hilbert_key(
    latitude: float, longitude: float, node_mode_id: int = 0
) -> int:
    """Return the key that orders the nodes of a network file: the node mode id,
    then the position of the point on the Hilbert curve.

    The position is from 0 to 4^16 - 1, so the node mode id goes above it in the
    same integer. Example: the node mode id 1 and the position 5 give
    `1 << 32 | 5`, which is 4294967301. With the default node mode id 0, the key is
    the position.
    """
    side = 1 << CURVE_ORDER
    x = min(side - 1, max(0, int((longitude + 180.0) / 360.0 * side)))
    y = min(side - 1, max(0, int((latitude + 90.0) / 180.0 * side)))
    key, s = 0, side >> 1
    while s:
        rx = 1 if x & s else 0
        ry = 1 if y & s else 0
        key += s * s * ((3 * rx) ^ ry)
        if not ry:
            if rx:
                x, y = s - 1 - x, s - 1 - y
            x, y = y, x
        s >>= 1
    return node_mode_id << 2 * CURVE_ORDER | key


def get_hilbert_order(
    points: list[list[float]], node_mode_ids: list[int] | None = None
) -> list[int]:
    """Return the ids of the nodes in Hilbert order.

    Args:
        points: The point of each node, as `[latitude, longitude]`.
        node_mode_ids: The node mode of each node, as a number. The nodes are then
            ordered by node mode first, and along the curve inside each node mode. The
            nodes of one node mode stay together.

    Returns:
        `order`, where `order[new_id]` is the old id of the node. Nodes with the
        same point keep their order: the nodes of a junction stay together, the
        node of the junction first
        (`scgraph.turn_restrictions.find_nodes_of_junction`).
    """
    # When every node has the node mode id 0, the key needs no node mode id
    if node_mode_ids is None or not any(node_mode_ids):
        return sorted(range(len(points)), key=lambda i: hilbert_key(*points[i]))
    return sorted(
        range(len(points)),
        key=lambda i: hilbert_key(*points[i], node_mode_ids[i]),
    )
