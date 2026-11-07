"""
Order nodes along a Hilbert curve over latitude and longitude, so that nodes close on the
globe get close ids. Searches then read memory in fewer places, and a range of ids covers a
compact area.

The curve has order 16: longitude is scaled to x in [0, 2^16) and latitude to y in [0, 2^16),
cells of about 600 m by 300 m at the equator. Nodes in the same cell keep their relative order.
"""

CURVE_ORDER = 16
# Recorded in built networks' manifests; changing it means raising PIPELINE_VERSION in each
# scgraph/pipelines/*.py, so that cached builds are built again
NODE_ORDER = {
    "name": "hilbert",
    "curve_order": CURVE_ORDER,
    "x": "longitude",
    "y": "latitude",
    "ties": "previous id",
}


def hilbert_key(latitude: float, longitude: float) -> int:
    """Position of a point on the Hilbert curve, from 0 to 4^16 - 1."""
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


def hilbert_order(
    nodes: list[list[float]], modes: list[int] | None = None
) -> list[int]:
    """
    The ids of `nodes` (a list of [latitude, longitude]) in Hilbert order: `order[new] = old`.

    With `modes` (the mode of each node, as numbers), nodes are ordered by mode first, so
    that the nodes of each mode stay together, then along the curve.
    """
    if modes is None:
        return sorted(range(len(nodes)), key=lambda i: hilbert_key(*nodes[i]))
    # One integer per node, the mode above the key (keys are below 4^CURVE_ORDER)
    return sorted(
        range(len(nodes)),
        key=lambda i: modes[i] << 2 * CURVE_ORDER | hilbert_key(*nodes[i]),
    )
