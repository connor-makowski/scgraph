"""The seven networks of scgraph 3.6.0, the built-in geographs.

This module is internal. It holds all that scgraph knows of these networks, and
nothing else:

- `BUILT_IN_GEOGRAPHS`, their names. Each one has its description and the released
  network that covers the same need with newer data;
- `GEOGRAPH_URL`, where their `.graphjson` files are published;
- `fetch_built_in_geograph`, which downloads one of these files into the cache.

`GeoGraph.load_geograph` and `GeoGraph.list_geographs` call this module.
"""

import os
import secrets
from pathlib import Path

import requests

GEOGRAPH_URL = (
    "https://raw.githubusercontent.com/connor-makowski/scgraph/main/geographs"
)
# The seven networks of scgraph 3.6.0, published as `.graphjson` files at `GEOGRAPH_URL`,
# and what `list_geographs` says of each one. `superseded_by` names
# the released network that covers the same need with newer data. That network may
# hold more modes, and its results differ.
BUILT_IN_GEOGRAPHS = {
    "marnet": {
        "description": "Sea lanes of the world (Eurostat SeaRoute)",
        "superseded_by": "world_sea",
    },
    "north_america_rail": {
        "description": "Class I railroads of North America",
        "superseded_by": "north_america",
    },
    "oak_ridge_maritime": {
        "description": "Sea lanes of the world (Oak Ridge National Laboratory, 2000)",
        "superseded_by": "world_sea",
    },
    "us_freeway": {
        "description": "Freeways of the United States",
        "superseded_by": "north_america",
    },
    "world_highways_and_marnet": {
        "description": "Highways of the world, joined to the sea lanes of marnet",
        "superseded_by": "world_multimodal",
    },
    "world_highways": {
        "description": "Highways of the world",
        "superseded_by": "world_multimodal",
    },
    "world_railways": {
        "description": "Railways of the world",
        "superseded_by": "world_rail",
    },
}


def fetch_built_in_geograph(
    name: str, cached_file: Path, geograph_url: str
) -> None:
    """Download the `.graphjson` file of a built-in geograph into the cache.

    Args:
        name: The name of the built-in geograph.
        cached_file: The path of the file to write, in the cache.
        geograph_url: The URL of the folder that holds `<name>.graphjson`.

    Raises:
        FileNotFoundError: The URL has no file of this name.
        ConnectionError: The server answers with another error status.
    """
    url = f"{geograph_url}/{name}.graphjson"
    response = requests.get(url, timeout=60)
    if response.status_code == 404:
        raise FileNotFoundError(
            f"Geograph '{name}' not found at '{url}'. "
            f"Check that the name is correct and the file exists in the scgraph GitHub repository."
        )
    if not response.ok:
        raise ConnectionError(
            f"Failed to download geograph '{name}' from '{url}'. "
            f"HTTP status: {response.status_code}."
        )
    # The download is written next to the cache file, then moved onto it. A download that
    # fails never leaves a part of a file under the name that later loads read.
    download = cached_file.with_name(
        f".{cached_file.name}.{os.getpid()}.{secrets.token_hex(4)}.download"
    )
    try:
        download.write_bytes(response.content)
        os.replace(download, cached_file)
    except BaseException:
        download.unlink(missing_ok=True)
        raise
