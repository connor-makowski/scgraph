"""Main roads (motorway, trunk, primary and their links) and car ferries of the world,
from the OpenStreetMap planet: `osm_main_roads` at the scale of the planet.

- A distance is in km along the main roads and car ferries. One-way roads are followed
  in their legal direction. There are no times.
- A car ferry, or a car shuttle train such as the Channel Tunnel's, joins, both ways and
  with the length of its route, the road nodes nearest its two ends if both lie within
  2 km; otherwise it is left out.
- The network keeps each strongly connected component of at least 1,000 nodes, so an
  island with roads of its own is a separate network. Nodes: junctions, and along a road
  nodes at most about 20 km apart (cut, then contracted, at 10 km). Drawings are
  simplified at 50 m when the ways are cut; lengths are measured before.
- Checked by the cases of `VALIDATION`. 20 driving distances between large cities are
  within 10 % of the distance of a road router (15 % for one case). The 1,004 cities
  above 500,000 people have a road route to the main city of their landmass; 1 % of
  them may fail. 11 crossings by bridge, tunnel or ferry have a road route.
- Size, with the planet of 2026-11-02: 2.9 million nodes, 5.0 million arcs, and a file
  of 258 MB.
- Source: the planet of the date in its URL, read by HTTP byte ranges and never stored;
  its published md5 is recorded. The build needs scgraph's C++ backend.
- Not for: navigation or travel times; places far from a main road, where the straight
  leg to the nearest node dominates the distance.
"""

import os
from collections.abc import Callable

from scgraph.pipelines import osm_main_roads
from scgraph.pipelines.steps.stage1_extract import osm

PIPELINE_VERSION = 2

SOURCES = {"roads": osm.PLANET}
MAX_KM = 10  # the cut and the contraction (first build)
MIN_NODES = 1000  # nodes of the smallest component kept


def build(
    files: dict[str, str],
    *,
    source: Callable = osm.open_osm_source,
    work_dir: str | os.PathLike | None = None,
) -> tuple[dict, list[dict]]:
    """Build the world main roads and car ferries network.

    Args:
        files: Mapping of source identifiers to local file paths.
        source: Factory resolving the OSM source reader (defaults to open_osm_source).
        work_dir: Working directory for intermediate checkpoints.

    Returns:
        The network file's arrays and the modes table, `(arrays, modes)`, of the built network.
    """
    return osm_main_roads.build(
        files,
        source=source,
        max_km_between_nodes=MAX_KM,
        min_nodes_per_strongly_connected_component=MIN_NODES,
        work_dir=work_dir,
    )


# ---------------------------------------------------------------------------
# Stage 4 Validation Contract
# ---------------------------------------------------------------------------
# Every crossing except `copenhagen_odense`. The centre of Odense is 5.2 km
# from the nearest main road, and the limit of the crossing rule is 5 km.
VALIDATION = {
    "cases": [
        "road_distances",
        "coverage",
        "london_paris",
        "dover_calais",
        "copenhagen_malmo",
        "ronne_copenhagen",
        "messina_reggio_di_calabria",
        "kadikoy_istanbul",
        "hobart_melbourne",
        "sapporo_tokyo",
        "victoria_vancouver",
        "manama_dammam",
        "singapore_johor_bahru",
    ],
}
