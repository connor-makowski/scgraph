"""The functions of the steps of a build, in four stages.

- `stage1_extract` reads the sources: OpenStreetMap files (`osm`) and ArcGIS layers
  (`arcgis`).
- `stage2_intermodal` joins the networks of several modes at hubs (`hubs`), with a
  land mask (`landmask`).
- `stage3_assembly` assembles the graph of the network file (`assembly`).
- `stage4_validation` checks a built network against known routes.
"""

from scgraph.pipelines.steps.stage3_assembly import assembly
from scgraph.pipelines.steps.stage2_intermodal import hubs, landmask
from scgraph.pipelines.steps.stage1_extract import arcgis, osm
from scgraph.pipelines.steps.stage4_validation import (
    ValidationResult,
    load_cases,
    validate_network,
)
