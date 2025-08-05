from math import pi, cos, sin


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


def closest_point(
    node, point, depth=0, best=None, axis_count=2, best_dist=float("inf")
):
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
    - `best_dist`
        - Type: float
        - What: The best distance found so far (default is infinity)

    Returns:

    - The closest point found in the KDTree to the given point.
    """
    if node == 0:
        return best, best_dist
    # Get the median node and its distance
    median_node = node[0]
    median_node_dist = squared_distance(
        point, median_node, axis_count=axis_count
    )
    # Update the best point and distance if necessary
    if best is None or median_node_dist < best_dist:
        best = median_node
        best_dist = median_node_dist
    # Calculate the difference for node selection given the current axis
    axis = node[1]
    diff = point[axis] - median_node[axis]
    # Choose side to search
    close, away = (node[2], node[3]) if diff < 0 else (node[3], node[2])
    # Search the close side first
    best, best_dist = closest_point(
        close,
        point,
        depth + 1,
        best,
        axis_count=axis_count,
        best_dist=best_dist,
    )
    # Check the other side if needed
    if diff**2 < best_dist:
        best, best_dist = closest_point(
            away,
            point,
            depth + 1,
            best,
            axis_count=axis_count,
            best_dist=best_dist,
        )
    return best, best_dist


def squared_distance_3d(p1, p2):
    """
    Function:

    - Calculate the squared distance between two 3D points.

    Required Arguments:

    - `p1`
        - Type: tuple
        - What: The first point in 3D space
    - `p2`
        - Type: tuple
        - What: The second point in 3D space

    Returns:

    - The squared distance between the two 3D points.
    """
    return sum(
        [(p1[0] - p2[0]) ** 2, (p1[1] - p2[1]) ** 2, (p1[2] - p2[2]) ** 2]
    )


def closest_point_3d(node, point, depth=0, best=None, best_dist=float("inf")):
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
    - `best_dist`
        - Type: float
        - What: The best distance found so far (default is infinity)

    Returns:

    - The closest point found in the KDTree to the given point.
    """
    if node == 0:
        return best, best_dist
    # Get the median node and its distance
    median_node = node[0]
    median_node_dist = squared_distance_3d(point, median_node)
    # Update the best point and distance if necessary
    if best is None or median_node_dist < best_dist:
        best = median_node
        best_dist = median_node_dist
    # Calculate the difference for node selection given the current axis
    axis = node[1]
    diff = point[axis] - median_node[axis]
    # Choose side to search
    close, away = (node[2], node[3]) if diff < 0 else (node[3], node[2])
    # Search the close side first
    best, best_dist = closest_point_3d(close, point, depth + 1, best, best_dist)
    # Check the other side if needed
    if diff**2 < best_dist:
        best, best_dist = closest_point_3d(
            away, point, depth + 1, best, best_dist
        )
    return best, best_dist


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
        return closest_point(self.tree, point)[
            0
        ]  # Return only the point, not the distance


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
        return closest_point_3d(
            self.tree,
            GeoKDTree.lat_lon_idx_to_xyz_idx(point[0], point[1]),
        )[0][
            3
        ]  # Return the point [0] and the index of the point [3]

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
        lat_rad = lat * pi / 180
        lon_rad = lon * pi / 180
        cos_lat = cos(lat_rad)
        x = cos_lat * cos(lon_rad)
        y = cos_lat * sin(lon_rad)
        z = sin(lat_rad)
        return (x, y, z, idx)
