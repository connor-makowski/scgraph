"""Railway lines (`railway=rail`, without sidings, spurs and yard tracks) of an OpenStreetMap extract
from Geofabrik, for example `region="europe/luxembourg"`. Every line runs both ways.

Drawings: each piece's shape is simplified at 50 m when the way is cut; lengths are
measured before.
"""

import os
from collections.abc import Callable
from typing import TYPE_CHECKING

from scgraph.pipelines.steps.stage1_extract import osm
from scgraph.pipelines.steps.stage3_assembly import assembly

if TYPE_CHECKING:  # annotations only: osmium stays optional at run time
    import osmium

PIPELINE_VERSION = 2

SOURCES = {"rail": osm.GEOFABRIK}

download = osm.download  # checks osmium before downloading a large extract


def build(
    files: dict[str, str],
    *,
    source: Callable = osm.open_osm_source,
    max_km_between_nodes: float = osm.MAX_KM,
    min_nodes_per_strongly_connected_component: int | None = None,
    work_dir: str | os.PathLike | None = None,
) -> tuple[dict, list[dict]]:
    """The keywords give another scale (`europe_rail`); `min_nodes_per_strongly_connected_component=None` keeps
    the largest component only."""
    stage1_work_dir = os.path.join(work_dir, "stage1") if work_dir else None
    pieces = osm.build_way_pieces(
        source(files["rail"]),
        {"rail": select_rail},
        ("railway",),
        max_km_between_nodes=max_km_between_nodes,
        work_dir=stage1_work_dir,
    )
    graph = assembly.build_graph_from_pieces(pieces)
    arrays = assembly.assemble(
        graph,
        max_km_between_nodes=max_km_between_nodes,
        min_nodes_per_strongly_connected_component=min_nodes_per_strongly_connected_component,
    )
    return arrays, [{"name": None}]


def select_rail(tags: "osmium.osm.TagList") -> int | None:
    """0 (both ways) for a railway line (`railway=rail`) that is not a siding, a spur or
    a yard track (`service=*`), None for any other way."""
    # A train can run both ways on a track. Some double tracks have a `oneway` tag, and
    # their return runs through a siding. Without the sidings, such a line would run one
    # way only, and its end would fall out of the strongly connected network. The
    # Trans-Siberian at Vladivostok is one example.
    if tags.get("railway") != "rail" or "service" in tags:
        return None
    return 0


# ---------------------------------------------------------------------------
# Stage 4 Validation Contract
# ---------------------------------------------------------------------------
VALIDATION = {
    "cases": {
        "europe/luxembourg": ["luxembourg_to_bettembourg"],
    },
}
