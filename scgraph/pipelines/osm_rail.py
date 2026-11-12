"""Railway lines (`railway=rail`, sidings and yards included) of an OpenStreetMap extract
from Geofabrik, for example `region="europe/luxembourg"`.

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

PIPELINE_VERSION = 1

SOURCES = {"rail": osm.GEOFABRIK}

download = osm.download  # checks osmium before downloading a large extract


def build(
    files: dict[str, str],
    *,
    source: Callable = osm.open_osm_source,
    max_km_between_nodes: float | int = osm.MAX_KM,
    min_nodes_per_strongly_connected_component: int | None = None,
    work_dir: str | os.PathLike | None = None,
) -> tuple[tuple[dict, list[dict]], list[dict]]:
    """The keywords give another scale (`europe_rail`); `min_nodes_per_strongly_connected_component=None` keeps
    the largest component only."""
    stage1_work_dir = os.path.join(work_dir, "stage1") if work_dir else None
    pieces, steps = osm.build_way_pieces(
        source(files["rail"]),
        {"rail": select_rail},
        ("railway",),
        max_km_between_nodes=max_km_between_nodes,
        work_dir=stage1_work_dir,
    )
    graph = assembly.build_graph_from_pieces(pieces)
    arrays, assembled = assembly.assemble(
        graph,
        max_km_between_nodes=max_km_between_nodes,
        min_nodes_per_strongly_connected_component=min_nodes_per_strongly_connected_component,
    )
    return (arrays, [{"name": None}]), steps + assembled


def select_rail(tags: "osmium.osm.TagList") -> int | None:
    """The direction of a railway line (`railway=rail`), None for any other way."""
    return (
        osm.get_way_direction(tags) if tags.get("railway") == "rail" else None
    )


# ---------------------------------------------------------------------------
# Stage 4 Validation Contract
# ---------------------------------------------------------------------------
VALIDATION = {
    "cases": {
        "europe/luxembourg": ["luxembourg_to_bettembourg"],
    },
}
