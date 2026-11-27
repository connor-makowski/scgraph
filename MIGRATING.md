# Migrating from 3.6 to 4.0

This page lists what release 4.0 changes for a user of scgraph 3.6, and what to write in place of each call.

| What changes | What to do |
|---|---|
| The seven networks of 3.6 (`marnet`, `us_freeway`, ...) are deprecated. They still load, with the same results and a `DeprecationWarning` | Load the network that replaces it, in the table below. Its lengths differ, because its data is newer |
| `load_geograph` numbers the nodes in another order. Of two routes with the same length, it can return the other one | `geograph.external_node_ids[i]` gives the id that node `i` had in 3.6 |
| The first load of a deprecated network converts its `<name>.graphjson` file into a faster `<name>.scgraph` file, in the cache | To keep the node ids of 3.6, call `load_from_graphjson` on the `<name>.graphjson` file of the cache |
| The `.scgraph` file rounds the coordinates of a deprecated network to 1e-7 degree | Nothing: a node moves by less than 1 cm |
| A route on `world_highways_and_marnet` starts and ends at the closest node. On its replacement, it uses the closest road node | Pass `snap_to_node_modes=["road", "sea", "port"]` to `get_shortest_path` to use the closest node of these node modes |
| `GeoGraph.get_shortest_path` takes its options by keyword | Write `get_shortest_path(origin, destination, output_units="mi")`, not `get_shortest_path(origin, destination, "mi")` |
| `CHGraph`, `TNRGraph`, `create_contraction_hierarchy` and `create_tnr_hierarchy` take their options by keyword, with the same names in both builds | Write `TNRGraph(graph, num_transit_nodes=100)` |
| `ch_graph_kwargs` and `tnr_graph_kwargs` have no effect and give a `DeprecationWarning` | Pass `settled_limit` and `heuristic_fn` |
| In pure Python, a wrong argument no longer raises an `AssertionError`. A wrong value raises `ValueError`, and a wrong type raises `TypeError`. `validate` raises `RuntimeError` for a graph that is not connected, and `remove_node` raises it for a graph with no node. The C++ build of 3.6 raised these types | Catch the type of the fault that you expect, not `AssertionError` |
| Both builds now refuse the same wrong origin or destination of an algorithm. A node id or a start distance of a wrong type raises `TypeError`: in pure Python, 3.6 raised `ValueError`. A list raises `TypeError`: with the C++ extension, 3.6 read it as a set | Give an origin as an int, as a set of ints, or as a dict of start distances |
| In pure Python, a search on a reduced graph no longer accepts a list or a tuple as an origin or a destination. It raises `TypeError`, as on a graph before `reduce()` and as with the C++ extension | Give a set of ints in place of the list |
| With the C++ extension, an origin given as a dict keeps its start distances when they are ints (`{0: 5}`). Release 3.6 read this dict as the set of its keys | Nothing: the result is now the one of the pure-Python build |
| With the C++ extension, a search reads the edges of a node in the order of its dict, as in pure Python. So `bidirectional_dijkstra`, `dijkstra_buckets` and `bidirectional_buckets` can return the other one of two paths with the same length | Nothing: the length is the same, and the path is the one of the pure-Python build |
| `Graph.get`, and `add_edge` and `remove_edge` of `Graph` and of `GeoGraph`, raise `ValueError` for a node id that is not in the graph. With the C++ extension, 3.6 raised `IndexError`. In pure Python, `add_edge` and `remove_edge` raised `AssertionError` | Catch `ValueError` |
| `Graph.contraction_hierarchy` and `Graph.tnr` raise `ValueError` for a node id that is not in the graph. With the C++ extension, 3.6 stopped the interpreter. In pure Python, 3.6 raised `IndexError`, or returned a wrong path for a negative id | Catch `ValueError` |
| In pure Python, an assignment to `reduced_graph_connections` or `reduced_inverse_graph_connections` raises `AttributeError`, as with the C++ extension in 3.6 | Nothing replaces the assignment: `reduce()` computes both |
| `GeoGraph` raises `ValueError` for a `geograph_units` other than `km`, `m`, `mi` and `ft`. Release 3.6 built such a geograph. Its queries then raised `AssertionError`, and its methods `haversine` and `cheap_ruler` gave km | Give one of the four units |
| `reduce` raises `ValueError` for `iterations` below -1, and `add_edge` raises `ValueError` for a distance that is NaN. Release 3.6 accepted both | Pass `iterations=-1` to reduce until no pass-through node is left |
| `GeoGraph.remove_node` removes the point of the node from `nodes` too | Do not remove the point yourself after the call |
| After `reduce()`, `Graph.graph` and `Graph.inverse_graph` are the original graph in both builds. In 3.6, the pure-Python build gave the reduced graph | A custom algorithm reads `search_graph` and `search_inverse_graph` |
| `GridGraph.format_coordinate` names its parameters `coordinate_dict` and `output_coordinate_path`. Release 3.6 had `cooinate_dict` and `output_coorinate_path` | A call by position does not change. A call by keyword uses the new names |
| `load_from_geojson` weighs each edge by its great-circle length, and numbers the nodes along a Hilbert curve. So the lengths differ from those of 3.6 for the same file | Nothing for the lengths. `geograph.external_node_ids[i]` gives the id that node `i` had in 3.6 |
| The internal names of the form `__name__` are now `_name`: `__graph__` is `_graph`, and `__input_check__` is `_input_check`. These 40 attributes and methods were never public. The two aliases `__run_with_reduced__` and `__dijkstra_on_graph__` of `GraphReducer` are removed | In a code that reads one of them, write the new name. Call `run_with_reduced` and `dijkstra_on_graph` in place of the two aliases |
| Six functions of `scgraph.utils` are deprecated and give a `DeprecationWarning`: `print_console`, `validate`, `time_test`, `cpp_check`, `adjacency_dict_to_list_tuples` and `adjacency_list_tuples_to_dict`. `print_console`, `validate`, `time_test` and `cpp_check` write their message with `logging`, not with `print` | Use `logging` in place of `print_console`, and `has_cpp()` in place of `cpp_check`. Nothing replaces `validate`, `time_test` and the two `adjacency_*` functions: copy the one that you use into your code |
| `reduce()` runs until no pass-through node is left (`iterations=-1`). Release 3.6 ran one pass | Pass `iterations=1` for one pass. Route lengths are the same |
| `'kdclosest'` and `'kdquadrant'` are deprecated values of `node_addition_type` | Use `'closest'` and `'quadrant'`, which give the same results |
| `geograph_url` is deprecated. Another URL than the default still loads `<name>.graphjson` from that URL, with a `DeprecationWarning` | Load your own file with `load_from_graphjson` or `load_from_scgraph` |
| scgraph prints nothing. The parameters `silent` and `show_progress` have no effect and give a `DeprecationWarning` | Remove them from your calls. Show the messages with `logging`: see [Logging](https://github.com/connor-makowski/scgraph/blob/main/guides/routing.md#logging) |
| In pure Python, `get_path_weight` raises `ValueError` for a missing edge, and `bmssp` raises `PathNotFoundError` when no path exists | These are the exceptions of the C++ build |
| Each result of `get_shortest_path` has one more key, `metric_totals`: the total of each metric along the route | Nothing, unless your code compares a whole result |
| `length_only` is deprecated, and gives a `DeprecationWarning` | Write `totals_only=True`, and read `metric_totals["length"]` |
| A length in miles or in feet moves by 0.006 % at most. A length in km does not move | Nothing |
| With `load_from_osmnx_graph(graph, weight_key="travel_time")`, `route["length"]` is now the km of the fastest route, not its seconds | Read the seconds in `route["metric_totals"]["travel_time"]`. `get_path_weight` and `distance_matrix` still give seconds on this geograph |
| With `load_from_osmnx_graph(graph, weight_key="travel_time")`, `length_only=True` raises a `ValueError` | Write `totals_only=True`, and read `metric_totals["travel_time"]` |
| After an edit of a geograph of `load_from_osmnx_graph(graph, weight_key="travel_time")`, a query without `metric` raises a `ValueError` | Pass `metric="length"`: the query gives the shortest route |
| Without `off_graph_travel_speed`, `travel_time` adds 240 seconds for each km off the graph. Release 3.6 added no time | Pass `off_graph_travel_speed`, in km/h, to choose another speed |

Release 5.0 removes what 4.0 deprecates, at the earliest.

## Deprecated Networks of scgraph 3.6.0

`load_geograph` still loads these seven networks, with a `DeprecationWarning`. In `GeoGraph.list_geographs()`, the key `superseded_by` of each one names its replacement.

| Name | Use instead | Description | Attribution |
|---|---|---|---|
| `marnet` | `GeoGraph.load_geograph("world_sea")` | Maritime network | [searoute](https://github.com/genthalili/searoute-py) · [Map](https://raw.githubusercontent.com/connor-makowski/scgraph/main/static/marnet.png) |
| `oak_ridge_maritime` | `GeoGraph.load_geograph("world_sea")` | Maritime network (Oak Ridge National Laboratory) | [ORNL](https://www.ornl.gov/) / [Geocommons](http://geocommons.com/datasets?id=25) · [Map](https://raw.githubusercontent.com/connor-makowski/scgraph/main/static/oak_ridge_maritime.png) |
| `north_america_rail` | `GeoGraph.load_geograph("north_america", node_modes=["rail"])` | Class 1 rail network for North America | [USDOT ArcGIS](https://geodata.bts.gov/datasets/usdot::north-american-rail-network-lines-class-i-freight-railroads-view/about) · [Map](https://raw.githubusercontent.com/connor-makowski/scgraph/main/static/north_america_rail.png) |
| `us_freeway` | `GeoGraph.load_geograph("north_america", node_modes=["road"])` | Freeway network for the United States | [USDOT ArcGIS](https://hub.arcgis.com/datasets/esri::usa-freeway-system-over-1500k/about) · [Map](https://raw.githubusercontent.com/connor-makowski/scgraph/main/static/us_freeway.png) |
| `world_highways_and_marnet` | `GeoGraph.load_geograph("world_multimodal", node_modes=["road", "sea", "port"])` | World highway network merged with the maritime network | [OpenStreetMap](https://www.openstreetmap.org/) / [searoute](https://github.com/genthalili/searoute-py) |
| `world_highways` | `GeoGraph.load_geograph("world_multimodal", node_modes=["road"])` | World highway network | [OpenStreetMap](https://www.openstreetmap.org/) |
| `world_railways` | `GeoGraph.load_geograph("world_rail")` | World railway network | [OpenStreetMap](https://www.openstreetmap.org/) |
