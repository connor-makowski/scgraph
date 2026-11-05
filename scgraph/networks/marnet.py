"""Sea lanes of the published `marnet` network (Eurostat SeaRoute, via searoute-py, edited
for scgraph around the antimeridian)."""

from scgraph.geograph import GeoGraph

VERSION = 2

SOURCES = {
    "lines": {
        "url": "https://raw.githubusercontent.com/connor-makowski/scgraph/22e9c1471ce9f41fdbe65b9c6130766a60db9df4/geograph_utils/marnet.geojson",
        "credit": "Eurostat SeaRoute, via searoute-py (edited for scgraph)",
        "license": "EUPL-1.2",
        "license_url": "https://github.com/eurostat/searoute/blob/master/LICENSE",
    }
}


def build(files):
    return GeoGraph.load_from_geojson(files["lines"], precision=4, silent=True)
