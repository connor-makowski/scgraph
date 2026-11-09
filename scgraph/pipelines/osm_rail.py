"""Railway lines (`railway=rail`, sidings and yards included) of an OpenStreetMap extract
from Geofabrik, for example `region="europe/luxembourg"`.

Drawings: each piece's shape is simplified at 50 m when the way is cut; lengths are
measured before.
"""

from scgraph.pipelines.steps.stage1_extract import osm
from scgraph.pipelines.steps.stage3_assembly import assembly

PIPELINE_VERSION = 1

SOURCES = {"rail": osm.GEOFABRIK}

download = osm.download  # checks osmium before downloading a large extract


def build(files):
    pieces, steps = osm.build_way_pieces(
        files["rail"], {"rail": rail}, ("railway",), osm.MAX_KM
    )
    graph = assembly.build_graph_from_pieces(pieces)
    arrays, assembled = assembly.assemble(
        graph, max_km=osm.MAX_KM, min_nodes=None
    )
    return (arrays, [{"name": None}]), steps + assembled


def rail(tags):
    """The direction of a railway line (`railway=rail`), None for any other way."""
    return osm.direction(tags) if tags.get("railway") == "rail" else None


# ---------------------------------------------------------------------------
# Stage 4 Validation Contract
# ---------------------------------------------------------------------------
VALIDATION = {
    "modes": ("rail",),
    "cases": {
        "europe/luxembourg": ["luxembourg_to_bettembourg"],
    },
}
