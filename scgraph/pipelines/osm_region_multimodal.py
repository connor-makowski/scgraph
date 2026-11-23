"""Roads and railways of one region, joined to the sea lanes of the world and to
flights at ports, airports and rail terminals. The region is an OpenStreetMap extract
of Geofabrik, for example `region="europe/denmark"`.

`osm_world_multimodal` builds the same network for the whole world, from the
OpenStreetMap planet. It calls the `build` of this module.

WHAT THE NETWORK HOLDS

- A distance is in km along the network. There are no times and no costs: a user
  derives them from the km and the class of each edge.
- Roads. The network holds the motorway, trunk and primary roads, and their links.
  One-way roads are followed in their legal direction.
- Vehicle ferries. A vehicle ferry joins two road nodes, both ways, with the length
  of its route. The pipeline reads as a ferry each way tagged `route=ferry` or
  `route=shuttle_train` (a train that carries cars and lorries, as in the Channel
  Tunnel). It leaves out a ferry closed to motor vehicles (`motor_vehicle=no` or
  `motorcar=no`). Each end of a ferry joins the closest road node, if that node is
  within 2 km. A ferry with an end farther than 2 km from every road node is left
  out. A ferry drawn as several ways that meet at sea is left out too, because each
  of its parts has an end at sea.
- Railways. The network holds the lines tagged `railway=rail`, without sidings,
  spurs and yard tracks. Every line is read both ways, whatever its `oneway` tag.
- Sea lanes. They are the sea lanes of the world, as `eurostat_sea_lanes` reads them,
  both ways.
- Flights. Two airports with regular flights are joined both ways, with the
  great-circle distance between them: large or medium airports with at least 104
  flights in 2021 between them (about one a week each way). Three sources count the
  flights: the OpenSky flight list, BTS T-100 for the flights that touch the United
  States, and Eurostat for those that touch Europe. The flights inside mainland
  China, and between China and the rest of Asia, are missing: no open source counts
  them.

HUBS AND CONNECTORS

- The road, rail and sea networks never share a node. A route goes from one network
  to another only through a hub: a port (road, sea, and rail where the port has a
  railway), an airport (road, and its flights) or a rail terminal (road and rail).
  A change of edge mode at a hub adds no km.
- A connector joins a hub to one network (`step2_hub_connectors.join_networks_at_hubs`). A hub joins the
  network when it reaches at least two networks. A hub that reaches fewer than two
  networks stays out.
- Road connector, and rail connector. It is a straight line from the hub to a node
  within 20 km for a road, or 10 km for a railway. The line crosses less than 3 km of
  water, or 10 km for an open roadstead (a port where ships anchor off the coast).
  Among the nodes that fit, the hub takes the closest one of the largest component.
  The connector weighs 1.2 times the length of the line, because a real road bends.
- Sea connector. It is the shortest path over water from a port to a sea node, at
  most 2,500 km long. The path starts at a water cell within 6 km of the port. It
  stays within 2 degrees of the roads of the region. It runs on cells of 1/240
  degree, made from the land, the lakes and the river centrelines of Natural Earth
  1:10m. The connector weighs the length of the path, plus the short line from its
  last cell to the sea node. Its shape points are the centres of the cells.

NODE MODES AND CLASSES

- The node mode of a node is the kind of place where the node is (`node_mode_ids`):
  `road`, `rail`, `sea`, `port`, `airport` or `rail_terminal`. Each node mode names the
  source of its node ids: OpenStreetMap for roads and railways, the World Port Index for
  a port, OurAirports for an airport, Wikidata for a rail terminal. A node with a
  negative id is in no source: the build added it (*Nodes and shapes*).
- Each edge has a class. `edge_class_ids` gives its position in `classes`. A road edge
  has the `highway` value of its way, and a vehicle ferry is `ferry` or `shuttle_train`.
  A railway edge is `rail_highspeed`, `rail_main`, `rail_branch` or `rail_other`. A sea
  edge has the name of its passage, for example `suez`, or `open_sea`. A flight is
  `flight`. A connector to a road has the class `road_connector`, a connector to a
  railway `rail_connector`, and a connector to a sea lane `sea_connector`.

NODES AND SHAPES

- The network of a region keeps its largest strongly connected component.
- A chain is a run of nodes without a junction. The build contracts a chain into one
  edge. A chain is never contracted across two node modes or two classes.
- A road or a railway is cut every 2 km, and a contracted edge ends at the first node
  where it reaches 2 km. Two nodes along a road or a railway are then at most about
  4 km apart. A sea lane is not cut, but its chains are contracted like those of a
  road.
- The shape of each road, ferry or railway edge is simplified to within 50 m. Its
  length is measured on the full shape.
- One edge at most goes from a node to another. Of several roads from one junction
  to another, the build keeps the shortest of each class. The shortest of all joins
  the two junctions. Each other one passes through a node that the build adds at its
  middle, with a negative id. The same rule holds for ferries and railways.

SOURCES AND LIMITS

- Sources: the OpenStreetMap extract of Geofabrik, the sea lanes of Eurostat
  SeaRoute, and Natural Earth for the land and the water. The hubs and the flights
  come from small tables kept with scgraph (`step2_hub_connectors.HUB_TABLES`, made by
  `utils/build_hub_tables.py`).
- The Geofabrik URL always gives the newest extract, and `PIPELINE_VERSION` does not
  change when a source changes. So a rebuild can give another network.
- A shortest route in km takes any edge mode. Between two distant places it takes a
  flight, because a flight is a straight line. To compare the edge modes, derive a
  cost per edge mode (time, CO2) from the km, or load the nodes of some node modes
  only (`load_from_scgraph(node_modes=...)`).
- A region without a railway, such as `europe/malta`, has no rail node. Its hubs join
  the roads and the sea lanes.
- `GeoGraph.load_from_osm` gives another graph from the same extract. That loader
  reads one network, attaches no ferry, contracts no chain and simplifies no shape.
- Not for navigation, timetables, the capacity of a terminal, or inland navigation
  between two points of a river.
"""

