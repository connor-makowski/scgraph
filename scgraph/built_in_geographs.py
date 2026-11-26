"""The seven networks of scgraph 3.6.0, the built-in geographs. They are deprecated.

This module is internal. It holds what scgraph knows of these networks, except the
conversion of a `.graphjson` file to a `.scgraph` file, which `geograph_networks` makes:

- `BUILT_IN_GEOGRAPHS`, their names. Each one has its description and the released
  network that covers the same need with newer data;
- `GEOGRAPH_URL`, where their `.graphjson` files are published;
- `fetch_built_in_geograph`, which downloads one of these files into the cache;
- `warn_deprecated_load` and `warn_deprecated_url`, the deprecation warnings of
  these networks and of `geograph_url`.

scgraph 5.0 removes these networks: this module and its calls then go.

`GeoGraph.load_geograph` and `GeoGraph.list_geographs` call this module.
"""

import warnings
from pathlib import Path

import requests

from scgraph import files

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


def warn_deprecated_url(geograph_url: str, stacklevel: int = 3) -> None:
    """Warn that `geograph_url` is deprecated, if the caller gave another URL than the
    default one. The default `stacklevel` points the warning at the caller of the
    function that calls this one."""
    if geograph_url != GEOGRAPH_URL:
        warnings.warn(
            "`geograph_url` is deprecated. scgraph 5.0 removes it. To load your "
            "own network, use `GeoGraph.load_from_graphjson` or "
            "`GeoGraph.load_from_scgraph`.",
            DeprecationWarning,
            stacklevel=stacklevel,
        )


def warn_deprecated_load(name: str, geograph_url: str) -> None:
    """Give the deprecation warnings of `load_geograph`: one for another
    `geograph_url`, and one for a network of scgraph 3.6.0.

    Args:
        name: The name of the network to load.
        geograph_url: The `geograph_url` of the call.
    """
    warn_deprecated_url(geograph_url, stacklevel=4)
    if geograph_url == GEOGRAPH_URL and name in BUILT_IN_GEOGRAPHS:
        replacement = BUILT_IN_GEOGRAPHS[name]["superseded_by"]
        warnings.warn(
            f"The network '{name}' of scgraph 3.6.0 is deprecated. scgraph 5.0 "
            f"removes it. Use '{replacement}', a released network with newer "
            "data. Its results differ (MIGRATING.md).",
            DeprecationWarning,
            stacklevel=3,
        )


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
    with files.write_atomically(cached_file, "download") as download:
        download.write_bytes(response.content)
