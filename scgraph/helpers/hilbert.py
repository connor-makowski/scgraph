"""
Order nodes along the cells of Google's S2 library, so that nodes close on the globe get close
ids. Searches then read memory in fewer places, and a range of ids covers a compact area.

Each point is projected onto the face of a cube around the globe that its unit vector points
to (6 faces), the face is mapped to a square with S2's quadratic projection (cells of every
face cover similar areas, within a factor of about 2), and a Hilbert curve runs over each
square, oriented so that the curve of each face ends where the next one starts
(https://s2geometry.io/devguide/s2cell_hierarchy). The key is the S2 cell id of the point's
leaf cell (30 levels, cells of about 1 cm) shifted right by one bit. Unlike a curve over
latitude and longitude, the antimeridian and the poles fall inside faces; the curve's seams
are the edges of the cube. Nodes in the same cell keep their relative order.
"""

from math import cos, isfinite, pi, sin, sqrt

LEVELS = 30
# Recorded in built networks' manifests; changing it means raising VERSION in each
# scgraph/networks/*.py, so that cached builds are built again
NODE_ORDER = {
    "name": "s2_cell",
    "levels": LEVELS,
    "projection": "quadratic",
    "ties": "previous id",
}

_SWAP, _INVERT = 1, 2
# S2's tables: for each orientation, the curve position of child (i, j), and the orientation
# change on entering the child at each position
_IJ_TO_POS = ((0, 1, 3, 2), (0, 3, 1, 2), (2, 3, 1, 0), (2, 1, 3, 0))
_POS_TO_ORIENTATION = (_SWAP, 0, 0, _INVERT | _SWAP)


def _lookup_table() -> list[int]:
    # 4 levels at a time: (4 bits of i, 4 bits of j, orientation) -> (8 bits of position,
    # orientation after them)
    table = [0] * 1024
    for i in range(16):
        for j in range(16):
            for start in range(4):
                orientation, pos = start, 0
                for k in range(3, -1, -1):
                    p = _IJ_TO_POS[orientation][
                        (((i >> k) & 1) << 1) | ((j >> k) & 1)
                    ]
                    pos = (pos << 2) | p
                    orientation ^= _POS_TO_ORIENTATION[p]
                table[(i << 6) | (j << 2) | start] = (pos << 2) | orientation
    return table


_LOOKUP = _lookup_table()


_DEG = pi / 180.0
_SIDE = 1 << LEVELS


def hilbert_key(latitude: float, longitude: float) -> int:
    """Position of a point along the S2 cells, from 0 to 6 * 4^30 - 1."""
    a, b = latitude * _DEG, longitude * _DEG
    c = cos(a)
    x, y, z = c * cos(b), c * sin(b), sin(a)
    # The face of the largest component, ties going to the later axis (as S2)
    ax, ay, az = abs(x), abs(y), abs(z)
    if ax > ay and ax > az:
        face, u, v = (0, y / x, z / x) if x >= 0.0 else (3, z / x, y / x)
    elif ay > az:
        face, u, v = (1, -x / y, z / y) if y >= 0.0 else (4, z / y, -x / y)
    else:
        face, u, v = (2, -x / z, -y / z) if z >= 0.0 else (5, -y / z, -x / z)
    # S2's quadratic projection of the face to the unit square
    s = (
        0.5 * sqrt(1.0 + 3.0 * u)
        if u >= 0.0
        else 1.0 - 0.5 * sqrt(1.0 - 3.0 * u)
    )
    t = (
        0.5 * sqrt(1.0 + 3.0 * v)
        if v >= 0.0
        else 1.0 - 0.5 * sqrt(1.0 - 3.0 * v)
    )
    # s and t are in [0, 1] (the face is chosen so that |u|, |v| <= 1): only 1 is off the grid
    i, j = int(s * _SIDE), int(t * _SIDE)
    if i == _SIDE:
        i -= 1
    if j == _SIDE:
        j -= 1
    # 8 lookups of 4 levels each, written out: this key orders every converted network.
    # i and j have 30 bits: the first lookup reads 2 levels of zeros, which add nothing to the
    # position and leave the orientation unchanged
    L = _LOOKUP
    k = L[(i >> 22 & 0x3C0) | (j >> 26 & 0x3C) | (face & 1)]
    pos = k >> 2
    k = L[(i >> 18 & 0x3C0) | (j >> 22 & 0x3C) | (k & 3)]
    pos = pos << 8 | k >> 2
    k = L[(i >> 14 & 0x3C0) | (j >> 18 & 0x3C) | (k & 3)]
    pos = pos << 8 | k >> 2
    k = L[(i >> 10 & 0x3C0) | (j >> 14 & 0x3C) | (k & 3)]
    pos = pos << 8 | k >> 2
    k = L[(i >> 6 & 0x3C0) | (j >> 10 & 0x3C) | (k & 3)]
    pos = pos << 8 | k >> 2
    k = L[(i >> 2 & 0x3C0) | (j >> 6 & 0x3C) | (k & 3)]
    pos = pos << 8 | k >> 2
    k = L[(i << 2 & 0x3C0) | (j >> 2 & 0x3C) | (k & 3)]
    pos = pos << 8 | k >> 2
    k = L[(i << 6 & 0x3C0) | (j << 2 & 0x3C) | (k & 3)]
    return face << 2 * LEVELS | pos << 8 | k >> 2


def hilbert_order(
    nodes: list[list[float]], blocks: list[list[int]] | None = None
) -> list[int]:
    """
    The ids of `nodes` (a list of [latitude, longitude]) in Hilbert order: `order[new] = old`.

    `blocks` are [start, end) ranges of ids covering every node once (for example the nodes of
    each mode of a multimodal network); each block is ordered on its own and keeps its place.
    """
    if not isfinite(sum(map(sum, nodes))):
        raise ValueError("node coordinates must be finite numbers")
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
