"""
Pipelines: how `GeoGraph.build_geograph` builds a network from its online sources, one
module per network, each a starting point to copy and adapt.

A pipeline is a module with four names:

- `SOURCES`: name -> each source to download: its `url` (`{region}` in it is replaced by
  the `region` argument of `build_geograph`), the `credit` to cite with results, and its
  `license` (SPDX identifier, `LicenseRef-…` when SPDX has none, `NOASSERTION` when it could
  not be established) with the `license_url` where it is stated
- `PIPELINE_VERSION`: an integer, raised when the same sources would give a different
  graph; a refactoring that leaves the graph unchanged does not raise it; it is never lowered
  once released. A network that reuses others adds their versions; a cached network built
  with another `PIPELINE_VERSION` is built again
- `build(files)`: given name -> downloaded file, returns the GeoGraph, or `(GeoGraph,
  details)` where `details` is a dict added to the manifest
- `download(url, filename)`, optional: how to download a source (default: `download_file`)

The first paragraph of the module docstring describes the network (shown by
`GeoGraph.list_buildable_geographs`). Functions that `build` passes on, such as a `select`
of ways or a `connect` of two networks, are conventions inside `build`, not part of the
contract. Steps pass a graph as the tuple `graph, nodes, shapes, node_ids`, the GeoGraph
layout.

The steps (`scgraph.pipelines.steps`), for each scale:

- a region, in memory: `osm.located_ways` -> `polylines_to_graph` (`scgraph.helpers.polylines`, also
  used by `load_from_geojson`) -> `osm.keep_largest_component`
- the planet, streamed: `osm.located_ways` -> `cut_polylines` (`scgraph.helpers.polylines`) ->
  `csr_from_arcs` -> `strong_components` -> `simplify_shapes` (the last three are added
  with the assembly kernels, #206)

The core never imports `scgraph.pipelines` at load time: `load_from_osm` and
`build_geograph` import it when they are called.

A pipeline of your own, here the cycleways of an OpenStreetMap extract, both ways:

```py
from scgraph import GeoGraph
from scgraph.pipelines.steps import osm

PIPELINE_VERSION = 1
SOURCES = {"ways": osm.GEOFABRIK}
download = osm.download  # checks osmium before downloading the extract

def select(tags):
    return 0 if tags.get("highway") == "cycleway" else None

def build(files):
    return GeoGraph.load_from_osm(files["ways"], select=select)
```

Saved as `cycleways.py`, it is built and cached like a named network, under the last part
of the module's name: `import cycleways`, then `GeoGraph.build_geograph(cycleways,
region="europe/luxembourg")` writes `networks/cycleways/europe/luxembourg/` of the cache.
Give an adapted copy a name of its own: a module named like a built-in pipeline is refused,
and two modules with the same last name share one cache entry.
"""

import logging

import requests

logger = logging.getLogger("scgraph.networks")

NAMES = (
    "eurostat_marnet",
    "marnet",
    "north_america_rail",
    "oak_ridge_maritime",
    "osm_main_roads",
    "osm_main_roads_and_marnet",
    "osm_rail",
    "us_freeway",
)
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