import logging
import os
from typing import TYPE_CHECKING

from scgraph.helpers.osm import select_main_roads_with_class
from scgraph.pipelines import eurostat_sea_lanes
from scgraph.pipelines.steps import step1_osm_ways
from scgraph.pipelines.steps import step2_hub_connectors
from scgraph.pipelines.steps.step2_land_mask import LandMask
from scgraph.pipelines.steps import step3_network_assembly
from scgraph.step_logs import log_step

if TYPE_CHECKING:  # annotations only: osmium stays optional at run time
    import osmium

logger = logging.getLogger(__name__)

PIPELINE_VERSION = 6


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
    "sea": eurostat_sea_lanes.SOURCES["sea_lanes"],
    "land": _natural_earth("land"),
    "lakes": _natural_earth("lakes"),
    "rivers": _natural_earth("rivers_lake_centerlines"),
    **step2_hub_connectors.HUB_TABLES,
    "osm": step1_osm_ways.GEOFABRIK,
}
MODES = [
    {"name": "road", "source": "osm"},
    {"name": "rail", "source": "osm"},
    {"name": "sea", "source": "sea"},
    {"name": "port", "source": "ports"},
    {"name": "airport", "source": "airports"},
    {"name": "rail_terminal", "source": "rail_terminals"},
]
# The land mask covers the roads of the region and this margin around them, in
# degrees. A sea connector runs inside the mask.
MARGIN_DEGREES = 2

download = (
    step1_osm_ways.download
)  # for the sources without their own download: checks osmium first


def select_vehicle_ferries_with_class(
    tags: "osmium.osm.TagList",
) -> tuple[int, str] | None:
    """Return the direction and the class of a vehicle ferry, and None for any other
    way. The class is the `route` value of the way. Example: a shuttle train gives
    `(0, "shuttle_train")`.
    """
    direction = step1_osm_ways.select_vehicle_ferries(tags)
    return None if direction is None else (direction, tags["route"])


