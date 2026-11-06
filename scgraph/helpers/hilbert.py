"""
Order nodes along a Hilbert curve over latitude and longitude, so that nodes close on the
globe get close ids. Searches then read memory in fewer places, and a range of ids covers a
compact area.

The curve has order 16: longitude is scaled to x in [0, 2^16) and latitude to y in [0, 2^16),
cells of about 600 m by 300 m at the equator. Nodes in the same cell keep their relative order.
"""

CURVE_ORDER = 16
# Recorded in built networks' manifests; changing it means raising VERSION in each
# scgraph/networks/*.py, so that cached builds are built again
NODE_ORDER = {
    "name": "hilbert",
    "curve_order": CURVE_ORDER,
    "x": "longitude",
    "y": "latitude",
    "ties": "previous id",
}


# scgraph/cpp/src/snap_index.cpp has a C++ copy of this function, so that the C++ index
# checks and sorts nodes without Python objects. Change both together
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
    nodes: list[list[float]], blocks: list[list[int]] | None = None
) -> list[int]:
    """
    The ids of `nodes` (a list of [latitude, longitude]) in Hilbert order: `order[new] = old`.

    `blocks` are [start, end) ranges of ids covering every node once (for example the nodes of
    each mode of a multimodal network); each block is ordered on its own and keeps its place.
    """
    ranges = sorted(blocks) if blocks else [[0, len(nodes)]]
    order = []
    for start, end in ranges:
        if start != len(order) or end < start:
            raise ValueError(
                "blocks must cover every node once, as [start, end) ranges"
            )
        order.extend(
            sorted(range(start, end), key=lambda i: hilbert_key(*nodes[i]))
        )
    if len(order) != len(nodes):
        raise ValueError(
            "blocks must cover every node once, as [start, end) ranges"
        )
    return order
