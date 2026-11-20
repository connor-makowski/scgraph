"""Main roads (motorway, trunk, primary and their links) and vehicle ferries of an
OpenStreetMap extract from Geofabrik, for example `region="europe/luxembourg"`.

- A distance is in km along the roads and the ferries. One-way roads are followed in
  their legal direction. There are no times.
- A vehicle ferry joins two road nodes, both ways, with the length of its route. The
  pipeline reads as a ferry each way tagged `route=ferry` or `route=shuttle_train` (a
  train that carries cars and lorries, as in the Channel Tunnel). It leaves out a
  ferry closed to motor vehicles (`motor_vehicle=no` or `motorcar=no`).
- Each end of a ferry joins the nearest road node, if that node is within 2 km. A
  ferry with an end farther than 2 km from every road node is left out. A ferry drawn
  as several ways that meet at sea is left out too, because each of its parts has an
  end at sea.
- Roads and ferries are read together. So a road is also cut at a node that it shares
  with a ferry.
- The network keeps its largest strongly connected component. A road is cut every
  2 km, and a contracted arc ends at the first node where it reaches 2 km. Two nodes
  along a road are then at most about 4 km apart.
- The shape of each arc is simplified to within 50 m. Its length is measured on the
  full shape.
- `GeoGraph.load_from_osm` gives another graph from the same file. That loader does
  not attach ferries, does not contract chains and does not simplify shapes.
"""

import os

from scgraph.pipelines.steps.stage1_extract import osm
from scgraph.pipelines.steps.stage3_assembly import assembly

PIPELINE_VERSION = 2

SOURCES = {"roads": osm.GEOFABRIK}
SELECTS = {
    "road": {
        "ways": osm.select_main_roads,
        "ferries": osm.select_vehicle_ferries,
    }
}

download = osm.download  # checks osmium before downloading a large extract


def build(
    files: dict[str, str],
    *,
    work_dir: str | os.PathLike | None = None,
) -> tuple[dict, list[dict]]:
    """Build the main roads of a region.

    Args:
        files: The path of the downloaded file of each source of `SOURCES`.
        work_dir: A folder where the build keeps files between its steps, so that a later
            build resumes from them. None keeps nothing.

    Returns:
        `(arrays, modes)`: the arrays of the network file, and the modes table.
    """
    stage1_work_dir = os.path.join(work_dir, "stage1") if work_dir else None
    pieces = osm.build_way_pieces(
        files["roads"],
        SELECTS,
        ("highway", "route"),
        max_km_between_nodes=osm.MAX_KM_BETWEEN_NODES,
        work_dir=stage1_work_dir,
    )
    graph = assembly.build_graph_from_pieces(pieces["road"])
    arrays = assembly.assemble(
        graph,
        max_km_between_nodes=osm.MAX_KM_BETWEEN_NODES,
        min_component_nodes=None,  # only the largest component
    )
    return arrays, [{"name": None}]


# `europe/denmark` has no case. The three crossings with an end in Denmark do not
# fit this extract. Malmo is outside it. No vehicle ferry of the extract joins Ronne
# to the other roads. The centre of Odense is 5.1 km from the nearest road node of
# this network, above the 5 km limit of the crossing rule.
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
