"""Freeways of the United States, from the Esri USA Freeway System layer."""

from scgraph.geograph import GeoGraph
from scgraph.pipelines.steps.stage1_extract import arcgis

PIPELINE_VERSION = 1

SOURCES = {
    "freeway_lines": {
        "url": "https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/USA_Freeway_System/FeatureServer/1",
        "credit": "Esri, USA Freeway System; sources: Esri; Bureau of Transportation Statistics (BTS); Federal Highway Administration (FHWA); GeoSystems Global Corporation in association with National Geographic Maps and Melcher Media, Inc.; i-cubed; Members of the Geographic Information Systems Laboratory, Pellissippi Research Institute, The University of Tennessee, Knoxville",
        "license": "LicenseRef-Esri-MLA",
        "license_url": "https://www.arcgis.com/home/item.html?id=91c6a5f6410b4991ab0db1d7c26daacb",
    }
}

download = arcgis.download  # the layer is read page by page


def build(files):
    return GeoGraph.load_from_geojson(
        files["freeway_lines"], precision=4, silent=True, max_km_between_nodes=2
    )


# ---------------------------------------------------------------------------
# Stage 4 Validation Contract
# ---------------------------------------------------------------------------
VALIDATION_CASES = [
    {
        "id": "new_york_to_chicago",
        "origin": (40.75, -73.98),
        "destination": (41.83, -87.75),
        "expected_km": 1326.0,
        "tolerance": 0.05,
        "comment": "I-80 / I-90 freeway corridor from East Coast to Midwest",
    },
    {
        "id": "los_angeles_to_san_francisco",
        "origin": (34.05, -118.25),
        "destination": (37.77, -122.42),
        "expected_km": 619.7,
        "tolerance": 0.05,
        "comment": "I-5 corridor connecting Southern and Northern California",
    },
]
