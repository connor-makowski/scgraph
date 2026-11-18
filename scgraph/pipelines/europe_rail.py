"""Railway lines (`railway=rail`, without sidings, spurs and yard tracks) of Europe,
from the OpenStreetMap Europe extract.

Every line is read both ways, whatever its `oneway` tag. Drawings: each piece's shape
is simplified at 50 m when the way is cut; lengths are measured before.
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
MAX_KM = 5  # intermediate continental resolution
MIN_NODES = 50  # retain regional rail networks


def build(
    files: dict[str, str],
    *,
    work_dir: str | os.PathLike | None = None,
) -> tuple[dict, list[dict]]:
    """Build the Europe railway network.

    Args:
        files: Mapping of source identifiers to local file paths.
        work_dir: Working directory for intermediate checkpoints.

    Returns:
        The network file's arrays and the modes table, `(arrays, modes)`, of the built network.
    """
    return osm_rail.build(
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
        "rotterdam_duisburg",
        "hamburg_munich",
        "paris_marseille_rail",
        "luxembourg_to_bettembourg",
    ],
}
