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
`steps.step1_osm_sources` and of `steps.step4_validation_cases`. The other functions of
`steps` are internal. A copy of a pipeline of scgraph that calls them follows one
version of scgraph.

WHAT A PIPELINE MODULE HOLDS

- Its docstring. The first paragraph describes the network, and
  `GeoGraph.list_buildable_geographs` shows it. The network file stores the whole
  docstring.
- `SOURCES`: a dict that gives a name to each source. A source is a dict:
    - `url`: where the source is. The runner replaces `{region}` in it by the `region`
      argument of `build_geograph`. A pipeline needs a region when one of its URLs
      holds `{region}`, and takes none otherwise: the runner refuses another call.
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
    - `(arrays, node_modes)`. `arrays` holds the arrays of the network file, as
      `network_file.write` takes them. The nodes are already in the order of the
      file: by node mode, then along a Hilbert curve (`scgraph.network_assembly.assemble_network`
      gives this order). `metric_length` holds km. `arrays` also holds `node_mode_ids`, the
      node mode id of each node, when the network has several node modes; the runner
      writes the count of the nodes of each node mode in its place. `node_modes` lists
      the node modes (see below). `osm_region_multimodal` and `osm_world_multimodal`
      do this. `arrays` may hold `edge_class_ids`, the class of each edge (see *The classes*). The runner then
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
- `CLASSES`, optional: the classes of the pipeline, in place of the classes of this
  package (see *The classes*).

The runner reads no other name. Names such as `MODES`, `MARGIN_DEGREES` or
`MAX_KM_BETWEEN_NODES` are choices of one pipeline.

THE DOWNLOAD FUNCTIONS

A download function is `download(url, filename)`. It writes to `filename` what `build`
reads. This is the source itself, or a small file that says how to read the source in
place (`step1_osm_sources.download_streamed` does this for the planet, which is never stored).

The function may return a dict. The runner adds it to the record of the source: the
entry of the source in the header of the network file. For example, `step1_osm_sources.download`
returns the `version` of an OpenStreetMap extract, the time that its data is up to.

The runner also puts the `sha256` and the `bytes` of the downloaded file in the
record. There is one exception. A source can have its own `download` in `SOURCES`.
When that function returns a dict, the dict must identify the source, and the runner
does not compute `sha256` and `bytes`. `step1_osm_sources.download_streamed` gives the `bytes` and
the `md5` that the server publishes.

THE NODE MODES

The node mode of a node is the kind of place where the node is: on a network (`road`,
`rail`, `sea`) or at a hub (`port`, `airport`, `rail_terminal`). `node_modes`,
the second value of `build`, lists the node modes: one dict for each node mode, with its
`name` and the `source` that gives the ids of its nodes. A network with one node mode gives `[{"name": None}]`.

THE CLASSES

The class of an edge is its category in the source: a motorway, a vehicle ferry, a
main railway line, a sea passage. `CLASSES` gives the edge mode
of each class. The edge mode of a class is the kind of transport of its edges: `road`,
`rail`, `sea` or `air`:

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
an edge mode.

A pipeline records classes when its select functions give them. A select function
returns the direction of a way: 1, -1 or 0. It may return a pair in its place: the
direction and the name of a class, for example `(1, "motorway")`. A select function
uses the names of `CLASSES` only.

A pipeline that fills `edge_class_ids` itself may define its own `CLASSES` dict in its
module, with the same form. A value of `edge_class_ids` is then the id of a class of
that `CLASSES`, and the runner writes its classes into the header.

A network file holds the class of each edge and one row `{"name", "edge_mode"}` for each
class (`ARCHITECTURE.md`, section 7), and `network_file.read` returns them. A GeoGraph
loaded from the file holds them: `GeoGraph.classes` and `GeoGraph.get_edges`.

HOW TO RUN A PIPELINE

    GeoGraph.build_geograph("osm_region_multimodal", region="europe/denmark")
    python -m scgraph.pipelines.network_builder osm_region_multimodal --region europe/denmark --validate

The first line builds the network, or loads it from the cache. The command builds the
network without loading it, and prints the path of its file. With `--validate`, the
network enters the cache only if it passes its cases.

THE STEPS OF A BUILD

A build runs steps, such as "read and cut the ways" or "contract the chains". Each
step logs one line at DEBUG, with its counts and its duration (`step_logs.log_step`).
The functions of steps 2 and 4 are in `scgraph.pipelines.steps`, with the downloads of
step 1. `GeoGraph.load_from_osm` calls the other functions too, so they are in
`scgraph.helpers.osm` and in `scgraph.network_assembly`:

