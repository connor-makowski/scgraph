"""Main roads (motorway, trunk, primary and their links) and vehicle ferries of the
world, from the OpenStreetMap planet: `osm_main_roads` for the planet.

- A distance is in km along the main roads and the vehicle ferries. One-way roads are
  followed in their legal direction. There are no times.
- A vehicle ferry joins two road nodes, both ways, with the length of its route. A
  car shuttle train, such as the one of the Channel Tunnel, counts as a ferry. Each
  end joins the nearest road node, if that node is within 2 km. Otherwise the ferry is
  left out.
- The network keeps each strongly connected component of at least 1,000 nodes, so an
  island with roads of its own is a separate network.
- A road is cut every 10 km, and a contracted arc ends at the first node where it
  reaches 10 km. Two nodes along a road are then at most about 20 km apart.
- The shape of each arc is simplified to within 50 m. Its length is measured on the
  full shape.
- Checked by the cases of `VALIDATION`. 20 driving distances between large cities are
  within 10 % of the distance of a road router (15 % for one case). The 1,004 cities
  above 500,000 people have a road route to the main city of their landmass; 1 % of
  them may fail. 11 crossings by bridge, tunnel or ferry have a road route.
- Size, with the planet of 2026-11-02: 2.9 million nodes, 5.0 million arcs, and a file
  of 258 MB.
- Source: the OpenStreetMap planet of the date in its URL. It is read by HTTP byte
  ranges and never stored, and its published md5 is recorded. The build needs the C++
  extension of scgraph.
- Not for navigation or travel times. Not for places far from a main road: there, the
  straight line to the nearest node is most of the distance.
"""

import os

from scgraph.pipelines import osm_main_roads
from scgraph.pipelines.steps.stage1_extract import osm

PIPELINE_VERSION = 2

SOURCES = {"roads": osm.PLANET}
# The length in km at which a way is cut, and at which a chain is cut. A larger
# value gives fewer nodes: with 10, the world network has about 3 million nodes.
MAX_KM_BETWEEN_NODES = 10
# The network keeps each component of at least 1,000 nodes. The roads of an island
# then stay in the file, and a small fragment does not.
MIN_COMPONENT_NODES = 1000


def build(
    files: dict[str, str],
    *,
    work_dir: str | os.PathLike | None = None,
) -> tuple[dict, list[dict]]:
    """Build the main roads of the world: `osm_main_roads.build`, with the cut length and
    the component size of this module.
    """
    return osm_main_roads.build(
        files,
        max_km_between_nodes=MAX_KM_BETWEEN_NODES,
        min_component_nodes=MIN_COMPONENT_NODES,
        work_dir=work_dir,
    )


# Every crossing except `copenhagen_odense`. The centre of Odense is 5.2 km from
# the nearest road node of this network, and the limit of the crossing rule is
# 5 km. The two world networks with ports pass this case: their nearest road node
# is 4.9 km from the centre.
VALIDATION = {
    "cases": [
        "road_distances",
        "coverage",
        "london_paris",
        "dover_calais",
        "copenhagen_malmo",
        "ronne_copenhagen",
        "messina_reggio_di_calabria",
        "kadikoy_istanbul",
        "hobart_melbourne",
        "sapporo_tokyo",
        "victoria_vancouver",
        "manama_dammam",
        "singapore_johor_bahru",
    ],
}
