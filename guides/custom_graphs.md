# Your Own Graphs and Grids

This guide shows how to route on your own data: a graph without coordinates, a graph with coordinates, edits and merges of networks, and a grid.

## Custom Graph

Use `Graph` for a graph without coordinates. A graph is a list with one dict for each node. The dict of node `i` gives the nodes that node `i` has an edge to, each with the weight of the edge:

```py
from scgraph import Graph

graph = Graph([
    {1: 5, 2: 1},              # node 0: an edge to node 1 (weight 5) and an edge to node 2 (weight 1)
    {0: 5, 2: 2, 3: 1},
    {0: 1, 1: 2, 3: 4, 4: 8},
    {1: 1, 2: 4, 4: 3, 5: 6},
    {2: 8, 3: 3},
    {3: 6},
])
graph.validate()

output = graph.dijkstra(origin_id=0, destination_id=5)
print(output)  #=> {'path': [0, 2, 1, 3, 5], 'length': 10.0}

# reduce() replaces each chain of nodes with two neighbors by one edge: graph.reduced_graph is this reduced graph, and graph.graph stays the original graph
graph.reduce(iterations=1)
```

Nodes are numbered from zero. An edge has one direction: a two-way link is two edges. Each algorithm of [Choosing an Algorithm](https://github.com/connor-makowski/scgraph/blob/main/guides/routing.md#choosing-an-algorithm) is a method of `Graph`. Call `reduce()` once on a sparse network, before many queries: [Making Many Queries Fast](https://github.com/connor-makowski/scgraph/blob/main/guides/routing.md#making-many-queries-fast) says when it pays.

The decorator `@Graph.algorithm` adds an algorithm of your own, which also runs on a reduced graph:

```py
# On a reduced graph, a destination inside a replaced chain is passed as a dict {node_id: distance}:
# the nodes at the ends of its chain, each with its distance. A bidirectional algorithm gets its origin in the same form.
@Graph.algorithm
def custom_solver(self, origin_id: int | dict, destination_id: int | dict) -> dict:
    # A search in one direction on self.search_graph (the reduced graph after reduce()).
    # Read it once per call: with the C++ backend, each read is a copy
    ...

@Graph.algorithm(bidirectional=True)
def custom_bidirectional_solver(self, origin_id: int | dict, destination_id: int | dict) -> dict:
    # A search in two directions on self.search_graph and self.search_inverse_graph
    ...
```

[ARCHITECTURE.md](https://github.com/connor-makowski/scgraph/blob/main/ARCHITECTURE.md#5-adding-an-algorithm) describes what the function receives and returns.

## Custom GeoGraph

Use `GeoGraph` to attach a point to each node of your own graph. A **geograph** is a `GeoGraph` object, and a point is a `[latitude, longitude]` pair. A query takes any two points: each one snaps to its closest node.

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
    {1: 311},                            # London -> Paris
    {0: 311, 2: 878, 3: 1439, 4: 1053},  # Paris -> London, Berlin, Rome, Madrid
    {1: 878, 3: 1181},                   # Berlin -> Paris, Rome
    {1: 1439, 2: 1181},                  # Rome -> Paris, Berlin
    {1: 1053, 5: 623},                   # Madrid -> Paris, Lisbon
    {4: 623},                            # Lisbon -> Madrid
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
# {'length': 1799.4323, 'metric_totals': {'length': 1799.4323}, 'coordinate_path': [[52.4862, -1.8904], [51.5074, -0.1278], [48.8566, 2.3522], [40.4168, -3.7038], [41.6488, -0.8891]]}
# Birmingham and Zaragoza are off the graph. They snap to London and to Madrid, their closest nodes
```

**Edge classes.**

- The **class** of an edge is its category, such as `motorway`. A geograph holds 255 classes at most.
- `edge_classes` has one dict for each node, like `graph`: the name of the class of each edge, by its destination. An edge that is not in it has no class.
- `classes` has one dict for each class: its name and its edge mode.
- The **edge mode** of a class is the kind of transport of its edges: `road`, `rail`, `sea` or `air`.
- A **metric** gives each edge a weight under a name, such as its hours.
- A **weight per km** is the weight of 1 km of an edge in a metric.
- An **off-graph leg** is the straight line from the origin or the destination of a query to its node. `off_graph_weight_per_km` gives the weight of 1 km of an off-graph leg.

A metric gives a weight per km to an edge mode, and another one to a class:

```py
# Paris (0), Dijon (1) and Lyon (2): a motorway from Paris to Lyon, and a main road through Dijon
france = GeoGraph(
    nodes=[[48.8566, 2.3522], [47.3220, 5.0415], [45.7640, 4.8357]],
    graph=[{1: 263, 2: 465}, {0: 263, 2: 175}, {0: 465, 1: 175}],
    edge_classes=[{1: "main_road", 2: "motorway"}, {0: "main_road", 2: "main_road"}, {0: "motorway", 1: "main_road"}],
    classes=[{"name": "motorway", "edge_mode": "road"}, {"name": "main_road", "edge_mode": "road"}],
)
# Hours: 70 km/h by road, and 110 km/h on a motorway
france.create_metric("hours", weight_per_km={"road": 1 / 70}, off_graph_weight_per_km=1 / 30, class_weight_per_km={"motorway": 1 / 110})

paris, lyon = {"latitude": 48.8566, "longitude": 2.3522}, {"latitude": 45.7640, "longitude": 4.8357}
france.get_shortest_path(origin_node=paris, destination_node=lyon)["length"]  # 438: the main road, through Dijon
france.get_shortest_path(origin_node=paris, destination_node=lyon, metric="hours")["length"]  # 465: the motorway
```

The guide [Networks](https://github.com/connor-makowski/scgraph/blob/main/guides/networks.md#saving-and-loading-files) explains how to save a geograph to a file.

## Modifying a GeoGraph

Add or remove nodes and edges of a geograph. `graph_object` is the `Graph` of a geograph, without the points. The **circuity** multiplies the straight-line distance to give the length of a new edge: `1.2` adds 20 %.

```py
# Add a node at a point, and join it to the graph
node_id = my_geograph.add_coord_node(
    coord_dict={"latitude": 43.70, "longitude": 7.25},  # Nice, France
    auto_edge=True,
    circuity=1.2,
)

# Add an edge between two nodes of the graph, in both directions
my_geograph.graph_object.add_edge(origin_id=0, destination_id=5, distance=1850, symmetric=True)

# Remove the last node that add_coord_node added
my_geograph.remove_coord_node()
```

**An edit of the network removes its metrics: create them again after it.** An edit is a node or an edge that you add or remove, or a merge.

An edit on `graph_object`, as above, removes the metrics at the next call that reads them. Change the edges of `graph_object` only with `add_edge`, `remove_edge`, `add_node` and `remove_node`. If you change the edges in another way, `create_metric` and `save_as_scgraph` raise a `ValueError`.

**The classes stay.** The methods `add_edge`, `add_coord_edge`, `add_coord_node` and `add_haversine_edge` of a geograph take the keyword `edge_class`: a name of `geograph.classes`.

```py
world_sea = GeoGraph.load_geograph("world_sea")
world_sea.create_metric("days", weight_per_km={"sea": 1 / 600}, off_graph_weight_per_km=1 / 100)

# This edit removes the metric `days`, with a warning. The new edges have the class `sea_connector`
world_sea.add_coord_node(coord_dict={"latitude": 43.0, "longitude": 6.0}, edge_class="sea_connector")

# The new edges get the weight per km of `sea`: the edge mode of their class
world_sea.create_metric("days", weight_per_km={"sea": 1 / 600}, off_graph_weight_per_km=1 / 100)
```

| A new edge added by | Its class | Its weight per km in a later metric |
|---|---|---|
| A geograph method, with `edge_class` | That class | The weight of its class |
| A geograph method, without `edge_class` | None: `edge_class` and `edge_mode` are `None` | `off_graph_weight_per_km`, with a dict of `weight_per_km` |
| `graph_object.add_edge`, between the two nodes of an existing edge | The class of the replaced edge | The weight of its class |
| `graph_object.add_edge`, between two other nodes | None | `off_graph_weight_per_km`, with a dict of `weight_per_km` |

With this weight, a route by a metric can take an edge that you add without a class.

`edge_weight_fn` receives `None` as the `edge_class` and the `edge_mode` of an edge without a class. The function must return a weight for this edge. To close the edge, give it `None` in `edge_weights` ([time_cost_co2.md](https://github.com/connor-makowski/scgraph/blob/main/guides/time_cost_co2.md#closing-an-edge-mode-a-class-or-an-edge)).

The [modification notebook](https://colab.research.google.com/github/connor-makowski/scgraph/blob/main/examples/geograph_modifications.ipynb) has more examples.

## Merging Two GeoGraphs

Use `merge_with_other_geograph` to join two networks at the points where a route may change network:

```py
# New York City and Chicago by road; New York City, Chicago and Denver by rail
road_geograph = GeoGraph(nodes=[[40.71, -74.01], [41.88, -87.63]], graph=[{1: 1270}, {0: 1270}])
rail_geograph = GeoGraph(
    nodes=[[40.75, -73.99], [41.88, -87.64], [39.75, -105.00]], graph=[{1: 1540}, {0: 1540, 2: 1670}, {1: 1670}]
)

road_geograph.merge_with_other_geograph(
    other_geograph=rail_geograph,
    connection_nodes=[[40.71, -74.01], [41.88, -87.63]],  # New York City, Chicago
    circuity_to_current_geograph=1.2,
    circuity_to_other_geograph=1.2,
)
```

The merged geograph keeps the lengths and the classes of both geographs. A merge is an edit: it removes the metrics of both geographs, with a warning.

## GridGraph

Use `GridGraph` for the shortest path on a 2D grid with obstacles:

```py
from scgraph import GridGraph

blocks = [(10, i) for i in range(5, 20)]  # a wall from (10, 5) to (10, 19)

# By default, a cell has 8 neighbors: 4 cardinal and 4 diagonal
gridGraph = GridGraph(x_size=20, y_size=20, blocks=blocks, add_exterior_walls=True)

output = gridGraph.get_shortest_path(
    origin_node={"x": 2, "y": 10},
    destination_node={"x": 18, "y": 10},
    output_coordinate_path="list_of_lists",  # or 'list_of_dicts' (default)
    cache=True,  # Cache the origin tree for fast repeated queries
)

print(output)
# {'length': 20.9704, 'coordinate_path': [[2, 10], [3, 9], ..., [18, 10]]}
```

The wall makes the path longer: 20.9704 in place of 16.

`conn_data` replaces the 8 default moves of a cell by moves of your own:

```py
# conn_data: a list of (x_offset, y_offset, distance) tuples. Here 4 neighbors: right, left, up, down
conn_data = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0)]
gridGraph = GridGraph(x_size=10, y_size=10, blocks=[], conn_data=conn_data)
```
