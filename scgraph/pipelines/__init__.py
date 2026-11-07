"""
Pipelines: how `GeoGraph.build_geograph` builds a network from its online sources, one
module per network, each a starting point to copy and adapt.

A pipeline is a module with four names:

- `SOURCES`: name -> each source to download: its `url` (`{region}` in it is replaced by
  the `region` argument of `build_geograph`), the `credit` to cite with results, and its
  `license` (SPDX identifier, `LicenseRef-…` when SPDX has none, `NOASSERTION` when it could
  not be established) with the `license_url` where it is stated, and for a pinned source
  its `version` (a tag or a date)
- `PIPELINE_VERSION`: an integer, raised when the same sources would give a different
  graph; a refactoring that leaves the graph unchanged does not raise it; it is never lowered
  once released. A network that reuses others adds their versions; a cached network built
  with another `PIPELINE_VERSION` is built again
- `build(files)`: given name -> downloaded file, returns the GeoGraph, or `(GeoGraph,
  steps)` where `steps` lists what each step did, `{"step": name, <count>: int, ...}`
  (a network that reuses others concatenates their steps)
- `download(url, filename)`, optional: how to download a source (default: `download_file`);
  it may return a dict added to the source's record, such as the `version` of its data
  (`osm.download`: the time an OSM extract is up to; `arcgis.download`: a layer's last edit)

The first paragraph of the module docstring describes the network (shown by
`GeoGraph.list_buildable_geographs`). Functions that `build` passes on, such as a `select`
of ways or a `connect` of two networks, are conventions inside `build`, not part of the
contract. Steps pass a graph as the tuple `graph, nodes, shapes, node_ids`, the GeoGraph
layout.

The steps (`scgraph.pipelines.steps`), organized in sequential stages:

- `stage1_extract`: data extraction and ingestion (`osm.py`, `arcgis.py`)
- a region, in memory: `osm.read_osm` (`osm.locate_ways` -> `polylines_to_graph`, from
  `scgraph.helpers.polylines`, also used by `load_from_geojson`) ->
  `assembly.keep_largest_component`
- the planet, streamed: `osm.locate_ways` (every kind of way in one read) ->
  `cut_polylines` (`scgraph.helpers.polylines`) -> `csr_from_arcs` -> `strong_components`
  -> `contract_chains` (with the cut's `max_km`) -> `simplify_shapes` (`assembly`, C++
  when built)

`build_geograph` writes into the network file's header what built it (`build_metadata`),
read back by `GeoGraph.scgraph_info`: `pipeline` (`name`, `region`, `version`), `sources`
(`name`, `url`, `sha256`, `bytes`, `credit`, `license`, `license_url` and `version` if the
data has one), `software` (`scgraph`, its `backend`, `cpp` or `python`, and the `platform`
with its C library or macOS version), `description` (the module docstring, so `python
-OO`, which drops docstrings, gives another file) and `steps`. It holds no clock time (the
download time stays in the cache's `cache.json`). A cached network is built again only for
another `PIPELINE_VERSION` or file format.

Same pipeline, same sources, same scgraph version, same backend and same platform and C
library or macOS version: byte-identical file (tested). The C++ and Python builds give the
same graph, the same nodes, arcs and lengths (tested with the `marnet` pipeline on a small
synthetic input); only the order of arcs within a node and ties between equal-length
routes may differ. Across platforms, a few lengths or shape points may differ in the last
bit (the platform's math library).

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

import inspect
import logging
import platform
import sysconfig

import requests

from scgraph.utils import has_cpp

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


def build_metadata(
    name, region, version, sources, description=None, steps=None
):
    """The build metadata that `build_geograph` writes into a network file's header (its
    fields: this module's docstring), from plain values, without a GeoGraph: `name`,
    `region` and `version` are the pipeline's, `sources` the records of the downloaded
    sources, `description` the pipeline's docstring and `steps` what `build` returned;
    `software` is added.
    """
    from scgraph.geograph import GeoGraph

    libc = " ".join(platform.libc_ver()).strip()
    macos = platform.mac_ver()[0]
    system = f"macOS {macos}" if macos else libc
    return {
        "pipeline": {"name": name, "region": region, "version": version},
        "sources": sources,
        "software": {
            "scgraph": GeoGraph.__scgraph_version__(),
            "backend": "cpp" if has_cpp() else "python",
            "platform": f"{sysconfig.get_platform()} {system}".strip(),
        },
        **(
            {"description": inspect.cleandoc(description)}
            if description
            else {}
        ),
        **({"steps": steps} if steps else {}),
    }


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
