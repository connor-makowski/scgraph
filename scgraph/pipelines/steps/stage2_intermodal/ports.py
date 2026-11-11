"""Join ports to two networks: a straight road connector checked against water, and a
sea connector over water (`landmask`)."""

import csv
import logging
import math
from array import array

import requests

from scgraph.pipelines.steps.stage3_assembly.assembly import (
    NearNodes,
    PieceArrays,
    build_graph_from_pieces,
    strongly_connected_components,
)
from scgraph.utils import haversine

logger = logging.getLogger(__name__)

ROAD_KM, SEA_KM = 20, 2500  # longest road and sea connectors
# Water a road connector may cross: 3 km, 10 km for an open roadstead
WATER_KM, ROADSTEAD_WATER_KM = 3, 10
CIRCUITY = 1.2  # of a straight road connector


def download(url: str, filename: str) -> dict:
    """Download World Port Index data as CSV, falling back to NGA's ArcGIS service if direct download fails."""
    from scgraph.pipelines import download_file

    try:
        download_file(url, filename)
        return {}
    except requests.HTTPError as err:
        if err.response is None or err.response.status_code not in (
            500,
            502,
            503,
            504,
        ):
            raise
        logger.warning(
            "NGA MSI portal returned HTTP %s, falling back to official ArcGIS WPI service",
            err.response.status_code,
        )
        base_url = "https://services.arcgis.com/hRUr1F8lE8Jq2uJo/arcgis/rest/services/World_Port_Index/FeatureServer/0/query"
        features, offset = [], 0
        while True:
            params = {
                "where": "1=1",
                "outFields": "LATITUDE,LONGITUDE,HARBORTYPE",
                "f": "json",
                "resultOffset": offset,
                "resultRecordCount": 2000,
            }
            resp = requests.get(base_url, params=params, timeout=30)
            resp.raise_for_status()
            page = resp.json().get("features", [])
            if not page:
                break
            features.extend(page)
            offset += len(page)
        with open(filename, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["Latitude", "Longitude", "Harbor Type"])
            for feat in features:
                attrs = feat.get("attributes", {})
                lat, lon = attrs.get("LATITUDE"), attrs.get("LONGITUDE")
                if lat is not None and lon is not None:
                    writer.writerow(
                        [lat, lon, attrs.get("HARBORTYPE") or "Unknown"]
                    )
        return {"version": "ArcGIS-WPI"}