def select_rail(tags: "osmium.osm.TagList") -> int | None:
    """Return 0 (both ways) for a railway line (`railway=rail`) that is not a siding,
    a spur or a yard track, and None for any other way.
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


def select_rail_with_class(
    tags: "osmium.osm.TagList",
) -> tuple[int, str] | None:
    """Return the direction and the class of a railway line, and None for any other
    way. A line with `highspeed=yes` has the class `rail_highspeed`. Another line has
    the class of its `usage` value: `rail_main` for `main`, `rail_branch` for `branch`,
    and `rail_other` for any other value or none.
    """
    direction = select_rail(tags)
    if direction is None:
        return None
    if tags.get("highspeed") == "yes":
        return direction, "rail_highspeed"
    usage = {"main": "rail_main", "branch": "rail_branch"}
    return direction, usage.get(tags.get("usage"), "rail_other")


def build(
    files: dict[str, str],
    *,
    max_km_between_nodes: float = step1_osm_ways.MAX_KM_BETWEEN_NODES,
    min_component_nodes: int | None = None,
    work_dir: str | os.PathLike | None = None,
) -> tuple[dict, list[dict]]:
    """Build the multimodal network of a region. `osm_world_multimodal` calls this
    function with other values of the keywords.

    Args:
        files: The path of the downloaded file of each source of `SOURCES`.
        max_km_between_nodes: The length in km at which a way is cut, and at which a
            chain is cut. Two nodes along a way are at most about twice this far apart.
        min_component_nodes: The smallest number of nodes of a kept component. None keeps
            only the largest component.
        work_dir: A folder where the build keeps files between its steps, so that a later
            build resumes from them. None keeps nothing.

    Returns:
        `(arrays, node_modes)`: the arrays of the network file and the node modes table.
    """

    def folder(step):
        return os.path.join(work_dir, step) if work_dir else None

    # 1. The railways and the roads, in one read of the extract. Each network has its
    # own junctions and its own pieces, so that a level crossing does not join them.
    # Each select function gives the class of a way with its direction.
    pieces = step1_osm_ways.build_way_pieces(
        files["osm"],
        {
            "rail": {"ways": select_rail_with_class},
            "road": {
                "ways": select_main_roads_with_class,
                "ferries": select_vehicle_ferries_with_class,
            },
        },
        ("railway", "highway", "route"),
        max_km_between_nodes,
        folder("ways"),
        optional_modes=("rail",),
    )
    roads = step3_network_assembly.build_graph_from_pieces(pieces["road"])
    layers = {"road": roads}
    # A region may have no railway. Its hubs then join the roads and the sea lanes.
    if len(pieces["rail"].km):
        layers["rail"] = step3_network_assembly.build_graph_from_pieces(
            pieces["rail"]
        )
    del pieces  # the graphs hold their own arrays
    # 2. The sea lanes, with the passage of each lane as its class
    with log_step(logger, "read the sea lanes", {}) as counts:
        sea = eurostat_sea_lanes.build_sea_lane_arrays(
            {"sea_lanes": files["sea"]}
        )
        counts["nodes"] = len(sea["source_node_ids"])
    # 3. The land and the water around the roads, where connectors are checked
    node_points = memoryview(roads["node_points"])  # 1e-7 degree
    latitudes, longitudes = node_points[0::2], node_points[1::2]
    south = max(-90, min(latitudes) * 1e-7 - MARGIN_DEGREES)
    west = max(-180, min(longitudes) * 1e-7 - MARGIN_DEGREES)
    north = min(90, max(latitudes) * 1e-7 + MARGIN_DEGREES)
    east = min(180, max(longitudes) * 1e-7 + MARGIN_DEGREES)
    # `join_networks_at_hubs` frees the roads. Delete the views, so that nothing here keeps them
    del node_points, latitudes, longitudes
    mask = LandMask.from_natural_earth(
        *(files[name] for name in ("land", "lakes", "rivers")),
        bbox=(south, west, north, east),
    )
    # 4. The hubs inside the raster
    region_hubs = (
        step2_hub_connectors.read_ports(files["ports"])
        + step2_hub_connectors.read_airports(files["airports"])
        + step2_hub_connectors.read_rail_terminals(files["rail_terminals"])
    )
    region_hubs = [
        hub for hub in region_hubs if mask.get_cell(*hub.point) is not None
    ]
    # 5. Join the networks at the hubs, and the airports by their flights
    with log_step(
        logger, "join at the hubs", {"hubs": len(region_hubs)}
    ) as counts:
        graph, joined = step2_hub_connectors.join_networks_at_hubs(
            {**layers, "sea": sea},
            region_hubs,
            mask,
            [mode["name"] for mode in MODES],
            flights=step2_hub_connectors.read_flights(files["flights"]),
            work_dir=folder("hubs"),
        )
        counts.update(joined)
    # 6. Keep the connected network, contract its chains, number its nodes
    arrays = step3_network_assembly.assemble_network(
        graph,
        max_km_between_nodes=max_km_between_nodes,
        min_component_nodes=min_component_nodes,
    )
    return arrays, MODES


VALIDATION = {
    "cases": {
        "europe/denmark": [
            "aarhus_to_copenhagen_intermodal",
            "arhus_port",
            "aalborg_airport",
        ],
    },
}
