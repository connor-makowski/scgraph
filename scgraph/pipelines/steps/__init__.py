"""Pipeline execution stages:
- stage1_extract: Data ingestion and polyline extraction (OSM, ArcGIS)
"""

from scgraph.pipelines.steps.stage1_extract import arcgis, osm
