# How a pipeline builds a network

This guide follows one build from its sources to its network file. It explains what each step
receives, what it does and what it gives, with the numbers of a real build.

The build is the pipeline `osm_multimodal` for the region `europe/denmark`. It ran on
2026-11-20 on Linux, with the C++ extension, from the extract of 2026-11-18. The numbers come
from its log. Another day gives other numbers, because the OpenStreetMap extract changes every
day.

The guide gives no rule of its own. Each rule is in the docstring of the function that applies
it, and the guide names that function.

## The words

- A **network** is a graph with a position for each node. scgraph stores it in one file,
  `<name>.scgraph`.
- A **pipeline** is a Python module that builds one network. The docstring of
  `scgraph.pipelines` states what a pipeline holds.
- A **source** is a file on a server that a pipeline reads, such as an OpenStreetMap extract.
- The **runner** is the module `build.py`. It downloads the sources, calls the pipeline and
  keeps the network file in the cache.
- A **way** is a line of OpenStreetMap: a part of a road, of a railway or of a ferry route.
- A **piece** is the part of a way between two nodes of the network.
- A **mode** says what a node is: a node of one transport network (`road`, `rail`, `sea`), or
  a hub.
- A **hub** is a place where a route changes mode: a port, an airport or a rail terminal. A hub
  is one node.
- A **connector** is the pair of arcs that joins a hub to the network of one mode.
- The **class** of an arc is defined in the docstring of `scgraph.pipelines`, part *The
  classes*. Examples: `motorway`, `ferry`, `rail_main`.
- A **chain** is a row of nodes that each have only two neighbors, as along a road with no
  junction.

## The command

```
python -m scgraph.pipelines.build osm_multimodal --region europe/denmark --validate
```

The command prints the path of the network file. To see each step with its counts, set the
logging level to DEBUG before the call (README, section *Logging*).

## The build, step by step

### 1. The runner downloads the sources

`SOURCES` of the pipeline names nine sources. The runner brings each one into its work folder.
It downloads five of them. The four others are small tables kept with scgraph, which it copies.

| Source | What it is | Size |
|---|---|---|
| `sea` | the sea lanes of Eurostat SeaRoute | 7.0 MB |
| `land`, `lakes`, `rivers` | Natural Earth, to tell land from water | 3.6, 1.6 and 2.3 MB |
| `ports`, `airports`, `flights`, `rail_terminals` | the tables of the hubs and of the flights | under 1 MB each |
| `osm` | the Geofabrik extract of Denmark | 498.2 MB |

The extract comes last. When a small source fails, the large download has not started.

Where to read more: `build.py`, function `build_file`.

### 2. Read and cut the ways

`osm.build_way_pieces` reads the extract and keeps the ways that the pipeline selects. It cuts
each way at its junctions. It also cuts a way where a piece would be longer than
`max_km_between_nodes` (2 km), so that a point near a long road is near a node. It simplifies
the shape of each piece to within 50 m.

The pipeline reads the extract once, for its two modes. The log line of this step gives the
sum of the two counts: 26,457 pieces.

| Mode | Ways kept | Pieces |
|---|---|---|
| `rail` | railway lines | 5,680 |
| `road` | main roads | 20,777 |

Each select function of this pipeline also gives the class of the way, and each piece has
the class of its way.

Each mode has its own junctions and its own pieces, so the two networks stay apart. A road and
a railway share a node of OpenStreetMap at a level crossing, and no route changes mode there.

Then `osm.build_ferry_arcs` attaches the vehicle ferries to the roads: 12 arcs in this build.
A ferry is kept when both its ends are near a road node. The file has 10 arcs of the class
`ferry`: two ferry routes join the same two road nodes, and the graph keeps the shorter of
two arcs between the same two nodes.

Where to read more: the header of `steps/stage1_extract/osm.py`.

### 3. Read the sea lanes

The sea lanes are 72,444 lines. The pipeline turns them into a graph of 42,250 nodes. These are
the sea lanes of the whole world, not only those around Denmark: a route by sea may leave the
region and come back.

### 4. Tell land from water

`LandMask.from_natural_earth` draws a raster of the land around the roads of the region. Each
cell is land or water. The next step uses it for two checks: a connector to a road or to a
railway crosses little water, and a connector to a sea lane stays on water.

Where to read more: the header of `steps/stage2_intermodal/landmask.py`.

### 5. Join the networks at the hubs

At this point the build holds three graphs with no arc between them: roads, railways and sea
lanes. `hubs.join` adds the hubs and their connectors.

The tables give 242 hubs inside the raster. A hub is joined when it finds the networks that it
needs within its limits: 20 km to a road, 10 km to a railway, and a water path of 2,500 km to a
sea lane. This build joins 63 ports, 10 airports and 1 rail terminal.

For example, the port of Arhus gets three connectors: 0.91 km to a rail node, 4.89 km to a road
node and 0.99 km over water to a sea node.

The step also joins each pair of airports that has regular flights, by one arc each way. Its
length is the great-circle distance.

The result is one graph of 66,146 nodes and 195,274 arcs.

Where to read more: the header of `steps/stage2_intermodal/hubs.py`.

### 6. Assemble the graph

`assembly.assemble` does three things.

| Step | Nodes | Arcs |
|---|---|---|
| the joined graph | 66,146 | 195,274 |
| keep the largest strongly connected component | 63,784 | 192,735 |
| contract the chains | 50,320 | 171,999 |

