"""Sea lanes of Eurostat SeaRoute at 5 km resolution, with the lanes cut at the
antimeridian joined and the Arctic passages left out.

Eurostat stores the ends of a lane cut at the antimeridian twice, at -180 and at 180:
-180 becomes 180. The lines whose `pass` is `northeast` or `northwest` (Northern Sea
Route, Northwest Passage) are dropped: no query can avoid a passage yet, and these are
open only part of the year.

`build_sea_lane_arrays` gives the same network as arrays, with the class of each arc, for a
pipeline that joins the sea lanes to other modes. The class of an arc is the `pass` of
its lane, for example `suez`. It is `open_sea` for a lane outside a passage.
"""

import contextlib
import json
import struct
from array import array

from scgraph.geograph import GeoGraph
from scgraph.helpers.geojson import format_coord_list
from scgraph.pipelines import CLASS_ROWS
from scgraph.pipelines.steps import step3_network_assembly

PIPELINE_VERSION = 1

SOURCES = {
    "sea_lanes": {
        "url": "https://raw.githubusercontent.com/eurostat/searoute/88a2e568a8e0144d1f5a81c3931a7bc2bcce6901/modules/core/src/main/resources/marnet/marnet_plus_5km.gpkg",
        "credit": "Eurostat, SeaRoute maritime network (from the Oak Ridge National Laboratory Global Shipping Lane Network, 2000, enriched with AIS-based lines around European coasts)",
        "license": "EUPL-1.2",
        "license_url": "https://github.com/eurostat/searoute/blob/88a2e568a8e0144d1f5a81c3931a7bc2bcce6901/LICENSE",
    }
}
# The decimal places that the coordinates of the lanes are rounded to: about 1 m
COORDINATE_DECIMALS = 5


def _read_lines(files):
    """Return the lines of the source file as pairs `(line, passage)`, without the
    lines of the Arctic passages. A "line" is a row of the source file: a part of a
    lane, as a GeoJSON LineString. `passage` is the `pass` of the line, or None.
    """
    import sqlite3  # optional in a Python build: only the networks of Eurostat lanes need it

    with contextlib.closing(sqlite3.connect(files["sea_lanes"])) as database:
        rows = database.execute('select geometry, pass from "type"').fetchall()
    lines = []
    for geometry, passage in rows:
        if passage in ("northeast", "northwest"):
            continue
        # Every row of the pinned file: a GeoPackage header with a 32-byte envelope
        # (40 bytes), then a big-endian WKB LineString
        (count,) = struct.unpack_from(">I", geometry, 45)
        xy = struct.unpack_from(f">{2 * count}d", geometry, 49)
        line = {
            "type": "LineString",
            "coordinates": [
                [180.0 if x == -180 else x, y]
                for x, y in zip(xy[::2], xy[1::2])
            ],
        }
        lines.append((line, passage))
    return lines


def build(files: dict[str, str]) -> GeoGraph:
    lines = [line for line, _ in _read_lines(files)]
    geojson = files["sea_lanes"] + ".geojson"
    with open(geojson, "w") as file:
        json.dump({"type": "GeometryCollection", "geometries": lines}, file)
    return GeoGraph.load_from_geojson(geojson, precision=COORDINATE_DECIMALS)


def build_sea_lane_arrays(files: dict[str, str]) -> dict[str, array]:
    """Build the sea lanes as the arrays of a graph, with the class of each arc.

    The nodes and the arcs are those of the GeoGraph that `build` returns. The nodes
    are in the order of the GeoGraph. The arcs of a node are sorted by head. `build`
    makes one arc each way between two consecutive points of a lane. The two arcs have
    the class of the lane.

    Example: a lane with the `pass` value `suez` has the points A, B and C. The arcs
    A-B, B-A, B-C and C-B have the class `suez`.

    Args:
        files: The path of the downloaded file of the source `sea_lanes`.

    Returns:
        The graph as a dict of arrays, as `step3_network_assembly.build_graph_from_pieces` returns
        it, with `arc_classes`. The arcs have no shape points.
    """
    sea = build(files)

    def to_units(
        point,
    ):  # a [latitude, longitude] point, in units of 1e-7 degree
        return round(point[0] * 1e7), round(point[1] * 1e7)

    # The class row of an arc, by the points of its two ends. `load_from_geojson`
    # rounds each point of a lane with `format_coord_list`. No segment of the pinned
    # file is in two lines of different passages.
    class_row_of_arc = {}
    for line, passage in _read_lines(files):
        points = [
            to_units(format_coord_list(lon_lat, COORDINATE_DECIMALS)[::-1])
            for lon_lat in line["coordinates"]
        ]
        class_row = CLASS_ROWS[passage or "open_sea"]
        for a, b in zip(points, points[1:]):
            class_row_of_arc[a, b] = class_row_of_arc[b, a] = class_row
    offsets, heads, weights = (
        step3_network_assembly.build_csr_from_adjacency_list(
            sea.graph_object.graph
        )
    )
    points = [to_units(point) for point in sea.nodes]
    return {
        "offsets": offsets,
        "heads": heads,
        "weights": weights,
        "node_points": array("i", (x for point in points for x in point)),
        "shape_offsets": array("i", bytes(4 * (len(heads) + 1))),
        "shape_points": array("i"),
        "node_ids": array("q", sea.node_ids),
        "arc_classes": array(
            "B",
            (
                class_row_of_arc[points[u], points[v]]
                for u in range(len(points))
                for v in heads[offsets[u] : offsets[u + 1]]
            ),
        ),
    }


# The kind `sea_distances` measures between ports. This network has no port
# node, so that kind is checked on the network of `osm_world_multimodal`.
VALIDATION = {
    "cases": ["passages", "rotterdam_to_new_york", "rotterdam_to_singapore"],
}
