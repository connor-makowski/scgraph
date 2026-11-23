# Routes by Time, Cost and CO2

This guide shows how to find the fastest route, the cheapest route or the route with the least CO2. You give each edge your own weight, read the legs of a route, and close a canal.

```py
from scgraph import GeoGraph

europe = GeoGraph.load_geograph("europe")

# Hours: a speed by road, by rail, by sea and by air, and a wait at each port, airport and rail terminal
europe.create_metric(
    "hours",
    weight_per_km={"road": 1 / 70, "rail": 1 / 50, "sea": 1 / 30, "air": 1 / 750, "off_graph": 1 / 30},
    class_weight_per_km={"motorway": 1 / 90},
    weight_at_hub={"port": {"sea": 12}, "airport": {"air": 3}, "rail_terminal": {"rail": 4}},
    unit="h",
)

paris = {"latitude": 48.8566, "longitude": 2.3522}
berlin = {"latitude": 52.52, "longitude": 13.405}
route = europe.get_shortest_path(origin_node=paris, destination_node=berlin, metric="hours")
route["length"]         # the km of the fastest route
route["metric_totals"]  # {'length': ..., 'hours': ...}: its km and its hours
```

A **metric** gives each edge a weight under a name, such as its hours. The **total** of a metric along a route is the sum of the weights of its edges. A query with `metric="hours"` returns the route with the smallest total of hours.

- A **geograph** is a `GeoGraph` object, such as `europe`.
- A **weight per km** is the weight of 1 km of an edge. One number as `weight_per_km` gives this weight to every edge and to the off-graph legs. The numbers above are examples: scgraph gives no speed, no cost and no emission factor.
- The **edge mode** of an edge is its kind of transport: `road`, `rail`, `sea` or `air`.
- The **class** of an edge is its category in the source, such as `motorway`, `suez` or `flight`. Each class has one edge mode.
- The **node mode** of a node is the kind of place where the node is. A **hub** is a node of the node mode `port`, `airport` or `rail_terminal`.
- A **query point** is the origin or the destination of a query. An **off-graph leg** is the straight line from a query point to its node. The total of a route includes its two off-graph legs.

The call above gives the weights in three arguments:

| Argument | Its keys | Its values | In `hours` above |
|---|---|---|---|
| `weight_per_km` | The edge modes and `off_graph` | The weight of 1 km | `1 / 70`: 70 km/h on a road |
| `class_weight_per_km` | Classes | The weight of 1 km, in place of the weight of the edge mode | `1 / 90`: 90 km/h on a motorway |
| `weight_at_hub` | The node mode of a hub, then an edge mode | A weight, added to each edge of this edge mode that enters or leaves the hub | 3 hours at each end of a flight |

**The result.** `length` is the length of the route, in `output_units`. `metric_totals` holds the total of each metric, each in its own unit.

