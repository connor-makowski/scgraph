"""Main roads of an OpenStreetMap extract from Geofabrik joined to the sea lanes of
`eurostat_marnet` at the ports of the World Port Index (`hubs.join`), for example
`region="europe/denmark"`.

- A distance is in km along the network. The network holds main roads and vehicle
  ferries (directed, as in `osm_main_roads`), sea lanes (both ways, as in
  `eurostat_marnet`) and the two connectors of each joined port. There are no times.
  A change of mode at a port costs nothing.
- A port joins the network when it has a road connector and a sea connector. A port
  without one of them stays out: the pipeline does not join it by a line over land or
  across the sea.
- Road connector. It is a straight line from the port to a main-road node within
  20 km. The line crosses less than 3 km of water, or 10 km for an open roadstead (a
  port where ships anchor off the coast). Among the nodes that fit, the port takes the
  nearest one of the largest road component. The connector weighs 1.2 times the
  length of the line, because a real road bends.
- Sea connector. It is the shortest path over water from the port to a sea node, at
  most 2,500 km long. The path starts at a water cell within 6 km of the port. It
  stays within 2 degrees of the roads of the region. It runs on cells of 1/240 degree,
  made from the land, the lakes and the river centrelines of Natural Earth 1:10m. The
  connector weighs the length of the path, plus the short line from its last cell to
  the sea node. Its shape points are the centres of the
  cells, stored to 1e-7 degree.
- The network keeps its largest strongly connected component. Its nodes are the road
  junctions, the ports, the ends of their connectors and the points of the sea lanes.
  A road is cut every 2 km, and a contracted arc ends at the first node where it
  reaches 2 km. Two nodes along a road are then at most about 4 km apart. A sea lane
  is not cut, but its chains are contracted like those of a road. A chain is never
  contracted across two modes.
- The shape of each road or ferry arc is simplified to within 50 m. Its length is
  measured on the full shape.
- Each node has a mode: `road`, `port` or `sea`. `node_modes` gives its row in
  `modes`. Each mode names the source of its node ids. The id of a port is its World
  Port Index number.
- Sources. The ports come from a table kept with scgraph (`hubs.TABLES`), made from
  one copy of the World Port Index. The Geofabrik URL always gives the newest extract,
  and `PIPELINE_VERSION` does not change when a source changes. So a rebuild can give
  another network.
- Not for navigation or travel times. Not for inland navigation between two points of
  a river.
"""

import logging
import os

from scgraph.pipelines import eurostat_marnet
from scgraph.pipelines.steps.stage1_extract import osm
from scgraph.pipelines.steps.stage2_intermodal import hubs
from scgraph.pipelines.steps.stage2_intermodal.landmask import LandMask
from scgraph.pipelines.steps.stage3_assembly import assembly
from scgraph.utils import _log_step

logger = logging.getLogger(__name__)

PIPELINE_VERSION = 2


def _natural_earth(layer):
    return {
        "url": f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/f1890d9f152c896d250a77557a5751a93d494776/geojson/ne_10m_{layer}.geojson",
        "credit": "Natural Earth (1:10m)",
        "version": "5.1.2",
        "license": "LicenseRef-public-domain",
        "license_url": "https://github.com/nvkelso/natural-earth-vector/blob/f1890d9f152c896d250a77557a5751a93d494776/LICENSE.md",
    }


# The small sources come first. When one of them fails, the extract is not yet
# downloaded.
SOURCES = {
    "sea": eurostat_marnet.SOURCES["sea_lanes"],
    "ports": hubs.TABLES["ports"],
    "land": _natural_earth("land"),
    "lakes": _natural_earth("lakes"),
    "rivers": _natural_earth("rivers_lake_centerlines"),
    "roads": osm.GEOFABRIK,
}
# The land mask covers the roads of the region and this margin around them, in
# degrees. A sea connector runs inside the mask.
MARGIN = 2
SELECTS = {
    "road": {
        "ways": osm.select_main_roads,
        "ferries": osm.select_vehicle_ferries,
    }
}
MODES = [
    {"name": "road", "source": "roads"},
    {"name": "port", "source": "ports"},
    {"name": "sea", "source": "sea"},
]

# For the sources without a download function of their own: it checks osmium before
# the first download
download = osm.download


def build(
    files: dict[str, str],
    *,
    max_km_between_nodes: float = osm.MAX_KM_BETWEEN_NODES,
    min_component_nodes: int | None = None,
    work_dir: str | os.PathLike | None = None,
) -> tuple[dict, list[dict]]:
    """Build the roads and the sea lanes of a region, joined at ports.
    `world_main_roads_and_marnet` calls this function with other values of the keywords.

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
    stage2_work_dir = os.path.join(work_dir, "stage2") if work_dir else None
    pieces = osm.build_way_pieces(
        files["roads"],
        SELECTS,
        ("highway", "route"),
        max_km_between_nodes,
        stage1_work_dir,
    )
    graph = assembly.build_graph_from_pieces(pieces["road"])
    with _log_step(logger, "read the sea lanes", {}) as counts:
        sea = eurostat_marnet.build({"sea_lanes": files["sea"]})
        counts["nodes"] = len(sea.nodes)
        counts["arcs"] = sum(map(len, sea.graph_object.graph))
    node_points = memoryview(graph["node_points"])  # 1e-7 degree
    latitudes, longitudes = node_points[0::2], node_points[1::2]
    south = max(-90, min(latitudes) * 1e-7 - MARGIN)
    west = max(-180, min(longitudes) * 1e-7 - MARGIN)
    north = min(90, max(latitudes) * 1e-7 + MARGIN)
    east = min(180, max(longitudes) * 1e-7 + MARGIN)
    # join() frees the road graph. Delete the views, so that nothing here keeps it
    del node_points, latitudes, longitudes

    mask = LandMask.from_natural_earth(
        *(files[name] for name in ("land", "lakes", "rivers")),
        bbox=(south, west, north, east),
    )
    ports = hubs.read_ports(files["ports"])
    ports = [port for port in ports if mask.get_cell(*port.point) is not None]
    with _log_step(logger, "join the ports", {"ports": len(ports)}) as counts:
        graph, joined = hubs.join(
            {"road": graph, "sea": sea},
            ports,
            mask,
            [mode["name"] for mode in MODES],
            work_dir=stage2_work_dir,
        )
        counts["joined"] = joined.get("port", 0)
    arrays = assembly.assemble(
        graph,
        max_km_between_nodes=max_km_between_nodes,
        min_component_nodes=min_component_nodes,
    )
    return arrays, MODES


VALIDATION = {
    "cases": {
        "europe/denmark": ["aarhus_to_copenhagen_intermodal"],
    },
}
