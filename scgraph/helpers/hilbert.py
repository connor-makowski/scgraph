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


def hilbert_key(latitude: float, longitude: float) -> int:
    """Return the position of a point on the Hilbert curve, from 0 to 4^16 - 1."""
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
    return key


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
    if node_mode_ids is None:
        return sorted(range(len(points)), key=lambda i: hilbert_key(*points[i]))
    # One integer per node, the node mode above the key (keys are below 4^CURVE_ORDER)
    return sorted(
        range(len(points)),
        key=lambda i: node_mode_ids[i] << 2 * CURVE_ORDER
        | hilbert_key(*points[i]),
    )
