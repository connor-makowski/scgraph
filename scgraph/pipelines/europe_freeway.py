"""Freeways and main roads (motorway, trunk, primary and vehicle ferries) of Europe,
from the OpenStreetMap Europe extract.

Drawings: each piece's shape is simplified at 50 m when the way is cut; lengths are
measured before. Vehicle ferries attach to road nodes within 2 km.
"""

import os
from collections.abc import Callable

from scgraph.pipelines import osm_main_roads
from scgraph.pipelines.steps.stage1_extract import osm

PIPELINE_VERSION = 1

SOURCES = {
    "roads": {
        **osm.GEOFABRIK,
        "url": "https://download.geofabrik.de/europe-latest.osm.pbf",
        "download": osm.download_streamed,
    }
}
MAX_KM = 5  # intermediate continental resolution
MIN_NODES = 100  # retain European islands and regional networks


def build(
    files: dict[str, str],
    *,
    source: Callable = osm.open_osm_source,
    work_dir: str | os.PathLike | None = None,
) -> tuple[tuple[dict, list[dict]], list[dict]]:
    """Build the Europe freeway and main roads network.

    Args:
        files: Mapping of source identifiers to local file paths.
        source: Factory resolving the OSM source reader (defaults to open_osm_source).
        work_dir: Working directory for intermediate checkpoints.

    Returns:
        Tuple of ((arrays, modes), steps) describing the built network.
    """
    if work_dir is None and "roads" in files:
        work_dir = os.path.dirname(files["roads"])
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
VALIDATION = {
    "modes": ("road",),
    "cases": [
        "paris_berlin",
        "madrid_lisbon",
        "warsaw_kyiv",
        "paris_marseille",
        "luxembourg_to_esch",
    ],
}
