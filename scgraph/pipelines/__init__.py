"""
A pipeline builds one network from its online sources.

A pipeline is a module. `GeoGraph.build_geograph` runs it: the runner
(`scgraph.pipelines.network_builder`) downloads the sources, calls `build`, writes the network
file and keeps it in the cache. Each pipeline of this package is also an example to
copy and adapt. The guide `README.md` of this package follows a network from its
sources to its use: the build step by step, the derivation, the network release and the
load.

WHAT IS STABLE

scgraph keeps these names working from one release to the next: the contract below,
the three pipeline modules, `network_builder.build_network_file`,
`derived_networks.derive_network_file`, and the names in the `__all__` of
`steps.step1_osm_ways` and of `steps.step4_validation_cases`. The other functions of
`steps` are internal. A copy of a pipeline of scgraph that calls them follows one
version of scgraph.

WHAT A PIPELINE MODULE HOLDS

- Its docstring. The first paragraph describes the network, and
  `GeoGraph.list_buildable_geographs` shows it. The network file stores the whole
  docstring.
- `SOURCES`: a dict that gives a name to each source. A source is a dict:
    - `url`: where the source is. The runner replaces `{region}` in it by the `region`
      argument of `build_geograph`. A pipeline needs a region when one of its URLs
      holds `{region}`.
    - `credit`: the credit line that a user cites with results.
    - `license`: an SPDX identifier. Write `LicenseRef-…` when SPDX has no identifier,
      and `NOASSERTION` when the license could not be established.
    - `license_url`: the page that states the license.
    - `version`, optional: a tag or a date, for a source that does not change.
    - `download`, optional: a download function for this source only (see below).
- `PIPELINE_VERSION`: an integer. Raise it when the same sources would give another
  graph. Do not raise it for a change that leaves the graph the same. Never lower it
  after a release. The runner builds a cached network again when its
  `PIPELINE_VERSION` differs.
- `build(files)`: the function that builds the network. `files` gives the path of the
  downloaded file of each source, by the name of the source. `build` returns one of:
    - a GeoGraph. `eurostat_sea_lanes` does this, and so does the example below.
    - `(arrays, modes)`. `arrays` holds the arrays of the network file, as
      `network_file.write` takes them. The nodes are already in the order of the
      file: by mode, then along a Hilbert curve (`step3_network_assembly.assemble_network` gives this
      order). `weights_length` holds km. `node_modes` is the node modes table (see below).
      `geofabrik_multimodal` and `osm_world_multimodal` do this. `arrays` may hold
      `edge_class_ids`, the class of each edge (see *The classes*). The runner then
      writes the rows of `CLASSES` into the header of the network file.
  `build` may take a keyword `work_dir`. The runner then passes its work folder. A
  long build keeps files there between its steps, and a later build resumes from
  them.
- `VALIDATION`, optional: `{"cases": [...]}`, the cases that the built network must
  pass. A case describes a known route of the real world. The docstring of
  `steps/step4_validation_cases` describes the kinds of cases, their rules and the entries
  of this list. A pipeline with regions gives `{"cases": {region: [...]}}`.
- `download`, optional: a download function for the sources that have none of their
  own. The default is `download_file`.
- `NODE_ADDITION_MODES`, optional: a tuple of names of the modes table. A query
  point then snaps to a node of these modes by default. The runner writes them into
  the header of a network that `build` returns as arrays.
- `CLASSES`, optional: the classes table of the pipeline, in place of the table of
  this package (see *The classes*).

The runner reads no other name. Names such as `MODES`, `MARGIN_DEGREES` or
`MAX_KM_BETWEEN_NODES` are choices of one pipeline.

THE DOWNLOAD FUNCTIONS

A download function is `download(url, filename)`. It writes to `filename` what `build`
reads. This is the source itself, or a small file that says how to read the source in
place (`step1_osm_ways.download_streamed` does this for the planet, which is never stored).

The function may return a dict. The runner adds it to the record of the source: the
entry of the source in the header of the network file. For example, `step1_osm_ways.download`
returns the `version` of an OpenStreetMap extract, the time that its data is up to.

The runner also puts the `sha256` and the `bytes` of the downloaded file in the
record. There is one exception. A source can have its own `download` in `SOURCES`.
When that function returns a dict, the dict must identify the source, and the runner
does not compute `sha256` and `bytes`. `step1_osm_ways.download_streamed` gives the `bytes` and
the `md5` that the server publishes.

THE MODES TABLE

The mode of a node says what the node is: a node of a network (`road`, `rail`, `sea`)
or a hub (`port`, `airport`, `rail_terminal`). The modes table is a list with one
dict per mode: its `name`, and the `source` that gives the ids of its nodes. A network
with one mode gives `[{"name": None}]`.

THE CLASSES

The class of an edge is its category in the source: a motorway, a vehicle ferry, a
main railway line, a sea passage. `CLASSES` is the classes table: it gives the mode
of the edges of each class, by the name of the class. The modes of the edges are
`road`, `rail`, `sea` and `air`:

- `road`: `motorway`, `motorway_link`, `trunk`, `trunk_link`, `primary`,
  `primary_link`, `ferry`, `shuttle_train`, `road_connector`;
- `rail`: `rail_highspeed`, `rail_main`, `rail_branch`, `rail_other`,
  `rail_connector`;
- `sea`: `open_sea` for a lane outside a passage, the passages `babelmandeb`,
  `bering`, `corinth`, `dover`, `gibraltar`, `kiel`, `magellan`, `malacca`, `panama`
  and `suez`, and `sea_connector`;
- `air`: `flight`.

The purpose of a class is one speed for all its edges. So the connectors of a hub have
classes of their own: a sea connector can be 2,500 km long. No class has the name of
a mode.

A pipeline records classes when its select functions give them. A select function
returns the direction of a way: 1, -1 or 0. It may return a pair in its place: the
direction and the name of a class, for example `(1, "motorway")`. A select function
uses the names of `CLASSES` only.

A pipeline that fills `edge_class_ids` itself may define its own `CLASSES` dict in its
module, with the same form. A value of `edge_class_ids` is then the id of a class of that table,
and the runner writes that table into the header.

A network file holds the class of each edge and one row `{"name", "edge_mode"}` for each
class (`ARCHITECTURE.md`, section 7), and `network_file.read` returns them. A GeoGraph
loaded from the file holds them: `GeoGraph.classes` and `GeoGraph.get_edges`.

HOW TO RUN A PIPELINE

    GeoGraph.build_geograph("geofabrik_multimodal", region="europe/denmark")
    python -m scgraph.pipelines.network_builder geofabrik_multimodal --region europe/denmark --validate

The first line builds the network, or loads it from the cache. The command builds the
network without loading it, and prints the path of its file. With `--validate`, the
network enters the cache only if it passes its cases.

THE STEPS OF A BUILD

A build runs steps, such as "read and cut the ways" or "contract the chains". Each
step logs one line at DEBUG, with its counts and its duration (`_internal.log_step`).
The functions of the steps are in `scgraph.pipelines.steps`, one or two modules for
each step:

1. Read the sources. `step1_osm_ways.build_way_pieces` reads the ways of an OpenStreetMap
   file that the select functions keep. It takes the select functions
   of each mode. One read of the file serves every mode. Each mode gets its own
   junctions and its own pieces, so a road never joins a railway. The function
   cuts each way at the junctions of its mode, and where a piece reaches
   `max_km_between_nodes`. It simplifies the shape of each piece to within 50 m. It
   attaches the ferries to road nodes (`step1_osm_ways.build_ferry_edges`).
2. Join the modes. `step2_hub_connectors.join_networks_at_hubs` joins the networks of
   several modes at hubs: ports, airports and rail terminals. `step2_land_mask.LandMask` tells land
   from water for the connectors of a hub.
3. Assemble the graph. `step3_network_assembly.build_graph_from_pieces` stores the pieces as
   a graph. `step3_network_assembly.assemble_network` keeps the strongly connected
   components, contracts the chains of nodes and puts the nodes in the order of the
   file. No chain is contracted across two modes or two classes.
4. Validate the network. `step4_validation_cases.validate_network` checks the built
   file against the cases of `VALIDATION`.

A graph has two layouts in the steps. From `step3_network_assembly.build_graph_from_pieces` on, a
graph is a dict of the arrays of the network file. `scgraph.helpers.osm.read_osm` and
`scgraph.helpers.components.keep_largest_strongly_connected_component` use the layout of a
GeoGraph, because `load_from_osm` calls them.

WHAT THE NETWORK FILE RECORDS

The runner writes the metadata of the build into the header of the network file
(`build_metadata`). `GeoGraph.get_scgraph_info` reads it back:

- `pipeline`: its `name`, its `region` and its `version`;
- `sources`: the record of each source, with `name`, `url`, `credit`, `license`,
  `license_url`, `sha256` and `bytes` (or what the own `download` of the source
  returns), and `version` if the data has one;
- `software`: the version of `scgraph`, its `backend` (`cpp` or `python`) and the
  `platform`, with its C library or its macOS version;
- `description`: the docstring of the pipeline. `python -OO` drops docstrings, so it
  gives another file.

The header holds no clock time. The time of the download is in `cache.json`, in the
cache.

`scgraph.pipelines.derived_networks` derives a network file from another network file, with no
download. The derived file holds some modes of its parent file, and its land networks
inside a bbox. Its header has no `description`. It also records `derivation`: the
`parent_content_sha256`, and the `node_modes`, the `bbox` and the `min_component_nodes` of
the derivation.

Two builds give the same file, byte for byte, when they have the same pipeline, the
same sources, the same version of scgraph, the same backend, and the same platform
with the same C library or macOS version. A test checks this. The C++ build and the
pure-Python build give the same nodes, the same edges and the same lengths. Two
things may differ: the order of the edges of a node, and the choice between two
routes of the same length. A test checks this with `eurostat_sea_lanes` and
`geofabrik_multimodal`, on small inputs. Between two platforms, a few lengths or
shape points may differ in the last bit, because the math libraries differ.

A PIPELINE OF YOUR OWN

This pipeline builds the cycleways of an OpenStreetMap extract, both ways:

```py
from scgraph import GeoGraph
from scgraph.pipelines.steps import step1_osm_ways

PIPELINE_VERSION = 1
SOURCES = {"ways": step1_osm_ways.GEOFABRIK}
download = step1_osm_ways.download  # checks osmium before downloading the extract

def select(tags):
    return 0 if tags.get("highway") == "cycleway" else None

def build(files):
    return GeoGraph.load_from_osm(files["ways"], select=select)
```

Save it as `cycleways.py`. Then `import cycleways` and
`GeoGraph.build_geograph(cycleways, region="europe/luxembourg")` build the network.
The cache keeps it under the last part of the name of the module, in
`networks/cycleways/europe/luxembourg/`. To adapt a pipeline of scgraph, copy its
module under another name: scgraph refuses a module that has the name of one of its
pipelines. Two modules with the same last name share one cache entry.

HOW TO ADD A NETWORK TO SCGRAPH

1. Add the module to this package, with the names above.
2. Add its name to `NAMES` below and to the `Literal` of `GeoGraph.build_geograph`,
   in alphabetical order. A test checks that the two lists are the same.
3. Add its row to the table of *Building Networks from Their Sources*, in `README.md`
   and in the docstring of `scgraph/__init__.py`.
4. Add its cases to `steps/step4_validation_cases/cases/` and list them in `VALIDATION`.
5. Build and validate the network with the command above.

scgraph does not import this package when it is imported. The functions that need it
import it when they are called: `load_from_osm`, `build_geograph`,
`list_buildable_geographs`, `clear_geograph_cache`, and `load_geograph` for a network
of a network release.
"""