- **Keep the connected part.** In a strongly connected component, a route exists from every
  node to every other node. The step removes the rest, for example a road on a small island
  with no ferry.
- **Contract the chains.** A chain becomes one arc with the length and the shape of the chain.
  The route lengths do not change. A chain is never contracted across two modes, and a chain
  longer than `max_km_between_nodes` keeps nodes along it. In this build, the rule of the
  classes keeps 151 nodes more than a contraction without it.
- **Order the nodes.** The nodes are sorted by mode, then along a Hilbert curve. Nodes that are
  near on the map are then near in the file, so a search reads nearby memory.

Where to read more: the header of `steps/stage3_assembly/assembly.py`.

### 7. The runner writes the network file

The runner writes the arrays to one file of 4.2 MB. The header of the file records the
pipeline, each source with its version and its license, the software of the build, and the
names of the classes.
`GeoGraph.get_scgraph_info(file)` reads this back.

Where to read more: the docstring of `scgraph.pipelines`, part *What the network file
records*, and `ARCHITECTURE.md`, section 7.

### 8. Validate the network

With `--validate`, `validate_network` checks the file against the cases of the pipeline. A case
describes one known fact of the real world. This build has three cases, and all three pass. One
of them says that the port of Arhus has a connector to a road, to a railway and to a sea lane.

A network that fails a case does not enter the cache.

Where to read more: the docstring of `steps/stage4_validation`.

## What comes out

The file holds 50,320 nodes and 171,999 arcs.

| Mode | Nodes |
|---|---|
| `sea` | 42,157 |
| `road` | 6,162 |
| `rail` | 1,927 |
| `port` | 63 |
| `airport` | 10 |
| `rail_terminal` | 1 |

A route may use every mode. From the center of Aarhus to the center of Copenhagen, the shortest
route in this file is 188.1 km. It takes a railway, a sea lane, a road, then a railway again,
and it changes mode at three ports.

```py
from scgraph import GeoGraph

denmark = GeoGraph.build_geograph("osm_multimodal", region="europe/denmark")
route = denmark.get_shortest_path(
    {"latitude": 56.1629, "longitude": 10.2039},
    {"latitude": 55.6761, "longitude": 12.5683},
)
route["length"]  # 188.1
```

To keep some modes only, load the file with `modes`. With the roads alone, the same route is
302.2 km:

```py
from scgraph.pipelines.build import build_file

file = build_file("osm_multimodal", region="europe/denmark")  # the file of the cache
roads = GeoGraph.load_from_scgraph(file, modes=["road"])
```

Each arc has a class. A two-way road gives two arcs, and the table counts the km of both.

| Classes | Arcs | km |
|---|---|---|
| `motorway`, `motorway_link` | 2,198 | 2,845 |
| `trunk`, `trunk_link` | 1,040 | 787 |
| `primary`, `primary_link` | 6,799 | 5,061 |
| `ferry` | 10 | 153 |
| `rail_highspeed`, `rail_main`, `rail_branch`, `rail_other` | 4,540 | 6,770 |
| `open_sea` and the ten passages | 157,022 | 6,540,886 |
| `flight` | 28 | 5,050 |
| `road_connector`, `rail_connector`, `sea_connector` | 362 | 1,238 |

## A network derived from a network file

`derive_file` of `derive.py` writes a derived file from a network file, the parent file, with
no download. The derived file holds some modes of the parent file, and its land networks
inside a bbox. A bbox is `(south, west, north, east)`, in degrees. A view is a named choice of
modes and of bbox. `VIEWS` of the same module lists the views of `world_multimodal`, for
example `world_sea` and `oceania`.

```
python -m scgraph.pipelines.derive world_multimodal.scgraph oceania derived --validate
```

The command writes `derived/oceania.scgraph` and prints its path. With `--no-shapes`, it
writes `derived/oceania.no_shapes.scgraph`: the same network without the shapes of its arcs.

The numbers below come from one derivation of `oceania` on 2026-11-19, on Linux, with the C++
extension. The parent file is the `world_multimodal` of the data release
`networks-2026.11.19-dev.1` (325.6 MB).

| Step | Nodes | Arcs |
|---|---|---|
| the parent file | 3,281,281 | 6,174,775 |
| select the nodes and cut the graph | 124,937 | 337,401 |
| keep the components of at least 10 nodes | 124,889 | 337,365 |

- **Select the nodes.** The bbox of `oceania` cuts the roads, the railways and the rail
  terminals. The sea lanes, the ports and the airports of the world stay: a route may leave
  the bbox by sea or by air.
- **Keep the connected components.** The cut leaves 48 nodes apart from the rest, in groups
  of fewer than 10 nodes. The step removes them. A junction that lost a road stays as a node.

The derived file is 19.3 MB. Its header records the `content_sha256` of the parent file, the
modes and the bbox. With `--validate`, the command selects the cases of `world_multimodal`
whose two ends are inside the bbox: 16 cases here. The derived file passes when it fails no
case that the parent file passes. Here it fails none.

Where to read more: the header of `derive.py`.

## A network of your own

Copy the pipeline that is nearest to your need, and change its sources, its select functions or
its constants. The docstring of `scgraph.pipelines` gives a short pipeline to start from, and
the steps to add a network to scgraph.
