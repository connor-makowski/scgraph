"""Railway lines (`railway=rail`, without sidings, spurs and yard tracks) of an
OpenStreetMap extract from Geofabrik, for example `region="europe/luxembourg"`.

- A distance is in km along the lines. There are no times.
- Every line is read both ways, whatever its `oneway` tag. A crossover stays in the
  network: it joins the two tracks of a double line.
- The network keeps its largest strongly connected component. A line is cut every
  2 km, and a contracted arc ends at the first node where it reaches 2 km. Two nodes
  along a line are then at most about 4 km apart.
- The shape of each arc is simplified to within 50 m. Its length is measured on the
  full shape.
"""

import os
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
    max_km_between_nodes: float = osm.MAX_KM_BETWEEN_NODES,
    min_component_nodes: int | None = None,
    work_dir: str | os.PathLike | None = None,
) -> tuple[dict, list[dict]]:
    """Build the railway network of a region. `europe_rail` calls this function with
    other values of the keywords.

    Args:
        files: The path of the downloaded file of each source of `SOURCES`.
        max_km_between_nodes: The length in km at which a way is cut, and at which a
            chain is cut. Two nodes along a way are at most about twice this far apart.
        min_component_nodes: The smallest number of nodes of a kept component. None keeps
            only the largest component.
        work_dir: A folder where the build keeps files between its steps, so that a later
            build resumes from them. None keeps nothing.

    Returns:
        `(arrays, modes)`: the arrays of the network file, and the modes table.
    """
    stage1_work_dir = os.path.join(work_dir, "stage1") if work_dir else None
    pieces = osm.build_way_pieces(
        files["rail"],
        {"rail": {"ways": select_rail}},
        ("railway",),
        max_km_between_nodes=max_km_between_nodes,
        work_dir=stage1_work_dir,
    )
    graph = assembly.build_graph_from_pieces(pieces["rail"])
    arrays = assembly.assemble(
        graph,
        max_km_between_nodes=max_km_between_nodes,
        min_component_nodes=min_component_nodes,
    )
    return arrays, [{"name": None}]


def select_rail(tags: "osmium.osm.TagList") -> int | None:
    """0 (both ways) for a railway line (`railway=rail`) that is not a siding, a spur
    or a yard track, None for any other way.
    """
    if tags.get("railway") != "rail":
        return None
    # Of the service tracks, only a crossover is kept: it joins the two tracks of a
    # double line drawn track by track. Without it, one track is an island.
    if tags.get("service") not in (None, "crossover"):
        return None
    # A track carries trains both ways, and the two tracks of a double line have the
    # same km. A `oneway` tag is not followed: where no crossover lies beyond the end
    # of a one-way track (a terminus, the edge of an extract), that end would have no
    # return and would fall out of the strongly connected network.
    return 0


VALIDATION = {
    "cases": {
        "europe/luxembourg": ["luxembourg_to_bettembourg"],
    },
}
