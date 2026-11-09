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


def build(files):
    return GeoGraph.load_from_geojson(
        files["sea_lanes"], precision=4, silent=True
    )


# ---------------------------------------------------------------------------
# Stage 4 Validation Contract
# ---------------------------------------------------------------------------
VALIDATION_CASES = [
    {
        "id": "rotterdam_to_new_york",
        "origin": (51.95, 4.14),
        "destination": (40.71, -74.01),
        "expected_km": 6132.1,
        "tolerance": 0.05,
        "comment": "Transatlantic shipping corridor (ORNL 2000)",
    },
    {
        "id": "panama_canal_transit",
        "origin": (9.36, -79.90),
        "destination": (8.95, -79.57),
        "expected_km": 65.0,
        "tolerance": 0.10,
        "comment": "Panama Canal crossing between Caribbean and Pacific",
    },
]
