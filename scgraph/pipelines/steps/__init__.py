"""Pipeline execution stages:
- stage1_extract: Data ingestion and polyline extraction (OSM, ArcGIS)
- stage2_intermodal: Domain-specific connectors and integration (ports, landmask)
- stage3_assembly: CSR topology, connectivity, and assembly
"""

from scgraph.pipelines.steps.stage3_assembly import assembly
from scgraph.pipelines.steps.stage2_intermodal import landmask, ports
from scgraph.pipelines.steps.stage1_extract import arcgis, osm
