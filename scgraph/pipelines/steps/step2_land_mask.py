"""A land mask, and the shortest path over water on it.

WHAT IT ANSWERS

`LandMask.is_on_land` tells whether a point is on land. `LandMask.find_water_path`
gives the shortest path over water from a point to the closest of a set of cells.
`step2_hub_connectors.join_networks_at_hubs` uses it for the sea connector of a port.

HOW THE MASK IS STORED

The mask is a raster of cells of 1/`cells_per_degree` degree, one bit per cell: 1 for
land, 0 for water. Cells are numbered from the south-west corner:
`cell = row * width + column`. A cell is land when its centre is on land. A point
outside the raster is on land.

Example: a mask starts at latitude 56 and longitude 10, with 240 cells per degree and
480 columns. The point (56.152, 10.217) is in row 36 and column 52. Its cell is
36 * 480 + 52 = 17,332.

HOW A SEARCH RUNS

1. Find the cell of the start. A start outside the raster has no path.
2. Find the first cell of the path: the cell closest to the start that is water or a
   target. It must be within `start_on_land_km` of the start. The straight line from
   the start to this cell is the first leg of the path. A port is often drawn on
   land, so the path needs this leg.
3. From this cell, run Dijkstra's algorithm on the cells. A step goes to one of the 8
   neighbours of a cell, if it is water or a target. A step costs the distance
   between the centres of the two cells.
4. Stop at the first target that the search settles. The length of the path is the
   leg of step 2 plus the steps.

The search gives no path beyond `max_km`, or when it would hold more than `MAX_CELLS`
cells.

Example: at the equator, with 240 cells per degree, a step along a row or between two
rows is 0.46 km long, and a diagonal step is 0.66 km long. A path of two steps east
and one diagonal step is 1.58 km long.

WHY THE RESULT IS RIGHT

Dijkstra's algorithm settles the cells in rising order of length, so the first target
settled is the closest one over water. The path goes from cell centre to cell centre.
Its length is the length on this grid, not the exact shortest length over water.

THE C++ VERSION

`find_water_path_cells` is the C++ function of
`scgraph/cpp/src/pipelines/landmask.hpp` when the extension is built. The pure-Python
version gives the same answers. It stays reachable as `python.find_water_path_cells`.
"""

import json
import math
from array import array
from bisect import bisect_left
from collections.abc import Sequence
from heapq import heappop, heappush
from types import SimpleNamespace

from scgraph.utils import haversine

# The steps to the 8 neighbours of a cell, as (rows, columns), in the order of the
# search
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


# The largest number of cells that a search for a water path may hold. Of the ports of
# the World Port Index that find a sea node, the one with the largest search holds
# 2,726,042 cells: the limit is about twice that. Without a limit, a search near the
# poles grows without bound (McMurdo Station: over 3 GB). 6 million cells take about
# 0.3 GB in C++ and 1 GB in Python.
MAX_CELLS = 6_000_000


