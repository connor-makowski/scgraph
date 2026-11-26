# Networks: Load, Build and Save

This guide shows three ways to get a network: load one that scgraph publishes, build one from open data, or load your own data. It also shows how to save a network and load it again.

- A **released network** is a network that the maintainers of scgraph build and publish, such as `europe`.
- A **geograph** is a `GeoGraph` object: a network in memory.
- A **region** is a part of the world, such as a country, that has its own OpenStreetMap file.

| You have | Call | Section |
|---|---|---|
| The name of a released network | `GeoGraph.load_geograph(name)` | [Released Networks](#released-networks) |
| A region, and you need its current data | `GeoGraph.build_geograph(name, region=...)` | [Building Networks from Their Sources](#building-networks-from-their-sources) |
| A released network that is too large | `derive_network_file(parent_file, derived_file, bbox=...)` | [Deriving a Part of a Released Network](#deriving-a-part-of-a-released-network) |
| An OSMnx graph | `GeoGraph.load_from_osmnx_graph(graph)` | [Loading from OSMnx](#loading-from-osmnx) |
| An OpenStreetMap file | `GeoGraph.load_from_osm(file)` | [Loading an OpenStreetMap File](#loading-an-openstreetmap-file) |
| Lines in a GeoJSON file, or a file that scgraph saved | `load_from_geojson`, `load_from_scgraph`, `load_from_graphjson` | [Saving and Loading Files](#saving-and-loading-files) |

The [API documentation](https://connor-makowski.github.io/scgraph/scgraph.html) gives every parameter of these calls.

## Released Networks

The maintainers of scgraph build networks of the whole world from OpenStreetMap and other open sources. A **network release** is a set of these networks, published together on GitHub under one tag, for example `networks-2026.11.20`. `load_geograph` loads a released network by its name.

| Name | What it holds |
|---|---|
| `world_multimodal` | The main roads, the railways, the sea lanes and the regular flights of the world. Ports, airports and rail terminals join them |
| `world_sea` | The sea lanes and the ports of the world |
| `world_rail` | The railways and the rail terminals of the world |
| `europe` | Latitudes 34 to 72, longitudes -25 to 45 |
| `north_america` | Latitudes 7 to 84, longitudes -170 to -50 |
| `south_america` | Latitudes -57 to 13, longitudes -82 to -34 |
| `africa` | Latitudes -35 to 38, longitudes -18 to 52 |
| `west_south_asia` | Latitudes 5 to 45, longitudes 25 to 98 |
| `east_southeast_asia` | Latitudes -11 to 55, longitudes 92 to 150 |
| `north_asia` | Latitudes 40 to 78, longitudes 45 to 180 |
| `oceania` | Latitudes -50 to 0, longitudes 110 to 180 |

Each of the eight networks from `europe` to `oceania` is a part of `world_multimodal`. It holds the roads, the railways and the rail terminals inside the latitudes and longitudes of its row. It also holds every sea lane, port and airport of the world, so a route can leave this area by sea or by air.

Distances are in kilometers. `GeoGraph.list_geographs()` lists every network that `load_geograph` takes. For a released network, it gives the numbers of nodes and of edges, the sizes of the downloads and the date of the newest source data. The [releases page](https://github.com/connor-makowski/scgraph/releases) of the repository shows the files of each network release.

```py
from scgraph import GeoGraph

europe = GeoGraph.load_geograph("europe")

paris = {"latitude": 48.8566, "longitude": 2.3522}
berlin = {"latitude": 52.52, "longitude": 13.405}
route = europe.get_shortest_path(origin_node=paris, destination_node=berlin)
route["length"]  # the km of the shortest route

roads = GeoGraph.load_geograph("europe", node_modes=["road"])
roads.get_shortest_path(origin_node=paris, destination_node=berlin)["length"]  # the km by road
```

The **node mode** of a node is the kind of place where the node is: `road`, `rail`, `sea`, `port`, `airport` or `rail_terminal`.

- A **hub** is a port, an airport or a rail terminal. A route goes from a road to a sea lane only at a port.
- A **metric** gives each edge a weight, such as its hours. Without a metric, the shortest route between distant places often takes a flight.
- By default, the origin and the destination snap to their closest road node.
- The **shape** of an edge is the list of points that draw the edge on a map. Without the shapes, the `coordinate_path` of a route is straight from node to node.

| You want | Write |
|---|---|
| The roads only | `node_modes=["road"]` |
| The roads and the sea lanes, with the ports that join them | `node_modes=["road", "sea", "port"]` |
| The fastest or the cheapest route | A metric: see [Routes by Time, Cost and CO2](https://github.com/connor-makowski/scgraph/blob/main/guides/time_cost_co2.md) |
| A route that starts or ends off the roads | `snap_to_node_modes`: see [Where a Query Point Snaps](https://github.com/connor-makowski/scgraph/blob/main/guides/routing.md#where-a-query-point-snaps) |
| A smaller download, with the same lengths | `load_intermediate_nodes=False` |

| Case | What `load_geograph` does |
|---|---|
| First load | Downloads the file, decompresses it and checks its content |
| Later load | Reads the file from the cache, without a network request |
| The download is damaged | Raises `ValueError` and keeps no file |
| The server refuses the download | Raises `ConnectionError` |
| The network release does not have the network | Raises `FileNotFoundError` |
| `local_files_only=True`, and the cache does not have the file | Raises `FileNotFoundError` |

After an error, the cache is as it was before the call. You can make the call again.

### Loading the Same Network Again

Each version of scgraph loads one network release, so the same version loads the same network on every machine. A later version of scgraph may load a newer network release. To load exactly the same network then, record the tag of the network release and the `content_sha256` of the file. The `content_sha256` is the SHA-256 digest of the content of a network file.

```py
from scgraph import network_release

tag = network_release.TAG  # the tag of the network release that this scgraph loads
info = GeoGraph.get_scgraph_info(europe.scgraph_file)
digest = info["content_sha256"]
info["attribution"]  # the credit line to cite with your results
info["data_up_to"]   # the time of the newest source data

# Later, on any machine, with the two recorded values: this call loads the same file, or raises a ValueError
europe = GeoGraph.load_geograph("europe", network_release=tag, content_sha256=digest)
```

**Licenses of the data.** The code of scgraph is under the MIT license. The data of a released network keeps the licenses of its sources. The roads and the railways come from OpenStreetMap (ODbL 1.0), and the sea lanes from Eurostat SeaRoute (EUPL 1.2). The flights table is under CC BY 4.0.

A result that uses a released network cites the credit line of the file, `info["attribution"]` above. The header of the file lists each source with its license (`info["sources"]`).

A **pipeline** is a Python module that builds one network from its sources. The guide [Network Pipelines](https://github.com/connor-makowski/scgraph/blob/main/scgraph/pipelines/README.md) explains how these networks are built, checked and published.

## The Cache

`load_geograph` and `build_geograph` keep their files in a local cache.

```py
# Never download: use only the cache (FileNotFoundError if the network is not there)
world_sea = GeoGraph.load_geograph("world_sea", local_files_only=True)

# Every network that load_geograph takes, and whether the cache holds it (no network request)
GeoGraph.list_geographs()
# [..., {"name": "europe", "cached": True, "kind": "released", "description": "...", "nodes": ..., ...},
#  {"name": "marnet", "cached": False, "kind": "built-in", "description": "...", "superseded_by": "world_sea"}, ...]

# What the cache holds: one dict per file, with its kind, name, region, file and bytes
GeoGraph.list_geograph_cache()
```

- **The place.** The cache is in the cache directory of the platform, for example `~/.cache/scgraph/` on Linux.
  - `cache_dir="/path/to/cache"` gives another directory to one call.
  - The environment variable `SCGRAPH_CACHE_DIR` gives another directory to every call. A call with `cache_dir` uses the directory of its argument.
- **Offline.** `SCGRAPH_OFFLINE=1` makes `local_files_only=True` the default of `load_geograph` and `build_geograph`. A call with `local_files_only` uses the value of its argument.
- **Clearing.** The cache keeps the files of each network release until `GeoGraph.clear_geograph_cache()` removes them. This call keeps the other files of the directory. With `name`, and with `region` for a built network, it removes one network only.
- **Windows.** The files of a network that is still loaded in the process cannot be deleted. `clear_geograph_cache` does not delete them, and a logging warning names them. A later clear removes them.

## Building Networks from Their Sources

`build_geograph` builds a network on your machine from its online sources, with current data.

A source can be large, such as the OpenStreetMap file of a country: its **extract**. A warning is logged before a large download.

```py
import logging

logging.basicConfig(level=logging.INFO)  # optional: show the downloads and the credit to cite

# Roads and railways of Denmark, joined to the sea lanes of the world and to flights
# (needs: pip install scgraph[osm])
denmark = GeoGraph.build_geograph("osm_region_multimodal", region="europe/denmark")

# What can be built, who to credit, and what is already in the cache
GeoGraph.list_buildable_geographs()
# [{"name": "eurostat_sea_lanes", "description": "...", "credit": "...", "license": "EUPL-1.2",
#   "needs_region": False, "cached": False, "cached_regions": []}, ...]
```

Each pipeline of scgraph is a module of `scgraph.pipelines`. Its docstring describes the network, its rules and its limits. The **class** of an edge is its category in the source, such as `motorway`, `ferry`, `rail_main`, `suez` or `flight`.

| Pipeline | Network | Source |
|---|---|---|
| `eurostat_sea_lanes` | Sea lanes at 5 km resolution, lanes cut at the antimeridian joined, Arctic passages removed (the older `marnet` has them) | Eurostat SeaRoute, GeoPackage at a fixed commit of its repository |
| `osm_region_multimodal` | Main roads, railways, sea lanes and regular flights of a region, joined at ports, airports and rail terminals; each node has its node mode, and each edge has its class | OpenStreetMap extract from [Geofabrik](https://download.geofabrik.de), Eurostat SeaRoute, Natural Earth; hubs and flights from tables kept with scgraph (NGA World Port Index, OurAirports, flights of 2021 from OpenSky, BTS T-100 and Eurostat, Wikidata) |
| `osm_world_multimodal` | `osm_region_multimodal` for the world (needs the C++ extension). This pipeline builds the released network `world_multimodal` | The sources of `osm_region_multimodal`, with the OpenStreetMap planet in place of the extract. The planet is read by byte ranges and never stored |

**The region.** The region of `osm_region_multimodal` is the path of a [Geofabrik extract](https://download.geofabrik.de) in its download URL: `europe/luxembourg`, `europe/france/bretagne`, `north-america/us/texas`. Geofabrik lists [all its extracts](https://download.geofabrik.de/index-v1-nogeom.json) in a JSON file. A region that Geofabrik does not have raises a `ValueError` before the download of the extract.

**The command line.** `python -m scgraph.pipelines.network_builder NAME [--region R] [--cache-dir D]` builds a network without loading it, and prints the path of its file.

A build keeps its downloaded sources in a **work folder** of the cache. The file `scgraph_work.json` of this folder records the pipeline, its version, the region and the version of scgraph. When a build finds other values, it empties its own folder. It refuses a `work_dir` that you give, unless you pass `refresh=True`. The docstring of `build_network_file` gives the rule.

| Case | What `build_geograph` does |
|---|---|
| First call | Downloads the sources, builds the network, and keeps the file in the cache |
| Later call | Loads the file from the cache, without network access |
| An upgrade of scgraph changed the pipeline or the file format | Builds the network again |
| The file is missing or damaged | Builds the network again |
| `refresh=True` | Empties the work folder, downloads the sources and builds the network again |
| A build fails | Keeps the work folder. The next build uses its sources |
| `local_files_only=True`, and the cache does not have the network | Raises `FileNotFoundError` |
| `local_files_only=True`, and another version of the pipeline built the file | Loads the file, with a warning |
| `local_files_only=True`, and the file has another file format | Raises `ValueError` |

A new build removes the old file. [ARCHITECTURE.md](https://github.com/connor-makowski/scgraph/blob/main/ARCHITECTURE.md#6-caches-and-invalidation) describes the folders of the cache.

Two versions of scgraph can use one cache. If their pipelines differ, each version builds again the networks of the other. Give each version its own `SCGRAPH_CACHE_DIR`, or pass `local_files_only=True` in the older one.

**What a built network holds.**

- Its sources are newer than the sources of a released network. So its nodes and its results differ.
- A multimodal network has node modes and hubs. Each edge has a class, and `geograph.classes` lists the classes.
- `osm_region_multimodal` adds nodes along a long road or railway, so the origin of a query finds a node close to it. `reduce_iterations=-1` removes the nodes that routing does not need.
- The build simplifies the shape of each road, ferry or railway edge. The length of the edge is the length of its full shape.
- `build_geograph` takes `node_modes`, as `load_geograph` does.

**A pipeline of your own.** `build_geograph(pipeline=my_module)` builds the network of your own pipeline module, for example an adapted copy of a pipeline of scgraph. The cache keeps it in `networks/<last part of the module name>/`. A module with the name of a pipeline of scgraph raises a `ValueError`.

The docstring of `scgraph.pipelines` states what a pipeline holds. The guide [Network Pipelines](https://github.com/connor-makowski/scgraph/blob/main/scgraph/pipelines/README.md#part-1-building-a-network) describes each step of one build.

## Deriving a Part of a Released Network

`derive_network_file` writes a smaller network file from a network file, and downloads nothing. It keeps the roads, the railways and the rail terminals inside a bbox: a rectangle `(south, west, north, east)` in degrees. The sea lanes, the ports and the airports of the world all stay. With `node_modes`, it keeps some node modes only.

```py
from scgraph.pipelines.derived_networks import derive_network_file

# The file of a loaded network is in the cache: scgraph_file gives its path. It must have the shapes of its edges
derive_network_file(europe.scgraph_file, "iberia.scgraph", bbox=(36, -10, 44, 4))
iberia = GeoGraph.load_from_scgraph("iberia.scgraph")
```

## Loading from OSMnx

[OSMnx](https://osmnx.readthedocs.io/) downloads the streets of a place from OpenStreetMap: to drive, to cycle or to walk. `load_from_osmnx_graph` makes a `GeoGraph` from its graph:

```py
import osmnx as ox

# The drivable streets of Ann Arbor, MI, with a speed and a travel time for each edge
osmnx_graph = ox.graph_from_place("Ann Arbor, Michigan, USA", network_type="drive")
osmnx_graph = ox.add_edge_travel_times(ox.add_edge_speeds(osmnx_graph))

ann_arbor = GeoGraph.load_from_osmnx_graph(osmnx_graph, off_graph_travel_speed=30)

origin = {"latitude": 42.2808, "longitude": -83.7430}
destination = {"latitude": 42.2622, "longitude": -83.7482}
shortest = ann_arbor.get_shortest_path(origin_node=origin, destination_node=destination)
fastest = ann_arbor.get_shortest_path(origin_node=origin, destination_node=destination, metric="travel_time")
print(fastest["length"], fastest["metric_totals"]["travel_time"])  # its km, then its seconds
```

The `length` of an edge is its distance, in km. When every edge has a `travel_time`, the geograph keeps it as the metric `travel_time`, in seconds. One geograph then gives the shortest route and the fastest route. `off_graph_travel_speed` is the speed in km/h from the origin or the destination to its node.

The geograph also keeps the `highway` value of each edge as its class. The **edge mode** of a class is the kind of transport of its edges: here `road`.

**The default metric.** The **default metric** of a geograph is the metric of a query that names no metric. `geograph.default_metric` gives its name. `weight_key` sets it for an OSMnx geograph: `'length'`, the default, or `'travel_time'`.

```py
# With weight_key="travel_time", a query that names no metric finds the fastest route
by_time = GeoGraph.load_from_osmnx_graph(osmnx_graph, weight_key="travel_time", off_graph_travel_speed=30)
by_time.default_metric  # 'travel_time'
fastest = by_time.get_shortest_path(origin_node=origin, destination_node=destination)
print(fastest["length"], fastest["metric_totals"]["travel_time"])  # still its km, then its seconds
shortest = by_time.get_shortest_path(origin_node=origin, destination_node=destination, metric="length")
```

OSMnx can give several edges from one node to another. The geograph keeps the one with the smallest value of `weight_key`, with its length, its class and its travel time. With `weight_key='length'`, the metric `travel_time` holds the travel time of the shortest edge, and another of these edges may be faster.

The [OSMnx notebook](https://colab.research.google.com/github/connor-makowski/scgraph/blob/main/examples/osmnx.ipynb) compares the fastest and the shortest route on a bike network.

## Loading an OpenStreetMap File

`load_from_osm` builds a geograph from an OpenStreetMap file, for example an extract. It needs an optional dependency: `pip install scgraph[osm]`. An OpenStreetMap **way** is a line of a road, of a railway or of another feature.

```py
# Main roads (motorway to primary, with their links); one-way streets are respected
michigan_roads = GeoGraph.load_from_osm("michigan-latest.osm.pbf")
# Minutes: 80 km/h on a road, and 110 km/h on a road of the class motorway
michigan_roads.create_metric("minutes", weight_per_km={"road": 60 / 80, "off_graph": 60 / 30}, class_weight_per_km={"motorway": 60 / 110})

# Other ways: select(tags) gives the direction of a way (1 or -1: one way, 0: both
# directions) or None to exclude it; only ways with one of the tag keys reach select.
# Here railway lines without yards, sidings and spurs, in both directions. The crossovers
# stay: they join the two tracks of a double line drawn track by track
michigan_rail = GeoGraph.load_from_osm(
    "michigan-latest.osm.pbf",
    select=lambda tags: (
        0
        if tags.get("railway") == "rail"
        and tags.get("service") in (None, "crossover")
        else None
    ),
    tag_keys=("railway",),
)
```

Each edge has the class that `select` gives to its way. The default `select` gives the `highway` value of the way. A `select` that returns directions alone, as the railway example above, gives a geograph without classes.

A **weight per km** is the weight of 1 km of an edge in a metric. A metric can give a weight per km to each class of road, as `minutes` above.

Ways meet only where they share an OSM node, so roads that cross on a bridge or in a tunnel are not connected. Each edge has the length of its piece of way, in kilometers. `max_km_between_nodes` cuts a long way into several edges, so that the nodes are closer together.

### Turn Restrictions

A **turn restriction** of OpenStreetMap forbids a turn at a junction, such as `no_left_turn`. It can also give the only turn that is allowed, such as `only_straight_on`. `load_from_osm` reads the turn restrictions of the file, and a route makes none of the forbidden turns:

```py
# Every street of a city, with nodes about 200 m apart
from scgraph.helpers.osm import get_way_direction

STREETS = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
           "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"}
paris = GeoGraph.load_from_osm(
    "ile-de-france-latest.osm.pbf",
    select=lambda tags: get_way_direction(tags) if tags.get("highway") in STREETS else None,
    max_km_between_nodes=0.2,
)
# The same streets, where a route may make any turn
paris_any_turn = GeoGraph.load_from_osm(..., load_turn_restrictions=False)
```

**What changes in the geograph.** A junction with a turn restriction has more than one node. These nodes have the same point and the same external id, and they follow each other. Every search then runs without a change. On the streets of Paris, Berlin and Greater London, the turn restrictions add 1 to 3 % of nodes.

- The `path` of a result may hold any node of a junction. `geograph.external_node_ids[node_id]` gives the OpenStreetMap id of the junction for each of them.
- A query point that snaps to a junction is connected to each node of the junction. So a route can end there from any street, and a route that starts there can take any street.
- The row of `node_modes` has `"has_turn_restrictions": True` for a node mode that follows turn restrictions. `save_as_scgraph` and `save_as_graphjson` keep the turn restrictions. `save_as_geojson` writes the lines of the edges only, so a geograph loaded from a GeoJSON file follows none.
- The turn restrictions are those of cars. The restrictions that hold for some hours only, or for another kind of vehicle, are not read. The docstring of `scgraph/helpers/osm.py` gives the rules.
- The pipelines `osm_region_multimodal` and `osm_world_multimodal` follow the turn restrictions too, between the roads that they keep.
- `add_coord_edge` joins two nodes, and not the other nodes of their junctions.
- A route may turn back at any node, unless a restriction forbids it there: `no_u_turn`, or an `only_` restriction.

The module [`scgraph/turn_restrictions.py`](https://github.com/connor-makowski/scgraph/blob/main/scgraph/turn_restrictions.py) explains the method, with diagrams.

### The Pipeline of scgraph 3.6.0 for OpenStreetMap

The paper of scgraph, in its Appendix B.1, refers to an earlier pipeline for its OpenStreetMap networks. This pipeline is not a module of scgraph: it uses osmium-tool, a GeoJSON export, Mapshaper and `load_from_geojson`. It still works:

```bash
# 1. Get an OSM PBF file: a regional extract from https://download.geofabrik.de/, or the full planet (needs the AWS CLI)
aws s3 cp s3://osm-pds/planet-latest.osm.pbf .

# 2. Install Osmium: `brew install osmium-tool` on macOS, `sudo apt-get install osmium-tool` on Ubuntu

# 3. Extract your region with its polygon file, keep the main roads, and export them as GeoJSON
curl https://download.geofabrik.de/north-america/us/michigan.poly > michigan.poly
osmium extract -p michigan.poly --overwrite -o michigan.osm.pbf planet-latest.osm.pbf
osmium tags-filter michigan.osm.pbf w/highway=motorway,trunk,primary,motorway_link,trunk_link,primary_link,secondary,secondary_link,tertiary,tertiary_link -t --overwrite -o michigan_roads.osm.pbf
osmium export michigan_roads.osm.pbf -f geojson --overwrite -o michigan_roads.geojson

# 4. Simplify the GeoJSON: first with scgraph, which makes Mapshaper faster, then with Mapshaper.
#    Mapshaper repairs the line intersections, which correct routing needs
npm install -g mapshaper
python -c "from scgraph.helpers.geojson import simplify_geojson; simplify_geojson('michigan_roads.geojson', 'michigan_roads_simple.geojson', precision=4, pct_to_keep=100, min_points=3)"
mapshaper michigan_roads_simple.geojson -simplify 10% -filter-fields -o force michigan_roads_simple.geojson
mapshaper michigan_roads_simple.geojson -snap -clean -o force michigan_roads_simple.geojson
```

```py
# 5. Load the GeoJSON as a GeoGraph
michigan_roads_geograph = GeoGraph.load_from_geojson("michigan_roads_simple.geojson")
```

## Saving and Loading Files

Save a geograph to a file to load it faster later, without its sources:

```py
world_sea.save_as_scgraph("my_network.scgraph")      # a binary network file: the fastest to load
world_sea.save_as_graphjson("my_network.graphjson")  # JSON, also readable by older versions of scgraph
world_sea.save_as_geojson("my_network.geojson")      # GeoJSON, for other tools: a larger file

my_network = GeoGraph.load_from_scgraph("my_network.scgraph")
my_network = GeoGraph.load_from_graphjson("my_network.graphjson")
GeoGraph.get_scgraph_info("my_network.scgraph")  # what the file holds, without loading the network
```

| Format | Graph, nodes and shapes | Node modes, classes, metrics | Build metadata |
|---|---|---|---|
| `.scgraph` | Yes, with the external ids of the nodes | Yes | Yes |
| `.graphjson` | Yes | No | No |
| GeoJSON | One line for each edge, with its shape and its length | No | No |

**The metadata of a network file.** The header of a `.scgraph` file stores the pipeline, the sources with the date of their data, and the software of the build. `get_scgraph_info` reads the header, with the credit line to cite (`attribution`) and the `content_sha256`.

A geograph loaded from a file keeps this metadata (`geograph.metadata`) and the path of the file (`geograph.scgraph_file`). `save_as_scgraph` writes this metadata again, unless you give other `metadata`. [ARCHITECTURE.md](https://github.com/connor-makowski/scgraph/blob/main/ARCHITECTURE.md#7-network-file-format) describes the format.

**Where a file may be saved.** `save_as_scgraph` and `save_as_graphjson` raise a `ValueError` for a file under `networks/` of the cache directory. Save an edited network in another folder.

**Coordinates.** A file stores its coordinates as float64, or as int32 in 1e-7 degree (about 1 cm). The `coordinate_dtype` parameter of `save_as_scgraph` chooses the form: `"float64"`, `"int32"` or `"auto"`, the default. With `"auto"`, a geograph keeps its own `coordinate_dtype`:

- `"int32"` for a network read from an int32 file;
- `"int32"` for a network loaded from OSM, OSMnx or GeoJSON, with coordinates rounded to 7 decimals or fewer;
- `"float64"` otherwise.

**Mapped files.** In the C++ build, `load_from_scgraph` maps the file and reads it in place as long as the geograph exists. On Windows, such a file can then be neither replaced nor deleted: `save_as_scgraph` onto it raises `PermissionError`.

**Nodes and edge shapes read from the file.** A geograph read from a network file reads its node coordinates and its edge shapes from the file. This holds for `load_geograph` and `build_geograph` too.

- `nodes` is read as a list: `nodes[i]`, `len(nodes)` and a loop over `nodes` work. `nodes[i]` is a new list at each read. To change a node, assign it: `nodes[i] = [latitude, longitude]`.
  - Six operations need a list: `json.dumps`, `+`, `*`, `copy()`, `sort()` and an ordering comparison. Write `list(nodes)` before each of them.
- `intermediate_nodes[i]` is a new read-only mapping `{destination: shape}` each time. Editing a shape changes nothing, and assigning raises a `TypeError`.
  - `copy.copy` and pickling give a list of dicts. `json.dumps` needs `[dict(row) for row in intermediate_nodes]`.
