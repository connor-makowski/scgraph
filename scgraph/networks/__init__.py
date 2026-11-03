"""
Build scripts of the networks that `GeoGraph.build_geograph` builds from their online
sources, one module per network:

- the first paragraph of the module docstring describes the network (shown by
  `GeoGraph.list_downloadable_geographs`)
- `SOURCES`: name -> each source to download: its `url` (`{region}` in it is replaced by
  the `region` argument of `build_geograph`), the `credit` to cite with results, and its
  `license` (SPDX identifier, `LicenseRef-…` when SPDX has none, `NOASSERTION` when it could
  not be established) with the `license_url` where it is stated
- `build(files)`: given name -> downloaded file, returns the GeoGraph
- `VERSION`: an integer, raised when `build` changes the network it returns; a cached
  network built with another `VERSION` is built again
- `download(url, filename)`, optional: how to download a source when it is not a single file
  (default: `download_file`)
"""

import logging

import requests

logger = logging.getLogger(__name__)

NAMES = (
    "marnet",
    "north_america_rail",
    "oak_ridge_maritime",
    "osm_main_roads",
    "osm_rail",
    "us_freeway",
)
REGIONS = "https://download.geofabrik.de"  # where the regions of the OSM networks are listed
LARGE_DOWNLOAD = (
    100e6  # bytes; announced with a warning, visible without logging set up
)


def download_file(url: str, filename: str) -> None:
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        size = int(response.headers.get("Content-Length", 0))
        logger.log(
            logging.WARNING if size > LARGE_DOWNLOAD else logging.INFO,
            "Downloading %s (%.1f MB)",
            url,
            size / 1e6,
        )
        with open(filename, "wb") as file:
            for chunk in response.iter_content(chunk_size=1 << 20):
                file.write(chunk)
