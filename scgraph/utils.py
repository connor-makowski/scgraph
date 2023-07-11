import math


class Distance:
    @classmethod
    def haversine(
        self,
        origin: dict,
        destination: dict,
        units: str = "km",
        circuity: [float, int] = 1,
    ):
        """
        Function:

        - Calculate the great circle distance in kilometers between two points on the earth (specified in decimal degrees)

        Required Arguments:

        - `origin`:
            - Type: dict
            - What: is the origin point? (dict with keys "longitude" and "latitude")
        - `destination`:
            - Type: dict
            - What: is the destination point? (dict with keys "longitude" and "latitude")

        Optional Arguments:

        - `units`:
            - Type: str
            - What: units to return the distance in? (one of "km", "m", "mi", or "ft")
            - Default: "km"
        - `circuity`:
            - Type: float | int
            - What: Multiplier to increase the calculated distance (to account for circuity)
            - Default: 1

        """
        # convert decimal degrees to radians
        lon1, lat1, lon2, lat2 = map(
            math.radians,
            [
                origin["longitude"],
                origin["latitude"],
                destination["longitude"],
                destination["latitude"],
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


def hardRound(decimal_places, a):
    """
    Function:

    - Round a number to a specified number of decimal places

    Required Arguments:

    - `decimal_places`:
        - Type: int
        - What: number of decimal places to round to
    - `a`:
        - Type: float | int
        - What: number to round
    """
    return int(a * (10**decimal_places) + (0.5 if a > 0 else -0.5)) / (
        10**decimal_places
    )
