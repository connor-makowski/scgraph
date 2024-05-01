import math, json


def haversine(
    origin: list[float, int],
    destination: list[float, int],
    units: str = "km",
    circuity: [int, float] = 1,
):
    """
    Function:

    - Calculate the great circle distance in kilometers between two points on the earth (specified in decimal degrees)

    Required Arguments:

    - `origin`:
        - Type: list of two floats | ints
        - What: The origin point as a list of "longitude" and "latitude"
    - `destination`:
        - Type: list of two floats | ints
        - What: The destination point as a list of "longitude" and "latitude"

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
    try:
        # convert decimal degrees to radians
        lon1, lat1, lon2, lat2 = map(
            math.radians,
            [
                origin[1],
                origin[0],
                destination[1],
                destination[0],
            ],
        )
        # haversine formula
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(a**0.5)
        # Set the radius of earth based on the units specified
        if units == "km":
            radius = 6371
        elif units == "m":
            radius = 6371000
        elif units == "mi":
            radius = 3959
        elif units == "ft":
            radius = 3959 * 5280
        else:
            raise ValueError('Units must be one of "km", "m", "mi", or "ft"')
        return c * radius * circuity
    except:
        print(origin, destination)
        raise Exception()


def hard_round(decimal_places: int, a: [int, float]):
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
    distance: [int, float], input_units: str, output_units: str
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
