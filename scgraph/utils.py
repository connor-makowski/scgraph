import json
from math import pi, sin, cos, asin

# Constants for haversine and cheap ruler calculations
earth_radius = {
    "km": 6371,
    "m": 6371000,
    "mi": 3959,
    "ft": 3959 * 5280,
}
radians_per_degree = pi / 180  # radians per degree
cheap_e2 = (1 / 298.257223563) * (2 - (1 / 298.257223563))


def haversine(
    origin: list[float | int],
    destination: list[float | int],
    units: str = "km",
    circuity: [float | int] = 1,
):
    """
    Function:

    - Calculate the great circle distance in kilometers between two points on the earth (specified in decimal degrees)

    Required Arguments:

    - `origin`:
        - Type: list of two floats | ints
        - What: The origin point as a list of "latitude" and "longitude"
    - `destination`:
        - Type: list of two floats | ints
        - What: The destination point as a list of "latitude" and "longitude"

    Optional Arguments:

    - `units`:
        - Type: str
        - What: units to return the distance in? (one of "km", "m", "mi", or "ft")
        - Default: "km"
    - `circuity`:
        - Type: int | float
        - What: Multiplier to increase the calculated distance (to account for circuity)
        - Default: 1

    """
    # convert decimal degrees to radians
    lon1 = radians_per_degree * origin[1]
    lat1 = radians_per_degree * origin[0]
    lon2 = radians_per_degree * destination[1]
    lat2 = radians_per_degree * destination[0]

    # haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(a**0.5)
    # Set the radius of earth based on the units specified
    radius = earth_radius.get(
        units, 6371
    )  # Default to kilometers if not specified or invalid
    return c * radius * circuity


def cheap_ruler(origin, destination, units="km", circuity=1):
    """
    Function:

    Calculates a fast approximate distance between two lat/lon points using Mapbox's "cheap ruler" method.

    Note: In general, this method is considered faster than the haversine formula, but less accurate, especially near the poles and for long distances.
    For this implementation, it tests slower than haversine, but it seems like there might be some room for optimization.

    Required Arguments
    - `origin`
        - Type: list of two floats | ints
        - What: The origin point as a list of "latitude" and "longitude"
    - `destination`
        - Type: list of two floats | ints
        - What: The destination point as a list of "latitude" and "longitude"

    Optional Arguments

    - `units`
        - Type: str
        - What: units to return the distance in? (one of "km", "m", "mi", or "ft")
        - Default: "km"
        origin: [lat, lon] in degrees
        destination: [lat, lon] in degrees
        units: 'km', 'm', 'mi', or 'ft'
    - `circuity`
        - Type: int | float
        - What: Multiplier to increase the calculated distance (to account for circuity)
        - Default: 1
        - Note: Consider using this as less than 1 when you are writing a heuristic function for
            A* as this method can overestimate distances, especially near the Earth's poles.

    Returns:
        Distance in the specified units
    """

    # Constants
    radius = earth_radius.get(
        units, 6371
    )  # Default to kilometers if not specified
    lat1, lon1 = origin
    lat2, lon2 = destination
    # Get the adjusted longitude difference
    lon_diff = abs(lon2 - lon1)
    lon_diff = min(360 - lon_diff, lon_diff)

    # Midpoint latitude in radians
    mid_lat = (lat1 + lat2) / 2 * radians_per_degree
    cos_lat = cos(mid_lat)

    # Radius adjustments
    w_squared = 1 / (1 - cheap_e2 * (1 - cos_lat**2))
    w = w_squared**0.5

    # Meters per degree at this latitude (scaled for km)
    m = radians_per_degree * radius
    kx = m * w * cos_lat
    ky = m * w * w_squared * (1 - cheap_e2)

    dx = (lon_diff) * kx
    dy = (lat2 - lat1) * ky

    return (dx**2 + dy**2) ** 0.5 * circuity


def hard_round(decimal_places: int, a: [float | int]):
    """
    Function:

    - Round a number to a specified number of decimal places

    Required Arguments:

    - `decimal_places`:
        - Type: int
        - What: number of decimal places to round to
    - `a`:
        - Type: int | float
        - What: number to round
    """
    return int(a * (10**decimal_places) + (0.5 if a > 0 else -0.5)) / (
        10**decimal_places
    )


def distance_converter(
    distance: [float | int], input_units: str, output_units: str
):
    """
    Function:

    - Convert a distance from one unit to another

    Required Arguments:

    - `distance`:
        - Type: int | float
        - What: distance to convert
    - `input_units`:
        - Type: str
        - What: units of the input distance (one of "mi", "km", "m", or "ft")
    - `output_units`:
        - Type: str
        - What: units of the output distance (one of "mi", "km", "m", or "ft")
    """
    assert input_units in ["mi", "km", "m", "ft"]
    assert output_units in ["mi", "km", "m", "ft"]
    km_table = {"mi": 0.621371, "m": 1000, "ft": 3280.84, "km": 1}
    return (distance / km_table[input_units]) * km_table[output_units]


def get_line_path(output: [list, dict], filename=None):
    """
    Function:

    - Convert a `get_shortest_path` output into a GeoJSON LineString dictionary object
    - Optionally save the output to a file

    Required Arguments:

    - `output`:
        - Type: list | dict
        - What: output of `get_shortest_path`

    Optional Arguments:

    - `filename`:
        - Type: str
        - What: path to save the output to
        - Default: None
        - Note: if `filename` is not None, the output will be saved to the specified path
    """
    if isinstance(output["coordinate_path"], list):
        if output.get("long_first"):
            coordinates = output["coordinate_path"]
        else:
            coordinates = [[i[1], i[0]] for i in output["coordinate_path"]]
        linestring = {
            "type": "LineString",
            "coordinates": coordinates,
        }
    elif isinstance(output["coordinate_path"], dict):
        linestring = {
            "type": "LineString",
            "coordinates": [
                [i["longitude"], i["latitude"]]
                for i in output["coordinate_path"]
            ],
        }
    if filename:
        with open(filename, "w") as f:
            f.write(json.dumps(linestring))
    return linestring


def print_console(*args, silent: bool = False, **kwargs):
    """
    Function:

    - Print messages to the console if `silent` is False
    - This is a utility function to standardize printing behavior across the codebase

    Args:

    - `*args`: Args to pass to the print function
    - `silent`: Whether to suppress printing
        - Default: False
    - `**kwargs`: Additional keyword arguments to pass to the print function

    """
    if not silent:
        print(*args, **kwargs)


def get_lat_lon_bound_between_pts(
    origin: dict[str, int | float], destination: dict[str, int | float]
):
    """
    Function:

    - Calculate a rough bounding latitude and longitude difference given two points
    - This is the haversine distance divided by 111, which is roughly the number of kilometers per degree of latitude and longitude at the equator

    Required Arguments:

    - `origin`:
        - Type: dict
        - What: Origin point with "latitude" and "longitude" keys
    - `destination`:
        - Type: dict
        - What: Destination point with "latitude" and "longitude" keys
    """
    return (
        haversine(
            (origin["latitude"], origin["longitude"]),
            (destination["latitude"], destination["longitude"]),
            units="km",
        )
        / 111
    )
