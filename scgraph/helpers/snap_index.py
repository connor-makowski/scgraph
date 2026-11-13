"""
Pure-Python version of the C++ `SnapIndex`, with the same answers. The algorithm is
described in `scgraph/cpp/src/snap_index.hpp`.

Same as in C++: the leaves, the tree, the boxes of unit vectors, the quadrant rules, and
the leaves-per-query limit that refuses scattered nodes (NodeOrderError). The boxes are
kept in double here, not rounded to float.

Different: the search works in double throughout and compares distances exactly, so
there is no float selection, no margin and no candidate to confirm. The nearest-node
search has no first descent: it runs step 4 of the header from the root. Each box also
keeps the lowest and the highest latitude and longitude of its nodes. The per-quadrant
search decides from these four values which quadrants a box may hold. The C++ index
decides it from the unit vectors. The Python index counts levels from the leaves: level 0
is a leaf here, while in C++ level 0 holds the parents of the leaves.
"""

from array import array
from collections.abc import Sequence
from math import cos, inf, isfinite, radians, sin
from operator import mul

# Same values as the C++ index (snap_index.hpp, snap_index.cpp)
LEAF = 32
FANOUT = 8
MAX_LEAVES_PER_QUERY = 16.0
SORT_HINT = (
    "Sort them along a Hilbert curve and map the answers back: "
    "order = scgraph.helpers.hilbert.hilbert_order(nodes); "
    "index = SnapIndex([nodes[i] for i in order]); "
    "node = order[index.closest_idx(point)]"
)
# Quadrant t of this tuple is bit 1 << t of the masks below
QUADRANTS = ("ne", "nw", "se", "sw")


def _wrap180(d: float) -> float:
    if d > 180.0:
        return d - 360.0
    if d < -180.0:
        return d + 360.0
    return d


def _unit(latitude: float, longitude: float) -> tuple[float, float, float]:
    # Longitudes -180 and 180 stay distinct, as in the C++ index (see there)
    a, b = radians(latitude), radians(longitude)
    c = cos(a)
    return c * cos(b), c * sin(b), sin(a)


class NodeOrderError(ValueError):
    """
    The nodes are too scattered for the snapping index: sort them first, as the
    message says.
    """


def _unit_area(box, c: int) -> float:
    # Area of unit-vector box c: the product of its two largest extents, as in C++
    e = sorted(
        (box[1][c] - box[0][c], box[3][c] - box[2][c], box[5][c] - box[4][c])
    )
    return e[2] * e[1]


def _box_quadrants(box, c: int, qlat: float, qlon: float, mask: int) -> int:
    # Quadrant bits that a latitude/longitude box may hold: 1 ne, 2 nw, 4 se, 8 sw, the
    # bits of the C++ index. Slots 6, 7, 8, 9 of a box are min lat, max lat, min lon,
    # max lon; they stay literals, not names, as this runs for every box a search visits
    if box[7][c] < qlat:
        mask &= 4 | 8
    if box[6][c] > qlat:
        mask &= 1 | 2
    width = box[9][c] - box[8][c]
    if width < 180.0:
        start = _wrap180(box[8][c] - qlon)
        if start > 0.0 and start + width < 180.0:
            mask &= 1 | 4
        elif start > -180.0 and start + width < 0.0:
            mask &= 2 | 8
    return mask


