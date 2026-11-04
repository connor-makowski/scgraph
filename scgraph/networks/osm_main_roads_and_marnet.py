"""Main roads of an OpenStreetMap extract from Geofabrik joined to the sea lanes of `marnet`
at the ports of the World Port Index, for example `region="europe/portugal"`.

A port joins the two networks only if it has a road node within 20 km and a sea node within
250 km; each connector is a straight line, 1.2 times the great-circle distance. Nodes are
stored by mode (roads, then ports, then sea), recorded as `node_modes` in the manifest.
Connectors are not checked against land and water: a sea connector of an inland port crosses
land.
"""

import csv

from scgraph.networks import marnet, osm_main_roads
from scgraph.utils import haversine

# Small sources first: a failure then costs no new download of the extract
# Follows the versions of the two builds it reuses
VERSION = 1 + marnet.VERSION + osm_main_roads.VERSION

SOURCES = {
    "sea": marnet.SOURCES["lines"],
    "ports": {
        "url": "https://msi.nga.mil/api/publications/download?type=view&key=16920959/SFH00000/UpdatedPub150.csv",
        "credit": "National Geospatial-Intelligence Agency, World Port Index (Pub. 150)",
        "license": "NOASSERTION",
        "license_url": "https://msi.nga.mil/Publications/WPI",
    },
    "roads": osm_main_roads.SOURCES["roads"],
}
MAX_KM = {"road": 20, "sea": 250}

download = osm_main_roads.download  # for every source: checks osmium first


def build(files):
    roads = osm_main_roads.build({"roads": files["roads"]})
    sea = marnet.build({"lines": files["sea"]})
    ports = [
        port
        for port in _ports(files["ports"])
        if _km_to_network(roads, port) <= MAX_KM["road"]
        and _km_to_network(sea, port) <= MAX_KM["sea"]
    ]
    road_nodes = len(roads.nodes)
    roads.merge_with_other_geograph(sea, connection_nodes=ports)
    modes = {
        "road": [0, road_nodes],
        "port": [road_nodes, road_nodes + len(ports)],
        "sea": [road_nodes + len(ports), len(roads.nodes)],
    }
    return roads, {"node_modes": modes}


def _ports(filename):
    with open(filename, newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            if (
                row["Latitude"] and row["Longitude"]
            ):  # skip ports without a position
                yield [float(row["Latitude"]), float(row["Longitude"])]


def _km_to_network(geograph, point):
    return haversine(
        point, geograph.nodes[geograph.geokdtree.closest_idx(point)]
    )
