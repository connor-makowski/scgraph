from heapq import heappush, heappop


def triangle_area(
    p1: tuple[int | float, int | float],
    p2: tuple[int | float, int | float],
    p3: tuple[int | float, int | float],
) -> int | float:
    """
    Calculate the 2x the area of the triangle formed by points p1, p2, and p3.
    This is done using the determinant method, which is efficient.

    Args:

    - p1: First point as a tuple (x, y)
    - p2: Second point as a tuple (x, y) (the vertex of the angle)
    - p3: Third point as a tuple (x, y)

    Returns:

    - The 2x the area of the triangle formed by the three points.
    """
    return abs(
        p1[0] * (p2[1] - p3[1])
        + p2[0] * (p3[1] - p1[1])
        + p3[0] * (p1[1] - p2[1])
    )


def min_edge(
    p1: tuple[int | float, int | float],
    p2: tuple[int | float, int | float],
    p3: tuple[int | float, int | float],
) -> int | float:
    """
    Calculate the square of the length of the shortest edge of the angle formed by points p1, p2, and p3.

    The edge between p2 and p3 is not considered for the min edge as it is not part of the actual angle.

    Args:

    - p1: First point as a tuple (x, y)
    - p2: Second point as a tuple (x, y) (the vertex of the angle)
    - p3: Third point as a tuple (x, y)

    Returns:

    - The square of the length of the shortest edge of the angle formed by the three points with the vertex at p2.
    """
    edge1_sq = (p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2
    edge2_sq = (p2[0] - p3[0]) ** 2 + (p2[1] - p3[1]) ** 2
    return min(edge1_sq, edge2_sq)


def triangle_area_plus_min_edge(
    p1: tuple[int | float, int | float],
    p2: tuple[int | float, int | float],
    p3: tuple[int | float, int | float],
) -> int | float:
    """
    Calculate the 2x the area of the triangle formed by points p1, p2, and p3,
    plus the square of the length of the shortest edge.

    This would be equivalent to adding the area of the parallelogram formed by the two edges in the graph plus
    the area of a square with edge length equal to the shortest edge of the triangle.

    This helps balance the simplification process for features like long narrow angles that are likely important
    but would otherwise be simplified too aggressively.

    Args:

    - p1: First point as a tuple (x, y)
    - p2: Second point as a tuple (x, y) (the vertex of the angle)
    - p3: Third point as a tuple (x, y)

    Returns:

    - The 2x the area of the triangle formed by the three points plus the square of the length of the shortest edge of the angle.
    """
    return triangle_area(p1, p2, p3) + min_edge(p1, p2, p3)


def visvalingam(
    coords: list[list[int | float]],
    pct_to_keep: float,
    min_points: int = 2,
    weight_fn: callable = triangle_area,
) -> list[list[int | float]]:
    """
    Simplify a linestring using Visvalingam-Whyatt algorithm.

    Args:

    - coords: List of [x, y] points
    - pct_to_keep: Percentage of the interior line points to keep 0-100
        - Note: This pct_to_keep is not applied to the endpoints of the line such that they are always kept.
        - Note: The max of the calculated number of points based on `pct_to_keep` and `min_points` will be used.
    - min_points: Minimum number of points to keep in the simplified line
        - Note: This number does include the endpoints.
        - Note: The max of the calculated number of points based on `pct_to_keep` and `min_points` will be used.
    - weight_fn: Function to calculate the weight of a point
        - Default: `triangle_area` which calculates the area of the triangle formed by three consecutive points.

    Returns:

    - A simplified list of coordinates [x, y] of at least `min_points` long.
    """
    pct_to_keep = pct_to_keep / 100.0
    assert 0 <= pct_to_keep <= 1, "pct_to_keep must be between 0 and 100"
    nodes_to_keep = max(
        int(round((len(coords) - 2) * pct_to_keep)) + 2, min_points
    )

    if nodes_to_keep >= len(coords):
        return coords

    nexts = list(range(1, len(coords))) + [-1]  # Next index for each point
    prevs = [-1] + list(range(len(coords) - 1))  # Previous index for each point
    areas = [0] * len(
        coords
    )  # Areas of triangles formed by each point and its neighbors
    area_heap = []

    first_idx = 0
    last_idx = len(coords) - 1

    for idx in range(1, last_idx):
        area = triangle_area(
            coords[prevs[idx]], coords[idx], coords[nexts[idx]]
        )
        areas[idx] = area
        heappush(area_heap, (area, idx))

    nodes_left = len(coords)

    while area_heap:
        min_area, min_index = heappop(area_heap)
        # Only continue if the minimum area is valid and has not since been updated
        if areas[min_index] != min_area:
            continue
        prev_idx = prevs[min_index]
        next_idx = nexts[min_index]

        # Update the next and previous pointers
        areas[min_index] = -1
        prevs[next_idx] = prev_idx
        nexts[prev_idx] = next_idx

        # Recalculate areas of neighbors
        for idx in (prev_idx, next_idx):
            if idx == first_idx or idx == last_idx:
                continue
            area = triangle_area(
                coords[prevs[idx]], coords[idx], coords[nexts[idx]]
            )
            areas[idx] = area
            heappush(area_heap, (area, idx))
        nodes_left -= 1
        if nodes_left <= nodes_to_keep:
            break
    return [coords[i] for i in range(len(coords)) if areas[i] != -1]
