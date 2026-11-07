"""Download an ArcGIS feature layer as one GeoJSON file, page by page."""

import json
import logging
from datetime import datetime, timezone

import requests

logger = logging.getLogger("scgraph.networks.arcgis")


def download(url: str, filename: str) -> dict:
    """Write the layer as GeoJSON; return its `version`, the time of the last edit of its
    data (ISO 8601), if the layer gives it."""
    layer = _get(url, f="json")
    count = _get(f"{url}/query", where="1=1", returnCountOnly="true", f="json")[
        "count"
    ]
    logger.info("Downloading %s features from %s", f"{count:,}", url)
    features = []
    while len(features) < count:
        page = _get(
            f"{url}/query",
            where="1=1",
            outFields=layer["objectIdField"],
            outSR=4326,
            orderByFields=layer["objectIdField"],
            resultOffset=len(features),
            resultRecordCount=layer["maxRecordCount"],
            f="geojson",
        )["features"]
        if not page:
            break
        features += page
    if len(features) != count:
        raise ConnectionError(
            f"{url}: received {len(features)} features, the layer has {count}"
        )
    with open(filename, "w") as file:
        json.dump({"type": "FeatureCollection", "features": features}, file)
    # The last edit of its data (in ms), not of its schema, when the layer says
    editing = layer.get("editingInfo", {})
    edited = editing.get("dataLastEditDate", editing.get("lastEditDate"))
    if edited is None:
        return {}
    time = datetime.fromtimestamp(edited / 1000, timezone.utc)
    return {"version": time.isoformat(timespec="seconds")}


def _get(url, **params):
    response = requests.get(url, params=params, timeout=300)
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise ConnectionError(f"{url}: {data['error']}")
    return data
