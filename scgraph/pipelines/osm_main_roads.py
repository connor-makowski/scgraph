"""Main roads (motorway, trunk, primary and their links) of an OpenStreetMap extract from
Geofabrik, for example `region="europe/luxembourg"`."""

from scgraph.geograph import GeoGraph
from scgraph.pipelines.steps.stage1_extract import osm

PIPELINE_VERSION = 1

SOURCES = {"roads": osm.GEOFABRIK}

download = osm.download  # checks osmium before downloading a large extract


def build(files):
    return GeoGraph.load_from_osm(files["roads"])
