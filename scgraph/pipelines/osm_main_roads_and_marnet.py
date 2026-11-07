"""Main roads of an OpenStreetMap extract from Geofabrik joined to the sea lanes of `marnet`
at the ports of the World Port Index, for example `region="europe/portugal"`.

A port joins the two networks only if it has a road node within 20 km and a sea node within
250 km; each connector is a straight line, 1.2 times the great-circle distance. Each node
has its mode, `road`, `port` or `sea` (`node_modes`, rows of `modes`), each mode citing the
source of its node ids.
Connectors are not checked against land and water: a sea connector of an inland port crosses
land.
"""

import csv

from scgraph.pipelines import marnet, osm_main_roads
from scgraph.pipelines.steps import osm
from scgraph.utils import haversine

# Small sources first: a failure then costs no new download of the extract
# Follows the versions of the two builds it reuses
PIPELINE_VERSION = 2 + marnet.PIPELINE_VERSION + osm_main_roads.PIPELINE_VERSION

SOURCES = {
    "sea": marnet.SOURCES["lines"],
    "ports": {
        "url": "https://msi.nga.mil/api/publications/download?type=view&key=16920959/SFH00000/UpdatedPub150.csv",
        "credit": "National Geospatial-Intelligence Agency, World Port Index (Pub. 150)",
        "license": "NOASSERTION",
        "license_url": "https://msi.nga.mil/Publications/WPI",
    },
    "roads": osm.GEOFABRIK,
}
MAX_KM = {"road": 20, "sea": 250}

download = osm.download  # for every source: checks osmium first


def build(files):
    roads = osm_main_roads.build({"roads": files["roads"]})
    sea = marnet.build({"lines": files["sea"]})
    ports = [
        port
        for port in _ports(files["ports"])
        if _km_to_network(roads, port) <= MAX_KM["road"]
        and _km_to_network(sea, port) <= MAX_KM["sea"]
    ]
    # Port nodes are created here: their ids are scgraph's, not the port index's
    roads.modes = [{"name": "road", "source": "roads"}, {"name": "port"}]
    sea.modes = [{"name": "sea", "source": "sea"}]
    roads.merge_with_other_geograph(sea, connection_nodes=ports, mode="port")
    return roads


def _ports(filename):
    with open(filename, newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            if (
                row["Latitude"] and row["Longitude"]
            ):  # skip ports without a position
                yield [float(row["Latitude"]), float(row["Longitude"])]


def _km_to_network(geograph, point):
    return haversine(
        point, geograph.nodes[geograph.snap_index.closest_idx(point)]
    )
