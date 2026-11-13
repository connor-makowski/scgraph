"""Land and water as a one-bit raster, and the cheapest path over water. Its kernel,
`water_path_cells`, is the C++ one (`scgraph/cpp/src/pipelines/landmask.hpp`) when built;
the pure-Python twin, with the same answers, stays in `python`."""

import json
import math
from array import array
from bisect import bisect_left
from collections.abc import Sequence
from heapq import heappop, heappush
from types import SimpleNamespace

from scgraph.utils import haversine

# 8-connected Moore neighborhood offsets (row, column) in search order
NEIGHBOR_OFFSETS = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
)


def _is_land(bits, cell):
    return bits[cell >> 3] >> (cell & 7) & 1


def _contains_cell(targets, cell):
    i = bisect_left(targets, cell)
    return i < len(targets) and targets[i] == cell


# Cells a water-path search may hold: about 2x the most a World Port Index port that
# finds a sea node needs (2,726,042); beyond, a search near the poles grows without bound
# (McMurdo Station: over 3 GB). 6 M cells take about 0.3 GB in C++, 1 GB in Python
MAX_CELLS = 6_000_000


def find_water_path_cells(
    bits: bytes | bytearray,
    width: int,
    height: int,
    wrap: bool,
    start: int,
    targets: array | list[int],
    max_km: float,
    east: array,
    diagonal: array,
    north: float,
    max_cells: int,
) -> tuple[float, list[int]] | None:
    """Find the shortest path over water cells from a start cell to target cells.

    Uses Dijkstra search on the 8-connected grid to find the least-cost path
    navigating exclusively over water cells (bit 0) and target cells. Steps cost
    `east[row]`, `north`, or `diagonal[row]` (to row + 1).

    Parameters:
        bits (bytes | bytearray): 1-bit raster bitmask (bit 1 = land, bit 0 = water).
        width (int): Grid raster width in cells.
        height (int): Grid raster height in cells.
        wrap (bool): Whether longitude wraps around 360 degrees.
        start (int): Start cell index (`row * width + column`).
        targets (array[int64] | list[int]): Sorted cell indices of candidate target nodes (e.g. sea nodes).
        max_km (float): Maximum allowed path distance in kilometres.
        east (array[float64]): Eastward cell transition distance per row in kilometres.
        diagonal (array[float64]): Diagonal cell transition distance per row in kilometres.
        north (float): Northward cell transition distance in kilometres.
        max_cells (int): Maximum cells to expand before aborting search.

    Returns:
        tuple[float, list[int]] | None:
            A tuple of `(distance_km, cell_indices_path)` if a path is found within
            `max_km` and `max_cells`, or `None` if unreachable or limits are exceeded.
    """
    km, before, heap = {start: 0.0}, {start: -1}, [(0.0, start)]
    while heap:
        d, cell = heappop(heap)
        if d > km[cell]:
            continue
        if _contains_cell(targets, cell):
            path = [cell]
            while before[path[-1]] >= 0:
                path.append(before[path[-1]])
            return d, path[::-1]
        row, column = divmod(cell, width)
        for dr, dc in NEIGHBOR_OFFSETS:
            r, c = row + dr, column + dc
            if not 0 <= r < height or not (wrap or 0 <= c < width):
                continue
            near = r * width + c % width
            low = min(row, r)
            step = diagonal[low] if dr and dc else east[row] if dc else north
            if d + step > max_km or d + step >= km.get(near, math.inf):
                continue
            if _is_land(bits, near) and not _contains_cell(targets, near):
                continue  # land
            if near not in km and len(km) >= max_cells:
                return None
            km[near], before[near] = d + step, cell
            heappush(heap, (d + step, near))
    return None


python = SimpleNamespace(find_water_path_cells=find_water_path_cells)
try:
    from scgraph.cpp import find_water_path_cells
except ImportError:
    pass


