"""Sea lanes of the published `oak_ridge_maritime` network (Oak Ridge National Laboratory,
Global Shipping Lane Network, 2000)."""

from scgraph.geograph import GeoGraph

PIPELINE_VERSION = 1

SOURCES = {
    "sea_lanes": {
        "url": "https://raw.githubusercontent.com/connor-makowski/scgraph/22e9c1471ce9f41fdbe65b9c6130766a60db9df4/geograph_utils/oak_ridge_maritime.geojson",
        "credit": "Oak Ridge National Laboratory, CTA Transportation Network Group, Global Shipping Lane Network (2000)",
        "license": "NOASSERTION",
        "license_url": None,
    }
}


def build(files: dict[str, str]) -> GeoGraph:
    return GeoGraph.load_from_geojson(files["sea_lanes"], precision=4)


# ---------------------------------------------------------------------------
# Stage 4 Validation Contract
# ---------------------------------------------------------------------------
VALIDATION = {
    "cases": ["rotterdam_to_new_york", "panama_canal_transit"],
}
