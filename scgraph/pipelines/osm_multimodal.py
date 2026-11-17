"""Roads, railways, sea lanes and flights of a region, joined at ports, airports and rail
terminals, for example `region="europe/denmark"`.

- A distance is in km along the network. It holds main roads and car ferries (as
  `osm_main_roads`), railway lines without sidings, spurs and yard tracks (as `osm_rail`),
  the sea lanes of `eurostat_marnet`, the regular flights between airports, and the
  connectors of the hubs. There are no times and no costs: a user derives them from the
  km and the mode of each arc.
- Two modes never share a node. A route changes mode only at a hub: a port (road, sea,
  and rail where the port has a railway), an airport (road, and its flights) or a rail
  terminal (road and rail). The connectors follow `hubs.join`: up to 20 km to a road,
  10 km to a railway, a water path up to 2,500 km to a sea lane.
- Two airports with regular flights are joined both ways, with the great-circle distance
  between them: large or medium airports with at least 104 flights in 2021 between them
  (about one a week each way). Three sources count the flights: the OpenSky flight list,
  BTS T-100 for the flights that touch the United States, and Eurostat for those that
  touch Europe. The flights inside mainland China, and between China and the rest of
  Asia, are missing: no open source counts them.
- Each node has its mode (`node_modes`, rows of `modes`): `road`, `rail`, `sea`, `port`,
  `airport` or `rail_terminal`. Each mode cites the source of its node ids: OpenStreetMap
  for roads and railways, the World Port Index number for a port, the OurAirports id for
  an airport, the Wikidata number for a rail terminal.
- The network keeps its largest strongly connected component (regional scale) or each
  component of at least 1,000 nodes (`world_multimodal`). Chains of nodes are contracted
  as in `osm_main_roads_and_marnet`, never across two modes.
- Sources: the OpenStreetMap extract (read twice: the railways, then the roads), the sea
  lanes and Natural Earth as `osm_main_roads_and_marnet`; the hubs and flights from small
  tables kept with scgraph (`hubs.TABLES`, made by `utils/build_hub_tables.py`).
- A shortest route in km takes any mode: between two distant places it flies, since a
  flight is the straight line. To compare modes, derive a cost per mode (time, CO2) from
  the km, or load only some modes (`load_from_scgraph(modes=...)`).
- The region needs at least one railway line. A region without one, such as
  `europe/malta`, raises a ValueError.
- Not for: navigation, timetables, or the capacity of a terminal.
"""

import logging
import os
from collections.abc import Callable

from scgraph.pipelines import (
    eurostat_marnet,
    osm_main_roads_and_marnet,
    osm_rail,
)
from scgraph.pipelines.steps.stage1_extract import osm
from scgraph.pipelines.steps.stage2_intermodal import hubs
from scgraph.pipelines.steps.stage2_intermodal.landmask import LandMask
from scgraph.pipelines.steps.stage3_assembly import assembly
from scgraph.utils import _log_step

logger = logging.getLogger(__name__)

PIPELINE_VERSION = 1

# Small sources first: a failure then costs no new download of the extract
SOURCES = {
    **{
        name: osm_main_roads_and_marnet.SOURCES[name]
        for name in ("sea", "land", "lakes", "rivers")
    },
    **hubs.TABLES,
    "osm": osm.GEOFABRIK,
}
MODES = [
    {"name": "road", "source": "osm"},
    {"name": "rail", "source": "osm"},
    {"name": "sea", "source": "sea"},
    {"name": "port", "source": "ports"},
    {"name": "airport", "source": "airports"},
    {"name": "rail_terminal", "source": "rail_terminals"},
]
MARGIN = osm_main_roads_and_marnet.MARGIN  # degrees of raster around the roads

download = (
    osm.download
)  # for the sources without their own download: checks osmium first


def build(
    files: dict[str, str],
    *,
    source: Callable = osm.open_osm_source,
    max_km_between_nodes: float = osm.MAX_KM,
    min_nodes_per_strongly_connected_component: int | None = None,
    work_dir: str | os.PathLike | None = None,
) -> tuple[dict, list[dict]]:
    """Build the multimodal network of a region. The keywords give another scale
    (`world_multimodal`).

    Args:
        files: The local file of each source of SOURCES.
        source: Opens the OSM extract for one read.
        max_km_between_nodes: The longest piece of a way, in km.
        min_nodes_per_strongly_connected_component: The nodes of the smallest
            component kept. None keeps the largest component only.
        work_dir: A folder for the files of each step, so that a build can resume.

    Returns:
        The network file's arrays and the modes table, `(arrays, MODES)`.
    """

    def folder(step):
        return os.path.join(work_dir, step) if work_dir else None

    # 1. The railways, then the roads: two reads of the same extract keep the two
    # networks apart, so that a level crossing is not a change of mode. The smaller
    # network is read first: it waits in memory while the roads are read.
    rails = assembly.build_graph_from_pieces(
        osm.build_way_pieces(
            source(files["osm"]),
            {"rail": osm_rail.select_rail},
            ("railway",),
            max_km_between_nodes,
            folder("rails"),
        )
    )
    roads = assembly.build_graph_from_pieces(
        osm.build_way_pieces(
            source(files["osm"]),
            osm_main_roads_and_marnet.SELECTS,
            ("highway", "route"),
            max_km_between_nodes,
            folder("roads"),
        )
    )
    # 2. The sea lanes
    with _log_step(logger, "read the sea lanes", {}) as counts:
        sea = eurostat_marnet.build({"sea_lanes": files["sea"]})
        counts["nodes"] = len(sea.nodes)
    # 3. The land and the water around the roads, where connectors are checked
    node_points = memoryview(roads["node_points"])  # 1e-7 degree
    latitudes, longitudes = node_points[0::2], node_points[1::2]
    south = max(-90, min(latitudes) * 1e-7 - MARGIN)
    west = max(-180, min(longitudes) * 1e-7 - MARGIN)
    north = min(90, max(latitudes) * 1e-7 + MARGIN)
    east = min(180, max(longitudes) * 1e-7 + MARGIN)
    # join() frees the roads. Delete the views, so that nothing here keeps them
    del node_points, latitudes, longitudes
    mask = LandMask.from_natural_earth(
        *(files[name] for name in ("land", "lakes", "rivers")),
        bbox=(south, west, north, east),
    )
    # 4. The hubs inside the raster
    region_hubs = (
        hubs.read_ports(files["ports"])
        + hubs.read_airports(files["airports"])
        + hubs.read_rail_terminals(files["rail_terminals"])
    )
    region_hubs = [
        hub for hub in region_hubs if mask.get_cell(*hub.point) is not None
    ]
    # 5. Join the networks at the hubs, and the airports by their flights
    with _log_step(
        logger, "join at the hubs", {"hubs": len(region_hubs)}
    ) as counts:
        graph, joined = hubs.join(
            {"road": roads, "rail": rails, "sea": sea},
            region_hubs,
            mask,
            [mode["name"] for mode in MODES],
            flights=hubs.read_flights(files["flights"]),
            work_dir=folder("hubs"),
        )
        counts.update(joined)
    # 6. Keep the connected network, contract its chains, number its nodes
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
        "europe/denmark": [
            "aarhus_to_copenhagen_intermodal",
            "arhus_port",
            "aalborg_airport",
        ],
    },
}
