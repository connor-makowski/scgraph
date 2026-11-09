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
