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
import struct
from array import array

from scgraph import network_assembly
from scgraph.coordinates import (
    encode_coordinate,
    get_coordinate_dtype_for_precision,
)
from scgraph.edge_classes import CLASS_IDS, CLASSES
from scgraph.geograph import GeoGraph
from scgraph.geograph_io import renumber_in_hilbert_order
from scgraph.helpers.geojson import format_coord_list
from scgraph.utils import hard_round, haversine

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


def _read_lane_graph(files):
    """Return the graph of the lines, with the nodes in the order of their first
    point in the lines.

    Each point of a line is rounded to COORDINATE_DECIMALS decimals, as
    `GeoGraph.load_from_geojson` rounds it. The points with the same rounded value
    are one node. Two consecutive points that differ give one edge each way, with
    their great-circle distance in km, rounded to 3 decimals. The edge has the class
    of its line.

    Example: two lines meet at the point (36.000001, 14.5). Both lines round it to
    (36.0, 14.5), so they share one node there.

    Returns:
        `(points, weights, class_ids)`. `points` holds the `[latitude, longitude]`
        of each node, in degrees. `weights[u]` gives the km of the edge from node `u`
        to each of its neighbours, and `class_ids[u]` gives the class id of this
        edge. The neighbours of a node are in the order in which the lines reach
        them, as in `load_from_geojson`.
    """
    node_ids = {}  # the node id of each rounded point
    points, weights, class_ids = [], [], []
    for line, passage in _read_lines(files):
        rounded = []
        for lon_lat in line["coordinates"]:
            point = format_coord_list(lon_lat, COORDINATE_DECIMALS)[::-1]
            if not rounded or point != rounded[-1]:
                rounded.append(point)
        if len(rounded) < 2:  # a line that rounds to one point gives no edge
            continue
        nodes = []
        for point in rounded:
            node_id = node_ids.setdefault(tuple(point), len(points))
            if node_id == len(points):
                points.append(point)
                weights.append({})
                class_ids.append({})
            nodes.append(node_id)
        class_id = CLASS_IDS[passage or "open_sea"]
        for a, b in zip(nodes, nodes[1:]):
            # Each direction has its own haversine, as in `load_from_geojson`
            weights[a][b] = hard_round(3, haversine(points[a], points[b]))
            weights[b][a] = hard_round(3, haversine(points[b], points[a]))
            class_ids[a][b] = class_ids[b][a] = class_id
    return points, weights, class_ids


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
    points, weights, class_ids = _read_lane_graph(files)
    sea = renumber_in_hilbert_order(
        GeoGraph(
            graph=weights,
            nodes=points,
            coordinate_dtype=get_coordinate_dtype_for_precision(
                COORDINATE_DECIMALS
            ),
        )
    )
    # `external_node_ids` gives the node id of each node before the Hilbert order
    old_ids = list(sea.external_node_ids)
    new_id = {old_id: node_id for node_id, old_id in enumerate(old_ids)}
    class_names = list(CLASSES)
    # The same graph and the same nodes, with the class of each edge
    return GeoGraph(
        graph=sea.graph_object,
        nodes=sea.nodes,
        external_node_ids=old_ids,
        coordinate_dtype=sea.coordinate_dtype,
        classes=[
            {"name": name, "edge_mode": edge_mode}
            for name, edge_mode in CLASSES.items()
        ],
        edge_classes=[
            {new_id[v]: class_names[c] for v, c in class_ids[old_id].items()}
            for old_id in old_ids
        ],
    )


def build_sea_lane_arrays(files: dict[str, str]) -> dict[str, array]:
    """Build the sea lanes as the arrays of a graph, for a pipeline that joins them
    to other networks.

    The nodes and the edges are those of the GeoGraph that `build` returns, with
    the nodes in the same order. The edges of a node are sorted by destination id.

    Args:
        files: The path of the downloaded file of the source `sea_lanes`.

    Returns:
        The graph as a dict of arrays, as `network_assembly.build_graph_from_pieces` returns
        it, with `edge_class_ids`. The edges have no shape points.
    """
    points, weights, class_ids = _read_lane_graph(files)
    node_first_edge_ids, edge_destination_node_ids, metric_length = (
        network_assembly.build_csr_from_adjacency_list(weights)
    )
    graph = {
        "node_first_edge_ids": node_first_edge_ids,
        "edge_destination_node_ids": edge_destination_node_ids,
        "metric_length": metric_length,
        "node_points": array(
            "i", (encode_coordinate(x) for point in points for x in point)
        ),
        "edge_first_shape_point_ids": array(
            "i", bytes(4 * (len(edge_destination_node_ids) + 1))
        ),
        "shape_points": array("i"),
        "external_node_ids": array("q", range(len(points))),
        "edge_class_ids": array(
            "B",
            (
                class_ids[u][v]
                for u in range(len(points))
                for v in sorted(class_ids[u])
            ),
        ),
    }
    # The Hilbert order of `build`, which `order_nodes` also gives
    return network_assembly.order_nodes(graph)


# The kind `sea_distances` measures between ports. This network has no port
# node, so that kind is checked on the network of `osm_world_multimodal`.
VALIDATION = {
    "cases": ["passages", "rotterdam_to_new_york", "rotterdam_to_singapore"],
}
