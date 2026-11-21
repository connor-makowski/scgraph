"""Douglas-Peucker line simplification for coordinates and shape arrays."""

import math
from array import array
from collections.abc import Sequence
from scgraph.utils import _is_sorted

# Metres per 1e-7 degree of latitude
_METRES = 6371000.0 * math.pi / 1.8e9


def _is_monotonically_increasing(offsets):
    """Return True if offsets start at 0 and are monotonically non-decreasing."""
    return offsets[0] == 0 and _is_sorted(offsets)


def perpendicular_distance(
    point: Sequence[float],
    start: Sequence[float],
    end: Sequence[float],
) -> float:
    """Return the distance from a point to a line segment, in a plane.

    Args:
        point: The `[x, y]` coordinates of the point.
        start: The `[x, y]` coordinates of the start of the segment.
        end: The `[x, y]` coordinates of the end of the segment.

    Returns:
        The shortest Euclidean distance from the point to the segment, in the unit of
        the coordinates.
    """
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    t = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length2
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
    proj_x = start[0] + t * dx
    proj_y = start[1] + t * dy
    return math.hypot(point[0] - proj_x, point[1] - proj_y)


def douglas_peucker(
    coords: list[list[int | float]],
    tolerance: float = 0.0,
    min_points: int = 2,
) -> list[list[int | float]]:
    """Simplify a line with the Ramer-Douglas-Peucker algorithm.

    The function keeps the two ends of the line. It drops a point between them when
    the point is within `tolerance` of the segment that joins the kept points around
    it.

    Args:
        coords: The `[x, y]` coordinates of the points of the line.
        tolerance: The largest distance from a dropped point to the simplified line,
            in the unit of the coordinates. The default, 0.0, drops only the points
            that are exactly on a straight line.
        min_points: The smallest number of points that the simplified line keeps.
            The default, 2, keeps at least the two ends.

    Returns:
        The `[x, y]` coordinates of the kept points.

    Raises:
        ValueError: `tolerance` is negative.
    """
    if tolerance < 0:
        raise ValueError("tolerance must be >= 0")
    if len(coords) <= min_points:
        return coords

    n = len(coords)
    max_distances = [0.0] * n
    keep = [False] * n
    keep[0] = True
    keep[-1] = True

    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        farthest_idx = -1
        farthest_dist = tolerance
        for i in range(a + 1, b):
            d = perpendicular_distance(coords[i], coords[a], coords[b])
            if d > max_distances[i]:
                max_distances[i] = d
            if d > farthest_dist:
                farthest_idx = i
                farthest_dist = d
        if farthest_idx >= 0:
            keep[farthest_idx] = True
            stack.append((a, farthest_idx))
            stack.append((farthest_idx, b))

    # Guarantee min_points by retaining points with the highest deviations
    kept_count = sum(keep)
    if kept_count < min_points:
        candidates = sorted(
            (i for i in range(1, n - 1) if not keep[i]),
            key=lambda i: max_distances[i],
            reverse=True,
        )
        for i in candidates[: min_points - kept_count]:
            keep[i] = True

    return [coords[i] for i in range(n) if keep[i]]


def simplify_shapes(
    shape_points: array | memoryview,
    shape_offsets: array | memoryview,
    endpoint_coords: array | memoryview,
    tolerance_meters: float,
) -> tuple[array, array]:
    """Simplify the shapes of many arcs with the Douglas-Peucker algorithm.

    The shape of an arc is the list of points between its two nodes. The function
    drops a shape point when it is within `tolerance_meters` of the segment that joins
    the kept points around it. It measures this distance on a flat map around each
    arc.

    Args:
        shape_points: The shape points of all the arcs, as int32 values in units of
            1e-7 degree: the latitude of a point, then its longitude.
        shape_offsets: The int32 offsets of the shapes. The points of shape `i` are
            the points `shape_offsets[i]` to `shape_offsets[i + 1] - 1`.
        endpoint_coords: Four int32 values for each shape, in units of 1e-7 degree:
            the latitude and the longitude of the origin, then of the destination.
            The function always keeps these two ends.
        tolerance_meters: The largest distance from a dropped point to the simplified
            shape, in meters. It is zero or more.

    Returns:
        `(kept_points, kept_offsets)`: the kept shape points and their offsets, in
        the layout of `shape_points` and `shape_offsets`.

    Raises:
        ValueError: `tolerance_meters` is negative, an array has the wrong length, or
            the offsets do not start at 0 or decrease.
    """
    shapes = len(shape_offsets) - 1
    if not tolerance_meters >= 0:
        raise ValueError("tolerance_meters must be >= 0")
    if (
        shapes < 0
        or len(shape_points) % 2
        or len(endpoint_coords) != 4 * shapes
    ):
        raise ValueError("expected two ints per point and four ends per shape")
    if shape_offsets[shapes] != len(
        shape_points
    ) // 2 or not _is_monotonically_increasing(shape_offsets):
        raise ValueError("offsets must rise from 0 to the number of items")

    tolerance2 = tolerance_meters * tolerance_meters
    kept, kept_offsets = array("i"), array("i", [0])
    for s in range(shapes):
        lat0, lon0 = endpoint_coords[4 * s], endpoint_coords[4 * s + 1]
        kx = _METRES * math.cos(lat0 * math.pi / 1.8e9)
        x, y = [], []
        line = shape_points[2 * shape_offsets[s] : 2 * shape_offsets[s + 1]]
        for latitude, longitude in zip(
            [lat0, *line[::2], endpoint_coords[4 * s + 2]],
            [lon0, *line[1::2], endpoint_coords[4 * s + 3]],
        ):
            dlon = longitude - lon0
            if dlon > 1800000000:
                dlon -= 3600000000
            elif dlon < -1800000000:
                dlon += 3600000000
            x.append(dlon * kx)
            y.append((latitude - lat0) * _METRES)
        last = len(x) - 1
        keep, stack = [False] * (last + 1), [(0, last)]
        while stack:
            a, b = stack.pop()
            dx, dy = x[b] - x[a], y[b] - y[a]
            length2 = dx * dx + dy * dy
            farthest, worst = -1, tolerance2
            for i in range(a + 1, b):
                px, py = x[i] - x[a], y[i] - y[a]
                if length2 > 0:
                    t = (px * dx + py * dy) / length2
                    t = 0 if t < 0 else 1 if t > 1 else t
                    px = px - t * dx
                    py = py - t * dy
                d2 = px * px + py * py
                if d2 > worst:
                    farthest, worst = i, d2
            if farthest >= 0:
                keep[farthest] = True
                stack.append((a, farthest))
                stack.append((farthest, b))
        for i in range(1, last):
            if keep[i]:
                kept.extend(line[2 * i - 2 : 2 * i])
        kept_offsets.append(len(kept) // 2)
    return kept, kept_offsets
