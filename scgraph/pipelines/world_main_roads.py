"""Main roads (motorway, trunk, primary and their links) and car ferries of the world,
from the OpenStreetMap planet: `osm_main_roads` at the scale of the planet.

- A distance is in km along the main roads and car ferries. One-way roads are followed
  in their legal direction. There are no times.
- A car ferry joins, both ways and with the length of its route, the road nodes nearest
  its two ends if both lie within 2 km; otherwise it is left out.
- The network keeps each strongly connected component of at least 1,000 nodes, so an
  island with roads of its own is a separate network. Nodes: junctions, and along a road
  nodes at most about 20 km apart (cut, then contracted, at 10 km). Drawings are
  simplified at 50 m when the ways are cut; lengths are measured before.
- Accuracy against a road router, coverage of large cities, size: not measured yet.
- Source: the planet of the date in its URL, read by HTTP byte ranges and never stored;
  its published md5 is recorded. The build needs scgraph's C++ backend.
- Not for: navigation or travel times; places far from a main road, where the straight
  leg to the nearest node dominates the distance.
"""

import os

from scgraph.pipelines import osm_main_roads
from scgraph.pipelines.steps.stage1_extract import osm

PIPELINE_VERSION = 1

SOURCES = {"roads": osm.PLANET}
MAX_KM = 10  # the cut and the contraction (first build)
MIN_NODES = 1000  # nodes of the smallest component kept


def build(files: dict[str, str], *, source=osm.open_osm_source):
    """Build the world main roads and car ferries network.

    Args:
        files: Mapping of source identifiers to local file paths.
        source: Factory resolving the OSM source reader (defaults to open_osm_source).

    Returns:
        Tuple of ((arrays, modes), steps) describing the built network.
    """
    return osm_main_roads.build(
        files,
        source=source,
        max_km=MAX_KM,
        min_nodes=MIN_NODES,
        folder=os.path.dirname(files["roads"]),  # the runner's, deleted after
    )


# ---------------------------------------------------------------------------
# Stage 4 Validation Contract
# ---------------------------------------------------------------------------
VALIDATION_CASES = [
    {
        "id": "paris_to_berlin",
        "origin": (48.8686, 2.3314),
        "destination": (52.5238, 13.3996),
        "expected_km": 1027.7,
        "tolerance": 0.05,
        "comment": "European highway corridor Paris-Berlin",
    },
    {
        "id": "chicago_to_houston",
        "origin": (41.8319, -87.7520),
        "destination": (29.8219, -95.3419),
        "expected_km": 1652.3,
        "tolerance": 0.05,
        "comment": "North American Interstate corridor",
    },
    {
        "id": "tokyo_to_osaka",
        "origin": (35.6895, 139.6917),
        "destination": (34.6937, 135.5023),
        "expected_km": 460.4,
        "tolerance": 0.05,
        "comment": "Japanese expressway corridor Tomei/Meishin",
    },
]
