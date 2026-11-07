"""Land and water as a one-bit raster, and the cheapest path over water (C++ in
`scgraph/cpp/src/landmask.hpp`, with the same answers as its twin `water_cells`).
"""

import json
import math
from array import array
from bisect import bisect_left
from heapq import heappop, heappush

from scgraph.utils import haversine

# Steps (row, column) to the 8 neighbours of a cell, in the order both kernels take them
STEPS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


def _land(bits, cell):
    return bits[cell >> 3] >> (cell & 7) & 1


def _has(targets, cell):
    i = bisect_left(targets, cell)
    return i < len(targets) and targets[i] == cell


def water_cells(
    bits, width, height, wrap, start, targets, max_km, east, diagonal, north
):
    """`(km, cells)` from cell `start` to the nearest cell of `targets` (sorted) over
    water cells (bit 0) and targets, or None beyond `max_km`. Steps cost `east[row]`,
    `north`, `diagonal[row]` (to row + 1). Ties: the lowest (km, cell) first."""
    km, before, heap = {start: 0.0}, {start: -1}, [(0.0, start)]
    while heap:
        d, cell = heappop(heap)
        if d > km[cell]:
            continue
        if _has(targets, cell):
            path = [cell]
            while before[path[-1]] >= 0:
                path.append(before[path[-1]])
            return d, path[::-1]
        row, column = divmod(cell, width)
        for dr, dc in STEPS:
            r, c = row + dr, column + dc
            if not 0 <= r < height or not (wrap or 0 <= c < width):
                continue
            near = r * width + c % width
            low = min(row, r)
            step = diagonal[low] if dr and dc else east[row] if dc else north
            if d + step > max_km or d + step >= km.get(near, math.inf):
                continue
            if _land(bits, near) and not _has(targets, near):
                continue  # land
            km[near], before[near] = d + step, cell
            heappush(heap, (d + step, near))
    return None


try:
    from scgraph.cpp import water_cells as _water_cells
except ImportError:
    _water_cells = water_cells


class LandMask:
    """Land (bit 1) and water (bit 0) on cells of 1/cells_per_degree degree: cell = row *
    width + column, from the south-west corner. A cell is land when its centre is; outside
    the raster is land. Columns wrap when the raster spans every longitude."""

    def __init__(self, bits, south, west, height, width, cells_per_degree):
        self.bits, self.south, self.west = bits, south, west
        self.height, self.width, self.size = height, width, 1 / cells_per_degree
        self.wrap = width == 360 * cells_per_degree
        lats = [self.centre(row * width)[0] for row in range(height)]
        self.north_km = haversine([0, 0], [self.size, 0])
        steps = [(a, a) for a in lats], zip(lats, lats[1:])
        self.east_km, self.diagonal_km = (
            array("d", (haversine([a, 0], [b, self.size]) for a, b in pairs))
            for pairs in steps
        )

    @staticmethod
    def from_natural_earth(
        land, lakes, rivers, cells_per_degree=240, bbox=None
    ):
        """Natural Earth 10m `land`, `lakes` and `rivers` (GeoJSON files): land polygons
        filled even-odd, then lakes removed one by one (the Great Lakes are also holes of
        the land), then river centrelines drawn as water. `bbox`: (south, west, north,
        east), in degrees within the world."""
        k = cells_per_degree
        bbox = bbox or (-90, -180, 90, 180)
        south, west, north, east = (round(v * k) for v in bbox)
        height, width = north - south, (east - west + 7) // 8 * 8  # whole bytes
        bits = bytearray(height * width // 8)

        def xy(ring):  # cell centres at integers
            return [(x * k - west - 0.5, y * k - south - 0.5) for x, y in ring]

        for burn, polygon in [(1, p) for p in _parts(land)] + [
            (0, p) for p in _parts(lakes)
        ]:
            cross = {}  # row -> x where the polygon's edges cross its centre
            for ring in map(xy, polygon):
                for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
                    top = min(height, math.ceil(max(y1, y2)))
                    for i in range(max(0, math.ceil(min(y1, y2))), top):
                        x = x1 + (i - y1) * (x2 - x1) / (y2 - y1)
                        cross.setdefault(i, []).append(min(width, max(0, x)))
            for i, xs in cross.items():
                c = sorted(math.ceil(x) for x in xs)
                lo, hi = c[0] >> 3, (c[-1] + 7) >> 3  # the bytes spans touch
                at = slice(i * width // 8 + lo, i * width // 8 + hi)
                v = int.from_bytes(bits[at], "little")
                span = sum((1 << b) - (1 << a) for a, b in zip(c[::2], c[1::2]))
                v = v | span >> 8 * lo if burn else v & ~(span >> 8 * lo)
                bits[at] = v.to_bytes(hi - lo, "little")
        for line in map(xy, _parts(rivers)):
            for (x1, y1), (x2, y2) in zip(line, line[1:]):
                n = math.ceil(max(abs(x2 - x1), abs(y2 - y1))) + 1
                for t in range(n + 1):
                    x = round(x1 + (x2 - x1) * t / n)
                    y = round(y1 + (y2 - y1) * t / n)
                    if 0 <= x < width and 0 <= y < height:
                        bits[(y * width + x) >> 3] &= ~(1 << (x & 7))
        return LandMask(bits, south / k, west / k, height, width, k)

    def cell(self, lat, lon):
        """The cell of a point, None outside the raster."""
        row = math.floor((lat - self.south) / self.size)
        column = math.floor((lon - self.west) / self.size)
        if 0 <= row < self.height and 0 <= column < self.width:
            return row * self.width + column
        return None

    def centre(self, cell):
        row, column = divmod(cell, self.width)
        s = self.size
        return [self.south + (row + 0.5) * s, self.west + (column + 0.5) * s]

    def on_land(self, lat, lon):
        cell = self.cell(lat, lon)
        return cell is None or bool(_land(self.bits, cell))

    def water_path(self, start, targets, max_km, start_on_land_km=6):
        """`(km, cell centres)` of the cheapest water path from `start` to a cell of
        `targets` (an array('q'), sorted), or None beyond `max_km`, from the water cell
        nearest to `start` within `start_on_land_km` (`km` counts the leg to it).
        """
        cell = self.cell(*start)
        if cell is None:
            return None
        row, column = divmod(cell, self.width)
        reach = 1 + int(start_on_land_km / self.east_km[row])  # east <= north
        first = min(
            (
                (haversine(start, self.centre(c)), c)
                for r in range(row - reach, row + reach + 1)
                for j in range(column - reach, column + reach + 1)
                if 0 <= r < self.height and (self.wrap or 0 <= j < self.width)
                for c in [r * self.width + j % self.width]
                if not _land(self.bits, c) or _has(targets, c)
            ),
            default=(math.inf, None),
        )
        if first[0] > min(start_on_land_km, max_km):
            return None
        found = _water_cells(
            self.bits, self.width, self.height, self.wrap, first[1], targets,
            max_km - first[0], self.east_km, self.diagonal_km, self.north_km,
        )  # fmt: skip
        if found is None:
            return None
        return first[0] + found[0], [self.centre(c) for c in found[1]]


def _parts(filename):
    """The polygons or lines of a GeoJSON file."""
    with open(filename, encoding="utf-8") as file:
        for feature in json.load(file)["features"]:
            g = feature["geometry"]
            parts = g["coordinates"]
            yield from parts if "Multi" in g["type"] else [parts]
