"""
Pure-Python version of the C++ `SnapIndex` (`scgraph/cpp/src/snap_index.cpp`, where the
algorithm is described), with the same answers.
"""

from math import cos, inf, radians, sin

from scgraph.helpers.hilbert import hilbert_key

LEAF = 32
FANOUT = 8
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


def _box_quadrants(box, c: int, qlat: float, qlon: float, mask: int) -> int:
    # Quadrant bits a latitude/longitude box may hold: 1 ne, 2 nw, 4 se, 8 sw
    if box[7][c] < qlat:
        mask &= 12
    if box[6][c] > qlat:
        mask &= 3
    width = box[9][c] - box[8][c]
    if width < 180.0:
        start = _wrap180(box[8][c] - qlon)
        if start > 0.0 and start + width < 180.0:
            mask &= 5
        elif start > -180.0 and start + width < 0.0:
            mask &= 10
    return mask


class SnapIndex:
    """
    Nearest node of a point on the sphere (exact, ties to the lowest id).

    - `SnapIndex(points)`: `points` is a sequence of [latitude, longitude] in degrees
    - `SnapIndex.from_arrays(latitudes, longitudes)`: the same, from two float64 arrays of
      degrees
    - `closest_idx(point)`: id of the point nearest to `point`
    - `closest_idx_per_quadrant(point)`: id of the nearest point in each quadrant around
      `point`, as a dict with the keys 'ne', 'nw', 'se', 'sw' (None if the quadrant is empty).
      A point is north if its latitude is >= the query's, south if <=, east if it lies within
      180 degrees of longitude eastwards, west likewise (as GeoKDTree)
    """

    @classmethod
    def from_arrays(cls, latitudes, longitudes) -> "SnapIndex":
        return cls(list(zip(latitudes, longitudes, strict=True)))

    def __init__(self, points):
        lat = [float(p[0]) for p in points]
        lon = [float(p[1]) for p in points]
        n = len(lat)
        if n == 0:
            raise ValueError("a snapping index needs at least one node")
        self.n = n
        # Keep the network's order if it is already sorted along a Hilbert curve, in runs of
        # 64 nodes or more on average, as judged on about 2,048 evenly spaced pairs of
        # neighbours (all of them up to 2,049 nodes); otherwise sort a copy along one (as
        # the C++ index)
        pairs = range(1, n, max(1, (n - 1) // 2048))
        descents = sum(
            hilbert_key(lat[i], lon[i]) < hilbert_key(lat[i - 1], lon[i - 1])
            for i in pairs
        )
        ids = list(range(n))
        if 64 * descents > len(pairs):
            keys = [hilbert_key(la, lo) for la, lo in zip(lat, lon)]
            ids.sort(key=lambda i: (keys[i], i))
        self.id = ids
        self.lat = [lat[i] for i in ids]
        self.lon = [lon[i] for i in ids]
        units = [_unit(la, lo) for la, lo in zip(self.lat, self.lon)]
        self.x = [u[0] for u in units]
        self.y = [u[1] for u in units]
        self.z = [u[2] for u in units]
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

    def closest_idx(self, point) -> int:
        qx, qy, qz = _unit(point[0], point[1])
        X, Y, Z, ids, n = self.x, self.y, self.z, self.id, self.n
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
                    dx, dy, dz = qx - X[p], qy - Y[p], qz - Z[p]
                    d = dx * dx + dy * dy + dz * dz
                    if d < best or (d == best and ids[p] < ids[best_p]):
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
        return ids[best_p]

    def closest_idx_per_quadrant(self, point) -> dict[str, int | None]:
        qlat, qlon = float(point[0]), float(point[1])
        qx, qy, qz = _unit(qlat, qlon)
        X, Y, Z, ids, n = self.x, self.y, self.z, self.id, self.n
        LAT, LON = self.lat, self.lon
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
                    dx, dy, dz = qx - X[p], qy - Y[p], qz - Z[p]
                    d = dx * dx + dy * dy + dz * dz
                    if d > reach(mask):
                        continue
                    la = LAT[p]
                    dl = _wrap180(LON[p] - qlon)
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
                        if d < best[t] or (
                            d == best[t] and ids[p] < ids[best_p[t]]
                        ):
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
            name: (ids[p] if p >= 0 else None)
            for name, p in zip(QUADRANTS, best_p)
        }
