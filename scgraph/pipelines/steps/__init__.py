"""Pipeline execution stages:
- stage1_extract: Data ingestion and polyline extraction (OSM, ArcGIS)
- stage3_assembly: CSR topology, connectivity, and assembly
"""

from scgraph.pipelines.steps.stage1_extract import arcgis, osm
from scgraph.pipelines.steps.stage3_assembly import assembly
