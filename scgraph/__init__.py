r"""
# SCGraph
[![PyPI version](https://badge.fury.io/py/scgraph.svg)](https://badge.fury.io/py/scgraph)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI Downloads](https://static.pepy.tech/badge/scgraph)](https://pepy.tech/project/scgraph/)

**A high-performance, lightweight Python library for shortest path routing on geographic and supply chain networks.**

![scgraph](https://raw.githubusercontent.com/connor-makowski/scgraph/main/static/scgraph.png)

SCGraph provides fast, flexible shortest path routing for road, rail, maritime, and custom networks. It ships with prebuilt geographic networks, supports arbitrary graph construction and OSMNx integration, and scales from simple point-to-point queries to massive distance matrices. It also supports graph reduction, lazy loading, optional C++ acceleration, and Contraction Hierarchy preprocessing for large-scale applications.

- **Docs**: https://connor-makowski.github.io/scgraph/scgraph.html
- **Paper**: https://ssrn.com/abstract=5388845
- **Award**: [2025 MIT Prize for Open Data](https://libraries.mit.edu/opendata/open-data-mit-home/mit-prize/)

---

## Citation

If you use SCGraph in your research, please cite:

> Makowski, C., Saragih, A., Guter, W., Russell, T., Heinold, A., & Lekkakos, S. (2025). SCGraph: A Dependency-Free Python Package for Road, Rail, and Maritime Shortest Path Routing Generation and Distance Estimation. *MIT Center for Transportation & Logistics Research Paper Series*, (2025-028). https://ssrn.com/abstract=5388845

```bibtex
@article{makowski2025scgraph,
  title={SCGraph: A Dependency-Free Python Package for Road, Rail, and Maritime Shortest Path Routing Generation and Distance Estimation},
  author={Makowski, Connor and Saragih, Austin and Guter, Willem and Russell, Tim and Heinold, Arne and Lekkakos, Spyridon},
  journal={MIT Center for Transportation & Logistics Research Paper Series},
  number={2025-028},
  year={2025},
  url={https://ssrn.com/abstract=5388845}
}
```

---

## Installation

```bash
pip install scgraph
```

### Pure Python Installation (Skip Binary Builds)

If you want to install `scgraph` in pure Python mode without compiling or using binary extensions (or in environments without a C++ compiler):

- **Linux / macOS / WSL2**:
  ```bash
  SCGRAPH_NO_BUILD=1 pip install --no-binary scgraph scgraph
  ```
  Or with `uv`:
  ```bash
  SCGRAPH_NO_BUILD=1 uv pip install --no-binary scgraph scgraph
  ```

- **Windows (PowerShell)**:
  ```powershell
  $env:SCGRAPH_NO_BUILD="1"
  pip install --no-binary scgraph scgraph
  ```

- **Windows (CMD)**:
  ```cmd
  set SCGRAPH_NO_BUILD=1
  pip install --no-binary scgraph scgraph
  ```

#### Automatic Fallback
When building from source, if a C++ compiler is not available or compilation fails, `scgraph` will automatically fall back to a pure Python implementation.

---

## Quick Start: Load a Network

Get the shortest maritime path between Shanghai and Savannah, GA:

```py
from scgraph import GeoGraph

world_sea = GeoGraph.load_geograph("world_sea")

output = world_sea.get_shortest_path(
    origin_node={"latitude": 31.23, "longitude": 121.47},
    destination_node={"latitude": 32.08, "longitude": -81.09},
    output_units='km',
)
print(output['length'])  #=> 19264.1889
```

`world_sea` is a released network: scgraph downloads it (3.7 MB) on the first load and keeps it in the cache. `marnet`, the sea network of scgraph 3.6.0, still loads the same way and still gives 19596.4653 km. The two networks come from different versions of the sea lanes, so their lengths differ.

The output dictionary always contains:

| Key | Description |
|---|---|
| `length` | Distance along the shortest path in the requested `output_units` |
| `coordinate_path` | List of `[latitude, longitude]` pairs making up the path |


### Which Network?

| Need | Network | Call |
|---|---|---|
| Routes over roads, railways, sea lanes and flights | `world_multimodal`, or a part of the world such as `europe` | `GeoGraph.load_geograph("europe")` |
| Routes by sea | `world_sea` | `GeoGraph.load_geograph("world_sea")` |
| Routes by rail | `world_rail` | `GeoGraph.load_geograph("world_rail")` |
| One mode of transport of a larger network, for example the roads | a released network, with `modes` | `GeoGraph.load_geograph("europe", modes=["road"])` |
| The same result later, on any machine | a released network, pinned | `GeoGraph.load_geograph("europe", version=..., content_sha256=...)` |
| The data of today for one region | a network built on your machine (needs `pip install scgraph[osm]`) | `GeoGraph.build_geograph("geofabrik_multimodal", region="europe/denmark")` |
| Your own lines | a GeoJSON or an OpenStreetMap file | `GeoGraph.load_from_geojson(file)` or `GeoGraph.load_from_osm(file)`, then `save_as_scgraph` to load it faster later |
| A result of scgraph 3.6.0, unchanged | a built-in geograph | `GeoGraph.load_geograph("marnet")` |

`GeoGraph.list_geographs()` lists every network that `load_geograph` takes. For each network it gives what the network holds, and for a released network the size of its download. For a network of scgraph 3.6.0, `superseded_by` names the released network that covers the same need with newer data. The networks of 3.6.0 still load, with the same results.

### Network Releases

The maintainers of scgraph also build networks of the whole world from OpenStreetMap and other open sources. A **network release** is a set of these networks, published together on GitHub under one tag, for example `networks-2026.11.20`. A network of a network release is a **released network**. `load_geograph` loads a released network by its name.

```py
from scgraph import GeoGraph

europe = GeoGraph.load_geograph("europe")

paris = {"latitude": 48.8566, "longitude": 2.3522}
berlin = {"latitude": 52.52, "longitude": 13.405}
route = europe.get_shortest_path(origin_node=paris, destination_node=berlin)
print(route["length"])  #=> 909.028 (km: the shortest route takes a flight)
```

**The networks.** Distances are in kilometers. The shape of an arc is the list of points that draw the arc on a map between its two nodes. Each network has a file with the shapes and a smaller file without them. The sizes are those of the network release `networks-2026.11.20-dev.1`.

| Name | What it holds | Download, with shapes | Without shapes |
|---|---|---|---|
| `world_multimodal` | The main roads, the railways, the sea lanes and the regular flights of the world. Ports, airports and rail terminals join them | 196.9 MB | 88.9 MB |
| `world_sea` | The sea lanes and the ports of the world | 3.7 MB | 1.2 MB |
| `world_rail` | The railways and the rail terminals of the world | 28.9 MB | 10.5 MB |
| `europe` | Latitudes 34 to 72, longitudes -25 to 45 | 60.4 MB | 28.3 MB |
| `north_america` | Latitudes 7 to 84, longitudes -170 to -50 | 41.3 MB | 19.0 MB |
| `south_america` | Latitudes -57 to 13, longitudes -82 to -34 | 16.6 MB | 7.4 MB |
| `africa` | Latitudes -35 to 38, longitudes -18 to 52 | 20.3 MB | 9.9 MB |
| `west_south_asia` | Latitudes 5 to 45, longitudes 25 to 98 | 30.2 MB | 14.5 MB |
| `east_southeast_asia` | Latitudes -11 to 55, longitudes 92 to 150 | 56.5 MB | 22.6 MB |
| `north_asia` | Latitudes 40 to 78, longitudes 45 to 180 | 13.0 MB | 5.1 MB |
| `oceania` | Latitudes -50 to 0, longitudes 110 to 180 | 9.2 MB | 3.5 MB |

A network named for a part of the world is a part of `world_multimodal`. It holds the roads, the railways and the rail terminals inside its rectangle. It also holds every sea lane, port and airport of the world, so a route can leave the rectangle by sea or by air.

**Some modes only.** Each node of these networks has a mode: `road`, `rail`, `sea`, `port`, `airport` or `rail_terminal`. A route changes mode at a port, an airport or a rail terminal. `modes` loads the nodes of some modes only:

```py
roads = GeoGraph.load_geograph("europe", modes=["road"])
route = roads.get_shortest_path(origin_node=paris, destination_node=berlin)
print(route["length"])  #=> 1031.6 (km, by road)
```

**A smaller download.** `shapes=False` downloads the file without the shapes. The route lengths are the same. The `coordinate_path` of a route then goes in a straight line from node to node.

**The first load and the next ones.** The first load downloads the file, decompresses it and checks its content. If the download is damaged, `load_geograph` raises a `ValueError` and keeps no file. Every later load reads the cache and makes no network request. The cache keeps the files of each network release until `clear_geograph_cache` removes them. The section *Built-in Geographs: Cache Management* gives the place of the cache and the offline switch.

**The same network later.** Each version of scgraph loads one network release, so the same version loads the same network on every machine. A later version of scgraph may load a newer network release. To load exactly the same network then, record the tag of the network release and the `content_sha256` of the file. The `content_sha256` is the SHA-256 digest of the content of a network file.

```py
from scgraph import network_release

network_release.TAG  # 'networks-2026.11.20-dev.1', the network release that this scgraph loads
info = GeoGraph.get_scgraph_info(europe.scgraph_file)
info["content_sha256"]  # '4212a887e6fa1807...'
info["attribution"]     # the credit line to cite with your results
info["data_up_to"]      # '2026-11-02T00:59:53Z', the time of the newest source data

# Later, on any machine: this call loads the same file, or raises a ValueError
europe = GeoGraph.load_geograph(
    "europe",
    version="networks-2026.11.20-dev.1",
    content_sha256="4212a887e6fa18071a1eb886a6a6ca69831255f3e09ddb14b5b7bc8cfa1ca6ad",
)
```

The guide [From open data to a route](https://github.com/connor-makowski/scgraph/blob/main/scgraph/pipelines/README.md) explains how these networks are built, checked, published and loaded.

The notebook [Routes on a multimodal network](https://colab.research.google.com/github/connor-makowski/scgraph/blob/main/examples/multimodal_networks.ipynb) draws routes of `oceania` on interactive maps. It shows the kinds of transport that a route uses, the choice of the modes, and two limit cases.

### Built-in Geographs
These are the seven networks of scgraph 3.6.0. `load_geograph` still loads them, with the same results. All built-in geographs measure distances in kilometers and are downloaded on first use and cached locally.

| Name | Load Key | Description | Attribution |
|---|---|---|---|
| `marnet` | `GeoGraph.load_geograph("marnet")` | Maritime network | [searoute](https://github.com/genthalili/searoute-py) · [Map](https://raw.githubusercontent.com/connor-makowski/scgraph/main/static/marnet.png) |
| `oak_ridge_maritime` | `GeoGraph.load_geograph("oak_ridge_maritime")` | Maritime network (Oak Ridge National Laboratory) | [ORNL](https://www.ornl.gov/) / [Geocommons](http://geocommons.com/datasets?id=25) · [Map](https://raw.githubusercontent.com/connor-makowski/scgraph/main/static/oak_ridge_maritime.png) |
| `north_america_rail` | `GeoGraph.load_geograph("north_america_rail")` | Class 1 rail network for North America | [USDOT ArcGIS](https://geodata.bts.gov/datasets/usdot::north-american-rail-network-lines-class-i-freight-railroads-view/about) · [Map](https://raw.githubusercontent.com/connor-makowski/scgraph/main/static/north_america_rail.png) |
| `us_freeway` | `GeoGraph.load_geograph("us_freeway")` | Freeway network for the United States | [USDOT ArcGIS](https://hub.arcgis.com/datasets/esri::usa-freeway-system-over-1500k/about) · [Map](https://raw.githubusercontent.com/connor-makowski/scgraph/main/static/us_freeway.png) |
| `world_highways_and_marnet` | `GeoGraph.load_geograph("world_highways_and_marnet")` | World highway network merged with the maritime network | [OpenStreetMap](https://www.openstreetmap.org/) / [searoute](https://github.com/genthalili/searoute-py) |
| `world_highways` | `GeoGraph.load_geograph("world_highways")` | World highway network | [OpenStreetMap](https://www.openstreetmap.org/) |
| `world_railways` | `GeoGraph.load_geograph("world_railways")` | World railway network | [OpenStreetMap](https://www.openstreetmap.org/) |

## Quick Start: OSMNx Integration

Route on any OpenStreetMap network (including bike, drive, and walk) using [OSMNx](https://osmnx.readthedocs.io/). This example finds the fastest and shortest bike paths between two points in Somerville and Cambridge, MA, then cross-evaluates each path's time and distance:

```py
import osmnx as ox
from scgraph import GeoGraph

# Download the bike network for Somerville and Cambridge, MA
G = ox.graph_from_place(
    ['Somerville, Massachusetts, USA', 'Cambridge, Massachusetts, USA'],
    network_type='bike'
)
G = ox.add_edge_speeds(G)
G = ox.add_edge_travel_times(G)

# Build a time-based and a distance-based GeoGraph from the same OSMNx graph
geograph_time     = GeoGraph.load_from_osmnx_graph(G, weight_key='travel_time')
geograph_distance = GeoGraph.load_from_osmnx_graph(G, weight_key='length')

origin      = {'latitude': 42.3601, 'longitude': -71.0942}  # MIT campus
destination = {'latitude': 42.3876, 'longitude': -71.0995}  # Somerville City Hall

time_result     = geograph_time.get_shortest_path(origin_node=origin, destination_node=destination, output_path=True)
distance_result = geograph_distance.get_shortest_path(origin_node=origin, destination_node=destination, output_path=True)

# Cross-evaluate: get the distance of the time-optimal path, and vice versa
time_path_distance_km = geograph_distance.get_path_weight(time_result)
distance_path_time_s  = geograph_time.get_path_weight(distance_result)

print(f"Time-optimal path:     {time_result['length']:.1f} s  |  {time_path_distance_km:.3f} km")
print(f"Distance-optimal path: {distance_path_time_s:.1f} s  |  {distance_result['length']:.3f} km")
# Time-optimal path:     340.9 s  |  3.920 km
# Distance-optimal path: 369.3 s  |  3.605 km
```

See the [OSMNx notebook](https://colab.research.google.com/github/connor-makowski/scgraph/blob/main/examples/osmnx.ipynb) for a full example with folium map visualization.

---

# Core Concepts

## What is a GeoGraph?

A `GeoGraph` is the primary object in SCGraph. It combines a **graph** (a network of nodes and weighted edges) with **geographic coordinates** (latitude/longitude for each node), enabling shortest path queries between arbitrary real-world coordinates, not just predefined graph nodes.

When you call `get_shortest_path`, SCGraph:
1. Connects your origin and destination to nearby graph nodes using haversine or euclidean distance, without modifying the graph
2. Runs the requested shortest path algorithm from those nodes
3. Returns the path in geographic coordinates

This means you never need to worry about whether your start/end points are "in" the network. SCGraph handles that automatically.

## Graph Structure

Internally, a graph is represented as a list of adjacency dicts:

```py
graph = [
    {1: 5, 2: 1},   # node 0: connected to node 1 (cost 5) and node 2 (cost 1)
    {0: 5, 2: 2},   # node 1: connected to node 0 and node 2
    {0: 1, 1: 2},   # node 2: connected to node 0 and node 1
]
```

Nodes are identified by their zero-based index. Edge weights are typically distances in kilometers for GeoGraphs.

---

# Algorithm Reference

## Graph Algorithms

All algorithms are available on `Graph` objects and accessible from `GeoGraph` via `algorithm_fn`:

| `algorithm_fn` | Description | Time Complexity |
|---|---|---|
| `'dijkstra'` | Standard Dijkstra; general purpose, non-negative weights | O((n+m) log n) |
| `'bidirectional_dijkstra'` | Bidirectional Dijkstra; simultaneous search from origin and destination | O((n+m) log n) |
| `'dijkstra_buckets'` | Dijkstra with buckets of a width set from the graph; non-negative weights | O(n+m+W) |
| `'bidirectional_buckets'` | Bidirectional Dijkstra (default for geographs) with buckets (Dial's algorithm); efficient for non-negative weights | O(n+m+W) |
| `'dijkstra_negative'` | Dijkstra with cycle detection; supports negative weights | O(n·m) |
| `'a_star'` | A* with optional heuristic; faster than Dijkstra with a good heuristic | O((n+m) log n) |
| `'bellman_ford'` | Bellman-Ford; supports negative weights, slower than Dijkstra | O(n·m) |
| `'bmssp'` | [BMSSP Algorithm](https://arxiv.org/pdf/2504.17033) / [Implementation](https://github.com/connor-makowski/bmsspy) | O(m log^(2/3)(n)) |
| `'cached_shortest_path'` | Caches shortest path tree from origin; near-instant repeated queries | O((n+m) log n) first, O(1) after |
| `'contraction_hierarchy'` | Bidirectional Dijkstra on preprocessed CH graph; fast arbitrary queries | O(k log k) per query |
| `'tnr'` | [Transit Node Routing](https://en.wikipedia.org/wiki/Transit_node_routing); extremely fast for global queries | O(1) per query (global) |

## Performance Guide

| Scenario | Recommended Approach |
|---|---|
| Single query | `dijkstra`, `bidirectional_buckets` or `bidirectional_dijkstra` |
| Sparse networks (road/rail/maritime) | Reduce with `geograph.reduce()` for 2–4x faster queries |
| Non-negative weights, single-direction search | `dijkstra_buckets` |
| Repeated queries from one origin | `cached_shortest_path` |
| Large distance matrix (same graph) | `distance_matrix` method |
| Many arbitrary queries on a fixed graph | `contraction_hierarchy` or `tnr` |
| Graph with negative weights | `dijkstra_negative` |
| Fast app startup / multi-network loading | `GeoGraph.load_geograph(..., lazy=True)` |

## Heuristic Functions (for A*)

GeoGraph provides built-in heuristics for A*:

```py
my_geograph = GeoGraph.load_geograph("marnet")  # or any other geograph

output = my_geograph.get_shortest_path(
    origin_node={"latitude": 42.29, "longitude": -85.58},
    destination_node={"latitude": 42.33, "longitude": -83.05},
    algorithm_fn='a_star',
    algorithm_kwargs={"heuristic_fn": my_geograph.haversine},
)
```

| Method | Description |
|---|---|
| `my_geograph.haversine` | Great-circle distance heuristic (accurate), in `geograph_units`; computed natively by `get_shortest_path` A* in the C++ build |
| `my_geograph.cheap_ruler` | Fast approximate distance (Mapbox method), in `geograph_units` |

A* returns the shortest path if the heuristic never exceeds the real distance left to the destination. When the destination is connected to more than 4 nodes of the graph (for example with `destination_node_addition_type='all'`), A* does not call the heuristic and searches as Dijkstra does.

---

# GeoGraph Usage

## Basic Routing

```py
from scgraph import GeoGraph

marnet_geograph = GeoGraph.load_geograph("marnet")

output = marnet_geograph.get_shortest_path(
    origin_node={"latitude": 31.23, "longitude": 121.47},      # Shanghai
    destination_node={"latitude": 32.08, "longitude": -81.09}, # Savannah, GA
    output_units='km',
)

print(output['length'])          # 19596.4653
print(output['coordinate_path']) # [[31.23, 121.47], ..., [32.08, -81.09]]
```

Supported `output_units`:

| Value | Unit |
|---|---|
| `km` | Kilometers (default) |
| `m` | Meters |
| `mi` | Miles |
| `ft` | Feet |

## Choosing an Algorithm

Pass any algorithm name (or function) to `algorithm_fn`:

```py
marnet_geograph = GeoGraph.load_geograph("marnet")

output = marnet_geograph.get_shortest_path(
    origin_node={"latitude": 31.23, "longitude": 121.47},
    destination_node={"latitude": 32.08, "longitude": -81.09},
    algorithm_fn='a_star',
    algorithm_kwargs={"heuristic_fn": marnet_geograph.haversine},
)
```

See the [Algorithm Reference](#algorithm-reference) for all available algorithms and when to use them. You can also pass any callable that matches the `Graph` method signature.

## Cached Queries (Same Origin, Many Destinations)

For repeated queries from the same origin point (e.g., distribution center → many customers), use `cached_shortest_path`. The full shortest path tree is computed once and cached:

```py
from scgraph import GeoGraph

marnet_geograph = GeoGraph.load_geograph("marnet")

# First call: computes and caches the shortest path tree (~same cost as dijkstra without an early termination)
output1 = marnet_geograph.get_shortest_path(
    origin_node={"latitude": 31.23, "longitude": 121.47}, # Shanghai
    destination_node={"latitude": 32.08, "longitude": -81.09}, # Savannah, GA
    algorithm_fn='cached_shortest_path',
)

# Subsequent calls to the same origin are near-instant (O(1) lookup)
output2 = marnet_geograph.get_shortest_path(
    origin_node={"latitude": 31.23, "longitude": 121.47}, # Shanghai (same)
    destination_node={"latitude": 51.50, "longitude": -0.13},  # London
    algorithm_fn='cached_shortest_path',
)
```

## Distance Matrix

For all-pairs distance computation across a set of locations, use `distance_matrix`. Each origin's shortest path tree is cached internally, making this highly efficient for large matrices:

```py
from scgraph import GeoGraph

us_freeway_geograph = GeoGraph.load_geograph("us_freeway")

cities = [
    {"latitude": 34.0522, "longitude": -118.2437},  # Los Angeles
    {"latitude": 40.7128, "longitude": -74.0060},   # New York City
    {"latitude": 41.8781, "longitude": -87.6298},   # Chicago
    {"latitude": 29.7604, "longitude": -95.3698},   # Houston
]

matrix = us_freeway_geograph.distance_matrix(cities, output_units='km')
# [
#  [0.0,    4510.97, 3270.39, 2502.89],
#  [4510.97, 0.0,   1288.47, 2637.58],
#  [3270.39, 1288.47, 0.0,  1913.19],
#  [2502.89, 2637.58, 1913.19, 0.0 ],
# ]
```

For large matrices, throughput can approach 500 nanoseconds per distance query.

## Graph Reduction

Sparse networks (highways, rail lines, shipping corridors) often contain long chains of pass-through nodes with only two connections (degree 2). Graph reduction compresses these chains into single composite edges while preserving exact distances and full path reconstruction:

```py
from scgraph import GeoGraph

us_freeway = GeoGraph.load_geograph("us_freeway")

# Reduce the graph by bypassing pass-through chains (e.g. simplifies ~88% of nodes on us_freeway)
us_freeway.reduce(iterations=1)

# All standard algorithms (dijkstra, bidirectional_dijkstra, a_star, etc.)
# automatically execute on the reduced graph and expand paths back to original coordinates:
output = us_freeway.get_shortest_path(
    origin_node={"latitude": 34.05, "longitude": -118.24},  # Los Angeles
    destination_node={"latitude": 40.71, "longitude": -74.01},  # New York City
    algorithm_fn='bidirectional_dijkstra',
)
print(output['length'])
```

Key features of graph reduction:
- **Zero inaccuracy**: Paths and lengths are guaranteed to be mathematically identical to the unreduced graph.
- **Same-chain routing**: If origin and destination fall on the same contracted chain, the original graph is used with the standard dijkstra algorithm.
- **Iterative reduction**: By default, `reduce()` repeats passes until a pass reduces nothing (simplifying sub-chains created after initial contraction); pass `iterations=1` for a single pass.

## Lazy Loading

To avoid upfront downloading, parsing, or memory overhead when defining multiple networks or optimizing startup latency, use `lazy=True`:

```py
from scgraph import GeoGraph

# Returns a LazyGeoGraph proxy immediately without downloading or parsing
world_net = GeoGraph.load_geograph("world_highways_and_marnet", lazy=True)

# The network is downloaded and instantiated only when first queried:
output = world_net.get_shortest_path(
    origin_node={"latitude": 31.23, "longitude": 121.47},
    destination_node={"latitude": 32.08, "longitude": -81.09},
)

# Or explicitly load the graph at any time:
world_net.load()
```

## Node Addition Options

Control how origin/destination are connected to the graph:

```py
marnet_geograph = GeoGraph.load_geograph("marnet")

output = marnet_geograph.get_shortest_path(
    origin_node={"latitude": 31.23, "longitude": 121.47},
    destination_node={"latitude": 32.08, "longitude": -81.09},
    # Max search radius in degrees (default: 'auto')
    node_addition_lat_lon_bound=180,
    # Connect origin to the closest node in each quadrant (NE, NW, SE, SW)
    node_addition_type='quadrant',
    # Connect destination to all nodes within the bound
    destination_node_addition_type='all',
)
```

| `node_addition_type` | Description |
|---|---|
| `'closest'` / `'kdclosest'` | Closest node (default) |
| `'quadrant'` / `'kdquadrant'` | Closest node in each quadrant |
| `'all'` | All nodes within the bound |


---

# Loading GeoGraphs

## Built-in Geographs: Cache Management

Built-in geographs are downloaded from GitHub on first use and stored in a local cache. Subsequent loads only require reading from the local cache and do not require network access.

For one of the seven networks of scgraph 3.6.0, the first load also converts the downloaded `<name>.graphjson` into a binary network file, `<name>.scgraph`, beside it. Later loads read the binary file, which is much faster. The `.graphjson` is kept. The conversion changes three things:

- **Node ids**: Nodes are numbered along a Hilbert curve, so that nodes close on the globe get close ids. Route lengths do not change. When two routes have exactly the same length, the other one may be returned.
- **Coordinates**: Coordinates are stored to 1e-7 degree (about 1 cm). A few published ports have 9 decimals.
- **Ids of scgraph 3.6.0**: `node_ids[i]` is the id that node `i` has in the `.graphjson`, so `[geo.node_ids[i] for i in path]` translates a path. `load_from_graphjson` on the cached `.graphjson` keeps the old numbering.

```py
from scgraph import GeoGraph

# Load a geograph (downloads on first call, loads from cache after)
marnet_geograph = GeoGraph.load_geograph("marnet")

# Optionally specify a custom cache directory
marnet_geograph = GeoGraph.load_geograph("marnet", cache_dir="/path/to/cache")

# Never download: use only the cache (FileNotFoundError if the geograph is not there)
marnet_geograph = GeoGraph.load_geograph("marnet", local_files_only=True)

# List all available geographs and whether each is cached locally (no network request)
available = GeoGraph.list_geographs()
# [
#     ...
#     {"name": "europe", "cached": True, "kind": "released",
#      "description": "The part of world_multimodal between latitudes 34 and 72 and longitudes -25 and 45, ...",
#      "nodes": 1048594, "arcs": 2071242, "download_mb": 60.4, "download_mb_without_shapes": 28.3,
#      "data_up_to": "2026-11-02T00:59:53Z"},
#     {"name": "marnet", "cached": False, "kind": "built-in",
#      "description": "Sea lanes of the world (Eurostat SeaRoute)", "superseded_by": "world_sea"},
#     ...
# ]

# What the cache holds: one dict per file, with its kind, name, region, path and size
GeoGraph.get_cache_info()

# Clear the cached geographs (other files in the cache directory are kept)
GeoGraph.clear_geograph_cache()
# ... or only one network (and, for a built network, one region)
GeoGraph.clear_geograph_cache(name="geofabrik_multimodal", region="europe/denmark")
```

On Windows, the files of a network still loaded in the process can't be deleted: `clear_geograph_cache` leaves them in place, with a logging warning that names them, and a later clear removes them.

The cache location defaults to the platform-appropriate directory:

| Platform | Default cache path |
|---|---|
| Linux | `~/.cache/scgraph/` |
| macOS | `~/Library/Caches/scgraph/` |
| Windows | `%LOCALAPPDATA%\scgraph\` |

To use another directory for every call, set the environment variable `SCGRAPH_CACHE_DIR`; a `cache_dir` argument wins over it. To work without network access, set `SCGRAPH_OFFLINE=1`: it makes `local_files_only=True` the default of `load_geograph` and `build_geograph`, and a `local_files_only` argument wins over it.

### `load_geograph` Parameters

| Parameter | Default | Description |
|---|---|---|
| `name` | required | Name of the built-in geograph (e.g. `'marnet'`, `'us_freeway'`), or of a released network (e.g. `'europe'`) |
| `cache_dir` | `None` | Custom directory for downloaded files; defaults to `SCGRAPH_CACHE_DIR` if set, else the OS cache dir above |
| `geograph_url` | `'https://raw.githubusercontent.com/...'` | Base URL for fetching geographs. With another URL, every name loads `<name>.graphjson` from that URL |
| `reduce_iterations` | `0` | Number of reduction iterations to perform upon loading (`0` = none, `1` = single pass, `-1` = full convergence) |
| `lazy` | `False` | Defer loading/fetching until the geograph is first accessed |
| `local_files_only` | `None` | Use only the cache, never download; defaults to `True` if `SCGRAPH_OFFLINE=1`, else `False` |
| `version` | `None` | For a released network: the tag of the network release, e.g. `'networks-2026.11.20'`; defaults to the network release of the installed scgraph (`scgraph.network_release.TAG`) |
| `content_sha256` | `None` | For a released network: the `content_sha256` that the file must have (as `get_scgraph_info` gives it); another file raises a `ValueError`. With `version`, it loads exactly the same network again later |
| `modes` | `None` | For a released network: the modes to load, e.g. `["road"]`; `None` loads every mode |
| `shapes` | `True` | For a released network: `False` loads the file without the shapes of the arcs |

## Building Networks from Their Sources

`build_geograph` builds a network on your machine from its online sources. It downloads the sources once and keeps the built network in the local cache. Later calls load the network from the cache, without network access. A source can be large: the OpenStreetMap extract of a country can take several GB. scgraph logs a warning before a download above 100 MB.

Each network is built by a pipeline. A pipeline is a module of `scgraph.pipelines`, and its docstring describes the network: what it holds, its rules and its limits. From the command line, `python -m scgraph.pipelines.network_builder NAME [--region R] [--cache-dir D]` builds a network without loading it, and prints the path of its file.

```py
import logging
from scgraph import GeoGraph

logging.basicConfig(level=logging.INFO)  # optional: show the downloads and the credit

# Roads and railways of Denmark, joined to the sea lanes of the world and to flights
# (needs: pip install scgraph[osm])
denmark = GeoGraph.build_geograph("geofabrik_multimodal", region="europe/denmark")
# INFO:scgraph.pipelines:Downloading https://download.geofabrik.de/europe/denmark-latest.osm.pbf (498.2 MB)
# INFO:scgraph.pipelines.network_builder:Building geofabrik_multimodal
# The last INFO line gives the credit to cite.

# Sea lanes of the world, from Eurostat SeaRoute
sea = GeoGraph.build_geograph("eurostat_sea_lanes")

# What can be built, who to credit, and what is already in the cache
GeoGraph.list_buildable_geographs()
# [{"name": "eurostat_sea_lanes", "description": "Sea lanes of Eurostat SeaRoute at 5 km resolution, (...)",
#   "credit": "Eurostat, SeaRoute maritime network (...)", "license": "EUPL-1.2",
#   "needs_region": False, "cached": False, "cached_regions": []},
#  ...]
```

The region of `geofabrik_multimodal` is the path of a [Geofabrik extract](https://download.geofabrik.de), as in its download URL: `europe/luxembourg`, `europe/france/bretagne`, `north-america/us/texas` ([all extracts](https://download.geofabrik.de/index-v1-nogeom.json), machine-readable). A region that Geofabrik does not have raises a `ValueError`, before any large download.

| Name | Network | Source |
|---|---|---|
| `eurostat_sea_lanes` | Sea lanes at 5 km resolution, lanes cut at the antimeridian joined, Arctic passages left out (unlike the built-in `marnet`) | Eurostat SeaRoute, GeoPackage at a fixed commit of its repository |
| `geofabrik_multimodal` | Main roads, railways, sea lanes and regular flights of a region, joined at ports, airports and rail terminals; each node has its mode, and each arc has its class | OpenStreetMap extract from [Geofabrik](https://download.geofabrik.de), Eurostat SeaRoute, Natural Earth; hubs and flights from tables kept with scgraph (NGA World Port Index, OurAirports, flights of 2021 from OpenSky, BTS T-100 and Eurostat, Wikidata) |
| `osm_world_multimodal` | `geofabrik_multimodal` for the world (needs the C++ extension). This pipeline builds the released network `world_multimodal` | The sources of `geofabrik_multimodal`, with the OpenStreetMap planet in place of the extract. The planet is read by byte ranges and never stored |

**Where a built network is kept.** Each network has a folder in the cache directory: `networks/<name>/`, or `networks/<name>/<region>/` for `geofabrik_multimodal`. The folder holds the network file, named by the SHA-256 of its content, and a `cache.json` that names this file. The downloaded sources are deleted once the network is built. A build that fails keeps its work folder, `.work/` in the cache directory, with the downloaded sources. The next build resumes from this folder. `refresh=True` empties it first. `GeoGraph.clear_geograph_cache()` removes it. scgraph also writes a `CACHEDIR.TAG` in `networks/`, so that backup tools that honour it skip the built networks. [ARCHITECTURE.md](https://github.com/connor-makowski/scgraph/blob/main/ARCHITECTURE.md#6-caches-and-invalidation) describes the cache in detail.

**What a network file says about itself.** The file stores the pipeline, the sources with the time of their data, and the software that built it. `GeoGraph.get_scgraph_info(file)` reads this metadata, with the credit line to cite (`attribution`) and the newest data time (`data_up_to`). The fields are listed in the docstring of `scgraph.pipelines` and in [ARCHITECTURE.md](https://github.com/connor-makowski/scgraph/blob/main/ARCHITECTURE.md#7-network-file-format).

**When a network is built again.** A network is built again in three cases:

- An upgrade of scgraph changed the version of its pipeline or the file format.
- The file that `cache.json` names is missing.
- You pass `refresh=True`.

A rebuild removes the old network file. On Windows, an old file that another process holds open stays until the cache is cleared.

**Offline.** With `local_files_only=True`, nothing is downloaded. A network that is not in the cache raises a `FileNotFoundError`. A network built with another version of its pipeline is loaded with a warning that names what differs. A network in another file format is refused.

**Two versions of scgraph on one cache.** Each version rebuilds a network that the other version built. Give each version its own `SCGRAPH_CACHE_DIR`, or use `local_files_only=True` in the older one.

**Saving.** `save_as_scgraph` and `save_as_graphjson` refuse to write under `networks/` of the cache directory. Save an edited network elsewhere.

**Networks of several modes.** `geofabrik_multimodal` and `osm_world_multimodal` join several modes of transport. Ports, airports and rail terminals join roads, railways, sea lanes and regular flights. Such a place is a hub, and a hub is one node. A connector is the pair of arcs that joins a hub to the network of one mode. The docstring of `geofabrik_multimodal` gives the rules of the connectors.

Each node has a mode, for example `road`, `sea` or `port`. `geo.node_modes[i]` gives the row of node `i` in `geo.modes`. That row names the mode and the source of the node ids (OpenStreetMap for roads). The file stores the nodes of each mode together. Routes use kilometers for every mode.

In these networks, the shortest route in kilometers between two distant places takes a flight, because a flight is a straight line. To route on some modes only, load the file with these modes and the hubs that join them: `GeoGraph.load_from_scgraph(file, modes=["road", "rail", "rail_terminal"])`. Without a hub mode, the networks of two modes have no link.

The file of these networks also records the class of each arc, for example `motorway`, `primary`, `ferry`, `rail_main`, `suez` or `flight`. `scgraph.network_file.read(file)` returns `(arrays, metadata)`, and the class of arc `a` is `metadata["classes"][arrays["arc_classes"][a]]`. The docstring of `scgraph.pipelines` lists the classes.

**A pipeline of your own.** The docstring of `scgraph.pipelines` states what a pipeline holds and how to write one. The guide [From open data to a route](https://github.com/connor-makowski/scgraph/blob/main/scgraph/pipelines/README.md), Part 1, follows one build step by step, with its numbers. `build_geograph` also takes a pipeline module of your own, for example an adapted copy of a pipeline of scgraph under another name. Its network is cached under `networks/<last part of the module name>/`. A module that has the name of a pipeline of scgraph is refused, and `list_buildable_geographs` does not list your module.

The networks that `build_geograph` builds are not the built-in geographs of `load_geograph`. They come from other sources, or from a newer version of a source, so their nodes and their results differ.

`geofabrik_multimodal` has a node at every junction, and two nodes along a road or a railway are at most about 4 km apart (about 20 km in `osm_world_multimodal`). Sea lanes are not cut. `reduce_iterations=-1` removes the nodes that routing does not need.

In these networks, the shape of each road, ferry or railway arc is simplified to within 50 m (Douglas–Peucker). Lengths are measured on the full shape.

### `build_geograph` Parameters

| Parameter | Default | Description |
|---|---|---|
| `name` | required | Name of the network (table above), or a pipeline module |
| `region` | `None` | For `geofabrik_multimodal`: the path of a [Geofabrik extract](https://download.geofabrik.de), as in its download URL (e.g. `'europe/luxembourg'`, `'north-america/us/texas'`) |
| `cache_dir` | `None` | Custom cache directory; defaults to `SCGRAPH_CACHE_DIR` if set, else the OS cache dir above |
| `reduce_iterations` | `0` | Number of reduction iterations to perform upon loading (`0` = none, `1` = single pass, `-1` = full convergence) |
| `lazy` | `False` | Defer downloading/loading until the geograph is first accessed |
| `refresh` | `False` | Download the sources and build the network again, even if the cache holds a current build |
| `local_files_only` | `None` | Use only the cache, never download; defaults to `True` if `SCGRAPH_OFFLINE=1`, else `False` |
| `modes` | `None` | The modes to load from the built network, e.g. `["road"]`; `None` loads every mode |
| `validate` | `False` | Check the built network against the validation cases of its pipeline; a network that fails is not kept in the cache, and a `RuntimeError` names the failed cases |

## Loading from OSMNx

SCGraph integrates directly with [OSMNx](https://osmnx.readthedocs.io/) — load any OpenStreetMap network and convert it to a `GeoGraph` in two lines:

```py
import osmnx as ox
from scgraph import GeoGraph

# Download the drivable road network for Ann Arbor, MI
osmnx_graph = ox.graph_from_place("Ann Arbor, Michigan, USA", network_type="drive")

# Convert to a GeoGraph
ann_arbor_geograph = GeoGraph.load_from_osmnx_graph(osmnx_graph)

# Route between two points
output = ann_arbor_geograph.get_shortest_path(
    origin_node={"latitude": 42.2808, "longitude": -83.7430},
    destination_node={"latitude": 42.2622, "longitude": -83.7482},
    output_units='km',
)
print(output['length'])
```

### `load_from_osmnx_graph` Parameters

| Parameter | Default | Description |
|---|---|---|
| `osmnx_graph` | required | An OSMNx graph object |
| `coord_precision` | `5` | Decimal places for lat/lon coordinates |
| `weight_precision` | `3` | Decimal places for edge weights |
| `weight_key` | `'length'` | Edge attribute to use as weight (`'length'` or `'travel_time'`) |
| `off_graph_travel_speed` | `None` | Speed (km/h) for off-graph connections; used to convert time-based weights to distances |
| `load_intermediate_nodes` | `True` | Load intermediate shape points for accurate path visualization |
| `silent` | `None` | Deprecated and without effect. scgraph reports its messages through `logging`. |
| `reduce_iterations` | `0` | Number of reduction iterations to perform upon loading (`0` = none, `1` = single pass, `-1` = full convergence) |
| `lazy` | `False` | Defer loading until the geograph is first accessed |

## Building from OSM Data (Without OSMNx)

Build a geograph directly from an OpenStreetMap file, for example a regional extract from [Geofabrik](https://download.geofabrik.de/). Reading OSM files needs an optional dependency:

```bash
pip install scgraph[osm]
```

```py
from scgraph import GeoGraph

# Main roads (motorway to primary, with their links); one-way streets are respected
michigan_roads = GeoGraph.load_from_osm("michigan-latest.osm.pbf")

# Other ways: select(tags) gives the direction of a way (1 or -1: one way, 0: both
# ways) or None to leave it out; only ways with one of the tag keys reach select.
# Here railway lines without yards, sidings and spurs, both ways. The crossovers
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

Ways meet only where they share an OSM node, so roads that cross on a bridge or in a tunnel are not connected. Each arc has the length of its piece of way, in kilometers. A way is also cut at the first point where the arc since the previous node reaches `max_km_between_nodes` (2 km by default). The earlier pipeline (osmium-tool, a GeoJSON export and Mapshaper), which the paper refers to, is kept below. `load_from_geojson` still loads such files.

### `load_from_osm` Parameters

| Parameter | Default | Description |
|---|---|---|
| `filename` | required | Path of the OSM file (`.osm.pbf`, `.osm` or `.osm.bz2`), or a source object (`scgraph.pipelines.steps.step1_osm_ways.locate_ways`) |
| `select` | `None` (`scgraph.pipelines.steps.step1_osm_ways.select_main_roads`) | Gives, from the tags of a way, its direction (`1` or `-1`: one way along or against its drawing, `0`: both ways) or `None` to leave it out; the default keeps main roads (`scgraph.pipelines.steps.step1_osm_ways.MAIN_ROADS`), one way where `scgraph.pipelines.steps.step1_osm_ways.get_way_direction(tags)` returns `1` or `-1` |
| `tag_keys` | `("highway",)` | Tag keys of which a way must have at least one to reach `select`, filtered in osmium (faster); `()` sends every way to `select` |
| `max_km_between_nodes` | `2` | Length in kilometers at which a way is cut into a new arc, at the next point of the way |
| `largest_component` | `True` | Keep only the largest part where every node can reach every other, so that no origin or destination lands on a one-way dead end or a fragment cut by the border of the extract |
| `load_intermediate_nodes` | `True` | Keep the shape of each arc, to draw routes |
| `reduce_iterations` | `0` | Number of reduction iterations to perform upon loading (`0` = none, `1` = single pass, `-1` = full convergence) |
| `lazy` | `False` | Defer loading until the geograph is first accessed |


### How the Built-in World Networks Were Built

This is the pipeline of scgraph 3.6.0 that the paper's Appendix B.1 refers to for the built-in OpenStreetMap networks (osmium-tool, a GeoJSON export, Mapshaper and `load_from_geojson`):

**1. Download an OSM PBF file**

[Geofabrik](https://download.geofabrik.de/) provides regional extracts. For the full planet (requires AWS CLI, ~100 GB):

```bash
aws s3 cp s3://osm-pds/planet-latest.osm.pbf .
```

**2. Install Osmium**

```bash
# macOS
brew install osmium-tool
# Ubuntu
sudo apt-get install osmium-tool
```

**3. Extract and filter OSM data for your region**

```bash
# Download a polygon file for your region
curl https://download.geofabrik.de/north-america/us/michigan.poly > michigan.poly

# Extract and filter to highway types
osmium extract -p michigan.poly --overwrite -o michigan.osm.pbf planet-latest.osm.pbf
osmium tags-filter michigan.osm.pbf w/highway=motorway,trunk,primary,motorway_link,trunk_link,primary_link,secondary,secondary_link,tertiary,tertiary_link -t --overwrite -o michigan_roads.osm.pbf
osmium export michigan_roads.osm.pbf -f geojson --overwrite -o michigan_roads.geojson
```

**4. Simplify the GeoJSON**

[Mapshaper](https://mapshaper.org/) repairs line intersections, which is essential for correct routing. Pre-simplify with SCGraph first to speed up Mapshaper:

```bash
npm install -g mapshaper

python -c "from scgraph.helpers.geojson import simplify_geojson; simplify_geojson('michigan_roads.geojson', 'michigan_roads_simple.geojson', precision=4, pct_to_keep=100, min_points=3)"
mapshaper michigan_roads_simple.geojson -simplify 10% -filter-fields -o force michigan_roads_simple.geojson
mapshaper michigan_roads_simple.geojson -snap -clean -o force michigan_roads_simple.geojson
```

**5. Load as a GeoGraph**

```py
from scgraph import GeoGraph

michigan_roads_geograph = GeoGraph.load_from_geojson('michigan_roads_simple.geojson')
```

---

# GeoGraph Serialization

Save and reload GeoGraphs to avoid rebuilding from source data each time.

```py
# Save as a binary network file (fastest reload)
my_geograph.save_as_scgraph('my_geograph.scgraph')
# Or as JSON, also readable by older versions of scgraph
my_geograph.save_as_graphjson('my_geograph.graphjson')

# Reload later
from scgraph import GeoGraph
my_geograph = GeoGraph.load_from_scgraph('my_geograph.scgraph')
my_geograph = GeoGraph.load_from_graphjson('my_geograph.graphjson')
```

The `.scgraph` format is described in [ARCHITECTURE.md](https://github.com/connor-makowski/scgraph/blob/main/ARCHITECTURE.md#7-network-file-format) and in the header of each file. `GeoGraph.get_scgraph_info(filename)` reads that header without loading the network: metadata, sources, modes, number of nodes and arcs, `coordinate_dtype`, `content_sha256`. A GeoGraph loaded from a file keeps that metadata (`geo.metadata`), and `save_as_scgraph` writes it back unless given other `metadata`. It also keeps the path of the file (`geo.scgraph_file`).

**Coordinates.** Coordinates are stored as float64 (exact) or as int32 in 1e-7 degree (OSM's encoding, about 1 cm, 8 bytes less per node). The `coordinate_dtype` parameter of `save_as_scgraph` chooses the form: `"float64"`, `"int32"` or `"auto"` (the default). With `"auto"`, a GeoGraph keeps its own `coordinate_dtype`. It is `"int32"` for a network read from an int32 file or loaded from OSM, OSMnx or GeoJSON (rounded to 7 decimals or fewer), and `"float64"` otherwise.

**Mapped files.** In the C++ build, `load_from_scgraph` maps the file and reads it in place while the GeoGraph is alive. With `modes`, it copies only the arrays whose values are not consecutive in the file. On Windows, such a file can then be neither replaced nor deleted: `save_as_scgraph` onto it raises `PermissionError`.

**Nodes and arc shapes read from the file.** A GeoGraph read from a network file (so also from `load_geograph` and `build_geograph`) reads its node coordinates and its arc shapes from the file:

- `nodes` behaves as a list, but `nodes[i]` is a new list each time. To change a node, assign it: `nodes[i] = [latitude, longitude]`. `json.dumps`, `+`, `*`, `copy()`, `sort()` and ordering comparisons need `list(nodes)` first.
- `intermediate_nodes[i]` is a new read-only mapping `{destination: shape}` each time. Editing a shape changes nothing, and assigning raises a `TypeError`. `copy.copy` and pickling give a list of dicts. `json.dumps` needs `[dict(row) for row in intermediate_nodes]`.

| Method | Description |
|---|---|
| `save_as_geojson(filename)` | Save as GeoJSON (interoperable, larger file) |
| `save_as_graphjson(filename)` | Save as SCGraph JSON (compact, fast reload) |
| `save_as_scgraph(filename)` | Save as a binary network file (fastest reload) |
| `load_geograph(name)` | Load a built-in geograph by name (cached download) |
| `build_geograph(name, region=None)` | Download the source of a reference network, build it and keep it in the cache |
| `list_buildable_geographs()` | List the networks `build_geograph` builds, their credit and what is cached |
| `get_cache_info()` | List what the cache holds on disk, with sizes and build versions |
| `load_from_geojson(filename)` | Load from GeoJSON file |
| `load_from_graphjson(filename)` | Load from SCGraph JSON |
| `load_from_scgraph(filename, modes=None)` | Load from a binary network file (only the nodes of `modes` and the arcs between them, if given) |
| `get_scgraph_info(filename)` | Read what a binary network file holds, without loading it |
| `load_from_osmnx_graph(osmnx_graph)` | Load from OSMNx graph object |
| `load_from_osm(filename)` | Load from an OpenStreetMap file (needs `pip install scgraph[osm]`) |

---

# Custom Graphs and Geographs

## Custom Graph

Use the low-level `Graph` class to work with arbitrary graph data:

```py
from scgraph import Graph

graph = Graph([
    {1: 5, 2: 1},
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6}
])

graph.validate()

output = graph.dijkstra(origin_id=0, destination_id=5)
print(output)  #=> {'path': [0, 2, 1, 3, 5], 'length': 10}

# Reduce the graph (contracts pass-through nodes):
graph.reduce(iterations=1)
# graph.graph stays the original graph; graph.reduced_graph is the reduced one

# Custom algorithm decorator with automated reduced graph support.
# On a reduced graph, a destination inside a contracted chain (and, for
# bidirectional algorithms, an origin) is passed as a {node_id: distance} dict
# of the chain's boundary nodes.
@Graph.algorithm
def custom_solver(self, origin_id: int | dict, destination_id: int | dict) -> dict:
    # Single-sided search on self.search_graph (the reduced graph after reduce())
    # Read it once per call: with the C++ backend, each read is a copy
    ...

@Graph.algorithm(bidirectional=True)
def custom_bidirectional_solver(self, origin_id: int | dict, destination_id: int | dict) -> dict:
    # Bidirectional search on self.search_graph and self.search_inverse_graph
    ...
```

## Custom GeoGraph

Attach latitude/longitude coordinates to your own graph data:

```py
from scgraph import GeoGraph

nodes = [
    [51.5074, -0.1278],   # 0: London
    [48.8566,  2.3522],   # 1: Paris
    [52.5200, 13.4050],   # 2: Berlin
    [41.9028, 12.4964],   # 3: Rome
    [40.4168, -3.7038],   # 4: Madrid
    [38.7223, -9.1393],   # 5: Lisbon
]

graph = [
    {1: 311},                           # London -> Paris
    {0: 311, 2: 878, 3: 1439, 4: 1053},# Paris -> London, Berlin, Rome, Madrid
    {1: 878, 3: 1181},                  # Berlin -> Paris, Rome
    {1: 1439, 2: 1181},                 # Rome -> Paris, Berlin
    {1: 1053, 5: 623},                  # Madrid -> Paris, Lisbon
    {4: 623},                           # Lisbon -> Madrid
]

my_geograph = GeoGraph(nodes=nodes, graph=graph)
my_geograph.validate()
my_geograph.validate_nodes()

# Route Birmingham, England -> Zaragoza, Spain
output = my_geograph.get_shortest_path(
    origin_node={'latitude': 52.4862, 'longitude': -1.8904},
    destination_node={'latitude': 41.6488, 'longitude': -0.8891},
)
print(output)
# {
#     'length': 1799.4323,
#     'coordinate_path': [
#         [52.4862, -1.8904],  # Birmingham (off-graph, auto-connected)
#         [51.5074, -0.1278],  # London
#         [48.8566,  2.3522],  # Paris
#         [40.4168, -3.7038],  # Madrid
#         [41.6488, -0.8891]   # Zaragoza (off-graph, auto-connected)
#     ]
# }
```

## Modifying a GeoGraph

Add or remove nodes and edges dynamically:

```py
# Add a new coordinate node and auto-connect it to the graph
node_id = my_geograph.add_coord_node(
    coord_dict={"latitude": 43.70, "longitude": 7.25},  # Nice, France
    auto_edge=True,
    circuity=1.2,
)

# Add a direct edge between two existing nodes
my_geograph.graph_object.add_edge(origin_id=0, destination_id=5, distance=1850, symmetric=True)

# Remove the last added coordinate node
my_geograph.remove_coord_node()
```

See the [modification notebook](https://colab.research.google.com/github/connor-makowski/scgraph/blob/main/examples/geograph_modifications.ipynb) for more examples.

## Merging Two GeoGraphs

Combine networks (e.g., road + rail) at specified interchange nodes:

```py
road_geograph.merge_with_other_geograph(
    other_geograph=rail_geograph,
    connection_nodes=[[40.71, -74.01], [41.88, -87.63]],  # NYC, Chicago
    circuity_to_current_geograph=1.2,
    circuity_to_other_geograph=1.2,
)
```

---

# GridGraph Usage

`GridGraph` provides shortest path routing on a 2D grid with obstacles and configurable connectivity.

```py
from scgraph import GridGraph

x_size = 20
y_size = 20
# Wall from (10,5) to (10,19)
blocks = [(10, i) for i in range(5, y_size)]

gridGraph = GridGraph(
    x_size=x_size,
    y_size=y_size,
    blocks=blocks,
    add_exterior_walls=True,
    # Default: 8-neighbor connections (4 cardinal + 4 diagonal)
)

output = gridGraph.get_shortest_path(
    origin_node={"x": 2, "y": 10},
    destination_node={"x": 18, "y": 10},
    output_coordinate_path="list_of_lists",  # or 'list_of_dicts' (default)
    cache=True,  # Cache the origin tree for fast repeated queries
)

print(output)
# {'length': 20.9704, 'coordinate_path': [[2, 10], [3, 9], ..., [18, 10]]}
```

Without the wall, the direct path length would be 16; the wall forces a detour to 20.9704.

### Custom Connectivity

Override the default 8-neighbor grid with a custom connection matrix:

```py
# conn_data: list of (x_offset, y_offset, distance) tuples
# 4-neighbor (cardinal only) example:
conn_data = [
    (1, 0, 1.0),   # right
    (-1, 0, 1.0),  # left
    (0, 1, 1.0),   # up
    (0, -1, 1.0),  # down
]

gridGraph = GridGraph(x_size=10, y_size=10, blocks=[], conn_data=conn_data)
```

---

# Contraction Hierarchies

Contraction Hierarchies (CH) provide extremely fast query times after a one-time preprocessing step. They are ideal when running many arbitrary origin-destination queries on the same large graph.

**Performance tradeoff**: Preprocessing is slow (seconds to minutes depending on graph size); longer routes can solve far faster than standard Dijkstra. Note: This will likely still be slower than a cached shortest path tree for repeated queries from the same origin.

## Preprocessing via GeoGraph

```py
from scgraph import GeoGraph

us_freeway_geograph = GeoGraph.load_geograph("us_freeway")

# One-time preprocessing — only needed once per graph
us_freeway_geograph.graph_object.create_contraction_hierarchy(
    # Optionally: pass CH parameters here.
)

# All subsequent queries use the fast CH algorithm
output = us_freeway_geograph.get_shortest_path(
    origin_node={"latitude": 34.05, "longitude": -118.24},  # Los Angeles
    destination_node={"latitude": 40.71, "longitude": -74.01},  # New York
    algorithm_fn='contraction_hierarchy',
)
print(output['length'])
```

A hierarchy can be saved and loaded again instead of being rebuilt. A hierarchy with transit nodes (`algorithm_fn='tnr'`) is built and saved the same way:

```py
from scgraph import CHGraph, TNRGraph

graph = us_freeway_geograph.graph_object
ch = graph.create_contraction_hierarchy()
ch.save_as_chjson("us_freeway.chjson")
ch = CHGraph.load_from_chjson("us_freeway.chjson")
print(ch.get_shortest_path(0, 100)['length'])  # between two node ids

tnr = graph.create_tnr_hierarchy()
tnr.save_as_tnrjson("us_freeway.tnrjson")
tnr = TNRGraph.load_from_tnrjson("us_freeway.tnrjson")
```

---

# Distance Utilities

```py
from scgraph.utils import haversine, cheap_ruler, distance_converter

# Great-circle distance between two lat/lon points
dist_km = haversine([31.23, 121.47], [32.08, -81.09], units='km')

# Fast approximate distance (good near equator)
dist_km = cheap_ruler([31.23, 121.47], [32.08, -81.09], units='km')

# Unit conversion
dist_mi = distance_converter(dist_km, input_units='km', output_units='mi')
```

---

# Logging

The library prints nothing. It reports through Python's `logging` module, on the logger `scgraph`. The parameters `silent` and `show_progress` no longer have an effect: remove them from your calls.

To follow `build_geograph`, `load_from_geojson` and `get_multi_path_geojson`, show the INFO messages:

```py
import logging

logging.basicConfig()  # send log messages to the console
logging.getLogger("scgraph").setLevel(logging.INFO)
```

To see how much work a load or a query did, show the DEBUG messages. Each step of a `GeoGraph` then logs one line:

```py
logging.getLogger("scgraph").setLevel(logging.DEBUG)
marnet = GeoGraph.load_geograph("marnet")
marnet.get_shortest_path(
    {"latitude": 31.23, "longitude": 121.47},
    {"latitude": 32.08, "longitude": -81.09},
)
# DEBUG:scgraph.geograph:read the network file: {'file': '.../marnet.scgraph', 'mapped': True, 'nodes': 11062, 'arcs': 34698, 'duration_ms': 0.205}
# DEBUG:scgraph.geograph:build the snapping index: {'nodes': 11062, 'sorted_for_the_index': False, 'duration_ms': 0.749}
# DEBUG:scgraph.geograph:find the shortest path: {'algorithm': 'bidirectional_buckets', 'distance_units': 'km', 'origin_snap_distance': 64.979, 'destination_snap_distance': 109.566, 'node_scans': 12504}
```

| Step | Values |
|---|---|
| `read the network file` | `file`, `mapped`, `nodes`, `arcs`, `duration_ms` |
| `convert the published network` | `name`, `duration_ms` |
| `build the snapping index` | `nodes`, `sorted_for_the_index`, `duration_ms` |
| `reduce the graph` | `iterations`, `nodes`, `kept_nodes`, `duration_ms` |
| `find the shortest path` | `algorithm`, `distance_units`, `origin_snap_distance`, `destination_snap_distance`, `node_scans` |

- `node_scans` is the size of the search: the number of times it went over the arcs of a node. Dijkstra, bidirectional Dijkstra, A* and the bucket searches report it.
- `origin_snap_distance` and `destination_snap_distance` are the distances from each end of the query to its nearest node of the network, in `distance_units`.
- `kept_nodes` is the number of nodes left after the reduction.
- `mapped` is true when the load maps the file and reads it in place. `sorted_for_the_index` is true when scgraph had to sort a copy of the nodes.

`build_geograph` also logs one line for each step of the OSM pipelines, with its counts and `duration_ms`. A step that removes nodes logs the counts that it received and the counts that it kept (`kept_nodes`, `kept_arcs`).

A program gets the same values as a dict, in the attribute `scgraph` of each log record. The key `step` of the dict names the step. The names of the values may change between versions.

```py
class Collector(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        if hasattr(record, "scgraph"):
            self.records.append(record.scgraph)

collector = Collector()
logging.getLogger("scgraph").addHandler(collector)
logging.getLogger("scgraph").setLevel(logging.DEBUG)
# After a query, collector.records[-1]["node_scans"] is its number of node scans
```

# Examples

### Google Colab Notebooks

- [Getting Started](https://colab.research.google.com/github/connor-makowski/scgraph/blob/main/examples/getting_started.ipynb) — Basic usage, visualization
- [Using OSMNx with SCGraph](https://colab.research.google.com/github/connor-makowski/scgraph/blob/main/examples/osmnx.ipynb) — Load OSM data, solve for time and distance on bike networks
- [Creating A Multi-Path GeoJSON](https://colab.research.google.com/github/connor-makowski/scgraph/blob/main/examples/multi_path_geojson.ipynb) — Export multiple routes as GeoJSON
- [Modifying A GeoGraph](https://colab.research.google.com/github/connor-makowski/scgraph/blob/main/examples/geograph_modifications.ipynb) — Add/remove nodes and edges
- [Routes on a Multimodal Network](https://colab.research.google.com/github/connor-makowski/scgraph/blob/main/examples/multimodal_networks.ipynb) — Load a released network, draw routes by kind of transport, choose the modes
- [Build the Network of a Region](https://colab.research.google.com/github/connor-makowski/scgraph/blob/main/examples/build_a_region.ipynb) — Build Denmark from the newest OpenStreetMap extract, read its sources, compare it with the released network, check it

---

# Development

Contributions start from the `dev` branch. The current developer guide is [`DEVELOPMENT.md` on `dev`](https://github.com/connor-makowski/scgraph/blob/dev/DEVELOPMENT.md). You need Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/connor-makowski/scgraph.git
cd scgraph
git checkout dev
uv sync --extra dev
```

Dev dependencies are declared in `[project.optional-dependencies] dev` in `pyproject.toml`.

| Command | Description |
|---|---|
| `uv run pytest` | Run all tests (about 850 tests, 1 to 2 minutes) |
| `uv run pytest test/NN_*.py` | Run a specific test file |
| `uv run nox` | Run tests (C++ then no-C++) across Python 3.11–3.14 |
| `uv run nox -s tests-3.14` | Run both build variants on a single Python version |
| `uv run utils/bench.py` | Run benchmarks (<30s), output `benchmark.md` |
| `uv run utils/prettify.py` | Remove unused imports (ruff), format (black) |
| `uv run nox -s lint` | Check the code with ruff and the types with pyrefly |

For full developer documentation see [DEVELOPMENT.md](DEVELOPMENT.md). For how scgraph works inside, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Attributions and Thanks

Originally inspired by [searoute](https://github.com/genthalili/searoute-py), including the use of one of their [datasets](https://github.com/genthalili/searoute-py/blob/main/searoute/data/marnet_densified_v2_old.geojson) that has been modified to work with this package.

"""

import logging

from scgraph.graph import NegativeCycleError, PathNotFoundError
from scgraph.graph_reducer import algorithm

try:
    from scgraph.cpp import Graph, CHGraph, TNRGraph

    # Assign python methods to the cpp graph class
    Graph.algorithm = staticmethod(algorithm)
except ImportError:
    from scgraph.graph import Graph
    from scgraph.contraction_hierarchies import CHGraph
    from scgraph.transit_node_routing import TNRGraph

from scgraph.geograph import GeoGraph
from scgraph.grid import GridGraph

# Messages go through logging; the application decides what is shown (Python Logging HOWTO)
logging.getLogger(__name__).addHandler(logging.NullHandler())
