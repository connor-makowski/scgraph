"""Class I railroads of North America, from the North American Rail Network of the U.S.
Federal Railroad Administration."""

from scgraph.geograph import GeoGraph
from scgraph.networks import arcgis

VERSION = 2

SOURCES = {
    "lines": {
        "url": "https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/NTAD_North_American_Rail_Network_Lines_Class_I_Railroads/FeatureServer/0",
        "credit": "Federal Railroad Administration and Bureau of Transportation Statistics, North American Rail Network Lines, Class I (NTAD)",
        "license": "LicenseRef-US-Government-Work",
        "license_url": "https://www.arcgis.com/home/item.html?id=197e48526e284a28bfddf9100553019f",
    }
}

download = arcgis.download  # the layer is read page by page


def build(files):
    # Arcs keep the length of their full shape, but not the shape itself: with about
    # 2 million points, it would make the network ten times slower to load
    return GeoGraph.load_from_geojson(
        files["lines"],
        precision=4,
        silent=True,
        max_km_between_nodes=2,
        load_intermediate_nodes=False,
    )
