"""Roads, railways, sea lanes and flights of the world, joined at ports, airports and
rail terminals: `geofabrik_multimodal` for the OpenStreetMap planet.

- Distances, modes, classes, hubs and their connectors are those of
  `geofabrik_multimodal`.
- A shortest route in km takes any mode. Between two distant places it takes a
  flight, because a flight is a straight line. To compare modes, derive a cost per
  mode from the km, or load only some modes (`load_from_scgraph(modes=...)`).
- The flights inside mainland China, and between China and the rest of Asia, are
  missing: no open source counts them.
- The network keeps each strongly connected component of at least 1,000 nodes, so an
  island with roads of its own is a separate network. A road or a railway is cut every
  10 km, and a contracted arc ends at the first node where it reaches 10 km. Two nodes
  along a road or a railway are then at most about 20 km apart.
- Sources: the OpenStreetMap planet of the date in its URL, and the other sources of
  `geofabrik_multimodal`. The planet is read by HTTP byte ranges and never stored. The
  build needs the C++ extension of scgraph.
- Not for navigation, timetables, the capacity of a terminal, or inland navigation
  between two points of a river.
"""

import os

from scgraph.pipelines import geofabrik_multimodal as regional
from scgraph.pipelines.steps import step1_osm_ways

PIPELINE_VERSION = 2

# The sources of the regional pipeline, with the planet in place of the extract
SOURCES = {**regional.SOURCES, "osm": step1_osm_ways.PLANET}
# The length in km at which a way is cut, and at which a chain is cut. A larger
# value gives fewer nodes: with 10, the world network has about 3.3 million nodes.
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
    """Build the multimodal network of the world: `geofabrik_multimodal.build`, with
    the cut length and the component size of this module.
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
        "rail_corridors",
        "sea_distances",
        "passages",
        "river_ports",
        "hubs",
    ]
}
