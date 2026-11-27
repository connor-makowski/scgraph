"""The integer form of a coordinate, and its conversion to degrees and back.

The integer form stores a coordinate as an int32 number of units of 1e-7 degree. This
is the form of OpenStreetMap, and one unit is about 1 cm. `load_from_osm` and the
pipelines build their points in this form, the snapping index reads it, and a network
file may store it.

This module is internal. Every conversion between degrees and units uses its
functions, or divides by `UNITS_PER_DEGREE` in a hot loop. Two formulas would give two
floats for one stored value: `value * 1e-7` and `value / 1e7` differ for about 3 values
in 10.

Example: the stored value -1222909963 is -122.2909963 degrees.
"""

import math
from array import array
from collections.abc import Sequence

# The units of one degree in the integer form
UNITS_PER_DEGREE = 1e7
# The types of a stored coordinate: int32 units of 1e-7 degree, or float64 degrees
COORDINATE_DTYPES = ("int32", "float64")


def encode_coordinates(
    point_arrays: Sequence[Sequence[float]], dtype: str
) -> list[Sequence[float]]:
    """Return arrays of points in the form that a network file stores.

    Args:
        point_arrays: Arrays of points, in float64 degrees.
        dtype: "float64" keeps the arrays as they are. "int32" converts each value to
            units of 1e-7 degree and rounds it. This is the encoding of OpenStreetMap,
            and one unit is about 1 cm.

    Returns:
        One array for each array of `point_arrays`, in `dtype`.

    Raises:
        ValueError: `dtype` is not one of the two names, a value is not a finite
            number, or an int32 value is beyond ±214.7483647 degrees.
    """
    if dtype not in COORDINATE_DTYPES:
        raise ValueError(
            f"coordinate_dtype must be 'float64' or 'int32', not {dtype!r}"
        )
    if dtype == "int32":
        try:
            return [
                array("i", (round(x * UNITS_PER_DEGREE) for x in v))
                for v in point_arrays
            ]
        # Not finite, or beyond the int32 range
        except (OverflowError, ValueError):
            raise ValueError(
                "Coordinates stored as int32 must be finite numbers within"
                " ±214.7483647 degrees"
            ) from None
    if not all(all(map(math.isfinite, values)) for values in point_arrays):
        raise ValueError("Coordinates must be finite numbers")
    return list(point_arrays)


def get_coordinate_dtype_for_precision(precision: int) -> str:
    """Return the type that stores a coordinate rounded to `precision` decimals
    without a loss: "int32" up to 7 decimals, because one unit is 1e-7 degree, and
    "float64" above."""
    return "int32" if precision <= 7 else "float64"


def encode_coordinate(degrees: float) -> int:
    """Return one coordinate in degrees as units of 1e-7 degree, rounded."""
    return round(degrees * UNITS_PER_DEGREE)


def decode_coordinate(units: int) -> float:
    """Return the degrees of one coordinate in units of 1e-7 degree."""
    return units / UNITS_PER_DEGREE


def decode_coordinates(units: array | memoryview) -> array:
    """Return the float64 degrees of an array of coordinates in units of 1e-7
    degree. The loop runs in C."""
    return array("d", map(UNITS_PER_DEGREE.__rtruediv__, units))


def get_units_per_degree(values: array | memoryview) -> float:
    """Return the units of one degree in an array of coordinates: 1e7 for int32
    values, and 1 for float64 degrees."""
    return UNITS_PER_DEGREE if memoryview(values).format == "i" else 1.0
