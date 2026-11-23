# Migrating from 3.6 to 4.0

This page lists what release 4.0 changes for a user of scgraph 3.6, and what to write in place of each call.

| What changes | What to do |
|---|---|
| The seven networks of 3.6 (`marnet`, `us_freeway`, ...) are deprecated. They still load, with the same results and a `DeprecationWarning` | Load the network that replaces it, in the table below. Its lengths differ, because its data is newer |
| A network loaded by `load_geograph` numbers its nodes in another order | `geograph.source_node_ids[i]` gives the id that node `i` had in 3.6 |
| `GeoGraph.get_shortest_path` takes its options by keyword | Write `get_shortest_path(origin, destination, output_units="mi")`, not `get_shortest_path(origin, destination, "mi")` |
| `CHGraph`, `TNRGraph`, `create_contraction_hierarchy` and `create_tnr_hierarchy` take their options by keyword, with the same names in both builds | Write `TNRGraph(graph, num_transit_nodes=100)` |
| `ch_graph_kwargs` and `tnr_graph_kwargs` have no effect and give a `DeprecationWarning` | Pass `settled_limit` and `heuristic_fn` |
| A wrong argument raises a `ValueError`, not an `AssertionError` | Catch `ValueError` |
| `reduce()` runs until no pass-through node is left (`iterations=-1`). Release 3.6 ran one pass | Pass `iterations=1` for one pass. Route lengths are the same |
| `'kdclosest'` and `'kdquadrant'` are deprecated values of `node_addition_type` | Use `'closest'` and `'quadrant'`, which give the same results |
| `geograph_url` is deprecated. Another URL than the default still loads `<name>.graphjson` from that URL, with a `DeprecationWarning` | Load your own file with `load_from_graphjson` or `load_from_scgraph` |
| scgraph prints nothing. The parameters `silent` and `show_progress` have no effect and give a `DeprecationWarning` | Remove them from your calls. Show the messages with `logging`: see [Logging](https://github.com/connor-makowski/scgraph/blob/main/guides/routing.md#logging) |
| In pure Python, `get_path_weight` raises `ValueError` for a missing edge, and `bmssp` raises `PathNotFoundError` when no path exists | These are the exceptions of the C++ build |
| A **metric** gives each edge a weight under a name, such as its seconds. `load_from_osmnx_graph` gives the metric `travel_time` to a geograph, when every edge of the OSMnx graph has a `travel_time`. Each result of this geograph has one more key, `metric_totals` | Read the travel time of a route in `metric_totals`. With `weight_key="length"`, `geograph.remove_metric("travel_time")` restores the result keys of 3.6 |
| With `load_from_osmnx_graph(graph, weight_key="travel_time")`, `route["length"]` was the seconds of the fastest route. It is now the km of this route. Without `off_graph_travel_speed`, release 3.6 added no time for the straight line from the origin or the destination to its node. Release 4.0 adds 240 seconds for each km of this line | Write `route["metric_totals"]["travel_time"]` for the seconds, in place of `route["length"]`. `get_path_weight` and `distance_matrix` still give seconds on this geograph |

Release 5.0 removes what 4.0 deprecates.

## Deprecated Networks of scgraph 3.6.0

These seven networks of scgraph 3.6.0 are deprecated. `load_geograph` still loads them, with the same results as 3.6.0 and a `DeprecationWarning`. scgraph 5.0 removes them. All seven networks measure distances in kilometers.

A **released network** replaces each one, with newer data: the maintainers of scgraph build it and publish it. Its results differ, because the data differ. In `GeoGraph.list_geographs()`, the key `superseded_by` of each one names its replacement.

| Name | Use instead | Description | Attribution |
|---|---|---|---|
| `marnet` | `GeoGraph.load_geograph("world_sea")` | Maritime network | [searoute](https://github.com/genthalili/searoute-py) · [Map](https://raw.githubusercontent.com/connor-makowski/scgraph/main/static/marnet.png) |
| `oak_ridge_maritime` | `GeoGraph.load_geograph("world_sea")` | Maritime network (Oak Ridge National Laboratory) | [ORNL](https://www.ornl.gov/) / [Geocommons](http://geocommons.com/datasets?id=25) · [Map](https://raw.githubusercontent.com/connor-makowski/scgraph/main/static/oak_ridge_maritime.png) |
| `north_america_rail` | `GeoGraph.load_geograph("north_america", node_modes=["rail"])` | Class 1 rail network for North America | [USDOT ArcGIS](https://geodata.bts.gov/datasets/usdot::north-american-rail-network-lines-class-i-freight-railroads-view/about) · [Map](https://raw.githubusercontent.com/connor-makowski/scgraph/main/static/north_america_rail.png) |
| `us_freeway` | `GeoGraph.load_geograph("north_america", node_modes=["road"])` | Freeway network for the United States | [USDOT ArcGIS](https://hub.arcgis.com/datasets/esri::usa-freeway-system-over-1500k/about) · [Map](https://raw.githubusercontent.com/connor-makowski/scgraph/main/static/us_freeway.png) |
| `world_highways_and_marnet` | `GeoGraph.load_geograph("world_multimodal", node_modes=["road", "sea", "port"])` | World highway network merged with the maritime network | [OpenStreetMap](https://www.openstreetmap.org/) / [searoute](https://github.com/genthalili/searoute-py) |
| `world_highways` | `GeoGraph.load_geograph("world_multimodal", node_modes=["road"])` | World highway network | [OpenStreetMap](https://www.openstreetmap.org/) |
| `world_railways` | `GeoGraph.load_geograph("world_rail")` | World railway network | [OpenStreetMap](https://www.openstreetmap.org/) |

**Where a route starts.** A **query point** is the origin or the destination of a query. A query point **snaps** to the node where its route starts or ends. The **node mode** of a node is the kind of place where the node is, such as `road`, `sea` or `port`.

On `world_highways_and_marnet`, a query point snaps to its closest node, on a road or on a sea lane. On the replacement, a query point snaps to its closest road node. To snap to the closest node of any node mode, as before, pass `snap_to_node_modes=["road", "sea", "port"]` to `get_shortest_path`.

**The files of these networks.** The first load downloads `<name>.graphjson` into the cache, and converts it into a binary network file, `<name>.scgraph`, beside it. Later loads read the binary file, which is much faster. The `.graphjson` is kept. The conversion changes three things:

- **Node ids**: Nodes are numbered along a Hilbert curve, so that nodes close on the globe get close ids. Route lengths do not change. When two routes have exactly the same length, the other one may be returned.
- **Coordinates**: Coordinates are stored to 1e-7 degree (about 1 cm). A few published ports have 9 decimals.
- **Ids of scgraph 3.6.0**: `source_node_ids[i]` is the id that node `i` has in the `.graphjson`, so `[geo.source_node_ids[i] for i in path]` translates a path. `load_from_graphjson` on the cached `.graphjson` keeps the old numbering.
