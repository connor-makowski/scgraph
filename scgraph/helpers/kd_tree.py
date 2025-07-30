import math
from time import time

# A node in the KDTree has this format: (point, axis, left, right)
def kdtree(points, depth=0, axis_count=2):
    if not points:
        return None
    axis = depth % axis_count
    points.sort(key=lambda p: p[axis])
    median = len(points) // 2
    return (
        points[median],
        axis,
        kdtree(points[:median], depth + 1),
        kdtree(points[median + 1:], depth + 1),
    )

def squared_distance(p1, p2, axis_count=2):
    return sum([(p1[i] - p2[i])**2 for i in range(axis_count)])

def closest_point(root, point, depth=0, best=None, axis_count=2):
    if root is None:
        return best
    if best is None or squared_distance(point, root[0], axis_count) < squared_distance(point, best, axis_count):
        best = root[0]

    axis = root[1]
    diff = point[axis] - root[0][axis]

    # Choose side to search
    close, away = (root[2], root[3]) if diff < 0 else (root[3], root[2])

    best = closest_point(close, point, depth + 1, best, axis_count=axis_count)

    # Check the other side if needed
    if diff**2 < squared_distance(point, best, axis_count):
        best = closest_point(away, point, depth + 1, best, axis_count=axis_count)

    return best

class KDTree:
    def __init__(self, points):
        self.tree = kdtree(points, axis_count=len(points[0]))

    def closest_point(self, point):
        return closest_point(self.tree, point)

class GeoKDTree:
    def __init__(self, points=None, tree=None):
        if tree is None and points is None:
            raise ValueError("Either points or tree must be provided")
        if tree is not None and points is not None:
            raise ValueError("Only one of points or tree should be provided")
        if tree is not None:
            self.tree = tree
        else:
            self.tree = kdtree([GeoKDTree.lat_lon_idx_to_xyz_idx(point[0], point[1], idx) for idx, point in enumerate(points)], axis_count=3)

    def closest_idx(self, point):
        return closest_point(self.tree, GeoKDTree.lat_lon_idx_to_xyz_idx(point[0], point[1]), axis_count=3)[3]
    
    @staticmethod
    def lat_lon_idx_to_xyz_idx(lat, lon, idx=0):
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)
        x = math.cos(lat_rad) * math.cos(lon_rad)
        y = math.cos(lat_rad) * math.sin(lon_rad)
        z = math.sin(lat_rad)
        return (x, y, z, idx)