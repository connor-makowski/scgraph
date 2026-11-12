"""Main roads (motorway, trunk, primary and their links) and vehicle ferries of an OpenStreetMap
extract from Geofabrik, for example `region="europe/luxembourg"`.

A vehicle ferry (`route=ferry`, unless `motor_vehicle=no` or `motorcar=no`) joins, both ways
and with the length of its route, the road nodes nearest its two ends if both lie
within 2 km; otherwise it is left out, as is each piece of a ferry drawn as several ways
that meet at sea. Roads and ferries are read together: a road is also cut where a ferry
way shares one of its nodes. Drawings: each piece's shape is simplified at 50 m when the
way is cut; lengths are measured before. Not the graph `GeoGraph.load_from_osm` gives from
the same file: that loader neither attaches ferries, nor contracts chains, nor simplifies
shapes.
"""

import os
from collections.abc import Callable

from scgraph.pipelines.steps.stage1_extract import osm
from scgraph.pipelines.steps.stage3_assembly import assembly

PIPELINE_VERSION = 1

SOURCES = {"roads": osm.GEOFABRIK}
SELECTS = {
    "roads": osm.select_main_roads,
    "ferries": osm.select_vehicle_ferries,
}

download = osm.download  # checks osmium before downloading a large extract


def build(
    files: dict[str, str],
    *,
    source: Callable = osm.open_osm_source,
    max_km_between_nodes: float = osm.MAX_KM,
    min_nodes_per_strongly_connected_component: int | None = None,
    work_dir: str | os.PathLike | None = None,
) -> tuple[tuple[dict, list[dict]], list[dict]]:
    """The keywords give another scale (`world_main_roads`); `min_nodes_per_strongly_connected_component=None` keeps
    the largest component only."""
    stage1_work_dir = os.path.join(work_dir, "stage1") if work_dir else None
    pieces, steps = osm.build_way_pieces(
        source(files["roads"]),
        SELECTS,
        ("highway", "route"),
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


# ---------------------------------------------------------------------------
# Stage 4 Validation Contract
# ---------------------------------------------------------------------------
# `europe/denmark` has no case. The two Danish crossings do not fit this
# extract: Malmo is outside it, and the centre of Odense is 5.1 km from the
# nearest main road, above the 5 km limit of the crossing rule.
VALIDATION = {
    "cases": {
        "europe/france": [
            "paris_marseille",
            "paris_bordeaux",
            "toulouse_nice",
            "lille_strasbourg",
        ],
        "europe/luxembourg": ["luxembourg_to_esch"],
    },
}