class LandMask:
    """Land (bit 1) and water (bit 0) on cells of 1/cells_per_degree degree: cell = row *
    width + column, from the south-west corner. A cell is land when its centre is; outside
    the raster is land. Columns wrap when the raster spans every longitude."""

    def __init__(self, bits, south, west, height, width, cells_per_degree):
        self.bits, self.south, self.west = bits, south, west
        self.height, self.width, self.size = height, width, 1 / cells_per_degree
        self.wrap = width == 360 * cells_per_degree
        lats = [self.get_cell_centre(row * width)[0] for row in range(height)]
        self.north_km = haversine([0, 0], [self.size, 0])
        steps = [(a, a) for a in lats], zip(lats, lats[1:])
        self.east_km, self.diagonal_km = (
            array("d", (haversine([a, 0], [b, self.size]) for a, b in pairs))
            for pairs in steps
        )

    @staticmethod
    def from_natural_earth(
        land: str,
        lakes: str,
        rivers: str,
        cells_per_degree: int = 240,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> "LandMask":
        """Construct a 1-bit land/water raster mask from Natural Earth vector features.

        Rasterizes 10m Natural Earth vector polygons and lines into a grid where
        bit 1 represents land and bit 0 represents navigable water.

        Algorithm:
        1. Land polygons: Rasterized using scanline polygon fill (even-odd rule)
           burning 1s (land).
        2. Lake polygons: Carved out by burning 0s (water) to restore inland water
           bodies and Great Lakes.
        3. River linestrings: Centrelines drawn as water (0s) to carve out
           navigable inland river channels.

        Parameters:
            land (str): Path to Natural Earth land GeoJSON file.
            lakes (str): Path to Natural Earth lakes GeoJSON file.
            rivers (str): Path to Natural Earth rivers GeoJSON file.
            cells_per_degree (int): Resolution in cells per degree. Defaults to 240
                (1/240 degree per cell, ~460m at the equator).
            bbox (tuple[float, float, float, float] | None): Optional bounding box
                `(south, west, north, east)` in degrees. Defaults to world `(-90, -180, 90, 180)`.

        Returns:
            LandMask: The initialized raster landmask instance.
        """
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

    def get_cell(self, lat: float, lon: float) -> int | None:
        """The cell of a point, None outside the raster."""
        row = math.floor((lat - self.south) / self.size)
        column = math.floor((lon - self.west) / self.size)
        if 0 <= row < self.height and 0 <= column < self.width:
            return row * self.width + column
        return None

    def get_cell_centre(self, cell: int) -> list[float]:
        row, column = divmod(cell, self.width)
        s = self.size
        return [self.south + (row + 0.5) * s, self.west + (column + 0.5) * s]

    def is_on_land(self, lat: float, lon: float) -> bool:
        cell = self.get_cell(lat, lon)
        return cell is None or bool(_is_land(self.bits, cell))

    def find_water_path(
        self,
        start: Sequence[float],
        targets: array,
        max_km: float,
        start_on_land_km: float = 6,
    ) -> tuple[float, list[list[float]]] | None:
        """`(km, cell centres)` of the cheapest water path from `start` to a cell of
        `targets` (an array('q'), sorted), or None beyond `max_km`, from the water cell
        nearest to `start` within `start_on_land_km` (`km` counts the leg to it).
        """
        cell = self.get_cell(*start)
        if cell is None:
            return None
        row, column = divmod(cell, self.width)
        reach = 1 + int(start_on_land_km / self.east_km[row])  # east <= north
        first = min(
            (
                (haversine(start, self.get_cell_centre(c)), c)
                for r in range(row - reach, row + reach + 1)
                for j in range(column - reach, column + reach + 1)
                if 0 <= r < self.height and (self.wrap or 0 <= j < self.width)
                for c in [r * self.width + j % self.width]
                if not _is_land(self.bits, c) or _contains_cell(targets, c)
            ),
            default=(math.inf, None),
        )
        if first[0] > min(start_on_land_km, max_km):
            return None
        found = find_water_path_cells(
            self.bits, self.width, self.height, self.wrap, first[1], targets,
            max_km - first[0], self.east_km, self.diagonal_km, self.north_km, MAX_CELLS,
        )  # fmt: skip
        if found is None:
            return None
        return first[0] + found[0], [self.get_cell_centre(c) for c in found[1]]


def _parts(filename):
    """The polygons or lines of a GeoJSON file."""
    with open(filename, encoding="utf-8") as file:
        for feature in json.load(file)["features"]:
            g = feature["geometry"]
            parts = g["coordinates"]
            yield from parts if "Multi" in g["type"] else [parts]
