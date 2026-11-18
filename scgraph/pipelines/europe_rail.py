"""Railway lines (`railway=rail`, without sidings, spurs and yard tracks) of Europe,
from the OpenStreetMap extract of Europe.

- This network is `osm_rail` for Europe, with fewer nodes. A line is cut every 5 km,
  and a contracted arc ends at the first node where it reaches 5 km. Two nodes along a
  line are then at most about 10 km apart.
- The network keeps each strongly connected component of at least 50 nodes.
- Every line is read both ways, whatever its `oneway` tag.
- The shape of each arc is simplified to within 50 m. Its length is measured on the
  full shape.
- Source: the Europe extract of Geofabrik, read by HTTP byte ranges and never stored.
  The build needs the C++ extension of scgraph.
"""

import os

from scgraph.pipelines import osm_rail
from scgraph.pipelines.steps.stage1_extract import osm

PIPELINE_VERSION = 2

SOURCES = {
    "rail": {
        **osm.GEOFABRIK,
        "url": "https://download.geofabrik.de/europe-latest.osm.pbf",
        "download": osm.download_streamed,
    }
}
# The length in km at which a line is cut. It is between the 2 km of a region and
# the 10 km of the world: fewer nodes than `osm_rail`, more detail than the world.
MAX_KM_BETWEEN_NODES = 5
# The network keeps each component of at least 50 nodes. A rail network without a
# link to the main one, such as the network of an island, then stays in the file.
MIN_COMPONENT_NODES = 50


def build(
    files: dict[str, str],
    *,
    work_dir: str | os.PathLike | None = None,
) -> tuple[dict, list[dict]]:
    """Build the railway network of Europe: `osm_rail.build`, with the cut length and the
    component size of this module.
    """
    return osm_rail.build(
        files,
        max_km_between_nodes=MAX_KM_BETWEEN_NODES,
        min_component_nodes=MIN_COMPONENT_NODES,
        work_dir=work_dir,
    )


VALIDATION = {
    "cases": [
        "rotterdam_duisburg",
        "hamburg_munich",
        "paris_marseille_rail",
        "luxembourg_to_bettembourg",
    ],
}
