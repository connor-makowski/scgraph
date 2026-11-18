"""Main roads of the world, from the OpenStreetMap planet, joined to the sea lanes of
`eurostat_marnet` at the ports of the World Port Index: `osm_main_roads_and_marnet` at
the scale of the planet.

- A distance is in km along the network: main roads and car ferries (directed, as
  `world_main_roads`), sea lanes (undirected, as `eurostat_marnet`) and the two
  connectors of each joined port. There are no times, and changing mode at a port costs
  nothing.
- Ports join by the rules of `osm_main_roads_and_marnet`: a road connector to the
  nearest main-road node within 20 km, a sea connector over water to a sea node, both
  checked against Natural Earth 1:10m land, lakes and river centrelines; a port with
  only one stays out. A search for a sea connector that would hold more than 6 million
  raster cells finds none (ports near the poles).
- The network keeps each strongly connected component of at least 1,000 nodes. Nodes:
  junctions, ports and the ends of their connectors, the points of the sea lanes, and
  along a road nodes at most about 20 km apart (cut, then contracted, at 10 km); no arc
  spans two modes. Road and ferry drawings are simplified at 50 m when the ways are cut;
  lengths are measured before. Each node has its mode, `road`, `port` or `sea`.
- Checked by the cases of `VALIDATION`. The roads pass the cases of `world_main_roads`.
  20 sea distances between ports are within 10 % of a published distance. 13 routes
  take or avoid a passage such as Suez or Panama, as ships do. 20 river ports reach
  the sea by water.
- Size, with the planet of 2026-11-02: 3,160 of the 3,795 ports are joined. The network
  has 2.9 million nodes and 5.2 million arcs, and its file takes 272 MB.
- Sources: the planet of the date in its URL, read by HTTP byte ranges and never stored
  (its published md5 is recorded); the others as `osm_main_roads_and_marnet`. The build needs scgraph's C++ backend.
- Not for: navigation or travel times; inland navigation between two river points.
"""

import os

from scgraph.pipelines import osm_main_roads_and_marnet as regional
from scgraph.pipelines.steps.stage1_extract import osm

PIPELINE_VERSION = 2

# The planet first: its download hook checks the C++ backend before any other download
SOURCES = {"roads": osm.PLANET, **regional.SOURCES}
SOURCES["roads"] = osm.PLANET
MAX_KM = 10  # the cut and the contraction (first build)
MIN_NODES = 1000  # nodes of the smallest component kept

download = regional.download  # for the other sources: checks osmium first


def build(
    files: dict[str, str],
    *,
    work_dir: str | os.PathLike | None = None,
) -> tuple[dict, list[dict]]:
    """Build the world main roads and marnet intermodal network.

    Args:
        files: Mapping of source identifiers to local file paths.
        work_dir: Working directory for intermediate checkpoints.

    Returns:
        The network file's arrays and the modes table, `(arrays, modes)`, of the built multimodal network.
    """
    return regional.build(
        files,
        max_km_between_nodes=MAX_KM,
        min_nodes_per_strongly_connected_component=MIN_NODES,
        work_dir=work_dir,
    )


# ---------------------------------------------------------------------------
# Stage 4 Validation Contract
# ---------------------------------------------------------------------------
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
