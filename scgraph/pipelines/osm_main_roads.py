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

from scgraph.pipelines.steps.stage1_extract import osm
from scgraph.pipelines.steps.stage3_assembly import assembly

PIPELINE_VERSION = 1

SOURCES = {"roads": osm.GEOFABRIK}
SELECTS = {"roads": osm.main_roads, "ferries": osm.vehicle_ferries}

download = osm.download  # checks osmium before downloading a large extract


def build(
    files,
    *,
    source=osm.open_osm_source,
    max_km=osm.MAX_KM,
    min_nodes=None,
    folder=None,
):
    """The keywords give another scale (`world_main_roads`); `min_nodes=None` keeps
    the largest component only."""
    pieces, steps = osm.build_way_pieces(
        source(files["roads"]), SELECTS, ("highway", "route"), max_km, folder
    )
    graph = assembly.build_graph_from_pieces(pieces)
    arrays, assembled = assembly.assemble(
        graph, max_km=max_km, min_nodes=min_nodes
    )
    return (arrays, [{"name": None}]), steps + assembled


# ---------------------------------------------------------------------------
# Stage 4 Validation Contract
# ---------------------------------------------------------------------------
VALIDATION_CASES = [
    {
        "id": "luxembourg_to_esch",
        "region": "europe/luxembourg",
        "origin": (49.6116, 6.1319),
        "destination": (49.4958, 5.9806),
        "expected_km": 19.7,
        "tolerance": 0.10,
        "comment": "Luxembourg capital to Esch-sur-Alzette (A4 freeway)",
    },
]
