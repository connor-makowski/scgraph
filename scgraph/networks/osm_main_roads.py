"""Main roads (motorway, trunk, primary and their links) of an OpenStreetMap extract from
Geofabrik, for example `region="europe/luxembourg"`."""

from scgraph.geograph import GeoGraph
from scgraph.networks import download_file
from scgraph.osm import require_osmium

VERSION = 1

SOURCES = {
    "roads": {
        "url": "https://download.geofabrik.de/{region}-latest.osm.pbf",
        "credit": "© OpenStreetMap contributors",
        "license": "ODbL-1.0",
        "license_url": "https://www.openstreetmap.org/copyright",
    }
}


def download(url, filename):
    require_osmium()  # before downloading a large extract it could not read
    download_file(url, filename)


def build(files):
    return GeoGraph.load_from_osm(files["roads"])
