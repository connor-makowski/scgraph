"""A small index of the nodes of a network by their position.

A build asks "which nodes are near this point?" in two places. `scgraph.helpers.osm`
joins each end of a ferry to the closest road node. `step2_hub_connectors` joins a hub to a
node of a road or of a railway. `NearNodes` answers without one Python object per
node, so it also serves the network of the world.
"""

import math
from array import array
from bisect import bisect_left, bisect_right
from collections.abc import Iterator, Sequence

from scgraph.coordinates import get_units_per_degree
from scgraph.utils import haversine


class NearNodes:
    """Find the nodes near a point, without one Python object per node.

    `latitudes` and `longitudes` are arrays of float64 degrees, or of int32 units of
    1e-7 degree, read in place. The index groups the nodes in rows of 0.2 degree of
    latitude. In a row, the nodes are sorted by longitude, and a search finds them by
    bisection.
    """

    def __init__(self, latitudes, longitudes):
        self.latitudes, self.longitudes = latitudes, longitudes
        self.rows = {}
        self.units_per_degree = units_per_degree = get_units_per_degree(
            latitudes
        )
        for i, lat in enumerate(latitudes):
            row = math.floor(lat / units_per_degree / 0.2)
            self.rows.setdefault(row, array("i")).append(i)
        for row, nodes in self.rows.items():
            self.rows[row] = array(
                "i", sorted(nodes, key=longitudes.__getitem__)
            )

    def find_within(
        self, point: Sequence[float], km: float
    ) -> Iterator[tuple[float, int]]:
        """Yield `(km, node)` for each node within `km` of `point`, a `[latitude, longitude]`
        pair in degrees.
        """
        lat, lon = point
        dlat = km / 110  # degrees: more than `km` (111.2 km per degree)
        cos = math.cos(math.radians(min(90, abs(lat) + dlat)))
        if cos < 1e-9 or (dlon := km / (110 * cos)) >= 180:
            spans = [(-180, 180)]
        else:  # around the antimeridian, two spans
            spans = [(lon - dlon, lon + dlon)]
            spans += [(w + 360, e + 360) for w, e in spans if w < -180]
            spans += [(w - 360, e - 360) for w, e in spans[:1] if e > 180]
        latitudes, longitudes = self.latitudes, self.longitudes
        units_per_degree = self.units_per_degree

        def key(i):
            return longitudes[i] / units_per_degree  # degrees (x / 1 == x)

        for row in range(
            math.floor((lat - dlat) / 0.2), math.floor((lat + dlat) / 0.2) + 1
        ):
            nodes = self.rows.get(row, ())
            for west, east in spans:
                lo, hi = bisect_left(nodes, west, key=key), bisect_right(
                    nodes, east, key=key
                )
                for i in nodes[lo:hi]:
                    d = haversine(
                        point,
                        [
                            latitudes[i] / units_per_degree,
                            longitudes[i] / units_per_degree,
                        ],
                    )
                    if d <= km:
                        yield d, i

    def find_closest(
        self, point: Sequence[float], km: float
    ) -> tuple[float, int | None]:
        """Return `(km, node)` for the node closest to `point` within `km`, or
        `(inf, None)` when there is none. When two nodes are as near, the lower one is
        returned.
        """
        return min(self.find_within(point, km), default=(math.inf, None))
