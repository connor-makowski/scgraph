"""Main roads of an OpenStreetMap extract from Geofabrik joined to the sea lanes of
`eurostat_marnet` at the ports of the World Port Index (`hubs.join`), for example
`region="europe/denmark"`.

- A distance is in km along the network: main roads and car ferries (directed, as
  `osm_main_roads`), sea lanes (undirected, as `eurostat_marnet`) and the two connectors
  of each joined port. There are no times, and changing mode at a port costs nothing.
- A port with a position joins when it has both connectors; the others stay out rather
  than be joined over land or across the sea.
- Road connector: a straight line to the nearest main-road node within 20 km whose line
  crosses less than 3 km of water (10 km for an open roadstead), in the largest road
  component that has such a node; it weighs 1.2 times its length.
- Sea connector: the shortest path over water to a sea node, at most 2,500 km and within
  2 degrees of the region's roads, starting within 6 km of the port, on cells of 1/240
  degree of Natural Earth 1:10m land, lakes and river centrelines; it weighs its length,
  and its shape points are the cells' centres, stored to 1e-7 degree.
- The network keeps its largest strongly connected component. Nodes: junctions, ports and
  the ends of their connectors, the points of the sea lanes (not cut, then contracted
  like the roads), and along a road nodes at most about 4 km apart (cut, then
  contracted, at 2 km); no arc spans two modes. Road and ferry drawings are simplified
  at 50 m when the ways are cut; lengths are measured before. Each node has its mode,
  `road`, `port` or `sea` (`node_modes`, rows of `modes`); each mode cites the source of
  its node ids (a port's id is its World Port Index number).
- Sources: the ports come from a table kept with scgraph (`hubs.TABLES`), made from one
  copy of the World Port Index; the Geofabrik URL is not pinned, and `PIPELINE_VERSION`
  does not follow changes of a source: a rebuild may differ.
- Not for: navigation or travel times; inland navigation between two river points.
"""

import logging
import os
from collections.abc import Callable

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


# Small sources first: a failure then costs no new download of the extract
SOURCES = {
    "sea": eurostat_marnet.SOURCES["sea_lanes"],
    "ports": hubs.TABLES["ports"],
    "land": _natural_earth("land"),
    "lakes": _natural_earth("lakes"),
    "rivers": _natural_earth("rivers_lake_centerlines"),
    "roads": osm.GEOFABRIK,
}
MARGIN = 2  # degrees of raster around the roads, where sea connectors run
SELECTS = {
    "roads": osm.select_main_roads,
    "ferries": osm.select_vehicle_ferries,
}
MODES = [
    {"name": "road", "source": "roads"},
    {"name": "port", "source": "ports"},
    {"name": "sea", "source": "sea"},
]

download = osm.download  # for every source: checks osmium first


def build(
    files: dict[str, str],
    *,
    source: Callable = osm.open_osm_source,
    max_km_between_nodes: float = osm.MAX_KM,
    min_nodes_per_strongly_connected_component: int | None = None,
    work_dir: str | os.PathLike | None = None,
) -> tuple[dict, list[dict]]:
    """The keywords give another scale (`world_main_roads_and_marnet`);
    `min_nodes_per_strongly_connected_component=None` keeps the largest component only.
    """
    stage1_work_dir = os.path.join(work_dir, "stage1") if work_dir else None
    stage2_work_dir = os.path.join(work_dir, "stage2") if work_dir else None
    pieces = osm.build_way_pieces(
        source(files["roads"]),
        SELECTS,
        ("highway", "route"),
        max_km_between_nodes,
        stage1_work_dir,
    )
    graph = assembly.build_graph_from_pieces(pieces)
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
        min_nodes_per_strongly_connected_component=min_nodes_per_strongly_connected_component,
    )
    return arrays, MODES


# ---------------------------------------------------------------------------
# Stage 4 Validation Contract
# ---------------------------------------------------------------------------
VALIDATION = {
    "cases": {
        "europe/denmark": ["aarhus_to_copenhagen_intermodal"],
    },
}
