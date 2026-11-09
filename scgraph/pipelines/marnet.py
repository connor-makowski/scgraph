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
        "expected_km": 6151.0,
        "tolerance": 0.05,
        "comment": "Transatlantic shipping corridor",
    },
    {
        "id": "rotterdam_to_singapore",
        "origin": (51.95, 4.14),
        "destination": (1.28, 103.85),
        "expected_km": 15551.1,
        "tolerance": 0.05,
        "comment": "Europe to Asia maritime corridor via Suez Canal",
    },
]