class SnapIndex:
    """
    Nearest node of a point on the sphere (exact, ties to the lowest id).

    - `SnapIndex(points)`: `points` is a sequence of [latitude, longitude] in degrees
    - `SnapIndex.from_arrays(latitudes, longitudes)`: the same, from two arrays of the same
      dtype, float64 degrees, which the index keeps (leave them unchanged), or int32 units
      of 1e-7 degree as network files may store them, decoded here into a float64 copy
      (the C++ index reads them in place)
    - The nodes must keep nearby nodes together, as a Hilbert curve does: a scattered order
      raises NodeOrderError, whose message says how to sort and map the answers back
    - `closest_idx(point)`: id of the point nearest to `point`
    - `closest_idx_per_quadrant(point)`: id of the nearest point in each quadrant around
      `point`, as a dict with the keys 'ne', 'nw', 'se', 'sw' (None if the quadrant is empty).
      A point is north if its latitude is >= the query's, south if <=, east if it lies within
      180 degrees of longitude eastwards, west likewise (as GeoKDTree)
    """

    @classmethod
    def from_arrays(
        cls, latitudes: array | memoryview, longitudes: array | memoryview
    ) -> "SnapIndex":
        dtypes = {
            memoryview(values).format for values in (latitudes, longitudes)
        }
        if dtypes not in ({"d"}, {"i"}):
            raise TypeError(
                "latitudes and longitudes must both be float64 or both int32"
            )
        if dtypes == {"i"}:
            # units / 1e7, the network file's division, in a loop that runs in C
            latitudes, longitudes = (
                array("d", map((1e7).__rtruediv__, values))
                for values in (latitudes, longitudes)
            )
        if len(latitudes) != len(longitudes):
            raise ValueError(
                "latitudes and longitudes must have the same length"
            )
        index = cls.__new__(cls)
        index._build(latitudes, longitudes)
        return index

    def __init__(self, points):
        lat = array("d", [p[0] for p in points])
        self._build(lat, array("d", [p[1] for p in points]))

    def _build(self, lat, lon):
        # Columns of float64 arrays, not lists of floats: 8 bytes per value instead of 32,
        # and built by loops that run in C
        n = len(lat)
        if n == 0:
            raise ValueError("a snapping index needs at least one node")
        # A NaN would leave its leaf out of every search (min and max skip it or return it);
        # one NaN or infinity makes the sum non-finite
        if not isfinite(sum(lat) + sum(lon)):
            raise ValueError("node coordinates must be finite numbers")
        self.n = n
        self.lat, self.lon = lat, lon
        # The unit vectors, as _unit computes them
        a, b = array("d", map(radians, lat)), array("d", map(radians, lon))
        c = array("d", map(cos, a))
        self.x = array("d", map(mul, c, map(cos, b)))
        self.y = array("d", map(mul, c, map(sin, b)))
        self.z = array("d", map(sin, a))
        # Level 0: the boxes of the leaves (min x, max x, min y, max y, min z, max z,
        # min lat, max lat, min lon, max lon); each level above groups FANOUT boxes
        nleaves = (n + LEAF - 1) // LEAF
        columns = (self.x, self.y, self.z, self.lat, self.lon)
        box = [[0.0] * nleaves for _ in range(10)]
        for j in range(nleaves):
            s, e = j * LEAF, min(n, j * LEAF + LEAF)
            for t, values in enumerate(columns):
                part = values[s:e]
                box[2 * t][j], box[2 * t + 1][j] = min(part), max(part)
        # Leaves per query, as in C++: the leaves' box areas over the area of the box around
        # them all, summed in the same order (a plain loop, not the compensated sum())
        leaf_areas = 0.0
        for j in range(nleaves):
            leaf_areas += _unit_area(box, j)
        root = [[min(box[t]) if t % 2 == 0 else max(box[t])] for t in range(6)]
        total = _unit_area(root, 0)
        per_query = leaf_areas / total if total > 0.0 else 0.0
        if per_query > MAX_LEAVES_PER_QUERY:
            raise NodeOrderError(
                "nodes scattered in the order given: a query would scan about "
                f"{int(per_query + 0.5)} blocks of 32 nodes "
                f"(at most {int(MAX_LEAVES_PER_QUERY)}). {SORT_HINT}"
            )
        self.levels = [(nleaves, box)]
        count = nleaves
        while count > 1:
            parents = (count + FANOUT - 1) // FANOUT
            lower = self.levels[-1][1]
            box = [[0.0] * parents for _ in range(10)]
            for p in range(parents):
                s, e = p * FANOUT, min(count, p * FANOUT + FANOUT)
                for t in range(10):
                    part = lower[t][s:e]
                    box[t][p] = min(part) if t % 2 == 0 else max(part)
            self.levels.append((parents, box))
            count = parents

    @staticmethod
    def _bound(box, c: int, qx: float, qy: float, qz: float) -> float:
        # Squared chord from the query to the nearest point of box c (0 if inside)
        dx = box[0][c] - qx
        if dx < 0.0:
            dx = qx - box[1][c]
            if dx < 0.0:
                dx = 0.0
        dy = box[2][c] - qy
        if dy < 0.0:
            dy = qy - box[3][c]
            if dy < 0.0:
                dy = 0.0
        dz = box[4][c] - qz
        if dz < 0.0:
            dz = qz - box[5][c]
            if dz < 0.0:
                dz = 0.0
        return dx * dx + dy * dy + dz * dz

    def closest_idx(self, point: Sequence[float]) -> int:
        qx, qy, qz = _unit(point[0], point[1])
        xs, ys, zs, n = self.x, self.y, self.z, self.n
        levels, bound = self.levels, self._bound
        best, best_p = inf, -1
        # (bound, level, index): level 0 is a leaf
        stack = [(0.0, len(levels), 0)]
        while stack:
            lb, level, c = stack.pop()
            if lb > best:
                continue
            if level == 0:
                for p in range(c * LEAF, min(n, c * LEAF + LEAF)):
                    dx, dy, dz = qx - xs[p], qy - ys[p], qz - zs[p]
                    d = dx * dx + dy * dy + dz * dz
                    if d < best or (d == best and p < best_p):
                        best, best_p = d, p
                continue
            count, box = levels[level - 1]
            children = []
            for k in range(c * FANOUT, min(count, c * FANOUT + FANOUT)):
                d = bound(box, k, qx, qy, qz)
                if d <= best:
                    children.append((d, level - 1, k))
            children.sort(reverse=True)
            stack.extend(children)
        return best_p

    def closest_idx_per_quadrant(
        self, point: Sequence[float]
    ) -> dict[str, int | None]:
        qlat, qlon = float(point[0]), float(point[1])
        qx, qy, qz = _unit(qlat, qlon)
        xs, ys, zs, n = self.x, self.y, self.z, self.n
        lats, lons = self.lat, self.lon
        levels, bound = self.levels, self._bound
        best = [inf, inf, inf, inf]
        best_p = [-1, -1, -1, -1]

        def reach(mask: int) -> float:
            # The farthest distance still useful to one of the quadrants of mask
            return max(
                (best[t] for t in range(4) if mask & (1 << t)), default=0.0
            )

        stack = [(0.0, len(levels), 0, 15)]
        while stack:
            lb, level, c, mask = stack.pop()
            if lb > reach(mask):
                continue
            if level == 0:
                for p in range(c * LEAF, min(n, c * LEAF + LEAF)):
                    dx, dy, dz = qx - xs[p], qy - ys[p], qz - zs[p]
                    d = dx * dx + dy * dy + dz * dz
                    if d > reach(mask):
                        continue
                    la = lats[p]
                    dl = _wrap180(lons[p] - qlon)
                    north, south = la >= qlat, la <= qlat
                    east = dl >= 0.0 or dl == -180.0
                    west = dl <= 0.0 or dl == 180.0
                    for t, inside in enumerate(
                        (
                            north and east,
                            north and west,
                            south and east,
                            south and west,
                        )
                    ):
                        if not inside or not mask & (1 << t):
                            continue
                        if d < best[t] or (d == best[t] and p < best_p[t]):
                            best[t], best_p[t] = d, p
                continue
            count, box = levels[level - 1]
            children = []
            for k in range(c * FANOUT, min(count, c * FANOUT + FANOUT)):
                mk = _box_quadrants(box, k, qlat, qlon, mask)
                if not mk:
                    continue
                d = bound(box, k, qx, qy, qz)
                if d <= reach(mk):
                    children.append((d, level - 1, k, mk))
            children.sort(reverse=True)
            stack.extend(children)
        return {
            name: (p if p >= 0 else None) for name, p in zip(QUADRANTS, best_p)
        }
