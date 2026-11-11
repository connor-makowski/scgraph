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
- Accuracy of roads and sea lanes, coverage, ports joined, size: not measured yet.
- Sources: the planet of the date in its URL, read by HTTP byte ranges and never stored
  (its published md5 is recorded); the others as `osm_main_roads_and_marnet`, the World
  Port Index unpinned. The build needs scgraph's C++ backend.
- Not for: navigation or travel times; inland navigation between two river points.
"""

import os
from collections.abc import Callable

from scgraph.pipelines import osm_main_roads_and_marnet as regional
from scgraph.pipelines.steps.stage1_extract import osm

PIPELINE_VERSION = 1

# The planet first: its download hook checks the C++ backend before any other download
SOURCES = {"roads": osm.PLANET, **regional.SOURCES}
SOURCES["roads"] = osm.PLANET
MAX_KM = 10  # the cut and the contraction (first build)
MIN_NODES = 1000  # nodes of the smallest component kept

download = regional.download  # for the other sources: checks osmium first


def build(
    files: dict[str, str],
    *,
    source: Callable = osm.open_osm_source,
    work_dir: str | os.PathLike | None = None,
) -> tuple[tuple[dict, list[dict]], list[dict]]:
    """Build the world main roads and marnet intermodal network.

    Args:
        files: Mapping of source identifiers to local file paths.
        source: Factory resolving the OSM source reader (defaults to open_osm_source).
        work_dir: Working directory for intermediate checkpoints.

    Returns:
        Tuple of ((arrays, modes), steps) describing the built multimodal network.
    """
    if work_dir is None and "roads" in files:
        work_dir = os.path.dirname(files["roads"])
    return regional.build(
        files,
        source=source,
        max_km_between_nodes=MAX_KM,
        min_nodes_per_strongly_connected_component=MIN_NODES,
        work_dir=work_dir,
    )


# ---------------------------------------------------------------------------
# Stage 4 Validation Contract
# ---------------------------------------------------------------------------
VALIDATION = {
    "modes": ("road", "port", "sea"),
    "cases": [
        "paris_berlin",
        "rotterdam_to_new_york_intermodal",
        "shanghai_to_los_angeles_intermodal",
    ],
}