def world_port_index(filename):
    """[latitude, longitude, harbour type] of each port with a position in the CSV file
    of the World Port Index."""
    with open(filename, newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            if row["Latitude"] and row["Longitude"]:
                lat, lon = float(row["Latitude"]), float(row["Longitude"])
                yield [lat, lon, row["Harbor Type"]]


def join(road_graph, sea_network, port_records, land_mask, work_dir=None):
    """
    `road_graph` (`assembly.road_graph`'s layout) joined to the sea lanes of the GeoGraph `sea_network`
    at the ports of `port_records` ([latitude, longitude, harbour type]) that have both
    connectors, on node indices: the sea nodes follow the road nodes, then the ports, each
    in their order; `node_modes` 0 for a road node, 1 for a port, 2 for a sea node; the
    ports' `node_ids` are scgraph's (negative). The drawings are kept as they are (the
    roads' were simplified when cut). Returns `(graph, ports joined)`; empties `road_graph`
    and releases the raster of `land_mask`, spent.
    With a `work_dir`, the arcs are kept in files there (`PieceArrays`).
    """
    offsets, heads, weights = (
        road_graph["offsets"],
        road_graph["heads"],
        road_graph["weights"],
    )
    starts, line = road_graph["shape_offsets"], road_graph["shape_points"]
    labels, sizes = strongly_connected_components(offsets, heads)
    components = array("i", (sizes[label] for label in labels))
    roads, seas = len(offsets) - 1, len(sea_network.nodes)
    # The road nodes' coordinates at 1e-7 degree, read in place
    lats, lons = road_graph["latitudes"], road_graph["longitudes"]
    near = NearNodes(lats, lons, scale=1e-7)
    others = list(sea_network.nodes)  # then the ports, in degrees
    cells = {}  # mask cell -> its first sea node
    for s, node in enumerate(sea_network.nodes):
        cells.setdefault(land_mask.cell(*node), s)
    cells.pop(None, None)
    targets = array("q", sorted(cells))
    # Every arc, one way, on node indices
    pieces = PieceArrays(tolerance_meters=None, work_dir=work_dir)

    def at(u):  # [latitude, longitude] of node u
        if u < roads:
            return [lats[u] * 1e-7, lons[u] * 1e-7]
        return others[u - roads]

    def add(u, v, km, shape):
        pieces.append(u, v, km, 1, [at(u), at(v)], shape)

    for u in range(roads):
        for a in range(offsets[u], offsets[u + 1]):
            points = line[2 * starts[a] : 2 * starts[a + 1]]
            shape = [
                [x * 1e-7, y * 1e-7] for x, y in zip(points[::2], points[1::2])
            ]
            add(u, heads[a], weights[a], shape)
    sea_shapes = sea_network.intermediate_nodes or [{}] * seas
    for u, row in enumerate(sea_network.graph_object.graph):
        for v, km in row.items():
            add(roads + u, roads + v, km, sea_shapes[u].get(v, []))
    for point, arcs in port_connectors(
        port_records,
        lambda port: road_connector(port, near, components, land_mask),
        lambda point: sea_connector(
            point, targets, cells, sea_network.nodes, land_mask
        ),
        roads + seas,
        roads,
    ):
        others.append(point)
        for a, b, km, shape in arcs:
            add(a, b, km, shape)
    ports = len(others) - seas
    ids = array("q", road_graph["node_ids"]) + array("q", sea_network.node_ids)
    road_graph.clear()  # freed before the joined graph is built, and the raster
    land_mask.bits = None
    del lats, lons, near, labels, sizes, components
    del offsets, heads, weights, starts, line
    joined = build_graph_from_pieces(pieces)
    ids += array("q", range(-1, -1 - ports, -1))  # scgraph's, for the ports
    modes = bytes(roads) + bytes([2]) * seas + bytes([1]) * ports
    joined["node_modes"] = array("B", (modes[u] for u in joined["node_ids"]))
    joined["node_ids"] = array("q", (ids[u] for u in joined["node_ids"]))
    return joined, ports


def port_connectors(
    port_records,
    road_connector_fn,
    sea_connector_fn,
    first_port_id,
    first_sea_id,
):
    """`(point, arcs)` of each port of `port_records` ([latitude, longitude, harbour type]) with
    a road connector, `road_connector_fn(port)` -> `(road node, km)`, and a sea connector,
    `sea_connector_fn(point)` -> `(sea node, km, path)` (None if none), ports numbered from
    `first_port_id`, sea nodes from `first_sea_id`. `arcs`: `(origin, destination, km, shape)`
    both ways, 1.2 times the straight line to the road, the water path to the sea.
    """
    p = first_port_id
    for port in port_records:
        to_road = road_connector_fn(port)
        to_sea = to_road and sea_connector_fn(port[:2])
        if to_sea:
            (u, road_km), (s, sea_km, path) = to_road, to_sea
            road_km, s = CIRCUITY * road_km, first_sea_id + s
            yield port[:2], [
                (p, u, road_km, []),
                (u, p, road_km, []),
                (p, s, sea_km, path),
                (s, p, sea_km, path[::-1]),
            ]
            p += 1


def road_connector(port_record, road_spatial_index, component_sizes, land_mask):
    """
    `(road node, km)`: the road connector of `port_record` ([latitude, longitude, harbour type]),
    or None. `road_spatial_index`: the road nodes' `assembly.NearNodes`; `component_sizes`: the size of each
    node's strongly connected component.
    """
    point = port_record[:2]
    water_km = (
        ROADSTEAD_WATER_KM if port_record[2] == "Open Roadstead" else WATER_KM
    )
    # Largest component first, then nearest
    for _, km, i in sorted(
        (-component_sizes[i], km, i)
        for km, i in road_spatial_index.within(point, ROAD_KM)
    ):
        target = [
            road_spatial_index.lats[i] * road_spatial_index.scale,
            road_spatial_index.lons[i] * road_spatial_index.scale,
        ]
        if _water_km(land_mask, point, target, km) < water_km:
            return i, km
    return None


def sea_connector(
    port_coords, sea_cell_targets, cell_to_sea_node, sea_node_coords, land_mask
):
    """`(sea node, km, path)`: the sea connector of `port_coords`, or None. `sea_cell_targets`: the mask
    cells of the sea nodes, sorted in an array('q'); `cell_to_sea_node`: {cell: sea node}.
    """
    found = land_mask.water_path(port_coords, sea_cell_targets, SEA_KM)
    if not found:
        return None
    km, path = found
    s = cell_to_sea_node[land_mask.cell(*path[-1])]
    return s, km + haversine(path[-1], sea_node_coords[s]), path


def _water_km(land_mask, point_a, point_b, distance_km):
    """km of water along the straight line point_a-point_b (`distance_km` long), sampled every 0.25 km."""
    n = max(1, math.ceil(distance_km / 0.25))
    water = sum(
        not land_mask.on_land(
            *(x + (j + 0.5) / n * (y - x) for x, y in zip(point_a, point_b))
        )
        for j in range(n)
    )
    return distance_km * water / n
