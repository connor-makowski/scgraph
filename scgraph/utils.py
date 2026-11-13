import json
import logging
import time
import platform
import os
import warnings
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
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

logger = logging.getLogger(__name__)


def haversine(
    origin: Sequence[float],
    destination: Sequence[float],
    units: str = "km",
    circuity: float = 1,
) -> float:
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


def cheap_ruler(
    origin: Sequence[float],
    destination: Sequence[float],
    units: str = "km",
    circuity: float = 1,
) -> float:
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


def hard_round(decimal_places: int, a: float) -> float:
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
    distance: float, input_units: str, output_units: str
) -> float:
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


def get_line_path(
    output: list | dict, filename: str | os.PathLike | None = None
) -> dict:
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


def warn_deprecated(name: str, stacklevel: int = 3) -> None:
    """
    Warns that a function or a parameter is deprecated.

    - `name`: the function or the parameter, as the message names it
    - `stacklevel`: the default points the warning at the caller of the function that
      calls this one
    """
    warnings.warn(
        f"{name} is deprecated. scgraph reports its messages through the logging"
        " module (README, section Logging)",
        DeprecationWarning,
        stacklevel=stacklevel,
    )


def warn_deprecated_parameter(name: str, value: object) -> None:
    """
    Warns that the parameter `name` is deprecated, if the caller gave it.

    - `value`: the value of the parameter; None means that the caller did not give it
    """
    if value is not None:
        warn_deprecated(f"The parameter `{name}`", stacklevel=4)


@contextmanager
def log_step(
    step_logger: logging.Logger, step: str, indicators: dict | None = None
) -> Iterator[dict | None]:
    """
    Logs at DEBUG how long a step took, with indicators of its work.

    - `step_logger`: the logger of the calling module
    - `step`: what the step does, in a few words, such as "reduce the graph"
    - `indicators`: values known before the step, such as a number of nodes
    - Yields a dict that the step completes with the values it knows at its end, or
      None when DEBUG is off: nothing is then measured or logged
    - The log record keeps the indicators, `step` and `duration_ms` in its attribute
      `scgraph`, for a handler of the application
    """
    if not step_logger.isEnabledFor(logging.DEBUG):
        yield None
        return
    work = {"step": step, **(indicators or {})}
    start = time.perf_counter()
    yield work
    work["duration_ms"] = round((time.perf_counter() - start) * 1000, 3)
    step_logger.debug("%s: %s", step, work, extra={"scgraph": work})


def print_console(*args, silent: bool = False, **kwargs) -> None:
    """
    Deprecated. Logs a message at INFO, unless `silent` is true.

    - `*args`: the parts of the message, joined by spaces
    - `**kwargs`: the other arguments of `print`, which are ignored
    """
    warn_deprecated("print_console")
    if not silent:
        logger.info(" ".join(str(arg) for arg in args))


def get_lat_lon_bound_between_pts(
    origin: dict[str, int | float], destination: dict[str, int | float]
) -> float:
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


def adjacency_dict_to_list_tuples(
    graph: list[dict[int, int | float]],
) -> list[list[tuple[int, int | float]]]:
    """
    Convert a graph from adjacency dictionary representation to adjacency list representation.

    Required Arguments:

    - `graph`:
        - Type: list[dict[int, int | float]]
        - What: The input graph to convert

    Returns:

    - Type: list[list[tuple[int, int | float]]]
    - What: The converted graph in adjacency list representation
    """
    if not graph:
        return []

    return [
        [(to_id, weight) for to_id, weight in connections.items()]
        for connections in graph
    ]


def adjacency_list_tuples_to_dict(
    graph: list[list[tuple[int, int | float]]],
) -> list[dict[int, int | float]]:
    """
    Convert a graph from adjacency list representation to adjacency dictionary representation.

    Required Arguments:

    - `graph`:
        - Type: list[list[tuple[int, int | float]]]
        - What: The input graph to convert

    Returns:

    - Type: list[dict[int, int | float]]
    - What: The converted graph in adjacency dictionary representation
    """
    if not graph:
        return []

    return [
        {to_id: weight for to_id, weight in connections}
        for connections in graph
    ]


def validate(name: str, realized: object, expected: object) -> None:
    """
    Deprecated. Logs at INFO whether `realized` equals `expected`.

    - The lengths in dictionaries are rounded to 3 decimals before the comparison
    """
    warn_deprecated("validate")
    # Custom length rounding for floating point precision issues
    if isinstance(realized, dict):
        if "length" in realized:
            realized["length"] = hard_round(3, realized["length"])
    if isinstance(expected, dict):
        if "length" in expected:
            expected["length"] = hard_round(3, expected["length"])
    if realized == expected:
        logger.info("%s: PASS", name)
    else:
        logger.info(
            "%s: FAIL\nExpected: %s\nRealized: %s", name, expected, realized
        )


def time_test(
    name: str,
    function: Callable,
    args: Iterable | None = None,
    kwargs: dict | None = None,
) -> None:
    """
    Deprecated. Logs at INFO the time that `function(*args, **kwargs)` takes, in
    milliseconds.
    """
    warn_deprecated("time_test")
    if args is None:
        args = ()
    if kwargs is None:
        kwargs = {}
    start = time.perf_counter()
    function(*args, **kwargs)
    logger.info(
        "%s: %sms", name, round((time.perf_counter() - start) * 1000, 4)
    )


def has_cpp() -> bool:
    try:
        from scgraph.cpp import Graph  # noqa: F401 (the import is the check)

        return True
    except ImportError:
        return False


def cpp_check() -> None:
    """
    Deprecated. Logs at INFO which build is installed. `has_cpp()` gives the same
    answer as a boolean.
    """
    warn_deprecated("cpp_check")
    if has_cpp():
        logger.info("Using C++ & Python implementation of SCGraph.")
    else:
        logger.info("Using Pure Python implementation of SCGraph.")


def resolve_cache_dir(cache_dir: str | os.PathLike | None = None) -> Path:
    """
    The cache directory of every function that uses the cache: `cache_dir` if given, else the
    `SCGRAPH_CACHE_DIR` environment variable if set, else the platform's cache directory
    (`get_default_cache_path`).
    """
    if cache_dir is not None:
        return Path(cache_dir)
    from_environment = os.environ.get("SCGRAPH_CACHE_DIR")
    if from_environment:
        return Path(from_environment)
    return get_default_cache_path()


def get_default_cache_path() -> Path:
    system = platform.system()
    if system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = (
            Path(local_app_data)
            if local_app_data
            else Path.home() / "AppData" / "Local"
        )
        return base.joinpath("scgraph")
    elif system == "Darwin":
        return Path.home().joinpath("Library", "Caches", "scgraph")
    else:
        return Path.home().joinpath(".cache", "scgraph")