def find_water_path_cells(
    bits: bytes | bytearray,
    width: int,
    height: int,
    wrap: bool,
    start: int,
    targets: array | list[int],
    max_km: float,
    east_km: array,
    diagonal_km: array,
    north_km: float,
    max_cells: int,
) -> tuple[float, list[int]] | None:
    """Find the shortest path over water from a start cell to the closest target cell.

    The function runs Dijkstra's algorithm on the cells. A step goes from a cell to one of
    its 8 neighbours. It enters a water cell (bit 0) or a target cell only.

    Args:
        bits: The raster, one bit per cell: 1 for land, 0 for water.
        width: The number of columns of the raster.
        height: The number of rows of the raster.
        wrap: True when the raster spans every longitude. The last column then touches
            the first one.
        start: The start cell, `row * width + column`.
        targets: The target cells, sorted (int64). For a sea connector, they are the
            cells of the sea nodes.
        max_km: The longest path accepted, in km.
        east_km: The length in km of a step along a row, for each row.
        diagonal_km: The length in km of a diagonal step between a row and the next row
            to the north, for each row.
        north_km: The length in km of a step between two rows, in the same column.
        max_cells: The largest number of cells that the search may hold. It bounds the
            memory of a search.

    Returns:
        `(km, cells)`: the length of the path, and its cells from the start to the
        target. None when no target is within `max_km`, or when the search would hold
        more than `max_cells` cells.
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
            step = (
                diagonal_km[low]
                if dr and dc
                else east_km[row] if dc else north_km
            )
            if d + step > max_km or d + step >= km.get(near, math.inf):
                continue
            if _is_land(bits, near) and not _contains_cell(targets, near):
                continue
            if near not in km and len(km) >= max_cells:
                return None
            km[near], before[near] = d + step, cell
            heappush(heap, (d + step, near))
    return None


# The twin stays beside its explanation, so the C++ function replaces it here.
python = SimpleNamespace(find_water_path_cells=find_water_path_cells)
try:
    from scgraph.cpp import find_water_path_cells
except ImportError:
    pass


class LandMask:
    """A land mask: land (bit 1) and water (bit 0) on cells of 1/`cells_per_degree`
    degree. The module docstring says how the cells are numbered. The columns wrap when
    the raster spans every longitude.
    """

    def __init__(self, bits, south, west, height, width, cells_per_degree):
        self.bits, self.south, self.west = bits, south, west
        self.height, self.width, self.size = height, width, 1 / cells_per_degree
        self.wrap = width == 360 * cells_per_degree
        latitudes = [
            self.get_cell_centre(row * width)[0] for row in range(height)
        ]
        self.north_km = haversine([0, 0], [self.size, 0])
        steps = [(a, a) for a in latitudes], zip(latitudes, latitudes[1:])
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
        """Build the land mask of a region from three files of Natural Earth (scale 1:10m).

        1. The function sets to land each cell whose centre is inside a land polygon.
        2. It sets back to water each cell whose centre is inside a lake polygon. The Great
           Lakes become water this way.
        3. It sets to water each cell that a river centreline crosses. A sea connector can
           then follow a river to a port inland.

        Args:
            land: The path of the GeoJSON file of the land polygons.
            lakes: The path of the GeoJSON file of the lake polygons.
            rivers: The path of the GeoJSON file of the river centrelines.
            cells_per_degree: The number of cells in one degree. With 240, a cell is 1/240
                degree wide: about 460 m at the equator.
            bbox: The region, `(south, west, north, east)` in degrees. None takes the world.

        Returns:
            The land mask of the region.
        """
        k = cells_per_degree
        bbox = bbox or (-90, -180, 90, 180)
        south, west, north, east = (round(v * k) for v in bbox)
        height, width = north - south, (east - west + 7) // 8 * 8  # whole bytes
        bits = bytearray(height * width // 8)

        def xy(ring):  # cell centres at integers
            return [(x * k - west - 0.5, y * k - south - 0.5) for x, y in ring]

        for burn, polygon in [(1, p) for p in _read_parts(land)] + [
            (0, p) for p in _read_parts(lakes)
        ]:
            cross = {}  # row -> x where the polygon's edges cross its centre
            for ring in map(xy, polygon):
                for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
                    top = min(height, math.ceil(max(y1, y2)))
                    for i in range(max(0, math.ceil(min(y1, y2))), top):
                        x = x1 + (i - y1) * (x2 - x1) / (y2 - y1)
                        cross.setdefault(i, []).append(min(width, max(0, x)))
            # In row `i`, the edges cross the line of the cell centres at the sorted
            # positions c[0], c[1], c[2]... The cells from c[0] to c[1], from c[2] to
            # c[3], and so on, are inside the polygon (even-odd rule). `span` has one
            # bit for each of these cells. The bytes of the row are read as one
            # integer, so one operation sets or clears all these bits.
            for i, xs in cross.items():
                c = sorted(math.ceil(x) for x in xs)
                lo, hi = c[0] >> 3, (c[-1] + 7) >> 3  # the bytes spans touch
                at = slice(i * width // 8 + lo, i * width // 8 + hi)
                v = int.from_bytes(bits[at], "little")
                span = sum((1 << b) - (1 << a) for a, b in zip(c[::2], c[1::2]))
                v = v | span >> 8 * lo if burn else v & ~(span >> 8 * lo)
                bits[at] = v.to_bytes(hi - lo, "little")
        for line in map(xy, _read_parts(rivers)):
            for (x1, y1), (x2, y2) in zip(line, line[1:]):
                n = math.ceil(max(abs(x2 - x1), abs(y2 - y1))) + 1
                for t in range(n + 1):
                    x = round(x1 + (x2 - x1) * t / n)
                    y = round(y1 + (y2 - y1) * t / n)
                    if 0 <= x < width and 0 <= y < height:
                        bits[(y * width + x) >> 3] &= ~(1 << (x & 7))
        return LandMask(bits, south / k, west / k, height, width, k)

    def get_cell(self, latitude: float, longitude: float) -> int | None:
        """Return the cell of a point, or None when the point is outside the raster."""
        row = math.floor((latitude - self.south) / self.size)
        column = math.floor((longitude - self.west) / self.size)
        if 0 <= row < self.height and 0 <= column < self.width:
            return row * self.width + column
        return None

    def get_cell_centre(self, cell: int) -> list[float]:
        """Return the `[latitude, longitude]` of the centre of a cell, in degrees."""
        row, column = divmod(cell, self.width)
        s = self.size
        return [self.south + (row + 0.5) * s, self.west + (column + 0.5) * s]

    def is_on_land(self, latitude: float, longitude: float) -> bool:
        """Return True when the cell of the point is land, or when the point is outside
        the raster."""
        cell = self.get_cell(latitude, longitude)
        return cell is None or bool(_is_land(self.bits, cell))

    def find_water_path(
        self,
        start: Sequence[float],
        targets: array,
        max_km: float,
        start_on_land_km: float = 6,
    ) -> tuple[float, list[list[float]]] | None:
        """Find the shortest path over water from `start` to the closest cell of `targets`.

        Args:
            start: The point, `[latitude, longitude]`.
            targets: The target cells, sorted, as an `array('q')`.
            max_km: The longest path accepted, in km.
            start_on_land_km: How far from `start` the first water cell may be, in km.

        Returns:
            `(km, points)`: the length of the path, with the leg from `start` to the first
            cell, and the centres of its cells. None when there is no such path.
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


def _read_parts(filename):
    """Yield the polygons or the lines of a GeoJSON file."""
    with open(filename, encoding="utf-8") as file:
        for feature in json.load(file)["features"]:
            g = feature["geometry"]
            parts = g["coordinates"]
            yield from parts if "Multi" in g["type"] else [parts]