import importlib.metadata
import inspect
import logging
import os
import platform
import sysconfig

import requests

from scgraph.utils import has_cpp

logger = logging.getLogger(__name__)

__all__ = ["CLASSES", "NAMES", "download_file"]

NAMES = (
    "eurostat_sea_lanes",
    "geofabrik_multimodal",
    "osm_world_multimodal",
)
# The mode of the edges of each class, by the name of the class (the docstring of this
# module, *The classes*)
CLASSES = {
    # Roads: the `highway` value of the way, or the `route` value of a vehicle ferry
    "motorway": "road",
    "motorway_link": "road",
    "trunk": "road",
    "trunk_link": "road",
    "primary": "road",
    "primary_link": "road",
    "ferry": "road",
    "shuttle_train": "road",
    "road_connector": "road",
    # A high-speed line is `rail_highspeed`. Another line takes its class from its
    # `usage` value.
    "rail_highspeed": "rail",
    "rail_main": "rail",
    "rail_branch": "rail",
    "rail_other": "rail",
    "rail_connector": "rail",
    # Sea lanes: `open_sea` outside a passage, then the passages of the source
    "open_sea": "sea",
    "babelmandeb": "sea",
    "bering": "sea",
    "corinth": "sea",
    "dover": "sea",
    "gibraltar": "sea",
    "kiel": "sea",
    "magellan": "sea",
    "malacca": "sea",
    "panama": "sea",
    "suez": "sea",
    "sea_connector": "sea",
    "flight": "air",
}
# The id of each class: the value that `edge_class_ids` holds for an edge of the class
CLASS_IDS = {name: class_id for class_id, name in enumerate(CLASSES)}
# In bytes. A larger download is logged at WARNING, which shows without a logging
# setup.
LARGE_DOWNLOAD_BYTES = 100e6


