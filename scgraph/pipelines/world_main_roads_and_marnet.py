"""Main roads of the world, from the OpenStreetMap planet, joined to the sea lanes of
`eurostat_marnet` at the ports of the World Port Index: `osm_main_roads_and_marnet`
for the planet.

- A distance is in km along the network. The network holds main roads and vehicle
  ferries (directed, as in `world_main_roads`), sea lanes (both ways, as in
  `eurostat_marnet`) and the two connectors of each joined port. There are no times.
  A change of mode at a port costs nothing.
- A port joins by the rules of `osm_main_roads_and_marnet`. It needs a road connector,
  to a main-road node within 20 km, and a sea connector, over water to a sea node.
  Both are checked against the land, the lakes and the river centrelines of Natural
  Earth 1:10m. A port with only one connector stays out.
- A search for a sea connector stops when it holds more than 6 million raster cells.
  This happens for ports near the poles, which then stay out.
- The network keeps each strongly connected component of at least 1,000 nodes. Its
  nodes are the road junctions, the ports, the ends of their connectors and the points
  of the sea lanes. A sea lane is not cut, but its chains are contracted like those of
  a road. A road is cut every 10 km, and a contracted arc ends at the first
  node where it reaches 10 km. Two nodes along a road are then at most about 20 km
  apart. A chain is never contracted across two modes.
- The shape of each road or ferry arc is simplified to within 50 m. Its length is
  measured on the full shape.
- Each node has a mode: `road`, `port` or `sea`.
- Checked by the cases of `VALIDATION`. The roads pass the kinds of cases of
  `world_main_roads`.
  20 sea distances between ports are within 10 % of a published distance. 13 routes
  take or avoid a passage such as Suez or Panama, as ships do. 20 river ports reach
  the sea by water.
- Size, with the planet of 2026-11-02: 3,160 of the 3,807 ports of the table are
  joined. The network has 2.9 million nodes and 5.2 million arcs, and its file takes
  272 MB.
- Sources: the OpenStreetMap planet of the date in its URL, and the other sources of
  `osm_main_roads_and_marnet`. The planet is read by HTTP byte ranges and never
  stored, and its published md5 is recorded. The build needs the C++ extension of
  scgraph.
- Not for navigation or travel times. Not for inland navigation between two points of
  a river.
"""

import os

from scgraph.pipelines import osm_main_roads_and_marnet as regional
from scgraph.pipelines.steps.stage1_extract import osm

PIPELINE_VERSION = 2

# The sources of the regional pipeline, with the planet in place of the extract
SOURCES = {**regional.SOURCES, "roads": osm.PLANET}
# The length in km at which a way is cut, and at which a chain is cut. A larger
# value gives fewer nodes: with 10, the world network has about 3 million nodes.
MAX_KM_BETWEEN_NODES = 10
# The network keeps each component of at least 1,000 nodes. The roads of an island
# then stay in the file, and a small fragment does not.
MIN_COMPONENT_NODES = 1000

# For the sources without a download function of their own: it checks osmium first
download = regional.download


def build(
    files: dict[str, str],
    *,
    work_dir: str | os.PathLike | None = None,
) -> tuple[dict, list[dict]]:
    """Build the roads and the sea lanes of the world, joined at ports:
    `osm_main_roads_and_marnet.build`, with the cut length and the component size of this
    module.
    """
    return regional.build(
        files,
        max_km_between_nodes=MAX_KM_BETWEEN_NODES,
        min_component_nodes=MIN_COMPONENT_NODES,
        work_dir=work_dir,
    )


VALIDATION = {
    "cases": [
        "road_distances",
        "crossings",
        "coverage",
        "sea_distances",
        "passages",
        "river_ports",
    ]
}
