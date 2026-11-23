# Routes by Time, Cost and CO2

This guide is for a user who routes by time, by cost or by CO2. After it, you can give each edge your own weight, find the best route by these weights, read its parts, and close a canal.

A network gives each edge a length. A **metric** gives each edge another weight, under a name: its hours, its cost, its kg of CO2. You create a metric on a geograph, then you name it in a query. The **total** of a metric along a route is the sum of the weights of its edges. A query by a metric returns the route with the smallest total. In the example below, `class_weight_per_km` gives the motorways their own speed, and `weight_at_hub` adds a wait at each port, airport and rail terminal.

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
route["metric_totals"]  # {'hours': ...}: its hours
```

- **Weight per km.** A **weight per km** is the weight of 1 km of an edge. Here it is in hours per km: `1 / 70` means 70 km/h. These numbers are examples. The library provides no speed, no cost and no emission factor: you give your own.
- **Edge mode.** The **edge mode** of an edge is the kind of transport of the edge: `road`, `rail`, `sea` or `air`.
- **Leg.** A **leg** is a part of a route on one edge mode. The mode of a leg is this edge mode.
- **Off the graph.** A **query point** is the origin or the destination of a query. An **off-graph leg** is the straight line from a query point to its node. Its mode is `off_graph`. The total of a route counts its two off-graph legs. The routing guide explains [where a query point snaps](https://github.com/connor-makowski/scgraph/blob/main/guides/routing.md#where-a-query-point-snaps).
- **Class.** Each edge of `europe` has a **class**: its category in the source, such as `motorway`, `rail_main`, `suez` or `flight`. So does each edge of the other networks that scgraph publishes. Each class has one edge mode.
- **Hub.** A **hub** is a port, an airport or a rail terminal. The **node mode** of a node is the kind of place where the node is: `road`, `rail`, `sea`, `port`, `airport` or `rail_terminal`. The node mode of a hub is one of the last three.

Each of the three dicts of the call has one kind of key:

- **`weight_per_km`.** Its keys are the modes that a leg can have: the edge modes and `off_graph`. They are the values of `leg["mode"]` in a result. One number in place of the dict is the weight per km of every edge and of the off-graph legs.
- **`class_weight_per_km`.** Its keys are classes. The weight per km of a class replaces the weight per km of its edge mode. Here a motorway is travelled at 90 km/h, and every other road at 70 km/h.
- **`weight_at_hub`.** It adds a weight at a hub. Its first key is the node mode of the hub, and its second key is an edge mode. The weight is added only to the edges of this edge mode: here nothing is added to a road edge at a port. It is added to an edge that enters the hub, and to an edge that leaves the hub. Here 3 hours are added to a flight at the airport that it leaves, and 3 hours at the airport that it reaches.

**The result.** `length` is always the length of the route. `metric_totals` holds the total of each metric other than `length` along the route.

**The default metric.** A query that names no metric uses the **default metric** of the geograph: `geograph.default_metric`. It is `length`, unless a loader or you set it: `europe.default_metric = "hours"`. `get_shortest_path`, `distance_matrix`, `get_path_weight` and `get_graph_object` apply this rule. An edit of the network removes the metrics. If it removes the default metric, each of these calls raises a `ValueError` until you create this metric again. The guide of the networks shows a loader that sets it, in [Loading from OSMnx](https://github.com/connor-makowski/scgraph/blob/main/guides/networks.md#loading-from-osmnx).

## The Legs of a Route

A **transfer** is a node where a route goes from a leg of one edge mode to a leg of another. `output_legs=True` returns the legs of a route, and its transfers:

```py
route = europe.get_shortest_path(origin_node=paris, destination_node=berlin, metric="hours", output_legs=True)
for leg in route["legs"]:
    print(leg["mode"], round(leg["length"]), "km", round(leg["metric_totals"]["hours"], 1), "h")
# One line for each leg: its mode, its km and its hours
route["transfers"]  # [{'node_id': ..., 'node_mode': 'airport'}, ...]: each transfer with its node mode
```

The first leg and the last leg are the two off-graph legs: their `mode` is `off_graph`. An off-graph leg ends at a node of the network: this node is not a transfer. Here each query point is at less than 0.5 km from its node, so each off-graph leg prints 0 km. A leg by air holds the hours of its two airports. A leg also holds `class_lengths` and `coordinate_path`. `class_lengths` gives the km of the leg on each class.

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

**A weighted sum.** A weighted sum is computed once, at its creation. When you create `hours` again, create `euros` again too. A weighted sum can also add two metrics of different units: `weighted_sum_of={"co2": 1, "hours": 10}` counts one hour as 10 kg of CO2. An edge that is closed in one metric of the sum is closed in the sum. The notebook [Trade-offs between time, cost and CO2](https://colab.research.google.com/github/connor-makowski/scgraph/blob/main/examples/time_cost_co2_trade_offs.ipynb) tries several coefficients, and draws the routes on charts and on a map.

**The function.** The function receives one edge as a dict, with the keys `origin_id`, `destination_id`, `length`, `edge_class`, `edge_mode` and `metric_weights`. `metric_weights` holds the weight of the edge in each metric that exists at the call. The function is called once for each edge, so a function is slower than weights per km. It is called for the edges only. `off_graph_weight_per_km` gives the weight of 1 km of an off-graph leg.

**The rules of a call.** A call gives exactly one of `weight_per_km`, `weighted_sum_of` and `edge_weight_fn`. `class_weight_per_km` and `weight_at_hub` need `weight_per_km`. A call that gives `edge_weight_fn` also gives `off_graph_weight_per_km`, and no other call gives it. A dict of `weight_per_km` gives a weight per km for `off_graph`. Each class that has an edge needs a weight per km: its own, or that of its edge mode. A geograph without classes takes one number as `weight_per_km`. A weight is a number of zero or more. A wrong argument raises a `ValueError` that names it. A metric that has the same name is replaced, and `remove_metric(name)` removes a metric. The docstring of [`create_metric`](https://connor-makowski.github.io/scgraph/scgraph.html#GeoGraph.create_metric) gives every argument.

## Closing an Edge Mode, a Class or an Edge

`None` in place of a weight per km closes an edge mode or a class. No route by this metric then takes one of its edges. `weight_per_km={"air": None, ...}` closes every flight. The Suez Canal is the class `suez` of the sea lanes:

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

## Reading the Network

A geograph gives its node modes, its classes, its metrics, its nodes and its edges:

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

**Files and edits.** `save_as_scgraph` writes the weights of each metric and the default metric to the network file, and `load_from_scgraph` reads them. An edit of the network removes its metrics: create them again after it. The guide of your own graphs gives more detail in [Modifying a GeoGraph](https://github.com/connor-makowski/scgraph/blob/main/guides/custom_graphs.md#modifying-a-geograph).

## Metrics and Algorithms

Each metric has its own graph: the edges of the network, with the weights of the metric. A query by a metric searches this graph, so every `algorithm_fn` works with every metric. `get_graph_object(metric)` returns this graph, for example to build a hierarchy of the metric. The routing guide gives the call in [Hierarchies: CH and TNR](https://github.com/connor-makowski/scgraph/blob/main/guides/routing.md#hierarchies-ch-and-tnr). [ARCHITECTURE.md](https://github.com/connor-makowski/scgraph/blob/main/ARCHITECTURE.md#classes-and-metrics) explains the graph of a metric.