def build_metadata(
    name: str,
    region: str | None,
    version: int,
    sources: list[dict],
    description: str | None = None,
) -> dict:
    """Return the metadata of a build, which the runner writes into the header of the
    network file. The docstring of this module lists its fields.

    Args:
        name: The name of the pipeline.
        region: The region of the build, or None for a pipeline without regions.
        version: The `PIPELINE_VERSION` of the pipeline.
        sources: The record of each downloaded source.
        description: The docstring of the pipeline.

    Returns:
        A dict with `pipeline`, `sources` and `software`, and with `description` when
        one is given.
    """
    try:
        scgraph_version = importlib.metadata.version("scgraph")
    except (
        importlib.metadata.PackageNotFoundError
    ):  # run from a source tree that is not installed
        scgraph_version = "unknown"
    libc = " ".join(platform.libc_ver()).strip()
    macos = platform.mac_ver()[0]
    system = f"macOS {macos}" if macos else libc
    return {
        "pipeline": {"name": name, "region": region, "version": version},
        "sources": sources,
        "software": {
            "scgraph": scgraph_version,
            "backend": "cpp" if has_cpp() else "python",
            "platform": f"{sysconfig.get_platform()} {system}".strip(),
        },
        **(
            {"description": inspect.cleandoc(description)}
            if description
            else {}
        ),
    }


def download_file(url: str, filename: str | os.PathLike) -> None:
    """Download `url` to `filename`. The function first logs the size of the file: at
    WARNING above `LARGE_DOWNLOAD_BYTES`, at INFO below. When the server gives the size, it
    then logs at INFO the megabytes done at each tenth of the download.

    Raises:
        requests.HTTPError: The server refuses the request.
    """
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        size = int(response.headers.get("Content-Length", 0))
        logger.log(
            logging.WARNING if size > LARGE_DOWNLOAD_BYTES else logging.INFO,
            "Downloading %s (%.1f MB)",
            url,
            size / 1e6,
        )
        next_tenth = 1
        with open(filename, "wb") as file:
            for chunk in response.iter_content(chunk_size=1 << 20):
                file.write(chunk)
                # The raw stream counts the bytes received, as Content-Length does,
                # also when requests decompresses them.
                done = response.raw.tell()
                if size and done >= next_tenth * size / 10:
                    logger.info(
                        "Downloaded %.1f of %.1f MB", done / 1e6, size / 1e6
                    )
                    next_tenth = done * 10 // size + 1
