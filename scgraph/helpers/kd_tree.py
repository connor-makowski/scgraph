import math


def kdtree(points, depth=0, axis_count=2):
    """
    Function:

    - Build a KDTree from a list of points.

    Required Arguments:

    - `points`
        - Type: list of tuples
        - What: A list of points to build the KDTree from

    Optional Arguments:

    - `depth`
        - Type: int
        - What: The current depth in the tree (used for axis selection)
    - `axis_count`
        - Type: int
        - What: The number of dimensions in the points (default is 2 for 2D points)

    Returns:

    - The constructed KDTree as a tuple in the format (point, axis, left, right).
    - Where left and right are subtrees.
    """
    if not points:
        return 0
    axis = depth % axis_count
    points.sort(key=lambda p: p[axis])
    median = len(points) // 2
    return (
        points[median],
        axis,
        kdtree(points[:median], depth + 1),
        kdtree(points[median + 1 :], depth + 1),
    )


def squared_distance(p1, p2, axis_count=2):
    """
    Function:

    - Calculate the squared distance between two points.

    Required Arguments:

    - `p1`
        - Type: tuple
        - What: The first point
    - `p2`
        - Type: tuple
        - What: The second point

    Optional Arguments:

    - `axis_count`
        - Type: int
        - What: The number of dimensions in the points
        - Default: 2 (for 2D points)

    Returns:

    - The squared distance between the two points.
    """
    return sum([(p1[i] - p2[i]) ** 2 for i in range(axis_count)])


def closest_point(node, point, depth=0, best=None, axis_count=2):
    """
    Function:

    - Find the closest point in the KDTree to a given point.

    Required Arguments:

    - `node`
        - Type: tuple
        - What: The node of the KDTree
    - `point`
        - Type: tuple
        - What: The point to find the closest point to

    Optional Arguments:

    - `depth`
        - Type: int
        - What: The current depth in the tree (used for axis selection)
    - `best`
        - Type: tuple or None
        - What: The best point found so far (default is None)
    - `axis_count`
        - Type: int
        - What: The number of dimensions in the points (default is 2 for 2D points)

    Returns:

    - The closest point found in the KDTree to the given point.
    """
    if node == 0:
        return best
    if best is None or squared_distance(
        point, node[0], axis_count
    ) < squared_distance(point, best, axis_count):
        best = node[0]

    axis = node[1]
    diff = point[axis] - node[0][axis]

    # Choose side to search
    close, away = (node[2], node[3]) if diff < 0 else (node[3], node[2])

    best = closest_point(close, point, depth + 1, best, axis_count=axis_count)

    # Check the other side if needed
    if diff**2 < squared_distance(point, best, axis_count):
        best = closest_point(
            away, point, depth + 1, best, axis_count=axis_count
        )

    return best


class KDTree:
    def __init__(self, points):
        """
        Function:

        - Build a KDTree from a list of points.

        Required Arguments:

        - `points`
            - Type: list of tuples
            - What: A list of points to build the KDTree from

        Returns:

        - A KDTree object that can be used to find the closest point to a given point.
        """
        self.tree = kdtree(points, axis_count=len(points[0]))

    def closest_point(self, point):
        """
        Function:

        - Find the closest point in the KDTree to a given point.

        Required Arguments:

        - `point`
            - Type: tuple
            - What: The point to find the closest point to

        Returns:

        - The closest point found in the KDTree to the given point.
        """
        return closest_point(self.tree, point)


class GeoKDTree:
    def __init__(self, points: list[tuple]):
        """
        Function:

        - Build a GeoKDTree from a list of latitude and longitude points or an existing KDTree.

        Required Arguments:

        - `points`
            - Type: list of tuples
            - What: A list of latitude and longitude points to build the GeoKDTree from
            - The points should be in the format [(lat1, lon1), (lat2, lon2), ...].

        Returns:

        - A GeoKDTree object that can be used to find the closest point to a given latitude and longitude.
        - The points should be in the format [(lat1, lon1), (lat2, lon2), ...].
        """
        self.tree = kdtree(
            [
                GeoKDTree.lat_lon_idx_to_xyz_idx(point[0], point[1], idx)
                for idx, point in enumerate(points)
            ],
            axis_count=3,
        )

    def closest_idx(self, point: tuple):
        """
        Function:

        - Find the index of the closest point in the GeoKDTree to a given latitude and longitude point.

        Required Arguments:

        - `point`
            - Type: tuple
            - What: The latitude and longitude point to find the closest point to

        Returns:

        - The index of the closest point found in the GeoKDTree to the given latitude and longitude point.
        """
        return closest_point(
            self.tree,
            GeoKDTree.lat_lon_idx_to_xyz_idx(point[0], point[1]),
            axis_count=3,
        )[3]

    @staticmethod
    def lat_lon_idx_to_xyz_idx(
        lat: int | float, lon: int | float, idx: int = 0
    ):
        """
        Function:

        - Convert latitude and longitude to Cartesian coordinates (x, y, z) and include an index.

        Required Arguments:

        - `lat`
            - Type: int or float
            - What: The latitude in degrees
        - `lon`
            - Type: int or float
            - What: The longitude in degrees

        Optional Arguments:

        - `idx`
            - Type: int
            - What: An index to include with the coordinates (default is 0)
        """
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)
        x = math.cos(lat_rad) * math.cos(lon_rad)
        y = math.cos(lat_rad) * math.sin(lon_rad)
        z = math.sin(lat_rad)
        return (x, y, z, idx)
