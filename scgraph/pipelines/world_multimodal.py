"""Roads, railways, sea lanes and flights of the world, joined at ports, airports and rail
terminals: `osm_multimodal` at the scale of the planet.

- Distances, modes, hubs and their connectors as in `osm_multimodal`.
- The network keeps each strongly connected component of at least 1,000 nodes, so an
  island with roads of its own is a separate network. Along a road or a railway, nodes lie
  at most about 20 km apart (cut, then contracted, at 10 km).
- Sources: the planet of the date in its URL, read by HTTP byte ranges and never stored,
  twice (the railways, then the roads); the others as `osm_multimodal`. The build needs
  scgraph's C++ backend.
- Not for: navigation, timetables, or the capacity of a terminal.
"""

import os
from collections.abc import Callable

from scgraph.pipelines import osm_multimodal as regional
from scgraph.pipelines.steps.stage1_extract import osm

PIPELINE_VERSION = 1

# The planet first: its download hook checks the C++ backend before any other download
SOURCES = {"osm": osm.PLANET, **regional.SOURCES}
SOURCES["osm"] = osm.PLANET
MAX_KM = 10  # the cut and the contraction
MIN_NODES = 1000  # nodes of the smallest component kept

download = regional.download  # for the other sources: checks osmium first


def build(
    files: dict[str, str],
    *,
    source: Callable = osm.open_osm_source,
    work_dir: str | os.PathLike | None = None,
) -> tuple[dict, list[dict]]:
    """`osm_multimodal.build` at the scale of the planet."""
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
