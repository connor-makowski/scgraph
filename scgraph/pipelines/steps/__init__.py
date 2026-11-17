"""Pipeline execution stages:
- stage1_extract: Data ingestion and polyline extraction (OSM, ArcGIS)
- stage2_intermodal: Domain-specific connectors and integration (hubs, landmask)
- stage3_assembly: CSR topology, connectivity, and assembly
- stage4_validation: Pipeline acceptance testing and route certification
"""

from scgraph.pipelines.steps.stage3_assembly import assembly
from scgraph.pipelines.steps.stage2_intermodal import hubs, landmask
from scgraph.pipelines.steps.stage1_extract import arcgis, osm
from scgraph.pipelines.steps.stage4_validation import (
    ValidationResult,
    load_cases,
    validate_network,
)
