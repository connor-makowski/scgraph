"""Main roads (motorway, trunk, primary and their links) and vehicle ferries of Europe,
from the OpenStreetMap extract of Europe.

- This network is `osm_main_roads` for Europe, with fewer nodes. A road is cut every
  5 km, and a contracted arc ends at the first node where it reaches 5 km. Two nodes
  along a road are then at most about 10 km apart.
- The network keeps each strongly connected component of at least 100 nodes.
- A vehicle ferry joins the road nodes nearest its two ends, if both are within 2 km.
- The shape of each arc is simplified to within 50 m. Its length is measured on the
  full shape.
- Source: the Europe extract of Geofabrik, read by HTTP byte ranges and never stored.
  The build needs the C++ extension of scgraph.
"""

import os

from scgraph.pipelines import osm_main_roads
from scgraph.pipelines.steps.stage1_extract import osm

PIPELINE_VERSION = 2

SOURCES = {
    "roads": {
        **osm.GEOFABRIK,
        "url": "https://download.geofabrik.de/europe-latest.osm.pbf",
        "download": osm.download_streamed,
    }
}
# The length in km at which a road is cut. It is between the 2 km of a region and
# the 10 km of the world: fewer nodes than `osm_main_roads`, more detail than the
# world.
MAX_KM_BETWEEN_NODES = 5
# The network keeps each component of at least 100 nodes. The roads of an island
# then stay in the file.
MIN_COMPONENT_NODES = 100


def build(
    files: dict[str, str],
    *,
    work_dir: str | os.PathLike | None = None,
) -> tuple[dict, list[dict]]:
    """Build the main roads of Europe: `osm_main_roads.build`, with the cut length and the
    component size of this module.
    """
    return osm_main_roads.build(
        files,
        max_km_between_nodes=MAX_KM_BETWEEN_NODES,
        min_component_nodes=MIN_COMPONENT_NODES,
        work_dir=work_dir,
    )


VALIDATION = {
    "cases": [
        "paris_berlin",
        "madrid_lisbon",
        "warsaw_kyiv",
        "paris_marseille",
        "luxembourg_to_esch",
    ],
}
