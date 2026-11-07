"""Sea lanes of Eurostat SeaRoute at 5 km resolution, with the lanes cut at the
antimeridian joined and the Arctic passages left out.

Eurostat stores the ends of a lane cut at the antimeridian twice, at -180 and at 180:
-180 becomes 180. The lines whose `pass` is `northeast` or `northwest` (Northern Sea
Route, Northwest Passage) are dropped: no query can avoid a passage yet, and these are
open only part of the year.
"""

import contextlib
import json
import struct

from scgraph.geograph import GeoGraph

PIPELINE_VERSION = 1

SOURCES = {
    "lines": {
        "url": "https://raw.githubusercontent.com/eurostat/searoute/88a2e568a8e0144d1f5a81c3931a7bc2bcce6901/modules/core/src/main/resources/marnet/marnet_plus_5km.gpkg",
        "credit": "Eurostat, SeaRoute maritime network (from the Oak Ridge National Laboratory Global Shipping Lane Network, 2000, enriched with AIS-based lines around European coasts)",
        "license": "EUPL-1.2",
        "license_url": "https://github.com/eurostat/searoute/blob/88a2e568a8e0144d1f5a81c3931a7bc2bcce6901/LICENSE",
    }
}


def build(files):
    import sqlite3  # optional in a Python build: only this network needs it

    with contextlib.closing(sqlite3.connect(files["lines"])) as database:
        rows = database.execute('select geometry, pass from "type"').fetchall()
    lines = []
    for geometry, passage in rows:
        if passage in ("northeast", "northwest"):
            continue
        # Every row of the pinned file: a GeoPackage header with a 32-byte envelope
        # (40 bytes), then a big-endian WKB LineString
        (count,) = struct.unpack_from(">I", geometry, 45)
        xy = struct.unpack_from(f">{2 * count}d", geometry, 49)
        lines.append(
            {
                "type": "LineString",
                "coordinates": [
                    [180.0 if x == -180 else x, y]
                    for x, y in zip(xy[::2], xy[1::2])
                ],
            }
        )
    geojson = files["lines"] + ".geojson"
    with open(geojson, "w") as file:
        json.dump({"type": "GeometryCollection", "geometries": lines}, file)
    return GeoGraph.load_from_geojson(geojson, precision=5, silent=True)
