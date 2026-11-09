"""Douglas-Peucker line simplification for coordinates and shape arrays."""

import math
from array import array
from operator import le

# Metres per 1e-7 degree of latitude
_METRES = 6371000.0 * math.pi / 1.8e9


def _is_monotonically_increasing(offsets):
    """Return True if offsets start at 0 and are monotonically non-decreasing."""
    return offsets[0] == 0 and all(map(le, offsets, offsets[1:]))


def perpendicular_distance(point, start, end):
    """Calculate the perpendicular distance from a 2D point to a line segment.

    Parameters:
        point (tuple or list): [x, y] coordinates of the point.
        start (tuple or list): [x, y] coordinates of the segment start.
        end (tuple or list): [x, y] coordinates of the segment end.

    Returns:
        float: Shortest Euclidean distance from point to the segment.
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
    """Simplify a linestring using the Ramer-Douglas-Peucker algorithm.

    Drops intermediate points that fall within `tolerance` perpendicular distance
    of the line segment connecting the retained endpoints.

    Parameters:
        coords (list[list[int | float]]): List of [x, y] coordinates.
        tolerance (float): Maximum perpendicular distance threshold. Points within
            this distance of the chord are eliminated. Defaults to 0.0 (removes only
            strictly colinear points).
        min_points (int): Minimum number of points to keep in the simplified line
            (default: 2, keeping at least endpoints).

    Returns:
        list[list[int | float]]: Simplified list of [x, y] coordinates.

    Raises:
        ValueError: If `tolerance < 0`.
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


def simplify_shapes(points, offsets, ends, tolerance_m):
    """Simplify intermediate polyline shapes using the Douglas-Peucker algorithm.

    Drops intermediate shape points that fall within `tolerance_m` metres of the
    segment connecting the retained endpoints, calculated on a local flat-map
    projection for each arc.

    Parameters:
        points (array[int32]): Flat sequence of intermediate `[lat, lon]` pairs
            encoded in 1e-7 degrees.
        offsets (array[int32]): Offsets indexing into `points // 2` for each shape.
            Shape `i` occupies slice `offsets[i]:offsets[i + 1]`.
        ends (array[int32]): Four coordinates per shape: origin latitude, origin
            longitude, destination latitude, destination longitude in 1e-7 degrees.
            These endpoints are always preserved.
        tolerance_m (float): Distance threshold in metres. Must be non-negative.

    Returns:
        tuple[array[int32], array[int32]]:
            A tuple of `(kept_points, kept_offsets)` containing the retained flat
            coordinate pairs and their corresponding slice offsets.

    Raises:
        ValueError: If `tolerance_m < 0`, coordinates are malformed, or offsets
            do not monotonically increase from 0.
    """
    shapes = len(offsets) - 1
    if not tolerance_m >= 0:
        raise ValueError("tolerance_m must be >= 0")
    if shapes < 0 or len(points) % 2 or len(ends) != 4 * shapes:
        raise ValueError("expected two ints per point and four ends per shape")
    if offsets[shapes] != len(points) // 2 or not _is_monotonically_increasing(
        offsets
    ):
        raise ValueError("offsets must rise from 0 to the number of items")

    tolerance2 = tolerance_m * tolerance_m
    kept, kept_offsets = array("i"), array("i", [0])
    for s in range(shapes):
        lat0, lon0 = ends[4 * s], ends[4 * s + 1]
        kx = _METRES * math.cos(lat0 * math.pi / 1.8e9)
        x, y = [], []
        line = points[2 * offsets[s] : 2 * offsets[s + 1]]
        for latitude, longitude in zip(
            [lat0, *line[::2], ends[4 * s + 2]],
            [lon0, *line[1::2], ends[4 * s + 3]],
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