**The default metric.** A query that names no metric uses the **default metric** of the geograph: `geograph.default_metric`. It is `length`, unless a loader or you set it: `europe.default_metric = "hours"`. [Loading from OSMnx](https://github.com/connor-makowski/scgraph/blob/main/guides/networks.md#loading-from-osmnx) shows a loader that sets it. `get_shortest_path`, `distance_matrix`, `get_path_weight` and `get_graph_object` apply this rule.

An edit of the network removes the metrics. If it removes the default metric, each of these calls raises a `ValueError` until you create this metric again.

## The Legs of a Route

A **leg** is a part of a route on one edge mode. The mode of the leg is this edge mode. A **transfer** is a node where a route goes from a leg of one edge mode to a leg of another. `output_legs=True` returns the legs of a route, and its transfers:

```py
route = europe.get_shortest_path(origin_node=paris, destination_node=berlin, metric="hours", output_legs=True)
for leg in route["legs"]:
    print(leg["mode"], round(leg["length"]), "km", round(leg["metric_totals"]["hours"], 1), "h")
# One line for each leg: mode, km, hours
route["transfers"]  # [{'node_id': ..., 'node_mode': 'airport'}, ...]: each transfer with its node mode
```

The first leg and the last leg are the two off-graph legs: their `mode` is `off_graph`. An off-graph leg ends at a node of the network: this node is not a transfer. Here each query point is less than 0.5 km from its node, so the loop prints 0 km for each off-graph leg.

The hours of a leg by air include the wait at its two airports: 3 hours at each, from `weight_at_hub`. A leg also holds `class_lengths` and `coordinate_path`. `class_lengths` gives the km of the leg on each class.

## Three Ways to Compute the Weights

`create_metric` computes the weights in one of three ways:

| Way | Argument | Use it when |
|---|---|---|
| Weights per km | `weight_per_km`, with `class_weight_per_km` and `weight_at_hub` | Each edge mode or each class has a weight per km, as in `hours` above |
| A weighted sum | `weighted_sum_of` | A metric combines other metrics, for example a cost of the hours and of the km |
| A function of an edge | `edge_weight_fn`, with `off_graph_weight_per_km` | The weight of an edge is not its km times a weight per km |

With each of the three ways, `edge_weights` gives the weights of chosen edges. Use it when a few edges differ from the others. These weights replace the computed ones.

```py
# A weighted sum: 30 euros for each hour and 0.5 euro for each km
europe.create_metric("euros", weighted_sum_of={"hours": 30, "length": 0.5}, unit="EUR")

# A function of an edge: a short flight emits more CO2 for each km than a long flight
def get_co2(edge):
    if edge["edge_mode"] == "air":
        return edge["length"] * (0.8 if edge["length"] < 1000 else 0.6)
    # None is the edge mode of an edge without a class, such as an edge that you add
    kg_per_km = {"road": 0.1, "rail": 0.02, "sea": 0.01, None: 0.1}
    return edge["length"] * kg_per_km[edge["edge_mode"]]

# The function gets the edges only: off_graph_weight_per_km is the kg of 1 km of an off-graph leg
europe.create_metric("co2", edge_weight_fn=get_co2, off_graph_weight_per_km=0.1, unit="kg")

# The weights of chosen edges: each vehicle ferry takes twice its hours.
# A sum of one metric with the coefficient 1 copies it
ferries = europe.get_edges(edge_class="ferry")
europe.create_metric(
    "hours_with_slow_ferries",
    weighted_sum_of={"hours": 1},
    edge_weights={
        (edge["origin_id"], edge["destination_id"]): 2 * edge["metric_weights"]["hours"]
        for edge in ferries
    },
)
```

**A weighted sum.** A weighted sum is computed once, at its creation. When you create `hours` again, create `euros` again too.

A weighted sum can also add two metrics of different units: `weighted_sum_of={"co2": 1, "hours": 10}` counts one hour as 10 kg of CO2. A **closed** edge is an edge that no route by the metric takes ([below](#closing-an-edge-mode-a-class-or-an-edge)). An edge closed in one metric of the sum is closed in the sum. The notebook [Trade-offs between time, cost and CO2](https://colab.research.google.com/github/connor-makowski/scgraph/blob/main/examples/time_cost_co2_trade_offs.ipynb) tries several coefficients and draws the routes.

**The function.** The function receives one edge as a dict, with the keys `origin_id`, `destination_id`, `length`, `edge_class`, `edge_mode` and `metric_weights`. `metric_weights` holds the weight of the edge in each metric that exists at the call. The function is called once for each edge, so a function is slower than weights per km.

**The rules of a call.**

- **The way.** A call gives exactly one of `weight_per_km`, `weighted_sum_of` and `edge_weight_fn`. `class_weight_per_km` and `weight_at_hub` need `weight_per_km`.
- **The off-graph legs.** A call that gives `edge_weight_fn` also gives `off_graph_weight_per_km`. A call without `edge_weight_fn` does not give it. A dict of `weight_per_km` gives a weight per km for `off_graph`.
- **The classes.** Each class that has an edge needs a weight per km: its own, or that of its edge mode. A geograph without classes takes one number as `weight_per_km`.
- **The values.** A weight is a number of zero or more. A wrong argument raises a `ValueError` that names it.
- **The name.** A metric of the same name is replaced, and `remove_metric(name)` removes a metric.

The docstring of [`create_metric`](https://connor-makowski.github.io/scgraph/scgraph.html#GeoGraph.create_metric) gives every argument.

## Closing an Edge Mode, a Class or an Edge

`None` in place of a weight per km closes an edge mode or a class. No route by this metric then takes one of its edges. `weight_per_km={"air": None, ...}` closes every flight, and `class_weight_per_km={"ferry": None}` closes every vehicle ferry. The Suez Canal is the class `suez` of the sea lanes:

```py
world_sea = GeoGraph.load_geograph("world_sea")
world_sea.create_metric("km_without_suez", weight_per_km={"sea": 1, "off_graph": 1}, class_weight_per_km={"suez": None})

rotterdam = {"latitude": 51.95, "longitude": 4.14}
singapore = {"latitude": 1.26, "longitude": 103.82}
by_the_canal = world_sea.get_shortest_path(origin_node=rotterdam, destination_node=singapore)
around_africa = world_sea.get_shortest_path(
    origin_node=rotterdam, destination_node=singapore, metric="km_without_suez"
)
around_africa["length"] > by_the_canal["length"]  # True
```

The network is not edited. A query by `length`, or by another metric, still takes the canal. When every route between two query points needs a closed edge, the query raises `PathNotFoundError`.

To close one edge, name it in `edge_weights`: `edge_weights={(origin_id, destination_id): None}`. An edge has one direction. Name `(destination_id, origin_id)` too to close both.

## Listing Nodes and Edges

A geograph lists its node modes, classes, metrics, nodes and edges:

```py
europe.node_modes  # [{'name': 'road', ...}, ...]: the node modes
europe.classes  # [{'name': 'motorway', 'edge_mode': 'road'}, ...]: each class with its edge mode
europe.metrics  # [{'name': 'length', 'unit': 'km'}, {'name': 'hours', 'unit': 'h', ...}, ...]

# The airports around Paris: bbox is (south, west, north, east) in degrees
europe.get_nodes(node_mode="airport", bbox=(48, 1, 50, 4))
# [{'node_id': ..., 'latitude': ..., 'longitude': ..., 'node_mode': 'airport'}, ...]

# The edges of one class, or the edges that leave one node: get_edges(origin_id=...)
europe.get_edges(edge_class="ferry")
# [{'origin_id': ..., 'destination_id': ..., 'length': ..., 'edge_class': 'ferry', 'edge_mode': 'road', 'metric_weights': {...}}, ...]

# The edges of a route, in its order: get_path_edges takes the node ids of the route
route = europe.get_shortest_path(origin_node=paris, destination_node=berlin, metric="hours", output_path=True)
europe.get_path_edges(route["path"])
```

**Files and edits.** `save_as_scgraph` writes the weights of each metric to the network file, but not the default metric. `load_from_scgraph` reads them. `guides/custom_graphs.md` explains the edits in [Modifying a GeoGraph](https://github.com/connor-makowski/scgraph/blob/main/guides/custom_graphs.md#modifying-a-geograph).

## Metrics and Algorithms

Each metric has its own graph: the edges of the network, with the weights of the metric. A query by a metric searches this graph, so every `algorithm_fn` works with every metric.

`get_graph_object(metric)` returns this graph, for example to build a hierarchy of the metric. The routing guide gives the call in [Hierarchies: CH and TNR](https://github.com/connor-makowski/scgraph/blob/main/guides/routing.md#hierarchies-ch-and-tnr). [ARCHITECTURE.md](https://github.com/connor-makowski/scgraph/blob/main/ARCHITECTURE.md#classes-and-metrics) explains the graph of a metric.