1. Read the sources. `scgraph.helpers.osm.build_way_pieces` reads the ways of an
   OpenStreetMap file that the select functions keep. It takes the select functions of
   each network, such as the road network. One read of the file serves every network.
   Each network gets its own junctions and its own pieces, so a road never joins a
   railway. The function cuts each way at the junctions of its network, and where a
   piece reaches `max_km_between_nodes`. It simplifies the shape of each piece to within
   50 m. It attaches the ferries to road nodes (`build_ferry_edges`).
2. Join the networks. `step2_hub_connectors.join_networks_at_hubs` joins the road, rail
   and sea networks at hubs: ports, airports and rail terminals.
   `step2_land_mask.LandMask` tells land from water for the connectors of a hub.
3. Assemble the graph. `scgraph.network_assembly.build_graph_from_pieces` stores the
   pieces as a graph. `scgraph.helpers.osm.read_turn_restrictions` reads the turn
   restrictions of the file, and `scgraph.turn_restrictions.list_forbidden_turns` gives them as forbidden turns
   of the road graph. After step 2, `forbid_turns` adds the nodes that make the graph
   follow them (`scgraph/turn_restrictions.py`). A hub is then joined to a junction
   that still has one node, and each added node gets the connectors of its junction.
   `assemble_network` keeps the strongly connected components, contracts the chains
   of nodes and puts the nodes in the order of the file. No chain is contracted
   across two node modes or two classes, or through a junction with several nodes.
4. Validate the network. `step4_validation_cases.validate_network` checks the built
   file against the cases of `VALIDATION`.

From `build_graph_from_pieces` on, a graph is a dict of the
arrays of the network file. `GeoGraph.load_from_osm` runs steps 1 and 3 on one node
mode, without the contraction of the chains, and keeps the arrays in memory. So a
network of `load_from_osm` and a network of a pipeline follow the turn restrictions
by the same code.

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
download. The derived file holds the nodes of some node modes of its parent file, and
its land networks inside a bbox. Its header has no `description`. It also records
`derivation`: the `parent_content_sha256`, and the `node_modes`, the `bbox` and the
`min_component_nodes` of the derivation.

Two builds give the same file, byte for byte, when they have the same pipeline, the
same sources, the same version of scgraph, the same backend, and the same platform
with the same C library or macOS version. A test checks this. The C++ build and the
pure-Python build give the same nodes, the same edges and the same lengths. Two
things may differ: the order of the edges of a node, and the choice between two
routes of the same length. A test checks this with `eurostat_sea_lanes` and
`osm_region_multimodal`, on small inputs. Between two platforms, a few lengths or
shape points may differ in the last bit, because the math libraries differ.

A PIPELINE OF YOUR OWN

This pipeline builds the cycleways of an OpenStreetMap extract, both ways:

```py
from scgraph import GeoGraph
from scgraph.pipelines.steps import step1_osm_sources

PIPELINE_VERSION = 1
SOURCES = {"ways": step1_osm_sources.GEOFABRIK}
download = step1_osm_sources.download  # checks osmium before downloading the extract

def select(tags):
    return 0 if tags.get("highway") == "cycleway" else None

def build(files):
    return GeoGraph.load_from_osm(files["ways"], select=select)
```

Save it as `cycleways.py`. Then `import cycleways` and
`GeoGraph.build_geograph(pipeline=cycleways, region="europe/luxembourg")` build the
network.
The cache keeps it under the last part of the name of the module, in
`networks/cycleways/europe/luxembourg/`. To adapt a pipeline of scgraph, copy its
module under another name: scgraph refuses a module that has the name of one of its
pipelines. Two modules with the same last name share one cache entry.

HOW TO ADD A NETWORK TO SCGRAPH

1. Add the module to this package, with the names above.
2. Add its name to `BUILDABLE_NETWORKS` of `scgraph/networks.py` and to the
   `Literal` of `GeoGraph.build_geograph`, in alphabetical order. A test checks that the
   two lists are the same.
3. Add its row to the table of *Building Networks from Their Sources*, in
   `guides/networks.md`.
4. Add its cases to `steps/step4_validation_cases/cases/` and list them in `VALIDATION`.
5. Build and validate the network with the command above.

scgraph does not import this package when it is imported. The functions that need it
import it when they are called: `build_geograph`,
`list_buildable_geographs`, `clear_geograph_cache`, and `load_geograph` for a network
of a network release.
"""

import importlib.metadata
import inspect
import platform
import sysconfig

from scgraph.edge_classes import CLASS_IDS, CLASSES
from scgraph.files import download_file
from scgraph.networks import BUILDABLE_NETWORKS
from scgraph.utils import has_cpp

__all__ = ["BUILDABLE_NETWORKS", "CLASSES", "download_file"]


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
            # The record names the build that ran: it chooses no kernel.
            "backend": "cpp" if has_cpp() else "python",
            "platform": f"{sysconfig.get_platform()} {system}".strip(),
        },
        **(
            {"description": inspect.cleandoc(description)}
            if description
            else {}
        ),
    }
