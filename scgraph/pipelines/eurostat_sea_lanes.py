"""Sea lanes of Eurostat SeaRoute at 5 km resolution, with the lanes cut at the
antimeridian joined and the Arctic passages left out.

Eurostat stores the ends of a lane cut at the antimeridian twice, at -180 and at 180:
-180 becomes 180. The lines whose `pass` is `northeast` or `northwest` (Northern Sea
Route, Northwest Passage) are dropped: no query can avoid a passage yet, and these are
open only part of the year.

The class of an edge is the `pass` of its lane, for example `suez`. It is `open_sea`
for a lane outside a passage.

`build_sea_lane_arrays` gives the same network as the arrays of a graph, for a pipeline
that joins the sea lanes to other networks.
"""

import contextlib
import json
import struct
from array import array

from scgraph.geograph import GeoGraph
from scgraph.helpers.geojson import format_coord_list
from scgraph.pipelines import CLASS_IDS, CLASSES
from scgraph.pipelines.steps import step3_network_assembly

PIPELINE_VERSION = 4

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
    """Build the sea lanes as a GeoGraph, with the class of each edge.

    A lane gives one node for each of its points, and one edge each way between two
    consecutive points. The two edges have the class of the lane.

    Example: a lane with the `pass` value `suez` has the points A, B and C. The edges
    A-B, B-A, B-C and C-B have the class `suez`.

    Args:
        files: The path of the downloaded file of the source `sea_lanes`.

    Returns:
        The GeoGraph of the lanes.
    """
    lines = _read_lines(files)
    geojson = files["sea_lanes"] + ".geojson"
    with open(geojson, "w") as file:
        json.dump(
            {
                "type": "GeometryCollection",
                "geometries": [line for line, _ in lines],
            },
            file,
        )
    sea = GeoGraph.load_from_geojson(geojson, precision=COORDINATE_DECIMALS)
    # The name of the class of each edge, by its two nodes. A node is found by its
    # point: `load_from_geojson` rounds each point of a lane with
    # `format_coord_list`. No segment of the pinned file is in two lines of
    # different passages.
    node_of_point = {
        _convert_to_e7_degrees(point): node_id
        for node_id, point in enumerate(sea.nodes)
    }
    edge_class_names = [{} for _ in sea.nodes]
    for line, passage in lines:
        nodes = [
            node_of_point[
                _convert_to_e7_degrees(
                    format_coord_list(lon_lat, COORDINATE_DECIMALS)[::-1]
                )
            ]
            for lon_lat in line["coordinates"]
        ]
        for a, b in zip(nodes, nodes[1:]):
            edge_class_names[a][b] = edge_class_names[b][a] = (
                passage or "open_sea"
            )
    # The same graph and the same nodes, with the class of each edge
    return GeoGraph(
        graph=sea.graph_object,
        nodes=sea.nodes,
        external_node_ids=list(sea.external_node_ids),
        coordinate_dtype=sea.coordinate_dtype,
        classes=[
            {"name": name, "edge_mode": edge_mode}
            for name, edge_mode in CLASSES.items()
        ],
        edge_classes=edge_class_names,
    )


def _convert_to_e7_degrees(point):
    # A [latitude, longitude] point, in units of 1e-7 degree
    return round(point[0] * 1e7), round(point[1] * 1e7)


def build_sea_lane_arrays(files: dict[str, str]) -> dict[str, array]:
    """Build the sea lanes as the arrays of a graph, for a pipeline that joins them
    to other networks.

    The nodes and the edges are those of the GeoGraph that `build` returns, with
    the nodes in the same order. The edges of a node are sorted by destination id.

    Args:
        files: The path of the downloaded file of the source `sea_lanes`.

    Returns:
        The graph as a dict of arrays, as `step3_network_assembly.build_graph_from_pieces` returns
        it, with `edge_class_ids`. The edges have no shape points.
    """
    sea = build(files)
    class_id_of_edge = {
        (edge["origin_id"], edge["destination_id"]): CLASS_IDS[
            edge["edge_class"]
        ]
        for edge in sea.get_edges()
    }
    node_first_edge_ids, edge_destination_node_ids, weights = (
        step3_network_assembly.build_csr_from_adjacency_list(
            sea.graph_object.graph
        )
    )
    return {
        "node_first_edge_ids": node_first_edge_ids,
        "edge_destination_node_ids": edge_destination_node_ids,
        "metric_length": weights,
        "node_points": array(
            "i",
            (x for point in sea.nodes for x in _convert_to_e7_degrees(point)),
        ),
        "edge_first_shape_point_ids": array(
            "i", bytes(4 * (len(edge_destination_node_ids) + 1))
        ),
        "shape_points": array("i"),
        "external_node_ids": array("q", sea.external_node_ids),
        "edge_class_ids": array(
            "B",
            (
                class_id_of_edge[u, v]
                for u in range(len(sea.nodes))
                for v in edge_destination_node_ids[
                    node_first_edge_ids[u] : node_first_edge_ids[u + 1]
                ]
            ),
        ),
    }


# The kind `sea_distances` measures between ports. This network has no port
# node, so that kind is checked on the network of `osm_world_multimodal`.
VALIDATION = {
    "cases": ["passages", "rotterdam_to_new_york", "rotterdam_to_singapore"],
}
