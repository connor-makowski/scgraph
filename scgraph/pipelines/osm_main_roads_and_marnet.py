"""Main roads of an OpenStreetMap extract from Geofabrik joined to the sea lanes of
`eurostat_marnet` at the ports of the World Port Index, for example `region="europe/denmark"`.

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
  `road`, `port` or `sea` (`node_modes`, rows of `modes`); `road` and `sea` cite the
  source of their node ids, ports have scgraph's (negative).
- Sources: the World Port Index and Geofabrik URLs are not pinned, and
  `PIPELINE_VERSION` does not follow changes of a source: a rebuild may differ.
- Not for: navigation or travel times; inland navigation between two river points.
"""

import os
from collections.abc import Callable

from scgraph.pipelines import eurostat_marnet
from scgraph.pipelines.steps.stage1_extract import osm
from scgraph.pipelines.steps.stage2_intermodal import ports
from scgraph.pipelines.steps.stage2_intermodal.landmask import LandMask
from scgraph.pipelines.steps.stage3_assembly import assembly

PIPELINE_VERSION = 1


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
    "ports": {
        "url": "https://msi.nga.mil/api/publications/download?type=view&key=16920959/SFH00000/UpdatedPub150.csv",
        "download": ports.download,
        "credit": "National Geospatial-Intelligence Agency, World Port Index (Pub. 150)",
        "license": "NOASSERTION",
        "license_url": "https://msi.nga.mil/Publications/WPI",
    },
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
    {"name": "port"},
    {"name": "sea", "source": "sea"},
]

download = osm.download  # for every source: checks osmium first


def build(
    files: dict[str, str],
    *,
    source: Callable = osm.open_osm_source,
    max_km_between_nodes: float | int = osm.MAX_KM,
    min_nodes_per_strongly_connected_component: int | None = None,
    work_dir: str | os.PathLike | None = None,
) -> tuple[tuple[dict, list[dict]], list[dict]]:
    """The keywords give another scale (`world_main_roads_and_marnet`);
    `min_nodes_per_strongly_connected_component=None` keeps the largest component only.
    """
    stage1_work_dir = os.path.join(work_dir, "stage1") if work_dir else None
    stage2_work_dir = os.path.join(work_dir, "stage2") if work_dir else None
    pieces, steps = osm.build_way_pieces(
        source(files["roads"]),
        SELECTS,
        ("highway", "route"),
        max_km_between_nodes,
        stage1_work_dir,
    )
    graph = assembly.build_graph_from_pieces(pieces)
    sea = eurostat_marnet.build({"sea_lanes": files["sea"]})
    sea_arcs = sum(map(len, sea.graph_object.graph))
    steps.append({"step": "sea", "nodes": len(sea.nodes), "arcs": sea_arcs})
    lats, lons = graph["latitudes"], graph["longitudes"]  # 1e-7 degree
    south = max(-90, min(lats) * 1e-7 - MARGIN)
    west = max(-180, min(lons) * 1e-7 - MARGIN)
    north = min(90, max(lats) * 1e-7 + MARGIN)
    east = min(180, max(lons) * 1e-7 + MARGIN)
    del lats, lons  # join frees the road graph: no reference left here
    mask = LandMask.from_natural_earth(
        *(files[name] for name in ("land", "lakes", "rivers")),
        bbox=(south, west, north, east),
    )
    wpi = ports.read_world_port_index(files["ports"])
    wpi = [p for p in wpi if mask.cell(*p[:2]) is not None]
    graph, joined = ports.join(graph, sea, wpi, mask, work_dir=stage2_work_dir)
    steps.append({"step": "ports", "joined": joined})
    arrays, assembled = assembly.assemble(
        graph,
        max_km_between_nodes=max_km_between_nodes,
        min_nodes_per_strongly_connected_component=min_nodes_per_strongly_connected_component,
    )
    return (arrays, MODES), steps + assembled


# ---------------------------------------------------------------------------
# Stage 4 Validation Contract
# ---------------------------------------------------------------------------
VALIDATION = {
    "cases": {
        "europe/denmark": ["aarhus_to_copenhagen_intermodal"],
    },
}
