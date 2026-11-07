"""Main roads (motorway, trunk, primary and their links) of an OpenStreetMap extract from
Geofabrik, for example `region="europe/luxembourg"`."""

from scgraph.geograph import GeoGraph
from scgraph.pipelines.steps import osm

VERSION = 1

SOURCES = {"roads": osm.GEOFABRIK}

download = osm.download  # checks osmium before downloading a large extract


def build(files):
    return GeoGraph.load_from_osm(files["roads"])
