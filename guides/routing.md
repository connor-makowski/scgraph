# Routing on a Network

This guide is for a user who routes on a network that exists, such as a network that scgraph publishes. After it, you can choose the options of a query, read its result, and make many queries fast.

The guide [Networks](https://github.com/connor-makowski/scgraph/blob/main/guides/networks.md) says how to get a network. The [API documentation](https://connor-makowski.github.io/scgraph/scgraph.html) gives every parameter of each method.

## Routing Options and Result Keys

A `GeoGraph` is a graph with a point for each node. `get_shortest_path` takes two points anywhere on the globe, and returns the shortest route between them:

```py
from scgraph import GeoGraph

world_sea = GeoGraph.load_geograph("world_sea")

route = world_sea.get_shortest_path(
    origin_node={"latitude": 31.23, "longitude": 121.47},       # Shanghai
    destination_node={"latitude": 32.08, "longitude": -81.09},  # Savannah, GA
    output_units="mi",  # km (the default), m, mi or ft
    output_path=True,
)
route["length"]           # the miles of the route
route["coordinate_path"]  # [[31.23, 121.47], ..., [32.08, -81.09]]
route["path"]             # the node ids of the route
```

The result is a dictionary. It always has these two keys:

- `length`: the length of the route, in `output_units`.
- `coordinate_path`: the points of the route, as `[latitude, longitude]` pairs. `output_coordinate_path` chooses another form.

A query can add these keys:

- `path`, with `output_path=True`: the node ids of the route.
- `metric_totals`. A **metric** gives each edge a weight under a name, such as its hours. When the geograph has a metric other than `length`, `metric_totals` holds the sum of these weights along the route, for each metric.
- `legs` and `transfers`, with `output_legs=True`. A **leg** is a part of a route by road, by rail, by sea or by air. A **transfer** is a node where the route goes from one of these four to another, such as a port.

The guide [Routes by Time, Cost and CO2](https://github.com/connor-makowski/scgraph/blob/main/guides/time_cost_co2.md) shows metrics, legs and transfers. To route by a metric, pass `metric=name` with any option of this guide.

## Where a Query Point Snaps

A **query point** is the origin or the destination of a query. `get_shortest_path` joins each query point to a node of the network: the point **snaps** to this node. The route starts or ends at this node. An **off-graph leg** is the straight line from a query point to its node.

A **released network** is a network that the maintainers of scgraph build and publish, such as `oceania`. Each of its nodes has a **node mode**, which says where the node is: `road`, `rail`, `sea`, `port`, `airport` or `rail_terminal`. `geograph.node_modes` gives the node modes of a geograph. In a released network with roads, a query point snaps to its closest road node, for every metric. A point at sea snaps to a road node too, however far. `node_addition_modes` lists the node modes that a query point may snap to:

```py
oceania = GeoGraph.load_geograph("oceania")

# Two points at sea: each one snaps to its closest sea node or port
route = oceania.get_shortest_path(
    origin_node={"latitude": -34.0, "longitude": 152.0},       # off Sydney
    destination_node={"latitude": -41.5, "longitude": 174.5},  # in Cook Strait
    node_addition_modes=["sea", "port"],
)
```

With `node_addition_modes=["road", "rail"]`, a route may also start or end at a rail node. A node mode that the geograph does not have raises a `ValueError`.

The default is `None`. A query point then snaps to the node modes that the network file names, in `geograph.default_node_addition_modes`. For a released network with roads, they are the roads. The point also snaps to a node without a named node mode, such as a node added by `add_coord_node` without `node_mode=`. A geograph without `default_node_addition_modes` snaps a query point to every node.

`node_addition_type` chooses the nodes that the origin is joined to, among the nodes of these node modes. `destination_node_addition_type` does the same for the destination:

- `'closest'`, the default: the closest node.
- `'quadrant'`: the closest node in each of the four quadrants around the point (NE, NW, SE, SW).
- `'all'`: every node within `node_addition_lat_lon_bound` degrees of the point. The default bound is `'auto'`.

[ARCHITECTURE.md](https://github.com/connor-makowski/scgraph/blob/main/ARCHITECTURE.md#3-answering-a-geographic-query) explains how a search weighs the off-graph legs when a point has several nodes.

## Choosing an Algorithm

`algorithm_fn` names the algorithm of a query. The default, `'bidirectional_buckets'`, suits a single query on a geographic network. `n` is the number of nodes, `m` the number of edges, and `W` the number of buckets that the search goes over.

| `algorithm_fn` | Use it for | Time |
|---|---|---|
| `'bidirectional_buckets'` | A single query, with weights of zero or more. Bidirectional Dijkstra with buckets (Dial's algorithm) | O(n+m+W) |
| `'dijkstra'` | A single query, with weights of zero or more. Standard Dijkstra | O((n+m) log n) |
| `'bidirectional_dijkstra'` | A single query. The search runs from the origin and from the destination at the same time | O((n+m) log n) |
| `'dijkstra_buckets'` | A search in one direction, with weights of zero or more. The width of a bucket comes from the finite weights of the graph | O(n+m+W) |
| `'a_star'` | A single query with a good heuristic ([A* Heuristics](#a-heuristics)) | O((n+m) log n) |
| `'dijkstra_negative'` | A graph with negative weights. Dijkstra with cycle detection | O(n·m) |
| `'bellman_ford'` | A graph with negative weights. Slower than Dijkstra | O(n·m) |
| `'bmssp'` | The [BMSSP algorithm](https://arxiv.org/pdf/2504.17033) ([implementation](https://github.com/connor-makowski/bmsspy)) | O(m log^(2/3)(n)) |
| `'cached_shortest_path'` | Many queries from one origin: it keeps the shortest path tree of the origin | O((n+m) log n) first, O(1) after |
| `'contraction_hierarchy'` | Many queries between any points of a fixed graph, after a preprocessing | O(k log k) per query |
| `'tnr'` | The same need, for long routes: [Transit Node Routing](https://en.wikipedia.org/wiki/Transit_node_routing) | O(1) per long query |

`algorithm_fn` also takes a function of your own that has the signature of a `Graph` method. `algorithm_kwargs` passes keyword arguments to the algorithm.

In every algorithm, a weight of infinity (`float("inf")`) closes its edge: no path takes this edge. When every path between two nodes needs a closed edge, the query raises `PathNotFoundError`.

## Making Many Queries Fast

One query needs no preparation. For many queries, choose a way by the form of your queries:

| Your queries | Way | What it costs |
|---|---|---|
| Many destinations from one origin | `algorithm_fn='cached_shortest_path'` | The first query from an origin computes the tree of this origin |
| Every pair of a list of places | `distance_matrix` | One tree for each place |
| Any queries on a sparse network: roads, railways, sea lanes | `reduce()`, once | One pass over the graph. The lengths stay exact |
| Very many queries between any points of a large network | A hierarchy: `'contraction_hierarchy'` or `'tnr'` | A preprocessing of seconds to minutes. An edit of the graph removes the hierarchy |
| A program that may never query one of its networks | `lazy=True` at the load | Nothing before the first use |

### Cached Queries from One Origin

Use `cached_shortest_path` for many queries from the same origin, for example from one distribution center to many customers. The first call computes the shortest path tree of the origin, and keeps it. A later call from the same origin reads the tree:

```py
shanghai = {"latitude": 31.23, "longitude": 121.47}

# The first call computes the tree: about the cost of one Dijkstra search that does not stop early
to_savannah = world_sea.get_shortest_path(
    origin_node=shanghai,
    destination_node={"latitude": 32.08, "longitude": -81.09},
    algorithm_fn="cached_shortest_path",
)
# A later call from the same origin reads the tree
to_london = world_sea.get_shortest_path(
    origin_node=shanghai,
    destination_node={"latitude": 51.50, "longitude": -0.13},
    algorithm_fn="cached_shortest_path",
)
```

### Distance Matrix

Use `distance_matrix` for the distances between every pair of a list of places. It computes one shortest path tree for each place:

```py
north_america = GeoGraph.load_geograph("north_america", node_modes=["road"])

cities = [
    {"latitude": 34.0522, "longitude": -118.2437},  # Los Angeles
    {"latitude": 40.7128, "longitude": -74.0060},   # New York City
    {"latitude": 41.8781, "longitude": -87.6298},   # Chicago
    {"latitude": 29.7604, "longitude": -95.3698},   # Houston
]

matrix = north_america.distance_matrix(cities, output_units="km")
matrix[0][1]  # the km from Los Angeles to New York City
```

`output_units` takes `km`, `m`, `mi` or `ft`. The two directions of a pair can differ a little: a one-way road is followed in its direction. A pair without a route has the distance `None`.

The **total** of a metric along a route is the sum of the weights of its edges. With a metric, the matrix holds the totals of this metric. `output_metric` names another metric to read along the same routes:

```py
north_america.create_metric("hours", weight_per_km={"road": 1 / 80, "off_graph": 1 / 30})
hours = north_america.distance_matrix(cities, metric="hours")
km_of_the_fastest_routes = north_america.distance_matrix(cities, metric="hours", output_metric="length")
```

### Graph Reduction

Use `reduce()` on a sparse network, such as roads, railways or sea lanes. Such a network has long chains of nodes with only two neighbors. The reduction replaces each chain by one edge. A search then visits fewer nodes, and every route keeps its exact length and its full path:

```py
north_america.reduce()

# Every algorithm now searches the reduced graph, and returns the path on the original nodes
route = north_america.get_shortest_path(
    origin_node={"latitude": 34.05, "longitude": -118.24},      # Los Angeles
    destination_node={"latitude": 40.71, "longitude": -74.01},  # New York City
    algorithm_fn="bidirectional_dijkstra",
)
```

`reduce()` repeats its passes until a pass reduces nothing. Pass `iterations=1` for a single pass. It also reduces the graph of each metric of the geograph. A loader does the same at the load with `reduce_iterations=-1`. [ARCHITECTURE.md](https://github.com/connor-makowski/scgraph/blob/main/ARCHITECTURE.md#4-graph-reduction) explains the reduction.

### Lazy Loading

Use `lazy=True` when a program names several networks and may not use them all. The loader then returns at once, and downloads nothing:

```py
europe = GeoGraph.load_geograph("europe", lazy=True)  # a LazyGeoGraph: nothing is loaded yet

europe.load()  # loads the network now; without this call, the first query loads it
```

### Hierarchies: CH and TNR

Use a contraction hierarchy (CH) for very many queries between any points of one large graph. The preprocessing runs once and is slow: seconds to minutes, by the size of the graph. A long route is then far faster than with Dijkstra. For many queries from one origin, a cached tree is still faster.

```py
oceania_roads = GeoGraph.load_geograph("oceania", node_modes=["road"])

# The preprocessing: once for each graph. It takes its options by keyword (settled_limit, heuristic_fn)
oceania_roads.graph_object.create_contraction_hierarchy()

route = oceania_roads.get_shortest_path(
    origin_node={"latitude": -33.87, "longitude": 151.21},       # Sydney
    destination_node={"latitude": -31.95, "longitude": 115.86},  # Perth
    algorithm_fn="contraction_hierarchy",
)
```

A hierarchy belongs to one metric. `oceania_roads.graph_object` is the graph of the lengths. For another metric, build the hierarchy on `oceania_roads.get_graph_object(metric)`, and pass `metric` to `get_shortest_path`. A metric that is created again has a new graph, without a hierarchy.

A hierarchy can be saved, and loaded again in place of a new preprocessing. A hierarchy with transit nodes (`algorithm_fn='tnr'`) is built and saved the same way:

```py
from scgraph import CHGraph, TNRGraph

graph = oceania_roads.graph_object
ch = graph.create_contraction_hierarchy()
ch.save_as_chjson("oceania_roads.chjson")
ch = CHGraph.load_from_chjson("oceania_roads.chjson")
# A hierarchy answers a query between two node ids: ch.get_shortest_path(origin_id, destination_id)

tnr = graph.create_tnr_hierarchy()
tnr.save_as_tnrjson("oceania_roads.tnrjson")
tnr = TNRGraph.load_from_tnrjson("oceania_roads.tnrjson")
```

[ARCHITECTURE.md](https://github.com/connor-makowski/scgraph/blob/main/ARCHITECTURE.md#trees-and-hierarchies) explains how a tree and a hierarchy answer a query.

## A* Heuristics

A* needs a heuristic: a function that gives a lower bound of the distance left to the destination. A geograph has two of them, in its own units (`geograph_units`):

```py
route = world_sea.get_shortest_path(
    origin_node={"latitude": 31.23, "longitude": 121.47},
    destination_node={"latitude": 32.08, "longitude": -81.09},
    algorithm_fn="a_star",
    algorithm_kwargs={"heuristic_fn": world_sea.haversine},
)
```

- `geograph.haversine`: the great-circle distance. It is exact, and the C++ build computes it inside the search.
- `geograph.cheap_ruler`: a fast approximate distance (the method of Mapbox).

A* returns the shortest path when the heuristic never exceeds the real distance left to the destination. With a metric other than `length`, scgraph scales its two heuristics to the weights of the metric. It does not scale a function of your own. Such a function must never exceed the total of the metric left to the destination. [ARCHITECTURE.md](https://github.com/connor-makowski/scgraph/blob/main/ARCHITECTURE.md#3-shortest-path-search) gives the rule of the scale, and the case where A* searches as Dijkstra does.

## Distance Utilities

`scgraph.utils` computes a distance between two points without a network:

```py
from scgraph.utils import haversine, cheap_ruler, distance_converter

dist_km = haversine([31.23, 121.47], [32.08, -81.09], units="km")    # great-circle distance
dist_km = cheap_ruler([31.23, 121.47], [32.08, -81.09], units="km")  # fast and approximate
dist_mi = distance_converter(dist_km, input_units="km", output_units="mi")
```

## Logging

scgraph prints nothing. It reports through the `logging` module of Python, on the logger `scgraph`.

Show the INFO messages to follow a long call. These calls are the first load of a released network, `build_geograph`, `load_from_geojson` and `get_multi_path_geojson`. A download then logs its progress at each tenth of its size:

```py
import logging

logging.basicConfig()  # send log messages to the console
logging.getLogger("scgraph").setLevel(logging.INFO)
```

Show the DEBUG messages to see how much work a load or a query did. Each step of a `GeoGraph` then logs one line:

```py
logging.getLogger("scgraph").setLevel(logging.DEBUG)
world_sea = GeoGraph.load_geograph("world_sea")
world_sea.get_shortest_path({"latitude": 31.23, "longitude": 121.47}, {"latitude": 32.08, "longitude": -81.09})
# DEBUG:scgraph.geograph:read the network file: {'file': '.../world_sea.scgraph', 'mapped': True, 'nodes': ..., ...}
# DEBUG:scgraph.geograph:build the snapping index: {'nodes': ..., 'sorted_for_the_index': False, 'duration_ms': ...}
# DEBUG:scgraph.geograph:find the shortest path: {'algorithm': 'bidirectional_buckets', 'node_scans': ..., ...}
```

| Step | Values |
|---|---|
| `read the network file` | `file`, `mapped`, `nodes`, `edges`, `duration_ms` |
| `convert the published network` | `name`, `duration_ms` |
| `build the snapping index` | `nodes`, `node_mode` (the name of the node mode, only for the index of one node mode), `sorted_for_the_index`, `duration_ms` |
| `reduce the graph` | `iterations`, `nodes`, `kept_nodes`, `duration_ms` |
| `find the shortest path` | `algorithm`, `distance_units`, `origin_snap_distance`, `destination_snap_distance`, `node_scans` |

- `node_scans` is the size of the search: the number of times it went over the edges of a node. Dijkstra, bidirectional Dijkstra, A* and the bucket searches report it.
- `origin_snap_distance` and `destination_snap_distance` are the distances from each query point to the closest node that it snaps to, in `distance_units`.
- `kept_nodes` is the number of nodes left after the reduction.
- `mapped` is true when the load maps the file and reads it in place. `sorted_for_the_index` is true when scgraph had to sort a copy of the nodes.

`build_geograph` also logs one line for each step of the OSM pipelines, with its counts and `duration_ms`. A step that removes nodes logs the counts that it received and the counts that it kept (`kept_nodes`, `kept_edges`).

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
# After a query, collector.records[-1]["node_scans"] is its number of node scans
```
