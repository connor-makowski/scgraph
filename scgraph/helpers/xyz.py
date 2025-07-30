import math


def lat_lon_idx_to_xyz_idx(lat: float | int, lon: float | int, idx: int):
    """
    Function:

    - Convert latitude and longitude to a 3D Cartesian coordinate system (x, y, z)

    Required Arguments:

    - `lat`:
        - Type: float | int
        - What: Latitude in degrees
    - `lon`:
        - Type: float | int
        - What: Longitude in degrees
    - `idx`:
        - Type: int
        - What: Index of the point (used for identification, e.g., in a KD-Tree)
    """

    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    x = math.cos(lat_rad) * math.cos(lon_rad)
    y = math.cos(lat_rad) * math.sin(lon_rad)
    z = math.sin(lat_rad)
    return (x, y, z, idx)


def xyz_distance_squared(p1, p2):
    """
    Function:

    - Calculate the squared Euclidean distance between two points in 3D space

    Required Arguments:

    - `p1`:
        - Type: tuple of floats
        - What: First point in 3D space (x, y, z)
    - `p2`:
        - Type: tuple of floats
        - What: Second point in 3D space (x, y, z)

    Returns:
        Euclidean distance between the two points
    """
    return (p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2 + (p1[2] - p2[2]) ** 2
