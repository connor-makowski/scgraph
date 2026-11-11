"""Railway lines (`railway=rail`, sidings and yards included) of Europe,
from the OpenStreetMap Europe extract.

Drawings: each piece's shape is simplified at 50 m when the way is cut; lengths are
measured before.
"""

import os
from collections.abc import Callable

from scgraph.pipelines import osm_rail
from scgraph.pipelines.steps.stage1_extract import osm

PIPELINE_VERSION = 1

SOURCES = {
    "rail": {
        **osm.GEOFABRIK,
        "url": "https://download.geofabrik.de/europe-latest.osm.pbf",
        "download": osm.download_streamed,
    }
}
MAX_KM = 5  # intermediate continental resolution
MIN_NODES = 50  # retain regional rail networks


def build(
    files: dict[str, str],
    *,
    source: Callable = osm.open_osm_source,
    work_dir: str | os.PathLike | None = None,
) -> tuple[tuple[dict, list[dict]], list[dict]]:
    """Build the Europe railway network.

    Args:
        files: Mapping of source identifiers to local file paths.
        source: Factory resolving the OSM source reader (defaults to open_osm_source).
        work_dir: Working directory for intermediate checkpoints.

    Returns:
        Tuple of ((arrays, modes), steps) describing the built network.
    """
    if work_dir is None and "rail" in files:
        work_dir = os.path.dirname(files["rail"])
    return osm_rail.build(
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
    "modes": ("rail",),
    "cases": [
        "rotterdam_duisburg",
        "hamburg_munich",
        "paris_marseille",
        "luxembourg_to_bettembourg",
    ],
}
