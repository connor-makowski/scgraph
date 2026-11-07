"""Railway lines (`railway=rail`, sidings and yards included) of an OpenStreetMap extract
from Geofabrik, for example `region="europe/luxembourg"`."""

from scgraph.geograph import GeoGraph
from scgraph.pipelines.steps import osm

PIPELINE_VERSION = 1

SOURCES = {"rail": osm.GEOFABRIK}

download = osm.download  # checks osmium before downloading a large extract


def build(files):
    return GeoGraph.load_from_osm(
        files["rail"], select=rail, tag_keys=("railway",)
    )


def rail(tags):
    """The direction of a railway line (`railway=rail`), None for any other way."""
    return osm.direction(tags) if tags.get("railway") == "rail" else None
