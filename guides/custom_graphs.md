# Your Own Graphs and Grids

This guide is for a user with data of their own. After it, you can route on your own graph, give it coordinates, edit or merge geographs, and route on a grid.

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

Nodes are numbered from zero. An edge has one direction: a two-way link is two edges. The routing guide lists the algorithms in [Choosing an Algorithm](https://github.com/connor-makowski/scgraph/blob/main/guides/routing.md#choosing-an-algorithm). Each one is a method of `Graph`.

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

Use `GeoGraph` to attach a point to each node of your own graph. A point is a `[latitude, longitude]` pair. A query then takes any two points: each one is joined to its closest node.

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
# {'length': 1799.4323, 'coordinate_path': [[52.4862, -1.8904], [51.5074, -0.1278], [48.8566, 2.3522], [40.4168, -3.7038], [41.6488, -0.8891]]}
# Birmingham and Zaragoza are off the graph. The path joins them to London and to Madrid, their closest nodes
```

**Classes of your own.** The **class** of an edge is its category, such as `motorway`. `edge_classes` gives the class of each edge, in the form of `graph`. An edge that is not in `edge_classes` has no class. `classes` gives each class with its edge mode. The **edge mode** of a class is the kind of transport of its edges: `road`, `rail`, `sea` or `air`. A geograph holds 255 classes at most. A **metric** gives each edge a weight other than its length, under a name, such as its hours. A **weight per km** is the weight of 1 km of an edge in a metric. A metric gives a weight per km to an edge mode, and another one to a class:

```py
# Paris (0), Dijon (1) and Lyon (2): a motorway from Paris to Lyon, and a main road through Dijon
france = GeoGraph(
    nodes=[[48.8566, 2.3522], [47.3220, 5.0415], [45.7640, 4.8357]],
    graph=[{1: 263, 2: 465}, {0: 263, 2: 175}, {0: 465, 1: 175}],
    edge_classes=[{1: "main_road", 2: "motorway"}, {0: "main_road", 2: "main_road"}, {0: "motorway", 1: "main_road"}],
    classes=[{"name": "motorway", "edge_mode": "road"}, {"name": "main_road", "edge_mode": "road"}],
)
# Hours: 70 km/h by road, and 110 km/h on a motorway
france.create_metric("hours", weight_per_km={"road": 1 / 70, "off_graph": 1 / 30}, class_weight_per_km={"motorway": 1 / 110})

paris, lyon = {"latitude": 48.8566, "longitude": 2.3522}, {"latitude": 45.7640, "longitude": 4.8357}
france.get_shortest_path(origin_node=paris, destination_node=lyon)["length"]  # 438: the main road, through Dijon
france.get_shortest_path(origin_node=paris, destination_node=lyon, metric="hours")["length"]  # 465: the motorway
```

The guide [Networks](https://github.com/connor-makowski/scgraph/blob/main/guides/networks.md#saving-and-loading-files) explains how to save a geograph to a file.

## Modifying a GeoGraph

Add or remove nodes and edges of a geograph that is loaded:

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

**An edit of the network removes its metrics: create them again after it.** An edit is a node or an edge that you add or remove, or a merge. A warning then names the removed metrics, once. A metric that a loader read is removed too. An edit made on `graph_object` directly, as above, removes the metrics at the next call that reads them.

**The classes stay.** `add_edge`, `add_coord_edge`, `add_coord_node` and `add_haversine_edge` of a geograph take the keyword `edge_class`. It is the class of the new edge: a name of `geograph.classes`. A metric that you create after the edit gives the new edge the weight per km of its class.

```py
world_sea = GeoGraph.load_geograph("world_sea")
world_sea.create_metric("days", weight_per_km={"sea": 1 / 600, "off_graph": 1 / 100})

# This edit removes the metric `days`, with a warning. The new edges have the class `sea_connector`
world_sea.add_coord_node(coord_dict={"latitude": 43.0, "longitude": 6.0}, edge_class="sea_connector")

# The new edges get the weight per km of `sea`: the edge mode of their class
world_sea.create_metric("days", weight_per_km={"sea": 1 / 600, "off_graph": 1 / 100})
```

Without `edge_class`, the new edge has no class: its `edge_class` and its `edge_mode` are `None`. An edge added on `graph_object` directly keeps the class of the edge that it replaces. Between two nodes that had no edge, it has no class. An **off-graph leg** is the straight line from the origin or the destination of a query to its node. In a metric made from weights per km, an edge without a class has the weight per km of `off_graph`. So a route by the metric can start at a node that you added. A function of an edge receives such an edge with `None` as its `edge_class` and as its `edge_mode`. It must return a weight for it. To close such an edge, name it in `edge_weights` with `None`. The guide of the metrics gives this call in [Closing an Edge Mode, a Class or an Edge](https://github.com/connor-makowski/scgraph/blob/main/guides/time_cost_co2.md#closing-an-edge-mode-a-class-or-an-edge).

The [modification notebook](https://colab.research.google.com/github/connor-makowski/scgraph/blob/main/examples/geograph_modifications.ipynb) has more examples.

## Merging Two GeoGraphs

Use `merge_with_other_geograph` to join two networks, for example roads and railways, at the points where a route may change network:

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

Without the wall, the direct path would have a length of 16. Around the wall, the shortest path has a length of 20.9704.

`conn_data` replaces the 8 default moves of a cell by moves of your own:

```py
# conn_data: a list of (x_offset, y_offset, distance) tuples. Here 4 neighbors: right, left, up, down
conn_data = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0)]
gridGraph = GridGraph(x_size=10, y_size=10, blocks=[], conn_data=conn_data)
```
