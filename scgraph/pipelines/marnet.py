"""Sea lanes of the published `marnet` network (Eurostat SeaRoute, via searoute-py, edited
for scgraph around the antimeridian)."""

from scgraph.geograph import GeoGraph

PIPELINE_VERSION = 1

SOURCES = {
    "sea_lanes": {
        "url": "https://raw.githubusercontent.com/connor-makowski/scgraph/22e9c1471ce9f41fdbe65b9c6130766a60db9df4/geograph_utils/marnet.geojson",
        "credit": "Eurostat SeaRoute, via searoute-py (edited for scgraph)",
        "license": "EUPL-1.2",
        "license_url": "https://github.com/eurostat/searoute/blob/master/LICENSE",
    }
}


def build(files: dict[str, str]) -> GeoGraph:
    return GeoGraph.load_from_geojson(
        files["sea_lanes"], precision=4, silent=True
    )


# ---------------------------------------------------------------------------
# Stage 4 Validation Contract
# ---------------------------------------------------------------------------
VALIDATION = {
    "cases": ["rotterdam_to_new_york", "rotterdam_to_singapore"],
}
